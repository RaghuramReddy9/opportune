"""
adapters/serpapi_adapter.py — Google Jobs via SerpApi.

Needs SERPAPI_API_KEY in .env.
Free tier: 100 searches/month.
Docs: https://serpapi.com/google-jobs-api
"""
import logging
import os

from core.http import SESSION, DEFAULT_TIMEOUT
from core.freshness import parse_relative_text

logger = logging.getLogger("adapters.serpapi")


def _get_api_key() -> str:
    return os.environ.get("SERPAPI_API_KEY", "")


def scrape(query: str = "AI ML intern jobs", location: str = "United States") -> dict:
    """Fetch jobs from Google Jobs via SerpApi."""
    result = {"jobs": [], "raw_count": 0, "error": None}

    api_key = _get_api_key()
    if not api_key:
        result["error"] = "SERPAPI_API_KEY not configured"
        return result

    try:
        url = "https://serpapi.com/search.json"
        params = {
            "engine": "google_jobs",
            "q": f"{query} in {location}",
            "api_key": api_key,
            "num": 10,
        }

        resp = SESSION.get(url, params=params, timeout=DEFAULT_TIMEOUT)
        if resp.status_code == 429:
            result["error"] = "SerpApi quota exhausted (429)"
            return result
        if resp.status_code != 200:
            result["error"] = f"SerpApi HTTP {resp.status_code}: {resp.text[:200]}"
            return result

        data = resp.json()
        jobs_results = data.get("jobs_results", [])

        for jd in jobs_results:
            title = jd.get("title", "")
            if not title:
                continue

            company = jd.get("company_name", "")
            location_name = jd.get("location", "")
            description = jd.get("description", "")
            apply_url = jd.get("apply_options", [{}])[0].get("link", "") if jd.get("apply_options") else ""
            date_posted = jd.get("date_posted", "")

            full_text = f"{title} {company} {description}"

            result["jobs"].append({
                "source": "api_serpapi",
                "company": company or "Unknown",
                "title": title,
                "location": location_name,
                "department": "",
                "employment_type": "",
                "posted_date": "",
                "freshness": parse_relative_text(date_posted),
                "description": description[:500],
                "apply_url": apply_url,
                "job_id": jd.get("job_id", ""),
                "raw_url": apply_url,
                "ats_type": "api",
                "ats_slug": "serpapi",
                "full_text": full_text[:3000],
            })

        result["raw_count"] = len(result["jobs"])
        logger.info("SerpApi: %d jobs for '%s'", result["raw_count"], query)

    except Exception as e:
        err_str = str(e)
        # Treat quota/rate-limit/connection errors as silent skips — not real failures
        if any(x in err_str for x in ("429", "quota", "Too Many Requests", "ResponseError", "ConnectionPool")):
            logger.info("SerpApi quota/rate-limit — skipping silently: %s", err_str[:100])
            result["error"] = None  # Don't mark as failed_source
            result["health_error"] = err_str
        else:
            result["error"] = err_str
            logger.warning("SerpApi failed: %s", e)

    return result
