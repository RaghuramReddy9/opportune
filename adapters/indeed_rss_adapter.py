"""
adapters/indeed_rss_adapter.py — Pull jobs from Indeed RSS feeds.
Free, no API key needed. Uses Indeed's public RSS feed.
"""
import logging
import re
import xml.etree.ElementTree as ET  # Safe: trusted Indeed RSS, not user XML.
from datetime import datetime, timezone
from typing import Optional

import requests

logger = logging.getLogger("adapters.indeed_rss")

SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
})


def _parse_rss_date(date_str: str) -> Optional[datetime]:
    """Parse RSS date formats like 'Mon, 15 Jun 2026 14:30:00 GMT'."""
    if not date_str:
        return None
    formats = [
        "%a, %d %b %Y %H:%M:%S %Z",
        "%a, %d %b %Y %H:%M:%S %z",
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%dT%H:%M:%S%z",
    ]
    for fmt in formats:
        try:
            return datetime.strptime(date_str.strip(), fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def _days_ago_freshness(days: int) -> str:
    if days <= 1:
        return "New (0-24h)"
    elif days <= 2:
        return "Recent (24-48h)"
    elif days <= 7:
        return "This Week (3-7d)"
    elif days <= 14:
        return "Old (8-14d)"
    else:
        return "Stale (15d+)"


def scrape(query: str = "AI+ML+intern", location: str = "United+States", max_jobs: int = 100) -> dict:
    """Fetch jobs from Indeed RSS feed.

    Free, no API key. Returns recent job listings with descriptions and dates.
    Example: https://www.indeed.com/rss?q=AI+ML+intern&l=United+States
    """
    result = {"jobs": [], "raw_count": 0, "error": None}

    try:
        url = "https://www.indeed.com/rss?q={}&l={}".format(query, location)
        resp = SESSION.get(url, timeout=20)

        if resp.status_code != 200:
            result["error"] = "HTTP {}".format(resp.status_code)
            return result

        # Parse RSS XML
        root = ET.fromstring(resp.content)
        ns = {"": "http://www.w3.org/2005/Atom"} if root.tag.endswith("feed") else {}

        items = root.findall(".//item") or root.findall(".//entry", ns)
        now = datetime.now(timezone.utc)

        for item in items[:max_jobs]:
            title_el = item.find("title") or item.find("title", ns)
            link_el = item.find("link") or item.find("link", ns)
            desc_el = item.find("description") or item.find("summary", ns)
            date_el = item.find("pubDate") or item.find("published", ns) or item.find("updated", ns)

            title = title_el.text.strip() if title_el is not None and title_el.text else ""
            if not title:
                continue

            # Extract link
            link = ""
            if link_el is not None:
                link = link_el.get("href", "") or (link_el.text or "")
            # Clean link
            link = link.strip()

            # Parse description (contains company, location, snippet)
            description = ""
            if desc_el is not None and desc_el.text:
                description = re.sub(r"<[^>]+>", "", desc_el.text).strip()

            # Parse date
            freshness = "Unknown"
            if date_el is not None and date_el.text:
                pub_date = _parse_rss_date(date_el.text)
                if pub_date:
                    days_ago = (now - pub_date).days
                    freshness = _days_ago_freshness(days_ago)

            # Extract company from title (Indeed format: "Job Title - Company Name")
            company = ""
            if " - " in title:
                parts = title.split(" - ", 1)
                title = parts[0].strip()
                company = parts[1].strip()

            # Extract location from description if possible
            location_found = ""
            loc_match = re.search(r"(?:Location|location):\s*(.+?)(?:\n|$)", description)
            if loc_match:
                location_found = loc_match.group(1).strip()

            full_text = "{} {}".format(title, description)

            normalized = {
                "source": "indeed_rss",
                "company": company or "Indeed",
                "title": title,
                "location": location_found,
                "department": "",
                "employment_type": "",
                "posted_date": date_el.text[:10] if date_el is not None and date_el.text else "",
                "freshness": freshness,
                "description": description[:500],
                "apply_url": link,
                "job_id": "",
                "raw_url": link,
                "ats_type": "indeed",
                "ats_slug": "",
                "full_text": full_text[:1000],
            }
            result["jobs"].append(normalized)

        result["raw_count"] = len(result["jobs"])
        logger.info("Indeed RSS: %d jobs for query=%s location=%s", result["raw_count"], query, location)

    except Exception as e:
        result["error"] = str(e)
        logger.warning("Indeed RSS failed: %s", e)

    return result
