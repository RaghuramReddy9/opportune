"""Deterministic Apply Window scoring.

This turns many noisy ranking signals into one user-facing decision:
act today, review first, or skip. It intentionally avoids LLM calls so dashboard
latency stays predictable.
"""
from __future__ import annotations

from typing import Any

TRUSTED_SOURCES = {
    "greenhouse",
    "lever",
    "ashby",
    "workday",
    "smartrecruiters",
    "ycombinator",
    "github_lists",
}
FRAGILE_SOURCES = {"linkedin_public", "linkedin", "indeed", "wellfound"}

# Aggregator/board wrappers that repost other companies' jobs. Lower trust:
# they are not the employer's own ATS and often go stale or block bots.
AGGREGATOR_HOSTS = {
    "lensa.com",
    "builtin.com",
    "builtinsf.com",
    "wellfound.com",
    "jsimg.net",
    "jobspath.com",
}


def _host_of(source: str, url: str | None) -> str:
    from urllib.parse import urlparse

    if url:
        host = urlparse(url).netloc.lower().replace("www.", "")
        if host:
            return host
    return source.replace("api_", "")


def _norm(value: Any) -> str:
    return str(value or "").strip().lower()


def _clamp(score: int) -> int:
    return max(0, min(100, score))


def _freshness_points(freshness: str, freshness_trust: str = "") -> tuple[int, str]:
    f = _norm(freshness)
    if _norm(freshness_trust) != "confirmed_posted_date":
        if any(token in f for token in ("stale", "15", "30")):
            return -12, "Unverified stale signal"
        return 4, "Freshness unverified"
    if any(token in f for token in ("0-24", "0-1", "today", "new")):
        return 24, "Fresh posting"
    if any(token in f for token in ("0-3", "1-3", "3d", "this week", "3-7")):
        return 16, "Recent posting"
    if any(token in f for token in ("7-14", "14")):
        return 6, "Older posting"
    if any(token in f for token in ("stale", "15", "30")):
        return -12, "Stale posting"
    return 4, "Freshness unverified"


def score_apply_window(job: dict[str, Any]) -> dict[str, Any]:
    """Return Apply Window fields for a normalized job dict."""
    score = 0
    reasons: list[str] = []

    match = int(job.get("resume_match_score", 0) or 0)
    if match >= 90:
        score += 36
        reasons.append("Strong skill match")
    elif match >= 75:
        score += 28
        reasons.append("Good skill match")
    elif match >= 60:
        score += 16
        reasons.append("Partial skill match")
    else:
        score += 6
        reasons.append("Weak skill match")

    points, reason = _freshness_points(
        str(job.get("freshness", "")),
        str(job.get("freshness_trust", "")),
    )
    score += points
    reasons.append(reason)

    source = _norm(job.get("source"))
    ats = _norm(job.get("ats_type"))
    source_key = source.replace("api_", "")
    host = _host_of(source, job.get("apply_url") or job.get("raw_url"))
    if source_key in TRUSTED_SOURCES or ats in TRUSTED_SOURCES:
        score += 18
        reasons.append("Trusted source")
    elif host in AGGREGATOR_HOSTS:
        score -= 6
        reasons.append("Aggregator listing — verify on employer site")
    elif source_key in FRAGILE_SOURCES:
        score += 5
        reasons.append("Source needs verification")
    elif source_key:
        score += 10
        reasons.append("Source available")
    else:
        reasons.append("Unknown source")

    if job.get("apply_url") or job.get("raw_url"):
        score += 10
        reasons.append("Apply link available")
    else:
        score -= 18
        reasons.append("Missing apply link")

    action_tag = _norm(job.get("action_tag"))
    if action_tag == "apply_now":
        score += 12
        reasons.append("Passed ready-to-apply gate")
    elif action_tag == "skip":
        score -= 28
        reasons.append("Pipeline marked skip")
    elif action_tag == "known_match":
        score -= 4
        reasons.append("Already seen before")

    risky = _norm(job.get("why_risky"))
    if risky:
        score -= 10
        reasons.append("Has review risk")

    families = job.get("target_role_families") or []
    if isinstance(families, str):
        families = [families]
    if families:
        score += 8
        reasons.append("Matches target role family")

    location_verdict = job.get("location_verdict") or {}
    if isinstance(location_verdict, dict) and _norm(location_verdict.get("status")) in {"us_verified", "remote_us_verified", "verified"}:
        score += 4
        reasons.append("Location verified")

    score = _clamp(score)
    if score >= 80:
        label = "high"
        next_action = "Apply today"
    elif score >= 55:
        label = "medium"
        next_action = "Review before applying"
    else:
        label = "low"
        next_action = "Skip unless manually interested"

    return {
        "apply_window_score": score,
        "apply_window_label": label,
        "apply_window_reasons": reasons[:6],
        "apply_window_next_action": next_action,
    }


def annotate_apply_window(job: dict[str, Any]) -> dict[str, Any]:
    """Return a shallow copy with Apply Window fields attached."""
    annotated = dict(job)
    annotated.update(score_apply_window(annotated))
    return annotated
