"""
adapters/builtin_adapter.py — Built In tech job board adapter.

Parses the application/ld+json structured data embedded in the listing page.
This data is present in the server-rendered HTML and doesn't require JavaScript.
No API key needed. Free.

Scrapes multiple role-category pages for AI/ML intern and entry-level roles.
"""
import json
import logging
import re
import time
import random

from bs4 import BeautifulSoup
from core.http import SESSION, DEFAULT_TIMEOUT

logger = logging.getLogger("adapters.builtin")

# Built In search URLs for applied AI roles at entry/new-grad level.
# Internship, data analytics, and plain machine-learning pages are intentionally excluded.
# Each URL returns up to ~25 jobs in the JSON-LD ItemList
_SEARCH_URLS = [
    "https://builtin.com/jobs?job_function=Artificial+Intelligence&experience=entry-level",
]

# Regional pages for target states (NY, DC, PA, NJ, VA, MD)
_REGIONAL_URLS = [
    "https://builtinnyc.com/jobs?job_function=Artificial+Intelligence&experience=entry-level",
    "https://builtindc.com/jobs?job_function=Artificial+Intelligence&experience=entry-level",
    "https://builtinboston.com/jobs?job_function=Artificial+Intelligence&experience=entry-level",
]


def _parse_jsonld(html: str, source_url: str) -> list:
    """Extract job listings from application/ld+json ItemList in the page."""
    jobs = []
    try:
        soup = BeautifulSoup(html, "html.parser")
        scripts = soup.find_all("script", type="application/ld+json")
        for script in scripts:
            if not script.string:
                continue
            try:
                data = json.loads(script.string)
            except json.JSONDecodeError:
                continue

            # Handle @graph wrapper
            graph = data.get("@graph", [data]) if isinstance(data, dict) else []
            for node in graph:
                if node.get("@type") == "ItemList":
                    for item in node.get("itemListElement", []):
                        title = item.get("name", "").strip()
                        url = item.get("url", "").strip()
                        description = item.get("description", "").strip()

                        if not title or not url:
                            continue

                        # Extract company from URL pattern: builtin.com/job/job-slug/company-id
                        # Or from description heuristic (first sentence often mentions company)
                        company = _extract_company_from_description(description)

                        full_text = f"{title} {company} {description}"

                        jobs.append({
                            "source": "builtin",
                            "company": company or "Unknown",
                            "title": title,
                            "location": "",  # Not in ItemList; enriched below
                            "department": "",
                            "employment_type": "",
                            "posted_date": "",
                            "freshness": "Unknown",  # Will be promoted to New by pipeline
                            "description": description[:500],
                            "apply_url": url,
                            "job_id": url.split("/")[-1] if url else "",
                            "raw_url": url,
                            "ats_type": "builtin",
                            "ats_slug": "builtin",
                            "full_text": full_text[:2000],
                        })
    except Exception as e:
        logger.warning("JSON-LD parse error for %s: %s", source_url, e)
    return jobs


def _extract_company_from_description(description: str) -> str:
    """Heuristic: extract company name from description.

    Built In descriptions often start with 'Lead X at CompanyName...' or
    'CompanyName is looking for...'.
    """
    if not description:
        return ""
    # Pattern: possessive "Company's" at the start
    match = re.match(r"^([A-Z][A-Za-z0-9\s&,.']+?)'s\b", description)
    if match:
        return match.group(1).strip()
    # Pattern: "at CompanyName" near the start
    match = re.search(r"\bat\s+([A-Z][A-Za-z0-9\s&,.]+?)[\.,]", description[:200])
    if match:
        candidate = match.group(1).strip()
        if 2 < len(candidate) < 50:
            return candidate
    return ""


def scrape(max_urls: int = 3) -> dict:
    """Fetch AI/ML entry-level and intern jobs from Built In's structured data.

    Uses the application/ld+json ItemList embedded server-side in listing pages.
    No JavaScript needed. Scrapes up to max_urls pages.
    """
    result = {"jobs": [], "raw_count": 0, "error": None}
    seen_urls = set()

    # Pick a subset of URLs to scrape per run (avoid hammering all pages daily)
    from datetime import date
    day_idx = date.today().timetuple().tm_yday
    all_urls = _SEARCH_URLS + _REGIONAL_URLS
    # Rotate: each day scrapes a window of max_urls pages
    start = day_idx % len(all_urls)
    urls_to_scrape = [all_urls[(start + i) % len(all_urls)] for i in range(max_urls)]

    for url in urls_to_scrape:
        try:
            time.sleep(random.uniform(1, 3))  # Polite crawling
            resp = SESSION.get(url, timeout=DEFAULT_TIMEOUT)
            if resp.status_code != 200:
                logger.warning("Built In %s: HTTP %d", url, resp.status_code)
                continue

            page_jobs = _parse_jsonld(resp.text, url)
            for job in page_jobs:
                apply_url = job.get("apply_url", "")
                if apply_url and apply_url not in seen_urls:
                    seen_urls.add(apply_url)
                    result["jobs"].append(job)

            logger.info("Built In %s: %d jobs", url, len(page_jobs))

        except Exception as e:
            logger.warning("Built In failed for %s: %s", url, e)
            if not result["error"]:
                result["error"] = str(e)

    result["raw_count"] = len(result["jobs"])
    logger.info("Built In total: %d jobs across %d pages", result["raw_count"], len(urls_to_scrape))
    return result
