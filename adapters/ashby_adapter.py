"""Ashby public job-board adapter with a legacy GraphQL fallback."""
from __future__ import annotations

import logging
from urllib.parse import urlparse

from core.freshness import parse_iso_date
from core.http import DEFAULT_TIMEOUT, SESSION

logger = logging.getLogger("adapters.ashby")


def _job_id(url: str) -> str:
    parts = [part for part in urlparse(url).path.split("/") if part]
    if not parts:
        return ""
    return parts[-2] if parts[-1] == "apply" and len(parts) > 1 else parts[-1]


def _normalize_public_job(company_name: str, slug: str, posting: dict) -> dict | None:
    title = str(posting.get("title") or "").strip()
    if not title or posting.get("isListed") is False:
        return None
    description = str(posting.get("descriptionPlain") or "").strip()
    published_at = str(posting.get("publishedAt") or "")
    job_url = str(posting.get("jobUrl") or "")
    apply_url = str(posting.get("applyUrl") or job_url)
    return {
        "source": "ashby",
        "company": company_name,
        "title": title,
        "location": posting.get("location", ""),
        "department": posting.get("department") or posting.get("team") or "",
        "employment_type": posting.get("employmentType", ""),
        "posted_date": published_at[:10],
        "freshness": parse_iso_date(published_at),
        "freshness_source": "ashby_published_at" if published_at else "",
        "description": description[:8000],
        "description_enriched": bool(description),
        "apply_url": apply_url,
        "job_id": _job_id(job_url or apply_url),
        "raw_url": job_url or apply_url,
        "ats_type": "ashby",
        "ats_slug": slug,
        "full_text": f"{title} {company_name} {description}"[:10000],
    }


def _scrape_legacy_graphql(company_name: str, slug: str) -> dict:
    api_url = "https://jobs.ashbyhq.com/api/non-user-graphql?op=ApiJobBoardWithTeams"
    payload = {
        "operationName": "ApiJobBoardWithTeams",
        "variables": {"organizationHostedJobsPageName": slug},
        "query": (
            "query ApiJobBoardWithTeams($organizationHostedJobsPageName: String!) {"
            " jobBoardWithTeams(organizationHostedJobsPageName: $organizationHostedJobsPageName) {"
            " jobPostings { id title locationName employmentType } } }"
        ),
    }
    response = SESSION.post(api_url, json=payload, timeout=DEFAULT_TIMEOUT)
    if response.status_code != 200:
        return {"jobs": [], "raw_count": 0, "error": f"Ashby HTTP {response.status_code}"}
    postings = (
        response.json().get("data", {}).get("jobBoardWithTeams", {}).get("jobPostings", [])
    )
    jobs = []
    for posting in postings:
        title = str(posting.get("title") or "").strip()
        if not title:
            continue
        job_id = str(posting.get("id") or "")
        url = f"https://jobs.ashbyhq.com/{slug}/{job_id}"
        jobs.append({
            "source": "ashby",
            "company": company_name,
            "title": title,
            "location": posting.get("locationName", ""),
            "department": "",
            "employment_type": posting.get("employmentType", ""),
            "posted_date": "",
            "freshness": "Unknown",
            "description": "",
            "apply_url": url,
            "job_id": job_id,
            "raw_url": url,
            "ats_type": "ashby",
            "ats_slug": slug,
            "full_text": f"{title} {company_name}",
        })
    return {"jobs": jobs, "raw_count": len(jobs), "error": None}


def scrape(company_name: str, slug: str, ats_url: str = "") -> dict:
    """Fetch all listed jobs from an Ashby public board without credentials."""
    try:
        url = f"https://api.ashbyhq.com/posting-api/job-board/{slug}"
        response = SESSION.get(url, timeout=DEFAULT_TIMEOUT)
        if response.status_code == 200:
            raw_jobs = response.json().get("jobs", [])
            jobs = [job for posting in raw_jobs if (job := _normalize_public_job(company_name, slug, posting))]
            logger.info("Ashby %s: %d jobs", company_name, len(jobs))
            return {"jobs": jobs, "raw_count": len(jobs), "error": None}

        logger.info("Ashby public feed failed for %s (HTTP %s); using fallback", company_name, response.status_code)
        return _scrape_legacy_graphql(company_name, slug)
    except Exception as exc:
        logger.warning("Ashby %s failed: %s", company_name, exc)
        return {"jobs": [], "raw_count": 0, "error": str(exc)}
