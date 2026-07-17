"""
adapters/ycombinator_adapter.py — Y Combinator job board adapter.

Scrapes job listings from YC's Hacker News job board as a reliable public source.
No API key needed.
"""
import logging
import re
from bs4 import BeautifulSoup
import requests
from core.http import DEFAULT_TIMEOUT

logger = logging.getLogger("adapters.ycombinator")

HN_JOBS_URL = "https://news.ycombinator.com/jobs"


def scrape() -> dict:
    """Fetch jobs from YC's Hacker News job board."""
    result = {"jobs": [], "raw_count": 0, "error": None}

    try:
        import time
        import random
        # Add random delay to let initial thread burst settle down (HN is rate sensitive)
        time.sleep(random.uniform(3, 6))

        # Create a dedicated session to prevent connection pool conflicts during parallel runs
        session = requests.Session()
        session.headers.update({
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/125.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        })

        resp = None
        for attempt in range(2):  # Up to 2 attempts with backoff on 429
            resp = session.get(HN_JOBS_URL, timeout=DEFAULT_TIMEOUT)
            if resp.status_code == 429:
                wait = 10 + random.uniform(0, 5)  # 10-15s backoff
                logger.info("HN rate-limited (attempt %d), waiting %.0fs...", attempt + 1, wait)
                time.sleep(wait)
            else:
                break

        if resp is None or resp.status_code != 200:
            result["error"] = f"Hacker News HTTP {resp.status_code if resp else 'no response'}"
            return result

        soup = BeautifulSoup(resp.text, "html.parser")
        rows = soup.find_all("tr", class_="athing")

        for row in rows:
            # Find the link inside span class titleline
            titleline = row.find("span", class_="titleline")
            if titleline:
                a_tag = titleline.find("a")
            else:
                a_tag = row.find("a")

            if not a_tag:
                continue

            text = a_tag.text.strip()
            href = a_tag.get("href", "").strip()

            if href.startswith("item?id="):
                href = f"https://news.ycombinator.com/{href}"

            # Parse company name and role
            # Pattern: "Mistral AI (YC W23) is hiring software engineers"
            match = re.search(r'^(.+?)(?:\s+\(YC\s+[A-Z0-9]+\))?\s+(?:is\s+hiring|hiring)\s+(.+)$', text, re.IGNORECASE)
            if match:
                company = match.group(1).strip()
                title = match.group(2).strip()
            else:
                parts = re.split(r'\s+is\s+hiring\s+|\s+hiring\s+', text, flags=re.IGNORECASE)
                if len(parts) >= 2:
                    company = parts[0].strip()
                    title = parts[1].strip()
                else:
                    # Clean up if it just says "Is Hiring" at the end
                    clean_text = re.sub(r'\s+\(YC\s+[A-Z0-9]+\)?', '', text)
                    clean_text = re.sub(r'\s+is\s+hiring\s*$', '', clean_text, flags=re.IGNORECASE)
                    clean_text = re.sub(r'\s+hiring\s*$', '', clean_text, flags=re.IGNORECASE)
                    company = clean_text.strip()
                    title = "General Software/AI Engineer"

            # Clean up company names that have extra YC tags
            company = re.sub(r'\s+\(YC\s+[A-Z0-9, ]+\)', '', company, flags=re.IGNORECASE)

            # Build full text for scoring
            full_text = f"{title} {company} {text}"

            result["jobs"].append({
                "source": "ycombinator",
                "company": company,
                "title": title,
                "location": "Remote / Onsite",
                "department": "",
                "employment_type": "Full-time",
                "posted_date": "",
                "freshness": "New (0-24h)",  # Treat as new since it's on the main active jobs page
                "description": text,
                "apply_url": href,
                "job_id": href.split("id=")[1] if "id=" in href else href,
                "raw_url": href,
                "ats_type": "ycombinator",
                "ats_slug": "yc",
                "full_text": full_text[:3000],
            })

        result["raw_count"] = len(result["jobs"])
        logger.info("YC: %d jobs", result["raw_count"])

    except Exception as e:
        result["error"] = str(e)
        logger.warning("YC failed: %s", e)

    return result
