"""
ats_discovery.py — Automatically detect ATS type and slug from company career pages.
"""
import re
import logging
import urllib.parse
import time
from typing import Optional, Tuple

import requests
from bs4 import BeautifulSoup

from core.source_registry import load_registry, update_company, get_unknown_ats_companies

logger = logging.getLogger("ats_discovery")

SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
})

# ATS URL patterns to search for in HTML
ATS_PATTERNS = {
    "greenhouse": [
        r"boards\.greenhouse\.io/([a-zA-Z0-9_-]+)",
        r"job-boards\.greenhouse\.io/([a-zA-Z0-9_-]+)",
        r"boards-api\.greenhouse\.io/([a-zA-Z0-9_-]+)",
        r"greenhouse\.io/embed[^'\"]*?for=([a-zA-Z0-9_-]+)",
    ],
    "lever": [
        r"jobs\.lever\.co/([a-zA-Z0-9_-]+)",
        r"api\.lever\.co/v0/([a-zA-Z0-9_-]+)",
    ],
    "ashby": [
        r"jobs\.ashbyhq\.com/([a-zA-Z0-9_-]+)",
        r"ashbyhq\.com/([a-zA-Z0-9_-]+)",
    ],
    "workday": [
        r"([a-zA-Z0-9_-]+)\.wd\d+\.myworkdayjobs\.com",
        r"([a-zA-Z0-9_-]+)\.myworkday\.com",
    ],
    "smartrecruiters": [
        r"jobs\.smartrecruiters\.com/([a-zA-Z0-9_-]+)",
    ],
    "workable": [
        r"([a-zA-Z0-9_-]+)\.workable\.com",
        r"apply\.workable\.com/([a-zA-Z0-9_-]+)(?:/|$)",
        r"workable\.com/api/accounts/([a-zA-Z0-9_-]+)(?:[/?]|$)",
    ],
    "icims": [
        r"([a-zA-Z0-9_-]+)\.icims\.com",
    ],
}

ATS_URL_TEMPLATES = {
    "greenhouse": "https://job-boards.greenhouse.io/{slug}",
    "lever": "https://jobs.lever.co/{slug}",
    "ashby": "https://jobs.ashbyhq.com/{slug}",
    "workday": "https://{slug}.wd1.myworkdayjobs.com/",
    "smartrecruiters": "https://jobs.smartrecruiters.com/{slug}",
    "workable": "https://apply.workable.com/{slug}/",
    "icims": "https://{slug}.icims.com/",
}


def _get(url: str, timeout: int = 10) -> Optional[requests.Response]:
    try:
        resp = SESSION.get(url, timeout=timeout)
        if resp.status_code == 200:
            return resp
        return None
    except Exception:
        return None


def discover_from_html(html_text: str) -> Optional[Tuple[str, str]]:
    """Parse HTML to find ATS links. Returns (ats_type, slug) or None."""
    for ats_type, patterns in ATS_PATTERNS.items():
        for pattern in patterns:
            match = re.search(pattern, html_text)
            if match:
                slug = match.group(1)
                # Filter out common false positives
                if slug.lower() in ("careers", "jobs", "apply", "www", "blog", "about"):
                    continue
                return ats_type, slug
    return None


def discover_from_scripts(html_text: str, base_url: str) -> Optional[Tuple[str, str]]:
    """Parse script tags and embedded JSON for ATS references."""
    soup = BeautifulSoup(html_text, "html.parser")

    # Check all script tags
    for script in soup.find_all("script"):
        text = script.string or ""
        result = discover_from_html(text)
        if result:
            return result

    # Check all links
    for link in soup.find_all("a", href=True):
        href = link["href"]
        result = discover_from_html(href)
        if result:
            return result

    # Check iframes
    for iframe in soup.find_all("iframe", src=True):
        result = discover_from_html(iframe["src"])
        if result:
            return result

    return None


def discover_from_search(company_name: str) -> Optional[Tuple[str, str]]:
    """Try to discover ATS via search engine queries (last resort)."""
    queries = [
        "{} careers site:greenhouse.io".format(company_name),
        "{} jobs site:lever.co".format(company_name),
        "{} careers site:ashbyhq.com".format(company_name),
        "{} careers site:apply.workable.com".format(company_name),
        "{} site:myworkdayjobs.com".format(company_name),
    ]

    for query in queries:
        try:
            # Use DuckDuckGo HTML search (no API key needed)
            url = "https://html.duckduckgo.com/html/?q={}".format(
                urllib.parse.quote(query)
            )
            resp = _get(url, timeout=10)
            if not resp:
                continue

            soup = BeautifulSoup(resp.text, "html.parser")
            results = soup.find_all("a", class_="result__a", href=True)

            for result in results[:3]:
                href = result["href"]
                result_parsed = discover_from_html(href)
                if result_parsed:
                    return result_parsed

            time.sleep(1.5)  # Be polite
        except Exception as e:
            logger.debug("Search query failed: %s", e)
            continue

    return None


def test_ats_url(ats_type: str, slug: str) -> bool:
    """Test if a discovered ATS URL actually works."""
    url = ATS_URL_TEMPLATES.get(ats_type, "").format(slug=slug)
    if not url:
        return False

    try:
        resp = _get(url, timeout=10)
        if resp and resp.status_code == 200:
            # For Greenhouse, verify it's not a 404 page
            if ats_type == "greenhouse":
                if "no jobs" in resp.text.lower() or "page not found" in resp.text.lower():
                    return False
            return True
    except Exception:
        pass
    return False


def discover_company(company_name: str, career_url: str) -> Optional[dict]:
    """Full discovery pipeline for a single company.

    Returns dict with ats_type, ats_slug, ats_url or None.
    """
    logger.info("Discovering ATS for %s (%s)", company_name, career_url)

    # Step 1: Fetch career page and parse HTML
    try:
        resp = _get(career_url, timeout=15)
        if resp:
            html = resp.text

            # Try direct HTML parsing
            result = discover_from_html(html)
            if result:
                ats_type, slug = result
                if test_ats_url(ats_type, slug):
                    return _make_discovery_result(ats_type, slug, "html_parse")

            # Try scripts and links
            result = discover_from_scripts(html, career_url)
            if result:
                ats_type, slug = result
                if test_ats_url(ats_type, slug):
                    return _make_discovery_result(ats_type, slug, "script_parse")
    except Exception as e:
        logger.debug("HTML parsing failed for %s: %s", company_name, e)

    # Step 2: ATS-specific search (most reliable)
    search_result = _discover_via_direct_search(company_name)
    if search_result:
        return search_result

    # Step 3: General search (slowest, last resort)
    try:
        result = discover_from_search(company_name)
        if result:
            ats_type, slug = result
            if test_ats_url(ats_type, slug):
                return _make_discovery_result(ats_type, slug, "web_search")
    except Exception as e:
        logger.debug("Search discovery failed for %s: %s", company_name, e)

    logger.info("ATS discovery failed for %s", company_name)
    return None


def _discover_via_direct_search(company_name: str) -> Optional[dict]:
    """Try known ATS URL patterns directly."""
    # Try Greenhouse
    slug_guess = company_name.lower().replace(" ", "").replace(".", "").replace(",", "")
    for suffix in ["", "ai", "inc", "hq", "labs"]:
        test_slug = "{}{}".format(slug_guess, suffix) if suffix else slug_guess
        url = "https://job-boards.greenhouse.io/embed/job_board?for={}".format(test_slug)
        try:
            resp = _get(url, timeout=8)
            if resp and resp.status_code == 200:
                # Check it's not a generic 404
                if len(resp.text) > 5000 and "opening" in resp.text.lower():
                    return _make_discovery_result("greenhouse", test_slug, "direct_test_greenhouse")
        except Exception:
            pass
        time.sleep(0.3)

    # Try Lever
    for suffix in ["", "ai", "inc", "hq"]:
        test_slug = "{}{}".format(slug_guess, suffix) if suffix else slug_guess
        url = "https://jobs.lever.co/{}".format(test_slug)
        try:
            resp = _get(url, timeout=8)
            if resp and resp.status_code == 200:
                if "lever" in resp.text.lower() and len(resp.text) > 3000:
                    return _make_discovery_result("lever", test_slug, "direct_test_lever")
        except Exception:
            pass
        time.sleep(0.3)

    # Try Ashby
    for suffix in ["", "ai", "inc", "hq"]:
        test_slug = "{}{}".format(slug_guess, suffix) if suffix else slug_guess
        url = "https://jobs.ashbyhq.com/{}".format(test_slug)
        try:
            resp = _get(url, timeout=8)
            if resp and resp.status_code == 200:
                if "ashby" in resp.text.lower() and len(resp.text) > 3000:
                    return _make_discovery_result("ashby", test_slug, "direct_test_ashby")
        except Exception:
            pass
        time.sleep(0.3)

    # Try Workable's documented public careers endpoint.
    for suffix in ["", "ai", "inc", "hq"]:
        test_slug = "{}{}".format(slug_guess, suffix) if suffix else slug_guess
        url = "https://www.workable.com/api/accounts/{}?details=false".format(test_slug)
        try:
            resp = _get(url, timeout=8)
            if resp:
                payload = resp.json()
                if isinstance(payload, dict) and "jobs" in payload:
                    return _make_discovery_result("workable", test_slug, "direct_test_workable")
        except Exception:
            pass
        time.sleep(0.3)

    return None


def _make_discovery_result(ats_type: str, slug: str, method: str) -> dict:
    """Create a discovery result dict."""
    url_template = ATS_URL_TEMPLATES.get(ats_type, "")
    ats_url = url_template.format(slug=slug) if url_template else ""
    return {
        "ats_type": ats_type,
        "ats_slug": slug,
        "ats_url": ats_url,
        "discovery_method": method,
    }


def run_discovery(max_companies: int = 10) -> dict:
    """Run ATS discovery for all unknown companies in the registry.

    Returns summary of results.
    """
    registry = load_registry()
    unknown = get_unknown_ats_companies(registry)

    results = {
        "attempted": 0,
        "discovered": 0,
        "failed": 0,
        "skipped": 0,
        "details": [],
    }

    for company in unknown[:max_companies]:
        name = company["company_name"]
        career_url = company.get("career_url", "")

        if not career_url:
            results["skipped"] += 1
            continue

        results["attempted"] += 1
        discovery = discover_company(name, career_url)

        if discovery:
            update_company(name, {
                "ats_type": discovery["ats_type"],
                "ats_slug": discovery["ats_slug"],
                "ats_url": discovery["ats_url"],
                "notes": "Auto-discovered via {}".format(discovery["discovery_method"]),
            }, registry)
            results["discovered"] += 1
            results["details"].append({
                "company": name,
                "ats_type": discovery["ats_type"],
                "slug": discovery["ats_slug"],
                "method": discovery["discovery_method"],
            })
        else:
            results["failed"] += 1
            results["details"].append({
                "company": name,
                "ats_type": "unknown",
                "slug": "",
                "method": "failed",
            })

        time.sleep(1.0)  # Be polite between companies

    logger.info("Discovery complete: %d discovered, %d failed out of %d attempted",
                results["discovered"], results["failed"], results["attempted"])
    return results
