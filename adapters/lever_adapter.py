"""
adapters/lever_adapter.py — Lever ATS adapter.

Scrapes job listings from Lever-hosted career pages.
No API key needed.
"""
import logging
from datetime import datetime

from core.http import SESSION, DEFAULT_TIMEOUT
from core.freshness import parse_iso_date

logger = logging.getLogger("adapters.lever")


def scrape(company_name: str, slug: str, ats_url: str = "") -> dict:
    """Fetch jobs from a Lever board."""
    result = {"jobs": [], "raw_count": 0, "error": None}

    try:
        url = f"https://api.lever.co/v0/postings/{slug}"
        resp = SESSION.get(url, timeout=DEFAULT_TIMEOUT)
        if resp.status_code != 200:
            result["error"] = f"Lever HTTP {resp.status_code}"
            return result

        data = resp.json()
        if not isinstance(data, list):
            data = [data]

        for job in data:
            title = job.get("text", "") or job.get("title", "")
            if not title:
                continue

            categories = job.get("categories")
            if not isinstance(categories, dict):
                categories = {}
            location = categories.get("location", "") or ""
            commitment = categories.get("commitment", "") or ""
            team = categories.get("team", "") or ""
            apply_url = job.get("applyUrl", "") or job.get("hostedUrl", "")

            full_text = f"{title} {company_name} {job.get('description', '')} {job.get('lists', '')}"

            created_at = job.get("createdAt")
            posted_date = ""
            freshness = "Unknown"
            if created_at:
                if isinstance(created_at, (int, float)):
                    try:
                        posted_date = datetime.fromtimestamp(created_at / 1000.0).strftime("%Y-%m-%d")
                    except Exception:
                        posted_date = ""
                elif isinstance(created_at, str):
                    posted_date = created_at[:10]

                if posted_date:
                    freshness = parse_iso_date(posted_date)

            result["jobs"].append({
                "source": "lever",
                "company": company_name,
                "title": title,
                "location": location,
                "department": team,
                "employment_type": commitment,
                "posted_date": posted_date,
                "freshness": freshness,
                "description": (job.get("description", "") or job.get("content", ""))[:500],
                "apply_url": apply_url,
                "job_id": str(job.get("id", "")),
                "raw_url": apply_url,
                "ats_type": "lever",
                "ats_slug": slug,
                "full_text": full_text[:3000],
            })

        result["raw_count"] = len(result["jobs"])
        logger.info("Lever %s: %d jobs", company_name, result["raw_count"])

    except Exception as e:
        result["error"] = str(e)
        logger.warning("Lever %s failed: %s", company_name, e)

    return result
