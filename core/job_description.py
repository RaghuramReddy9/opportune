"""
core/job_description.py — Lightweight job description enrichment.

Fetches direct apply pages for the final selected jobs only. This is deliberately
best-effort: failures never block the daily scrape.
"""
from __future__ import annotations

import logging
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from html import unescape
from typing import Iterable

from bs4 import BeautifulSoup

from core.http import SESSION, DEFAULT_TIMEOUT, is_safe_public_url

logger = logging.getLogger("core.job_description")

_MAX_DESCRIPTION_CHARS = 8000
_ENRICH_WORKERS = 8
_ENRICH_TIMEOUT = 10


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def extract_visible_text(html: str) -> str:
    """Extract compact visible text from an HTML page."""
    soup = BeautifulSoup(html or "", "html.parser")
    for tag in soup(["script", "style", "noscript", "svg", "nav", "footer", "header"]):
        tag.decompose()
    text = soup.get_text(" ")
    text = unescape(text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:_MAX_DESCRIPTION_CHARS]


def fetch_job_description(url: str) -> str:
    """Fetch a best-effort text description from a direct apply URL."""
    if not is_safe_public_url(url):
        return ""
    try:
        resp = SESSION.get(url, timeout=min(DEFAULT_TIMEOUT, _ENRICH_TIMEOUT))
        if resp.status_code >= 400:
            logger.info("Description fetch skipped %s: HTTP %s", url[:80], resp.status_code)
            return ""
        ctype = resp.headers.get("content-type", "")
        if "html" not in ctype and "text" not in ctype:
            return ""
        return extract_visible_text(resp.text)
    except Exception as e:
        logger.info("Description fetch failed %s: %s", url[:80], e)
        return ""


def _enrich_single(job: dict) -> dict:
    """Enrich one job dict with description metadata. Returns updated counts."""
    updated = 0
    existing = (job.get("description") or job.get("full_text") or "").strip()
    url = job.get("apply_url") or job.get("raw_url") or ""
    if (
        job.get("description_enriched")
        and len(existing) >= 500
        and job.get("posted_date")
        and job.get("location")
    ):
        return {"updated": 0}
    text = fetch_job_description(url)
    if len(text) > len(existing):
        job["description"] = text
        job["full_text"] = f"{job.get('title', '')} {job.get('company', '')} {text}"
        job["description_enriched"] = True
        updated += 1
    if not job.get("posted_date"):
        pd = _extract_posted_date(text)
        if pd:
            job["posted_date"] = pd
            job["freshness_source"] = "employer_page"
            updated += 1
    if not job.get("location"):
        loc = _extract_location(text)
        if loc and loc.strip().lower() not in _EXCLUDE_LOCATION_TOKENS:
            job["location"] = loc
            updated += 1
    return {"updated": updated}


def enrich_selected_jobs(jobs: Iterable[dict], max_jobs: int = 15) -> int:
    """Fetch missing/short descriptions for selected jobs.

    Returns the number of jobs enriched with additional text.
    """
    enriched = 0
    for job in list(jobs)[:max_jobs]:
        existing = (job.get("description") or job.get("full_text") or "").strip()
        if len(existing) >= 500:
            continue
        url = job.get("apply_url") or job.get("raw_url") or ""
        text = fetch_job_description(url)
        if len(text) > len(existing):
            job["description"] = text
            job["full_text"] = f"{job.get('title', '')} {job.get('company', '')} {text}"
            job["description_enriched"] = True
            enriched += 1
    return enriched


_DATE_PATTERNS = [
    r"posted\s*[:]\s*([A-Z][a-z]{2,8}\.?\s*\d{1,2},?\s*\d{4})",
    r"date\s*posted\s*[:]?\s*([A-Z][a-z]{2,8}\.?\s*\d{1,2},?\s*\d{4})",
    r"posted\s*on\s*([A-Z][a-z]{2,8}\.?\s*\d{1,2},?\s*\d{4})",
    r"(\d{4}-\d{2}-\d{2})",
    r"(\d{1,2}/\d{1,2}/\d{4})",
]


def _extract_posted_date(text: str) -> str:
    """Return an ISO-ish date string if a posting date is visible in the text."""
    from datetime import datetime

    for pat in _DATE_PATTERNS:
        m = re.search(pat, text, flags=re.IGNORECASE)
        if not m:
            continue
        raw = m.group(1).strip()
        try:
            dt = datetime.strptime(raw, "%B %d, %Y")
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            pass
        try:
            dt = datetime.strptime(raw, "%b %d, %Y")
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            pass
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", raw):
            return raw
        ms = re.fullmatch(r"(\d{1,2})/(\d{1,2})/(\d{4})", raw)
        if ms:
            return f"{ms.group(3)}-{int(ms.group(1)):02d}-{int(ms.group(2)):02d}"
    return ""


_LOCATION_PATTERNS = [
    r"location\s*[:]\s*([A-Z][^,\n]{2,40}(?:,\s*[A-Z]{2})?)",
    r"job\s*location\s*[:]\s*([A-Z][^,\n]{2,40}(?:,\s*[A-Z]{2})?)",
    r"based\s*in\s*([A-Z][^,\n]{2,40}(?:,\s*[A-Z]{2})?)",
    r"based\s*[:]?\s*([A-Z][^,\n]{2,40}(?:,\s*[A-Z]{2})?)",
]


_EXCLUDE_LOCATION_TOKENS = {
    "united states", "remote", "us", "usa", "worldwide", "multiple",
    "various", "anywhere",
}


def _extract_location(text: str) -> str:
    for pat in _LOCATION_PATTERNS:
        m = re.search(pat, text, flags=re.IGNORECASE)
        if not m:
            continue
        loc = m.group(1).strip().rstrip(".,")
        if len(loc) < 3:
            continue
        return loc
    return ""


def enrich_jobs_with_details(jobs: Iterable[dict], max_jobs: int = 60) -> int:
    """Enrich every non-duplicate candidate before geo/eligibility gates.

    For each job with a thin description, fetch the direct apply page and
    extract:
      - description / full_text (for skill + eligibility matching)
      - posted_date (so the UI can separate "found today" from
        "posted today")
      - location (so the strict U.S. geo gate has real data)

    Returns the number of jobs updated with new detail.
    """
    candidates = [job for job in list(jobs)[:max_jobs] if job.get("apply_url") or job.get("raw_url")]
    if not candidates:
        return 0

    total = 0
    with ThreadPoolExecutor(max_workers=_ENRICH_WORKERS) as pool:
        futures = {pool.submit(_enrich_single, job): job for job in candidates}
        for future in as_completed(futures):
            try:
                result = future.result(timeout=_ENRICH_TIMEOUT + 5)
                total += result.get("updated", 0)
            except Exception as e:
                logger.info("Enrichment task failed: %s", e)
    return total


def backfill_enrichment(limit: int = 50) -> dict:
    """Process pending jobs from the enrichment queue.

    Returns a summary dict with counts: processed, enriched, failed, skipped.
    """
    from dashboard.db import (
        connect, get_enrichment_backlog, mark_enriched, bump_enrichment_failure,
    )
    summary = {"processed": 0, "enriched": 0, "failed": 0, "skipped": 0}
    with connect() as conn:
        backlog = get_enrichment_backlog(conn, limit=limit)
        for item in backlog:
            uid = item["job_uid"]
            if item["attempts"] >= 5:
                summary["skipped"] += 1
                continue
            text = ""
            if item.get("apply_url"):
                text = fetch_job_description(item["apply_url"])
            if not text and item.get("title"):
                text = item["title"]
            if not text:
                bump_enrichment_failure(conn, uid, "no url or text")
                summary["failed"] += 1
                summary["processed"] += 1
                continue
            try:
                from core.skill_matcher import skill_match, load_user_profile
                profile = load_user_profile()
                match_score, missing = skill_match(text, profile)
                conn.execute(
                    """UPDATE jobs
                       SET description = COALESCE(NULLIF(description, ''), ?),
                           full_text = COALESCE(NULLIF(full_text, ''), ?),
                           date_updated = ?
                       WHERE job_uid = ?""",
                    (text[:8000], f"{item.get('company', '')} {item.get('title', '')} {text}", _now_iso(), uid),
                )
                mark_enriched(conn, uid)
                summary["enriched"] += 1
            except Exception as e:
                bump_enrichment_failure(conn, uid, str(e)[:500])
                summary["failed"] += 1
            summary["processed"] += 1
    return summary
