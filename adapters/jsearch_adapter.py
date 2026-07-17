"""
adapters/jsearch_adapter.py — OpenWebNinja JSearch API.

Needs JSEARCH_API_KEY in .env.
Docs: https://www.openwebninja.com/documentation (JSearch)
Endpoint: https://api.openwebninja.com/jsearch/search-v2
Free tier: varies by plan.
"""
import logging
import os

from core.http import SESSION, DEFAULT_TIMEOUT
from core.freshness import parse_iso_date

logger = logging.getLogger("adapters.jsearch")


def _get_api_key() -> str:
    return os.environ.get("JSEARCH_API_KEY", "")


def _extract_apply_url(job_data: dict) -> str:
    apply_options = job_data.get("apply_options") or []
    if apply_options and isinstance(apply_options, list):
        first = apply_options[0] or {}
        return first.get("apply_link", "") or first.get("link", "")
    return job_data.get("job_apply_link", "") or job_data.get("job_google_link", "") or ""


def scrape(query: str = "AI ML intern in United States", location: str = "United States", num_pages: int = 1) -> dict:
    """Fetch jobs from OpenWebNinja JSearch.

    search-v2 returns up to 10 jobs/page with cursor pagination.
    Each page consumes one request credit.
    """
    result = {"jobs": [], "raw_count": 0, "error": None}

    api_key = _get_api_key()
    if not api_key:
        result["error"] = "JSEARCH_API_KEY not configured"
        return result

    try:
        cursor = None
        for _ in range(max(1, num_pages)):
            url = "https://api.openwebninja.com/jsearch/search-v2"
            headers = {"x-api-key": api_key}
            params = {
                "query": query if " in " in query.lower() else f"{query} in {location}",
                "num_pages": 1,
                "country": "us",
                "language": "en",
            }
            if cursor:
                params["cursor"] = cursor

            resp = SESSION.get(url, headers=headers, params=params, timeout=DEFAULT_TIMEOUT)
            if resp.status_code != 200:
                result["error"] = f"OpenWebNinja JSearch HTTP {resp.status_code}: {resp.text[:200]}"
                break

            data = resp.json()
            payload = data.get("data", {})
            if isinstance(payload, dict):
                jobs_data = payload.get("jobs", []) or []
                cursor = payload.get("cursor")
            elif isinstance(payload, list):
                jobs_data = payload
                cursor = None
            else:
                break

            if not jobs_data:
                break

            for jd in jobs_data:
                title = jd.get("job_title", "") or jd.get("title", "")
                if not title:
                    continue

                posted_dt = jd.get("job_posted_at_datetime_utc", "") or ""
                freshness = parse_iso_date(posted_dt)

                full_text = f"{title} {jd.get('employer_name', '')} {jd.get('job_description', '')}"

                result["jobs"].append({
                    "source": "api_jsearch",
                    "company": jd.get("employer_name", "") or "Unknown",
                    "title": title,
                    "location": jd.get("job_location", "") or jd.get("location", "") or location,
                    "department": "",
                    "employment_type": (jd.get("detected_extensions") or {}).get("schedule_type", ""),
                    "posted_date": posted_dt[:10] if posted_dt else "",
                    "freshness": freshness,
                    "description": (jd.get("job_description", "") or jd.get("description", ""))[:500],
                    "apply_url": _extract_apply_url(jd),
                    "job_id": jd.get("job_id", ""),
                    "raw_url": jd.get("job_google_link", "") or _extract_apply_url(jd),
                    "ats_type": "api",
                    "ats_slug": "openwebninja_jsearch",
                    "full_text": full_text[:3000],
                })

            if not cursor:
                break

        result["raw_count"] = len(result["jobs"])
        logger.info("OpenWebNinja JSearch: %d jobs for '%s'", result["raw_count"], query)

    except Exception as e:
        result["error"] = str(e)
        logger.warning("OpenWebNinja JSearch failed: %s", e)

    return result
