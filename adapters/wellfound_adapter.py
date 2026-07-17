"""
adapters/wellfound_adapter.py - Wellfound startup job board adapter.

Wellfound's public pages change often, so this adapter uses a layered parser:
JSON-LD first, then embedded JSON, then visible job-card links. It only returns
public apply/detail URLs and does not require authentication.
"""
import json
import logging
import random
import re
import time
from html import unescape
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from core.freshness import parse_relative_text
from core.http import DEFAULT_TIMEOUT, SESSION

logger = logging.getLogger("adapters.wellfound")

_SEARCH_URLS = [
    "https://wellfound.com/jobs?keywords=New%20Grad%20Applied%20AI%20Engineer%20RAG&location=United%20States",
    "https://wellfound.com/jobs?keywords=Entry%20Level%20Applied%20AI%20Engineer%20LLM%20agents&location=United%20States",
    "https://wellfound.com/jobs?keywords=Junior%20AI%20Engineer%20RAG%20agents&location=United%20States",
    "https://wellfound.com/jobs?keywords=Software%20Engineer%20I%20AI%20Systems%20LLM&location=United%20States",
    "https://wellfound.com/jobs?keywords=LLM%20Applications%20Engineer%20RAG&location=United%20States",
]


def _clean_text(value: str) -> str:
    value = unescape(value or "")
    value = re.sub(r"<[^>]+>", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def _job_id_from_url(url: str) -> str:
    match = re.search(r"/jobs/([^/?#]+)", url or "")
    return match.group(1) if match else url


def _normalize_job(raw: dict, source_url: str) -> dict | None:
    title = _clean_text(raw.get("title") or raw.get("name") or raw.get("jobTitle") or "")
    apply_url = raw.get("url") or raw.get("applyUrl") or raw.get("jobUrl") or ""
    apply_url = urljoin("https://wellfound.com", apply_url)

    if not title or "/jobs/" not in apply_url:
        return None

    org = raw.get("hiringOrganization") or raw.get("company") or raw.get("startup") or {}
    company = org.get("name") if isinstance(org, dict) else str(org or "")
    company = _clean_text(company) or "Unknown"

    location = raw.get("jobLocation") or raw.get("location") or ""
    if isinstance(location, list):
        location = ", ".join(
            _clean_text(item.get("address", {}).get("addressLocality", "") if isinstance(item, dict) else str(item))
            for item in location
        )
    elif isinstance(location, dict):
        address = location.get("address", {})
        if isinstance(address, dict):
            location = ", ".join(
                x for x in [
                    address.get("addressLocality", ""),
                    address.get("addressRegion", ""),
                    address.get("addressCountry", ""),
                ] if x
            )
        else:
            location = location.get("name", "")
    location = _clean_text(location)

    description = _clean_text(raw.get("description") or raw.get("body") or "")
    posted_date = raw.get("datePosted") or raw.get("postedAt") or ""
    freshness = parse_relative_text(raw.get("postedAgo", "")) if raw.get("postedAgo") else "Unknown"

    return {
        "source": "wellfound",
        "company": company,
        "title": title,
        "location": location or "United States",
        "department": "",
        "employment_type": _clean_text(raw.get("employmentType", "")),
        "posted_date": posted_date,
        "freshness": freshness,
        "description": description[:1000],
        "apply_url": apply_url,
        "job_id": _job_id_from_url(apply_url),
        "raw_url": apply_url,
        "ats_type": "wellfound",
        "ats_slug": "wellfound",
        "full_text": f"{title} {company} {location} {description}"[:3000],
        "source_search_url": source_url,
    }


def _walk_json(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _walk_json(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_json(child)


def _parse_jsonld(soup: BeautifulSoup, source_url: str) -> list:
    jobs = []
    for script in soup.find_all("script", type="application/ld+json"):
        if not script.string:
            continue
        try:
            data = json.loads(script.string)
        except json.JSONDecodeError:
            continue
        for node in _walk_json(data):
            node_type = node.get("@type")
            if node_type == "JobPosting" or (isinstance(node_type, list) and "JobPosting" in node_type):
                job = _normalize_job(node, source_url)
                if job:
                    jobs.append(job)
    return jobs


def _parse_embedded_json(soup: BeautifulSoup, source_url: str) -> list:
    jobs = []
    for script in soup.find_all("script"):
        text = script.string or script.get_text() or ""
        if "/jobs/" not in text or not any(k in text.lower() for k in ("job", "title", "company")):
            continue
        for match in re.finditer(r"\{[^{}]*(?:title|name|jobTitle)[^{}]*?/jobs/[^{}]*?\}", text):
            raw_text = match.group(0)
            try:
                raw = json.loads(raw_text)
            except json.JSONDecodeError:
                continue
            job = _normalize_job(raw, source_url)
            if job:
                jobs.append(job)
    return jobs


def _parse_visible_cards(soup: BeautifulSoup, source_url: str) -> list:
    jobs = []
    for link in soup.find_all("a", href=True):
        href = link["href"]
        if "/jobs/" not in href:
            continue
        title = _clean_text(link.get_text(" "))
        if not title or len(title) < 4:
            continue

        card = link.find_parent(["article", "li", "div"])
        card_text = _clean_text(card.get_text(" ")) if card else title
        posted_match = re.search(r"(just posted|today|\d+\s+(?:hour|day|week)s?\s+ago)", card_text, re.I)
        freshness = parse_relative_text(posted_match.group(1)) if posted_match else "Unknown"

        jobs.append({
            "source": "wellfound",
            "company": "Unknown",
            "title": title[:180],
            "location": "United States",
            "department": "",
            "employment_type": "",
            "posted_date": "",
            "freshness": freshness,
            "description": card_text[:1000],
            "apply_url": urljoin("https://wellfound.com", href),
            "job_id": _job_id_from_url(href),
            "raw_url": urljoin("https://wellfound.com", href),
            "ats_type": "wellfound",
            "ats_slug": "wellfound",
            "full_text": card_text[:3000],
            "source_search_url": source_url,
        })
    return jobs


def scrape(max_urls: int = 3) -> dict:
    """Fetch startup AI/ML intern and junior roles from Wellfound."""
    result = {"jobs": [], "raw_count": 0, "error": None}
    first_error = None
    seen_urls = set()

    from datetime import date
    start = date.today().timetuple().tm_yday % len(_SEARCH_URLS)
    urls_to_scrape = [_SEARCH_URLS[(start + i) % len(_SEARCH_URLS)] for i in range(max_urls)]

    for url in urls_to_scrape:
        try:
            time.sleep(random.uniform(1, 2.5))
            resp = SESSION.get(url, timeout=DEFAULT_TIMEOUT)
            if resp.status_code != 200:
                logger.warning("Wellfound %s: HTTP %d", url, resp.status_code)
                if not first_error:
                    first_error = f"Wellfound HTTP {resp.status_code}"
                continue

            soup = BeautifulSoup(resp.text, "html.parser")
            page_jobs = _parse_jsonld(soup, url)
            if not page_jobs:
                page_jobs = _parse_embedded_json(soup, url)
            if not page_jobs:
                page_jobs = _parse_visible_cards(soup, url)

            for job in page_jobs:
                apply_url = job.get("apply_url", "")
                if apply_url and apply_url not in seen_urls:
                    seen_urls.add(apply_url)
                    result["jobs"].append(job)

            logger.info("Wellfound %s: %d jobs", url, len(page_jobs))
        except Exception as e:
            logger.warning("Wellfound failed for %s: %s", url, e)
            if not first_error:
                first_error = str(e)

    result["raw_count"] = len(result["jobs"])
    if not result["jobs"] and first_error:
        result["error"] = first_error
    logger.info("Wellfound total: %d jobs across %d pages", result["raw_count"], len(urls_to_scrape))
    return result
