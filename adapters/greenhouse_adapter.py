"""
adapters/greenhouse_adapter.py — Greenhouse ATS adapter.

Scrapes job listings from Greenhouse-hosted career pages.
No API key needed.
"""
import logging

from core.http import SESSION, DEFAULT_TIMEOUT

logger = logging.getLogger("adapters.greenhouse")


def scrape(company_name: str, slug: str, ats_url: str = "") -> dict:
    """Fetch jobs from a Greenhouse board."""
    result = {"jobs": [], "raw_count": 0, "error": None}

    try:
        url = f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs"
        resp = SESSION.get(url, params={"content": "true"}, timeout=DEFAULT_TIMEOUT)
        if resp.status_code != 200:
            result["error"] = f"Greenhouse HTTP {resp.status_code}"
            return result

        data = resp.json()
        jobs_data = data.get("jobs", [])

        for job in jobs_data:
            title = job.get("title", "")
            if not title:
                continue

            location = job.get("location", {})
            location_name = location.get("name", "") if isinstance(location, dict) else ""
            absolute_url = job.get("absolute_url", "")

            content = str(job.get("content") or "")
            full_text = f"{title} {company_name} {content}"

            result["jobs"].append({
                "source": "greenhouse",
                "company": company_name,
                "title": title,
                "location": location_name,
                "department": (job.get("departments") or [{}])[0].get("name", "") if job.get("departments") else "",
                "employment_type": job.get("metadata", [{}])[0].get("value", "") if job.get("metadata") else "",
                # Greenhouse exposes record update time here, not the original
                # posting date. Keep it as provenance without claiming a post age.
                "posted_date": "",
                "source_updated_at": job.get("updated_at", ""),
                "freshness_source": "ats_updated_at" if job.get("updated_at") else "",
                "freshness": "Unknown",
                "description": content[:8000],
                "description_enriched": bool(content),
                "apply_url": absolute_url,
                "job_id": str(job.get("id", "")),
                "raw_url": absolute_url,
                "ats_type": "greenhouse",
                "ats_slug": slug,
                "full_text": full_text[:10000],
            })

        result["raw_count"] = len(result["jobs"])
        logger.info("Greenhouse %s: %d jobs", company_name, result["raw_count"])

    except Exception as e:
        result["error"] = str(e)
        logger.warning("Greenhouse %s failed: %s", company_name, e)

    return result
