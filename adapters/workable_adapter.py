"""Workable public careers-feed adapter (no API key required)."""
from __future__ import annotations

import logging

from core.freshness import parse_iso_date
from core.http import DEFAULT_TIMEOUT, SESSION
from core.job_description import extract_visible_text

logger = logging.getLogger("adapters.workable")


def _plain_text(value) -> str:
    if value is None:
        return ""
    if isinstance(value, dict):
        return " ".join(filter(None, (_plain_text(item) for item in value.values())))
    if isinstance(value, (list, tuple)):
        return " ".join(filter(None, (_plain_text(item) for item in value)))
    text = str(value).strip()
    if "<" in text and ">" in text:
        return extract_visible_text(text)
    return " ".join(text.split())


def _location(job: dict) -> str:
    primary = job.get("location")
    if isinstance(primary, str) and primary.strip():
        return primary.strip()
    if isinstance(primary, dict):
        label = str(primary.get("location_str") or "").strip()
        if label:
            return label
        parts = [
            primary.get("city"),
            primary.get("region") or primary.get("region_code"),
            primary.get("country") or primary.get("country_name"),
        ]
        label = ", ".join(str(part).strip() for part in parts if part)
        if label:
            return label
        if primary.get("telecommuting"):
            return "Remote"
    locations = job.get("locations") or []
    if locations and isinstance(locations[0], dict):
        first = locations[0]
        parts = [first.get("city"), first.get("state_code"), first.get("country_name")]
        return ", ".join(str(part).strip() for part in parts if part)
    return ""


def scrape(company_name: str, slug: str, ats_url: str = "") -> dict:
    """Fetch every published listing from a Workable account snapshot."""
    result = {"jobs": [], "raw_count": 0, "error": None}
    try:
        url = f"https://www.workable.com/api/accounts/{slug}"
        response = SESSION.get(
            url,
            params={"details": "true"},
            timeout=DEFAULT_TIMEOUT,
        )
        if response.status_code != 200:
            result["error"] = f"Workable HTTP {response.status_code}"
            return result
        data = response.json()
        postings = data.get("jobs", []) if isinstance(data, dict) else []
        for posting in postings:
            if not isinstance(posting, dict):
                continue
            state = str(posting.get("state") or "").strip().lower()
            if state in {"draft", "closed", "archived", "internal", "confidential"}:
                continue
            title = str(posting.get("title") or "").strip()
            apply_url = str(
                posting.get("url")
                or posting.get("shortlink")
                or posting.get("application_url")
                or ""
            ).strip()
            if not title or not apply_url:
                continue
            description = _plain_text([
                posting.get("description"),
                posting.get("full_description"),
                posting.get("requirements"),
                posting.get("benefits"),
            ])
            published_at = str(
                posting.get("published_on") or posting.get("created_at") or ""
            ).strip()
            posted_date = published_at[:10] if published_at else ""
            location = _location(posting)
            job_id = str(
                posting.get("id") or posting.get("shortcode") or ""
            ).strip()
            result["jobs"].append({
                "source": "workable",
                "company": company_name,
                "title": title,
                "location": location,
                "department": _plain_text(posting.get("department")),
                "employment_type": _plain_text(
                    posting.get("employment_type") or posting.get("type")
                ),
                "posted_date": posted_date,
                "freshness": parse_iso_date(posted_date) if posted_date else "Unknown",
                "freshness_source": "workable_published_on" if published_at else "",
                "description": description[:8000],
                "description_enriched": bool(description),
                "apply_url": apply_url,
                "raw_url": apply_url,
                "job_id": job_id,
                "ats_type": "workable",
                "ats_slug": slug,
                "full_text": f"{title} {company_name} {description}"[:10000],
            })
        result["raw_count"] = len(result["jobs"])
        logger.info("Workable %s: %d jobs", company_name, result["raw_count"])
    except Exception as exc:
        result["error"] = str(exc)
        logger.warning("Workable %s failed: %s", company_name, exc)
    return result
