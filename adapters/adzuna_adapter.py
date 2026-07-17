"""
adapters/adzuna_adapter.py — Adzuna job search API.

Needs ADZUNA_APP_ID + ADZUNA_APP_KEY in .env.
Free tier: 100 requests/day.
Docs: https://developer.adzuna.com/
"""
import logging
import os

from core.http import SESSION, DEFAULT_TIMEOUT
from core.freshness import parse_iso_date

logger = logging.getLogger("adapters.adzuna")


def _get_credentials():
    return os.environ.get("ADZUNA_APP_ID", ""), os.environ.get("ADZUNA_APP_KEY", "")


def scrape(query: str = "AI ML intern", country: str = "us", max_results: int = 50) -> dict:
    """Fetch jobs from Adzuna API."""
    result = {"jobs": [], "raw_count": 0, "error": None}

    app_id, app_key = _get_credentials()
    if not app_id or not app_key:
        result["error"] = "ADZUNA_APP_ID and ADZUNA_APP_KEY not configured"
        return result

    try:
        url = f"https://api.adzuna.com/v1/api/jobs/{country}/search/1"
        params = {
            "app_id": app_id,
            "app_key": app_key,
            "results_per_page": max_results,
            "what": query,
            "max_days_old": 3,  # Match tiered age limits (Priority C max = 3 days)
        }

        resp = SESSION.get(url, params=params, timeout=DEFAULT_TIMEOUT)
        if resp.status_code != 200:
            result["error"] = f"Adzuna HTTP {resp.status_code}: {resp.text[:200]}"
            return result

        data = resp.json()

        for job in data.get("results", []):
            title = job.get("title", "")
            if not title:
                continue

            company = job.get("company", {})
            company_name = company.get("display_name", "") if isinstance(company, dict) else ""
            location = job.get("location", {})
            location_name = location.get("display_name", "") if isinstance(location, dict) else ""
            posted = job.get("created", "")

            full_text = f"{title} {company_name} {job.get('description', '')}"

            result["jobs"].append({
                "source": "api_adzuna",
                "company": company_name or "Unknown",
                "title": title,
                "location": location_name,
                "department": "",
                "employment_type": "",
                "posted_date": posted[:10] if posted else "",
                "freshness": parse_iso_date(posted),
                "description": job.get("description", "")[:500],
                "apply_url": job.get("redirect_url", ""),
                "job_id": str(job.get("id", "")),
                "raw_url": job.get("redirect_url", ""),
                "ats_type": "api",
                "ats_slug": "adzuna",
                "full_text": full_text[:1000],
            })

        result["raw_count"] = len(result["jobs"])
        logger.info("Adzuna: %d jobs for '%s'", result["raw_count"], query)

    except Exception as e:
        result["error"] = str(e)
        logger.warning("Adzuna failed: %s", e)

    return result
