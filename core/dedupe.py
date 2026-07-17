"""
dedupe.py — Enhanced deduplication for job listings.
"""
import logging
import re
import sqlite3
from datetime import date, timedelta
from typing import Optional, Tuple

from config import JOB_DB_PATH

logger = logging.getLogger("dedupe")


def get_conn() -> sqlite3.Connection:
    """Get SQLite connection with dedup table."""
    JOB_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(JOB_DB_PATH))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS seen_jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            apply_url TEXT,
            normalized_url TEXT NOT NULL,
            company TEXT NOT NULL,
            normalized_company TEXT NOT NULL,
            title TEXT NOT NULL,
            normalized_title TEXT NOT NULL,
            company_title_key TEXT NOT NULL,
            ats_job_id TEXT,
            location TEXT,
            date_seen TEXT NOT NULL DEFAULT (date('now')),
            date_first_seen TEXT NOT NULL DEFAULT (date('now')),
            last_seen TEXT NOT NULL DEFAULT (date('now')),
            source TEXT,
            priority TEXT,
            status TEXT DEFAULT 'Found'
        );

        CREATE UNIQUE INDEX IF NOT EXISTS idx_dedup_url
            ON seen_jobs (normalized_url);

        CREATE UNIQUE INDEX IF NOT EXISTS idx_dedup_company_title
            ON seen_jobs (company_title_key);

        CREATE INDEX IF NOT EXISTS idx_dedup_date
            ON seen_jobs (date_seen);

        CREATE INDEX IF NOT EXISTS idx_dedup_ats_id
            ON seen_jobs (ats_job_id);
    """)
    conn.commit()
    return conn


def normalize_url(url: str) -> str:
    """Normalize URL for dedup."""
    if not url:
        return ""
    u = url.strip().rstrip("/")
    for sep in ["?", "#"]:
        if sep in u:
            u = u.split(sep)[0]
    if u.startswith("http://"):
        u = "https://" + u[7:]
    if not u.startswith("https://"):
        u = "https://" + u
    return u.lower()


def normalize_company(name: str) -> str:
    """Normalize company name for dedup."""
    if not name:
        return ""
    n = name.lower().replace(" ", "").replace(".", "").replace(",", "")
    n = n.replace("-", "").replace("&", "and")
    # Remove common suffixes
    for suffix in ["inc", "llc", "ltd", "corp", "corporation", "co", "company"]:
        if n.endswith(suffix):
            n = n[:-len(suffix)]
    return n


def normalize_title(title: str) -> str:
    """Normalize job title for dedup."""
    if not title:
        return ""
    t = title.lower()
    # Remove common prefixes/suffixes
    for prefix in ["senior ", "sr ", "junior ", "jr ", "lead ", "principal ", "staff "]:
        if t.startswith(prefix):
            t = t[len(prefix):]
    for suffix in [" i", " ii", " iii", " iv", " v"]:
        if t.endswith(suffix):
            t = t[:-len(suffix)]
    # Normalize whitespace and special chars
    t = re.sub(r'[^a-z0-9]', '', t)
    return t


def make_company_title_key(company: str, title: str) -> str:
    """Create a normalized company+title key."""
    return "{}|{}".format(normalize_company(company), normalize_title(title))


def is_duplicate(conn: sqlite3.Connection, job: dict) -> Tuple[bool, Optional[dict]]:
    """Check if a job is a duplicate using multiple strategies.

    Returns (is_dup, existing_record).
    """
    apply_url = job.get("apply_url", job.get("raw_url", ""))
    company = job.get("company", "")
    title = job.get("title", "")
    ats_job_id = job.get("job_id", "")
    location = job.get("location", "")

    nurl = normalize_url(apply_url)
    ctk = make_company_title_key(company, title)

    # Strategy 1: Direct URL match
    if nurl:
        row = conn.execute(
            "SELECT * FROM seen_jobs WHERE normalized_url = ?", (nurl,)
        ).fetchone()
        if row:
            return True, _row_to_dict(row, conn)

    # Strategy 2: ATS job ID match
    if ats_job_id:
        row = conn.execute(
            "SELECT * FROM seen_jobs WHERE ats_job_id = ?", (ats_job_id,)
        ).fetchone()
        if row:
            return True, _row_to_dict(row, conn)

    # Strategy 3: Company + title match
    row = conn.execute(
        "SELECT * FROM seen_jobs WHERE company_title_key = ?", (ctk,)
    ).fetchone()
    if row:
        return True, _row_to_dict(row, conn)

    # Strategy 4: Same title + same company + same location within 30 days
    if company and title and location:
        thirty_days_ago = (date.today() - timedelta(days=30)).isoformat()
        row = conn.execute(
            """SELECT * FROM seen_jobs
               WHERE normalized_company = ? AND normalized_title = ?
               AND location = ? AND date_seen >= ?""",
            (normalize_company(company), normalize_title(title), location, thirty_days_ago)
        ).fetchone()
        if row:
            return True, _row_to_dict(row, conn)

    return False, None


def insert_job(conn: sqlite3.Connection, job: dict) -> bool:
    """Insert a new job into the dedup DB. Returns True if inserted, False if dup."""
    apply_url = job.get("apply_url", job.get("raw_url", ""))
    company = job.get("company", "")
    title = job.get("title", "")

    nurl = normalize_url(apply_url)
    ncompany = normalize_company(company)
    ntitle = normalize_title(title)
    ctk = make_company_title_key(company, title)

    try:
        conn.execute(
            """INSERT INTO seen_jobs
               (apply_url, normalized_url, company, normalized_company,
                title, normalized_title, company_title_key, ats_job_id,
                location, source, priority)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (apply_url, nurl, company, ncompany,
             title, ntitle, ctk,
             job.get("job_id", ""),
             job.get("location", ""),
             job.get("source", ""),
             job.get("priority", "")),
        )
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False


def _row_to_dict(row, conn) -> dict:
    """Convert a row tuple to dict using column names."""
    cols = [d[0] for d in conn.execute("SELECT * FROM seen_jobs LIMIT 1").description]
    return dict(zip(cols[:len(row)], row))


def count_today(conn: sqlite3.Connection) -> int:
    today = date.today().isoformat()
    row = conn.execute("SELECT COUNT(*) FROM seen_jobs WHERE date_seen = ?", (today,)).fetchone()
    return row[0] if row else 0


def count_by_status(conn: sqlite3.Connection) -> dict:
    rows = conn.execute("SELECT status, COUNT(*) FROM seen_jobs GROUP BY status").fetchall()
    return {r[0]: r[1] for r in rows}
