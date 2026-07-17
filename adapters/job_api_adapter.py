"""
adapters/job_api_adapter.py — Optional job search APIs.
Only activates if the corresponding API key exists in .env.
"""
import logging
import os

import requests

logger = logging.getLogger("adapters.job_api")

SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
})

# API keys from environment
JSEARCH_API_KEY = os.getenv("JSEARCH_API_KEY", "")
ADZUNA_APP_ID = os.getenv("ADZUNA_APP_ID", "")
ADZUNA_APP_KEY = os.getenv("ADZUNA_APP_KEY", "")
SERPAPI_API_KEY = os.getenv("SERPAPI_API_KEY", "")
SEARCHAPI_API_KEY = os.getenv("SEARCHAPI_API_KEY", "")


def _get(url: str, params: dict = None, headers: dict = None) -> dict:
    try:
        resp = SESSION.get(url, params=params, headers=headers, timeout=15)
        if resp.status_code == 200:
            return resp.json()
        return {}
    except Exception:
        return {}


def scrape_jsearch() -> dict:
    """Scrape via JSearch API (RapidAPI)."""
    result = {"jobs": [], "raw_count": 0, "error": None, "source": "jsearch"}

    if not JSEARCH_API_KEY:
        result["error"] = "No API key"
        return result

    try:
        url = "https://jsearch.p.rapidapi.com/search"
        headers = {
            "X-RapidAPI-Key": JSEARCH_API_KEY,
            "X-RapidAPI-Host": "jsearch.p.rapidapi.com",
        }

        queries = ["AI intern", "ML intern", "machine learning intern"]
        for query in queries:
            params = {
                "query": query + " United States",
                "page": "1",
                "num_pages": "1",
            }
            data = _get(url, params=params, headers=headers)
            jobs = data.get("data", [])
            result["raw_count"] += len(jobs)

            for job in jobs:
                normalized = {
                    "source": "jsearch",
                    "company": job.get("employer_name", ""),
                    "title": job.get("job_title", ""),
                    "location": "{}, {}".format(
                        job.get("job_city", ""),
                        job.get("job_state", "")
                    ),
                    "department": "",
                    "employment_type": job.get("job_employment_type", ""),
                    "posted_date": job.get("job_posted_at_datetime_utc", ""),
                    "freshness": "New (0-3d)",
                    "description": (job.get("job_description", ""))[:500],
                    "apply_url": job.get("job_apply_link", ""),
                    "job_id": job.get("job_id", ""),
                    "raw_url": job.get("job_apply_link", ""),
                    "ats_type": "jsearch",
                    "ats_slug": "",
                    "full_text": "{} {}".format(
                        job.get("job_title", ""),
                        job.get("job_description", "")
                    )[:1000],
                }
                result["jobs"].append(normalized)

        logger.info("JSearch: %d raw jobs", result["raw_count"])

    except Exception as e:
        result["error"] = str(e)
        logger.warning("JSearch failed: %s", e)

    return result


def scrape_adzuna() -> dict:
    """Scrape via Adzuna API."""
    result = {"jobs": [], "raw_count": 0, "error": None, "source": "adzuna"}

    if not ADZUNA_APP_ID or not ADZUNA_APP_KEY:
        result["error"] = "No API key"
        return result

    try:
        url = "https://api.adzuna.com/v1/api/jobs/us/search/1"
        queries = ["AI intern", "ML intern", "machine learning intern"]

        for query in queries:
            params = {
                "app_id": ADZUNA_APP_ID,
                "app_key": ADZUNA_APP_KEY,
                "what": query,
                "where": "United States",
                "max_days_old": "14",
                "results_per_page": "20",
            }
            data = _get(url, params=params)
            jobs = data.get("results", [])
            result["raw_count"] += len(jobs)

            for job in jobs:
                location = job.get("location", {})
                loc_str = location.get("display_name", "") if isinstance(location, dict) else str(location)

                normalized = {
                    "source": "adzuna",
                    "company": job.get("company", {}).get("display_name", ""),
                    "title": job.get("title", ""),
                    "location": loc_str,
                    "department": "",
                    "employment_type": job.get("contract_type", ""),
                    "posted_date": job.get("created", ""),
                    "freshness": "New (0-3d)",
                    "description": (job.get("description", ""))[:500],
                    "apply_url": job.get("redirect_url", ""),
                    "job_id": str(job.get("id", "")),
                    "raw_url": job.get("redirect_url", ""),
                    "ats_type": "adzuna",
                    "ats_slug": "",
                    "full_text": "{} {}".format(
                        job.get("title", ""),
                        job.get("description", "")
                    )[:1000],
                }
                result["jobs"].append(normalized)

        logger.info("Adzuna: %d raw jobs", result["raw_count"])

    except Exception as e:
        result["error"] = str(e)
        logger.warning("Adzuna failed: %s", e)

    return result


def scrape_serpapi() -> dict:
    """Use SerpApi for X-ray discovery of career pages and ATS URLs.
    NOT used as a primary job source — only for discovering new ATS URLs.
    """
    result = {"jobs": [], "raw_count": 0, "error": None, "source": "serpapi"}

    if not SERPAPI_API_KEY:
        result["error"] = "No API key"
        return result

    try:
        # Use SerpApi to find career pages with ATS links
        queries = [
            "site:greenhouse.io AI intern",
            "site:jobs.lever.co AI intern",
            "site:jobs.ashbyhq.com AI intern",
        ]

        for query in queries:
            url = "https://serpapi.com/search"
            params = {
                "q": query,
                "api_key": SERPAPI_API_KEY,
                "engine": "google",
                "num": "10",
            }
            data = _get(url, params=params)
            organic = data.get("organic_results", [])
            result["raw_count"] += len(organic)

            for item in organic:
                link = item.get("link", "")
                title = item.get("title", "")
                snippet = item.get("snippet", "")

                normalized = {
                    "source": "serpapi",
                    "company": "",
                    "title": title,
                    "location": "",
                    "department": "",
                    "employment_type": "",
                    "posted_date": "",
                    "freshness": "New (0-3d)",
                    "description": snippet[:500],
                    "apply_url": link,
                    "job_id": "",
                    "raw_url": link,
                    "ats_type": "serpapi",
                    "ats_slug": "",
                    "full_text": "{} {}".format(title, snippet)[:1000],
                }
                result["jobs"].append(normalized)

        logger.info("SerpApi: %d results", result["raw_count"])

    except Exception as e:
        result["error"] = str(e)
        logger.warning("SerpApi failed: %s", e)

    return result


def scrape_all() -> dict:
    """Run all available API adapters.

    Returns combined results.
    """
    all_results = {
        "jobs": [],
        "raw_count": 0,
        "errors": [],
        "sources": {},
    }

    adapters = [
        ("jsearch", scrape_jsearch),
        ("adzuna", scrape_adzuna),
        ("serpapi", scrape_serpapi),
    ]

    for name, adapter_fn in adapters:
        try:
            result = adapter_fn()
            all_results["jobs"].extend(result.get("jobs", []))
            all_results["raw_count"] += result.get("raw_count", 0)
            all_results["sources"][name] = result.get("raw_count", 0)
            if result.get("error"):
                all_results["errors"].append("{}: {}".format(name, result["error"]))
        except Exception as e:
            all_results["errors"].append("{}: {}".format(name, str(e)))

    return all_results
