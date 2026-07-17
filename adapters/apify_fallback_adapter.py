"""
adapters/apify_fallback_adapter.py — Apify fallback for hard sources (Workday, JS-heavy pages).
Only runs if APIFY_TOKEN exists and daily budget is not exhausted.
"""
import logging
import os
import time

import requests

from core.source_registry import can_run_apify, increment_apify_runs

logger = logging.getLogger("adapters.apify")

SESSION = requests.Session()
APIFY_TOKEN = os.getenv("APIFY_TOKEN", "")

# Known Apify actors for job scraping
APIFY_ACTORS = {
    "workday": "apify/web-scraper",  # Generic scraper for Workday
}


def scrape_workday(company_name: str, career_url: str) -> dict:
    """Scrape a Workday career page using Apify."""
    result = {"jobs": [], "raw_count": 0, "error": None, "source": "apify_workday"}

    if not APIFY_TOKEN:
        result["error"] = "No APIFY_TOKEN"
        return result

    if not can_run_apify():
        result["error"] = "Daily Apify budget exhausted"
        return result

    try:
        # Use Apify's web-scraper actor
        run_url = "https://api.apify.com/v2/acts/apify~web-scraper/runs"
        headers = {"Authorization": "Bearer {}".format(APIFY_TOKEN)}

        payload = {
            "startUrls": [{"url": career_url}],
            "pageFunction": _workday_page_function(),
            "proxyConfiguration": {"useApifyProxy": True},
        }

        resp = SESSION.post(run_url, json=payload, headers=headers, timeout=30)
        if resp.status_code not in (200, 201):
            result["error"] = "Apify run failed: {}".format(resp.status_code)
            return result

        run_data = resp.json()
        run_id = run_data.get("data", {}).get("id", "")

        # Poll for completion (simplified — in production, use webhooks)
        dataset_id = None
        for _ in range(30):  # Max 60 seconds
            time.sleep(2)
            status_url = "https://api.apify.com/v2/acts/apify~web-scraper/runs/{}".format(run_id)
            status_resp = SESSION.get(status_url, headers=headers, timeout=15)
            if status_resp.status_code == 200:
                status_data = status_resp.json()
                status = status_data.get("data", {}).get("status", "")
                if status == "SUCCEEDED":
                    dataset_id = status_data.get("data", {}).get("defaultDatasetId", "")
                    break
                elif status in ("FAILED", "ABORTED", "TIMING-OUT"):
                    result["error"] = "Apify run {}".format(status)
                    return result

        if dataset_id:
            # Fetch results
            items_url = "https://api.apify.com/v2/datasets/{}/items".format(dataset_id)
            items_resp = SESSION.get(items_url, headers=headers, timeout=15)
            if items_resp.status_code == 200:
                items = items_resp.json()
                if isinstance(items, list):
                    for item in items:
                        title = item.get("title", "")
                        if not title:
                            continue
                        normalized = {
                            "source": "apify_workday",
                            "company": company_name,
                            "title": title,
                            "location": item.get("location", ""),
                            "department": "",
                            "employment_type": "",
                            "posted_date": "",
                            "freshness": "New (0-3d)",
                            "description": item.get("description", "")[:500],
                            "apply_url": item.get("url", career_url),
                            "job_id": "",
                            "raw_url": item.get("url", career_url),
                            "ats_type": "workday",
                            "ats_slug": "",
                            "full_text": "{} {}".format(title, item.get("description", ""))[:1000],
                        }
                        result["jobs"].append(normalized)
                    result["raw_count"] = len(result["jobs"])

        increment_apify_runs()
        logger.info("Apify Workday %s: %d jobs", company_name, result["raw_count"])

    except Exception as e:
        result["error"] = str(e)
        logger.warning("Apify Workday failed for %s: %s", company_name, e)

    return result


def _workday_page_function() -> str:
    """JavaScript page function for Apify web-scraper to extract Workday jobs."""
    return """
    async function pageFunction(context) {
        const { $, request, log } = context;
        const jobs = [];

        // Workday job listings
        $('[data-automation-id="jobTitle"], .WMN0, .jobTitle, a[data-automation-id="jobTitle"]').each((i, el) => {
            const title = $(el).text().trim();
            const url = $(el).attr('href') || '';
            const location = $(el).closest('[data-automation-id="jobPosting"]').find('[data-automation-id="location"]').text().trim() || '';

            if (title && title.length > 3) {
                jobs.push({ title, url, location, description: '' });
            }
        });

        return jobs;
    }
    """
