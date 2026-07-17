"""
adapters/github_lists_adapter.py — GitHub-curated job lists (Simplify).

Scrapes job listings from GitHub repositories that maintain
curated lists of intern/new-grad positions. The tables are in HTML format.
No API key needed.
"""
import logging
import re
from html.parser import HTMLParser

from core.http import SESSION, DEFAULT_TIMEOUT

logger = logging.getLogger("adapters.github_lists")

# Known GitHub job list repos
SOURCES = [
    {
        "name": "Simplify Summer 2026 Internships",
        "url": "https://raw.githubusercontent.com/SimplifyJobs/Summer2026-Internships/dev/README.md",
        "type": "summer_intern",
    },
    {
        "name": "Simplify New Grad Positions",
        "url": "https://raw.githubusercontent.com/SimplifyJobs/New-Grad-Positions/dev/README.md",
        "type": "new_grad",
    },
]


class JobTableParser(HTMLParser):
    """Parse HTML tables from Simplify README."""

    def __init__(self):
        super().__init__()
        self.in_tbody = False
        self.in_tr = False
        self.in_td = False
        self.current_row = []
        self.current_cell = ""
        self.rows = []
        self.td_count = 0

    def handle_starttag(self, tag, attrs):
        if tag == "tbody":
            self.in_tbody = True
        elif tag == "tr" and self.in_tbody:
            self.in_tr = True
            self.current_row = []
            self.td_count = 0
        elif tag == "td" and self.in_tr:
            self.in_td = True
            self.current_cell = ""
            self.td_count += 1

        # Extract links from <a> tags
        if tag == "a":
            href = dict(attrs).get("href", "")
            if href:
                self.current_cell += f" [LINK:{href}] "

    def handle_endtag(self, tag):
        if tag == "tbody":
            self.in_tbody = False
        elif tag == "tr":
            self.in_tr = False
            if self.current_row:
                self.rows.append(self.current_row)
        elif tag == "td":
            self.in_td = False
            self.current_row.append(self.current_cell.strip())
            self.current_cell = ""

    def handle_data(self, data):
        if self.in_td:
            self.current_cell += data

    def handle_entityref(self, name):
        if self.in_td:
            self.current_cell += f"&{name};"

    def handle_charref(self, name):
        if self.in_td:
            self.current_cell += f"&#{name};"


def _parse_html_jobs(html: str, source_name: str) -> list:
    """Parse job listings from HTML table in Simplify README."""
    parser = JobTableParser()
    parser.feed(html)
    parser.close()

    jobs = []
    for row in parser.rows:
        if len(row) < 4:
            continue

        # Row format: [Company, Role, Location, Application, Age]
        company_cell = row[0] if len(row) > 0 else ""
        role_cell = row[1] if len(row) > 1 else ""
        location_cell = row[2] if len(row) > 2 else ""
        apply_cell = row[3] if len(row) > 3 else ""

        # Extract company name from cell (may contain link)
        company_match = re.search(r'<a[^>]*>([^<]+)</a>', company_cell)
        company = company_match.group(1).strip() if company_match else company_cell.strip()
        # Remove any [LINK:...] artifacts
        company = re.sub(r'\s*\[LINK:[^\]]+\]', '', company).strip()
        company = re.sub(r'\s+', ' ', company).strip()
        if not company or company == "↳":
            continue

        # Extract role
        role = role_cell.strip()
        role = re.sub(r'<[^>]+>', '', role)
        role = re.sub(r'\s+', ' ', role).strip()

        # Extract location
        location = location_cell.strip()
        location = re.sub(r'<br\s*/?>', ', ', location)
        location = re.sub(r'<[^>]+>', '', location)
        location = re.sub(r'\s+', ' ', location).strip()

        # Extract apply URL from application cell using [LINK:url] format
        apply_url = ""
        links = re.findall(r'\[LINK:([^\]\s]+)\]', apply_cell)
        if links:
            # The first link in the application cell is usually the direct apply URL
            apply_url = links[0]

        if not apply_url and role_cell:
            # Fallback to link in the role cell
            role_links = re.findall(r'\[LINK:([^\]\s]+)\]', role_cell)
            if role_links:
                apply_url = role_links[0]

        jobs.append({
            "source": "github_list",
            "company": company,
            "title": role,
            "location": location,
            "department": "",
            "employment_type": "",
            "posted_date": "",
            "freshness": "Unknown",
            "description": "",
            "apply_url": apply_url,
            "job_id": f"{company}|{role}",
            "raw_url": apply_url,
            "ats_type": "github_list",
            "ats_slug": source_name.lower().replace(" ", "_"),
            "full_text": f"{role} {company}",
        })

    return jobs


def scrape() -> dict:
    """Fetch jobs from GitHub-curated new-grad lists.

    The Simplify internship list is intentionally skipped for the candidate's completed-
    Master's pipeline; internships can still enter from other sources only when
    the posting text explicitly proves graduate eligibility.
    """
    result = {"jobs": [], "raw_count": 0, "error": None}

    for source in SOURCES:
        if source.get("type") != "new_grad":
            logger.info("GitHub list %s: skipped for strict non-intern targeting", source["name"])
            continue
        try:
            resp = SESSION.get(source["url"], timeout=DEFAULT_TIMEOUT)
            if resp.status_code != 200:
                result["errors"] = result.get("errors", [])
                result["errors"].append(f"{source['name']}: HTTP {resp.status_code}")
                continue

            jobs = _parse_html_jobs(resp.text, source["name"])
            result["jobs"].extend(jobs)
            logger.info("GitHub list %s: %d jobs", source["name"], len(jobs))

        except Exception as e:
            result["errors"] = result.get("errors", [])
            result["errors"].append(f"{source['name']}: {e}")
            logger.warning("GitHub list %s failed: %s", source["name"], e)

    result["raw_count"] = len(result["jobs"])
    return result
