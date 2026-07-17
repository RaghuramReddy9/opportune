"""Broad role-and-location discovery pool built before resume ranking.

The pool intentionally answers only two acquisition questions:
1. Does the title resemble one of the configured role preferences?
2. Is the listing location verified against the configured locations?

Freshness, experience, work mode, visa evidence, and resume score are stored as
metadata for later filtering. They never decide whether a qualifying listing is
kept in the local pool.
"""
from __future__ import annotations

import json
import re
from collections.abc import Iterable

from config import get_profile_config
from ranking.guardrails import apply_freshness_trust, location_verdict
from ranking.score import rank_job


_ROLE_CONCEPTS: tuple[tuple[tuple[str, ...], tuple[str, ...]], ...] = (
    (
        ("forward deployed", "fde"),
        (r"\bforward[-\s]+deployed(?:\s+(?:ai|ml))?\s+(?:engineer|scientist)\b", r"\bfde\b"),
    ),
    (
        ("llm", "language model", "generative ai", "genai"),
        (
            r"\bllm\b",
            r"\blarge\s+language\s+model",
            r"\blanguage\s+model\s+(?:engineer|developer)",
            r"\bgenerative\s+ai\b",
            r"\bgen\s*ai\b",
            r"\bgenai\b",
        ),
    ),
    (
        ("agent", "agentic"),
        (r"\bagentic\b", r"\bai\s+agents?\b", r"\bagents?\s+(?:engineer|developer)\b"),
    ),
    (
        ("data ai", "ai data", "data + ai", "data+ai"),
        (
            r"\bdata\s+(?:and|\+|&)?\s*ai\s+engineer\b",
            r"\bai\s+data\s+engineer\b",
            r"\bdata\s+(?:platform\s+)?engineer\b",
            r"\banalytics\s+engineer\b",
        ),
    ),
    (
        ("backend ai", "ai systems", "ai system"),
        (r"\bbackend\s+(?:software\s+)?engineer\b", r"\bai\s+systems?\s+engineer\b"),
    ),
    (
        ("ai solutions", "solutions engineer"),
        (r"\bsolutions?\s+engineer\b", r"\bai\s+solutions?\s+engineer\b"),
    ),
    (
        ("ai engineer", "applied ai", "artificial intelligence"),
        (
            r"\b(?:applied\s+)?ai\s+(?:software\s+)?engineer\b",
            r"\bartificial\s+intelligence\s+engineer\b",
            r"\bai[/\s-]*ml\s+engineer\b",
            r"\bmachine\s+learning\s+engineer\b",
            r"\bml\s+engineer\b",
        ),
    ),
)


def _normalize(value: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9+]+", " ", str(value or "").lower()).split())


def _role_patterns(roles: Iterable[str]) -> list[tuple[str, re.Pattern[str]]]:
    patterns: list[tuple[str, re.Pattern[str]]] = []
    seen: set[str] = set()
    for raw_role in roles:
        role = _normalize(raw_role)
        if not role:
            continue
        literal = r"\b" + r"[\s/+-]+".join(re.escape(part) for part in role.split()) + r"\b"
        if literal not in seen:
            patterns.append((str(raw_role), re.compile(literal, re.IGNORECASE)))
            seen.add(literal)
        for triggers, aliases in _ROLE_CONCEPTS:
            if not any(trigger in role for trigger in triggers):
                continue
            for alias in aliases:
                if alias not in seen:
                    patterns.append((str(raw_role), re.compile(alias, re.IGNORECASE)))
                    seen.add(alias)
    return patterns


def match_role_preference(job: dict, roles: Iterable[str] | None = None) -> str:
    """Return the matching configured role label, using title text only."""
    configured = list(roles if roles is not None else get_profile_config().get("target_roles", []))
    title = str(job.get("title") or job.get("role") or "").strip()
    if not title:
        return ""
    for role, pattern in _role_patterns(configured):
        if pattern.search(title):
            return role
    return ""


def classify_work_mode(job: dict) -> str:
    text = " ".join(
        str(job.get(key) or "")
        for key in ("location", "title", "description", "full_text")
    ).lower()
    if re.search(r"\bhybrid\b|\b[1-4]\s+days?\s+(?:a|per)\s+week\s+in(?:-|\s+)office\b", text):
        return "hybrid"
    if re.search(r"\bremote\b|work\s+from\s+home|distributed\s+team", text):
        return "remote"
    if re.search(r"\bon[-\s]?site\b|\bin[-\s]?office\b|office[-\s]?based", text):
        return "onsite"
    return "unknown"


def classify_experience_level(job: dict) -> str:
    title = str(job.get("title") or job.get("role") or "").lower()
    detail = f"{title} {job.get('description', '')} {job.get('full_text', '')}".lower()
    if re.search(r"\b(intern|internship|co[-\s]?op)\b", title):
        return "internship"
    if re.search(r"\b(chief|director|head|vice president|vp)\b", title):
        return "leadership"
    if re.search(r"\b(senior|sr\.?|staff|principal|lead|architect|manager)\b", title):
        return "senior"
    if re.search(r"\b(new\s+grad|graduate|entry[-\s]?level|early\s+career|junior|jr\.?|associate|engineer\s+i\b)", title):
        return "entry_level"
    years = [int(value) for value in re.findall(r"\b(\d{1,2})\+?\s+years?", detail)]
    minimum = min(years) if years else None
    if minimum is not None:
        if minimum <= 2:
            return "entry_level"
        if minimum <= 5:
            return "mid_level"
        return "senior"
    if re.search(r"\b(engineer\s+ii|mid[-\s]?level|intermediate)\b", title):
        return "mid_level"
    return "unknown"


def prepare_pool_job(job: dict, roles: Iterable[str] | None = None) -> dict | None:
    """Normalize one broad-pool row or return None when role/location miss."""
    role_match = match_role_preference(job, roles)
    if not role_match:
        return None
    verdict = location_verdict(job)
    if verdict.get("status") not in {"us_verified", "configured_verified"}:
        return None

    pooled = dict(job)
    try:
        rank_job(pooled)
    except Exception:
        pooled.setdefault("resume_match_score", 0)
        pooled.setdefault("matched_keywords", [])
        pooled.setdefault("target_role_families", [])
    apply_freshness_trust(pooled)
    pooled["action_tag"] = "pool"
    pooled["pool_match_reason"] = f"Title matches configured role: {role_match}"
    pooled["work_mode"] = classify_work_mode(pooled)
    pooled["experience_level"] = classify_experience_level(pooled)
    pooled["employment_type"] = str(pooled.get("employment_type") or "")
    pooled["description"] = str(pooled.get("description") or pooled.get("full_text") or "")
    pooled["location_verdict"] = verdict
    pooled["ready_to_apply"] = False
    if not pooled.get("why_matches"):
        pooled["why_matches"] = pooled["pool_match_reason"]
    return pooled


def build_discovery_pool(jobs: Iterable[dict], roles: Iterable[str] | None = None) -> list[dict]:
    """Return every unique minimal role+location match, without quality caps."""
    pool: list[dict] = []
    seen: set[tuple[str, str, str]] = set()
    for raw in jobs:
        job = prepare_pool_job(raw, roles)
        if job is None:
            continue
        key = (
            str(job.get("company") or "").strip().lower(),
            str(job.get("title") or job.get("role") or "").strip().lower(),
            str(job.get("apply_url") or job.get("raw_url") or "").split("?", 1)[0].rstrip("/").lower(),
        )
        if key in seen:
            continue
        seen.add(key)
        pool.append(job)
    pool.sort(
        key=lambda item: (
            str(item.get("posted_date") or ""),
            int(item.get("resume_match_score") or 0),
        ),
        reverse=True,
    )
    return pool


def materialize_catalog_pool(conn) -> dict[str, int]:
    """Rebuild broad-pool rows from active catalog payloads without scraping."""
    from dashboard.db import upsert_scraped_job
    from ranking.guardrails import detect_visa_sponsorship

    rows = conn.execute(
        "SELECT source, source_name, ats_job_id, payload_json, first_seen_at, "
        "last_seen_at, content_changed_at FROM job_catalog WHERE listing_state = 'active'"
    ).fetchall()
    source_jobs: list[dict] = []
    invalid_payloads = 0
    for row in rows:
        try:
            job = json.loads(row["payload_json"] or "{}")
        except (TypeError, ValueError, json.JSONDecodeError):
            invalid_payloads += 1
            continue
        job["source"] = job.get("source") or row["source"]
        job["ats_type"] = job.get("ats_type") or row["source"]
        job["source_name"] = row["source_name"]
        job["ats_job_id"] = row["ats_job_id"]
        job["first_seen_at"] = row["first_seen_at"]
        job["last_seen_at"] = row["last_seen_at"]
        job["content_changed_at"] = row["content_changed_at"]
        source_jobs.append(job)

    pool = build_discovery_pool(source_jobs)
    active = conn.execute(
        "SELECT profile_id FROM profiles WHERE is_active = 1 "
        "ORDER BY last_used_at DESC LIMIT 1"
    ).fetchone()
    profile_id = active["profile_id"] if active else ""
    for job in pool:
        job["profile_id"] = profile_id
        job.setdefault("visa_sponsorship", detect_visa_sponsorship(job))
    materialized_uids = {
        upsert_scraped_job(conn, job, check_links=False)
        for job in pool
    }
    return {
        "catalog_active": len(rows),
        "pool_matches": len(pool),
        "materialized": len(materialized_uids),
        "invalid_payloads": invalid_payloads,
    }
