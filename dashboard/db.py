"""dashboard/db.py — SQLite persistence for the real-time job-hunt dashboard.

Single source of truth for profiles, discovered jobs, catalog state, and manual
application tracking. No external sync database is required.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Iterator

from config import DASHBOARD_DB_PATH

DEFAULT_DB_PATH = DASHBOARD_DB_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_uid TEXT UNIQUE NOT NULL,
    company TEXT NOT NULL,
    title TEXT NOT NULL,
    location TEXT DEFAULT '',
    apply_url TEXT DEFAULT '',
    source TEXT DEFAULT '',
    ats_type TEXT DEFAULT '',
    resume_match_score INTEGER DEFAULT 0,
    freshness TEXT DEFAULT 'Unknown',
    freshness_trust TEXT DEFAULT 'unverified',
    action_tag TEXT DEFAULT 'watch',
    target_role_families TEXT DEFAULT '[]',
    matched_keywords TEXT DEFAULT '[]',
    why_matches TEXT DEFAULT '',
    why_risky TEXT DEFAULT '',
    opt_signal TEXT DEFAULT 'Unknown',
    best_matching_project TEXT DEFAULT '',
    apply_window_score INTEGER DEFAULT 0,
    apply_window_label TEXT DEFAULT 'medium',
    apply_window_reasons TEXT DEFAULT '[]',
    apply_window_next_action TEXT DEFAULT 'Review before applying',
    status TEXT DEFAULT 'discovered',
    status_date TEXT DEFAULT '',
    note TEXT DEFAULT '',
    date_discovered TEXT DEFAULT '',
    date_applied TEXT DEFAULT '',
    date_updated TEXT DEFAULT '',
    needs_sync INTEGER DEFAULT 0,
    is_demo INTEGER DEFAULT 0,
    link_status TEXT DEFAULT '',
    link_verified_at TEXT DEFAULT '',
    posted_date TEXT DEFAULT '',
    freshness_source TEXT DEFAULT ''
    ,first_seen_at TEXT DEFAULT ''
    ,last_seen_at TEXT DEFAULT ''
    ,content_changed_at TEXT DEFAULT ''
    ,listing_state TEXT DEFAULT 'active'
    ,description TEXT DEFAULT ''
    ,work_mode TEXT DEFAULT 'unknown'
    ,experience_level TEXT DEFAULT 'unknown'
    ,employment_type TEXT DEFAULT ''
    ,pool_match_reason TEXT DEFAULT ''
    ,profile_id TEXT DEFAULT ''
    ,visa_sponsorship INTEGER DEFAULT -1
);

CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
CREATE INDEX IF NOT EXISTS idx_jobs_action ON jobs(action_tag);
CREATE INDEX IF NOT EXISTS idx_jobs_company ON jobs(company);
CREATE INDEX IF NOT EXISTS idx_jobs_uid ON jobs(job_uid);
CREATE INDEX IF NOT EXISTS idx_jobs_profile ON jobs(profile_id);

CREATE TABLE IF NOT EXISTS profiles (
    profile_id TEXT PRIMARY KEY,
    name TEXT DEFAULT '',
    resume_text TEXT DEFAULT '',
    extracted_json TEXT DEFAULT '{}',
    is_active INTEGER DEFAULT 0,
    created_at TEXT NOT NULL,
    last_used_at TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS scrape_runs (
    run_id TEXT PRIMARY KEY,
    run_window TEXT DEFAULT '',
    started_at TEXT NOT NULL,
    finished_at TEXT DEFAULT '',
    status TEXT DEFAULT 'running',
    source_count INTEGER DEFAULT 0,
    listing_count INTEGER DEFAULT 0,
    error TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS job_catalog (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    catalog_uid TEXT UNIQUE NOT NULL,
    source_scope TEXT NOT NULL,
    source TEXT NOT NULL,
    source_name TEXT DEFAULT '',
    ats_job_id TEXT DEFAULT '',
    company TEXT NOT NULL,
    title TEXT NOT NULL,
    location TEXT DEFAULT '',
    apply_url TEXT DEFAULT '',
    normalized_url TEXT DEFAULT '',
    content_hash TEXT NOT NULL,
    payload_json TEXT DEFAULT '{}',
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    content_changed_at TEXT NOT NULL,
    last_seen_run_id TEXT NOT NULL,
    listing_state TEXT DEFAULT 'active',
    missing_since TEXT DEFAULT '',
    consecutive_misses INTEGER DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_catalog_scope ON job_catalog(source_scope);
CREATE INDEX IF NOT EXISTS idx_catalog_state ON job_catalog(listing_state);
CREATE INDEX IF NOT EXISTS idx_catalog_last_seen ON job_catalog(last_seen_at);
CREATE INDEX IF NOT EXISTS idx_catalog_url ON job_catalog(normalized_url);

CREATE TABLE IF NOT EXISTS enrichment_queue (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_uid TEXT NOT NULL,
    priority INTEGER DEFAULT 0,
    attempts INTEGER DEFAULT 0,
    last_error TEXT DEFAULT '',
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now')),
    UNIQUE(job_uid)
);
CREATE INDEX IF NOT EXISTS idx_enrichment_job_uid ON enrichment_queue(job_uid);
"""
# Runtime override (used by tests and CLI). Process-local; not thread-safe across
# processes, but fine for a single-user local dashboard.
_db_path_override: Path | None = None


def get_db_path() -> Path:
    return _db_path_override or DEFAULT_DB_PATH


def set_db_path(path: Path | None) -> None:
    global _db_path_override
    _db_path_override = path


@contextmanager
def connect(db_path: Path | None = None) -> Iterator[sqlite3.Connection]:
    path = str(db_path if db_path is not None else get_db_path())
    conn = sqlite3.connect(path, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=10000")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db(db_path: Path | None = None) -> None:
    with connect(db_path) as conn:
        table_exists = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='jobs'"
        ).fetchone()
        if not table_exists:
            conn.executescript(SCHEMA)
        else:
            _ensure_columns(conn)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_jobs_action ON jobs(action_tag)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_jobs_company ON jobs(company)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_jobs_uid ON jobs(job_uid)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_jobs_profile ON jobs(profile_id)")

        # Auxiliary tables must also be created when upgrading an existing DB;
        # running the full SCHEMA only for a brand-new jobs table misses them.
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS scrape_runs (
                run_id TEXT PRIMARY KEY,
                run_window TEXT DEFAULT '',
                started_at TEXT NOT NULL,
                finished_at TEXT DEFAULT '',
                status TEXT DEFAULT 'running',
                source_count INTEGER DEFAULT 0,
                listing_count INTEGER DEFAULT 0,
                error TEXT DEFAULT ''
            );
            CREATE TABLE IF NOT EXISTS job_catalog (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                catalog_uid TEXT UNIQUE NOT NULL,
                source_scope TEXT NOT NULL,
                source TEXT NOT NULL,
                source_name TEXT DEFAULT '',
                ats_job_id TEXT DEFAULT '',
                company TEXT NOT NULL,
                title TEXT NOT NULL,
                location TEXT DEFAULT '',
                apply_url TEXT DEFAULT '',
                normalized_url TEXT DEFAULT '',
                content_hash TEXT NOT NULL,
                payload_json TEXT DEFAULT '{}',
                first_seen_at TEXT NOT NULL,
                last_seen_at TEXT NOT NULL,
                content_changed_at TEXT NOT NULL,
                last_seen_run_id TEXT NOT NULL,
                listing_state TEXT DEFAULT 'active',
                missing_since TEXT DEFAULT '',
                consecutive_misses INTEGER DEFAULT 0
            );
            CREATE INDEX IF NOT EXISTS idx_catalog_scope ON job_catalog(source_scope);
            CREATE INDEX IF NOT EXISTS idx_catalog_state ON job_catalog(listing_state);
            CREATE INDEX IF NOT EXISTS idx_catalog_last_seen ON job_catalog(last_seen_at);
            CREATE INDEX IF NOT EXISTS idx_catalog_url ON job_catalog(normalized_url);
            CREATE TABLE IF NOT EXISTS enrichment_queue (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_uid TEXT NOT NULL,
                priority INTEGER DEFAULT 0,
                attempts INTEGER DEFAULT 0,
                last_error TEXT DEFAULT '',
                created_at TEXT DEFAULT (datetime('now')),
                updated_at TEXT DEFAULT (datetime('now')),
                UNIQUE(job_uid)
            );
            CREATE INDEX IF NOT EXISTS idx_enrichment_job_uid
                ON enrichment_queue(job_uid);
            CREATE TABLE IF NOT EXISTS profiles (
                profile_id TEXT PRIMARY KEY,
                name TEXT DEFAULT '',
                resume_text TEXT DEFAULT '',
                extracted_json TEXT DEFAULT '{}',
                is_active INTEGER DEFAULT 0,
                created_at TEXT NOT NULL,
                last_used_at TEXT DEFAULT ''
            );
            """
        )
        # Older seeded rows predate the explicit is_demo flag.
        conn.execute(
            "UPDATE jobs SET is_demo = 1 WHERE source = 'sample_data' AND is_demo = 0"
        )


def _ensure_columns(conn: sqlite3.Connection) -> None:
    """Add dashboard columns when upgrading an existing local DB."""
    existing = {row["name"] for row in conn.execute("PRAGMA table_info(jobs)").fetchall()}
    migrations = {
        "location": "ALTER TABLE jobs ADD COLUMN location TEXT DEFAULT ''",
        "apply_url": "ALTER TABLE jobs ADD COLUMN apply_url TEXT DEFAULT ''",
        "source": "ALTER TABLE jobs ADD COLUMN source TEXT DEFAULT ''",
        "ats_type": "ALTER TABLE jobs ADD COLUMN ats_type TEXT DEFAULT ''",
        "resume_match_score": "ALTER TABLE jobs ADD COLUMN resume_match_score INTEGER DEFAULT 0",
        "freshness": "ALTER TABLE jobs ADD COLUMN freshness TEXT DEFAULT 'Unknown'",
        "freshness_trust": "ALTER TABLE jobs ADD COLUMN freshness_trust TEXT DEFAULT 'unverified'",
        "action_tag": "ALTER TABLE jobs ADD COLUMN action_tag TEXT DEFAULT 'watch'",
        "target_role_families": "ALTER TABLE jobs ADD COLUMN target_role_families TEXT DEFAULT '[]'",
        "matched_keywords": "ALTER TABLE jobs ADD COLUMN matched_keywords TEXT DEFAULT '[]'",
        "why_matches": "ALTER TABLE jobs ADD COLUMN why_matches TEXT DEFAULT ''",
        "why_risky": "ALTER TABLE jobs ADD COLUMN why_risky TEXT DEFAULT ''",
        "opt_signal": "ALTER TABLE jobs ADD COLUMN opt_signal TEXT DEFAULT 'Unknown'",
        "best_matching_project": "ALTER TABLE jobs ADD COLUMN best_matching_project TEXT DEFAULT ''",
        "apply_window_score": "ALTER TABLE jobs ADD COLUMN apply_window_score INTEGER DEFAULT 0",
        "apply_window_label": "ALTER TABLE jobs ADD COLUMN apply_window_label TEXT DEFAULT 'medium'",
        "apply_window_reasons": "ALTER TABLE jobs ADD COLUMN apply_window_reasons TEXT DEFAULT '[]'",
        "apply_window_next_action": "ALTER TABLE jobs ADD COLUMN apply_window_next_action TEXT DEFAULT 'Review before applying'",
        "status": "ALTER TABLE jobs ADD COLUMN status TEXT DEFAULT 'discovered'",
        "status_date": "ALTER TABLE jobs ADD COLUMN status_date TEXT DEFAULT ''",
        "note": "ALTER TABLE jobs ADD COLUMN note TEXT DEFAULT ''",
        "date_discovered": "ALTER TABLE jobs ADD COLUMN date_discovered TEXT DEFAULT ''",
        "date_applied": "ALTER TABLE jobs ADD COLUMN date_applied TEXT DEFAULT ''",
        "date_updated": "ALTER TABLE jobs ADD COLUMN date_updated TEXT DEFAULT ''",
        "needs_sync": "ALTER TABLE jobs ADD COLUMN needs_sync INTEGER DEFAULT 0",
        "is_demo": "ALTER TABLE jobs ADD COLUMN is_demo INTEGER DEFAULT 0",
        "link_status": "ALTER TABLE jobs ADD COLUMN link_status TEXT DEFAULT ''",
        "link_verified_at": "ALTER TABLE jobs ADD COLUMN link_verified_at TEXT DEFAULT ''",
        "posted_date": "ALTER TABLE jobs ADD COLUMN posted_date TEXT DEFAULT ''",
        "freshness_source": "ALTER TABLE jobs ADD COLUMN freshness_source TEXT DEFAULT ''",
        "first_seen_at": "ALTER TABLE jobs ADD COLUMN first_seen_at TEXT DEFAULT ''",
        "last_seen_at": "ALTER TABLE jobs ADD COLUMN last_seen_at TEXT DEFAULT ''",
        "content_changed_at": "ALTER TABLE jobs ADD COLUMN content_changed_at TEXT DEFAULT ''",
        "listing_state": "ALTER TABLE jobs ADD COLUMN listing_state TEXT DEFAULT 'active'",
        "description": "ALTER TABLE jobs ADD COLUMN description TEXT DEFAULT ''",
        "work_mode": "ALTER TABLE jobs ADD COLUMN work_mode TEXT DEFAULT 'unknown'",
        "experience_level": "ALTER TABLE jobs ADD COLUMN experience_level TEXT DEFAULT 'unknown'",
        "employment_type": "ALTER TABLE jobs ADD COLUMN employment_type TEXT DEFAULT ''",
        "pool_match_reason": "ALTER TABLE jobs ADD COLUMN pool_match_reason TEXT DEFAULT ''",
        "profile_id": "ALTER TABLE jobs ADD COLUMN profile_id TEXT DEFAULT ''",
        "visa_sponsorship": "ALTER TABLE jobs ADD COLUMN visa_sponsorship INTEGER DEFAULT -1",
    }
    for column, sql in migrations.items():
        if column not in existing:
            conn.execute(sql)


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _today_iso() -> str:
    return date.today().isoformat()


def _normalized_catalog_url(url: str) -> str:
    """Return a stable URL without tracking parameters or fragments."""
    from urllib.parse import urlparse, urlunparse

    raw = str(url or "").strip()
    if not raw:
        return ""
    try:
        parsed = urlparse(raw)
        scheme = "https" if parsed.scheme in {"", "http", "https"} else parsed.scheme
        return urlunparse(
            (scheme, parsed.netloc.lower(), parsed.path.rstrip("/"), "", "", "")
        ).lower()
    except Exception:
        return raw.split("?", 1)[0].split("#", 1)[0].rstrip("/").lower()


def _source_scope(source_key: str, source_name: str) -> str:
    key = " ".join(str(source_key or "unknown").strip().lower().split())
    name = " ".join(str(source_name or "unknown").strip().lower().split())
    return f"{key}:{name}"


def _catalog_identity(source_scope: str, job: dict) -> tuple[str, str, str]:
    """Return catalog UID, ATS id, and normalized URL for one observation."""
    ats_job_id = str(job.get("job_id") or job.get("ats_job_id") or "").strip()
    apply_url = str(job.get("apply_url") or job.get("raw_url") or "").strip()
    normalized_url = _normalized_catalog_url(apply_url)
    if ats_job_id:
        stable_key = f"ats:{ats_job_id.lower()}"
    elif normalized_url:
        stable_key = f"url:{normalized_url}"
    else:
        company = " ".join(str(job.get("company") or "").lower().split())
        title = " ".join(str(job.get("title") or job.get("role") or "").lower().split())
        location = " ".join(str(job.get("location") or "").lower().split())
        stable_key = f"fallback:{company}|{title}|{location}"
    digest = hashlib.sha256(f"{source_scope}|{stable_key}".encode("utf-8")).hexdigest()
    return digest, ats_job_id, normalized_url


def _catalog_content(job: dict) -> tuple[str, str]:
    """Hash only material listing fields and return a compact source payload."""
    material_fields = (
        "company",
        "title",
        "role",
        "location",
        "department",
        "employment_type",
        "posted_date",
        "apply_url",
        "raw_url",
        "description",
        "full_text",
    )
    payload = {}
    for field in material_fields:
        value = job.get(field, "")
        if isinstance(value, str):
            value = " ".join(value.split())
        payload[field] = value
    payload_json = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload_json.encode("utf-8")).hexdigest(), payload_json


def start_scrape_run(
    conn: sqlite3.Connection,
    run_window: str,
    *,
    started_at: str | None = None,
) -> str:
    """Create a durable run record and return its opaque ID."""
    run_id = uuid.uuid4().hex
    conn.execute(
        "INSERT INTO scrape_runs (run_id, run_window, started_at) VALUES (?, ?, ?)",
        (run_id, run_window, started_at or _now_iso()),
    )
    return run_id


def reconcile_source_snapshot(
    conn: sqlite3.Connection,
    *,
    run_id: str,
    source_key: str,
    source_name: str,
    jobs: list[dict],
    close_after_misses: int = 2,
    seen_at: str | None = None,
) -> dict[str, int | str]:
    """Reconcile one complete, successful direct-source snapshot.

    A listing is marked ``missing`` after one successful snapshot omits it and
    ``closed`` after two. Failed source requests must never call this function,
    which prevents network outages from closing every job on a board.
    """
    scope = _source_scope(source_key, source_name)
    observed_at = seen_at or _now_iso()
    threshold = max(1, int(close_after_misses))
    discovered = changed = refreshed = 0

    for job in jobs:
        company = str(job.get("company") or source_name or "").strip()
        title = str(job.get("title") or job.get("role") or "").strip()
        if not company or not title:
            continue
        uid, ats_job_id, normalized_url = _catalog_identity(scope, job)
        content_hash, payload_json = _catalog_content(job)
        existing = conn.execute(
            "SELECT content_hash FROM job_catalog WHERE catalog_uid = ?", (uid,)
        ).fetchone()
        if existing is None:
            discovered += 1
        elif existing["content_hash"] != content_hash:
            changed += 1
        else:
            refreshed += 1
        apply_url = str(job.get("apply_url") or job.get("raw_url") or "").strip()
        conn.execute(
            """
            INSERT INTO job_catalog (
                catalog_uid, source_scope, source, source_name, ats_job_id,
                company, title, location, apply_url, normalized_url,
                content_hash, payload_json, first_seen_at, last_seen_at,
                content_changed_at, last_seen_run_id, listing_state,
                missing_since, consecutive_misses
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'active', '', 0)
            ON CONFLICT(catalog_uid) DO UPDATE SET
                company = excluded.company,
                title = excluded.title,
                location = excluded.location,
                apply_url = excluded.apply_url,
                normalized_url = excluded.normalized_url,
                ats_job_id = excluded.ats_job_id,
                payload_json = excluded.payload_json,
                content_changed_at = CASE
                    WHEN job_catalog.content_hash <> excluded.content_hash
                    THEN excluded.last_seen_at ELSE job_catalog.content_changed_at END,
                content_hash = excluded.content_hash,
                last_seen_at = excluded.last_seen_at,
                last_seen_run_id = excluded.last_seen_run_id,
                listing_state = 'active',
                missing_since = '',
                consecutive_misses = 0
            """,
            (
                uid,
                scope,
                source_key,
                source_name,
                ats_job_id,
                company,
                title,
                str(job.get("location") or ""),
                apply_url,
                normalized_url,
                content_hash,
                payload_json,
                observed_at,
                observed_at,
                observed_at,
                run_id,
            ),
        )

    omitted = conn.execute(
        """
        SELECT catalog_uid, consecutive_misses
        FROM job_catalog
        WHERE source_scope = ? AND last_seen_run_id <> ?
          AND listing_state IN ('active', 'missing')
        """,
        (scope, run_id),
    ).fetchall()
    newly_missing = newly_closed = 0
    for row in omitted:
        next_misses = int(row["consecutive_misses"] or 0) + 1
        next_state = "closed" if next_misses >= threshold else "missing"
        if next_state == "closed":
            newly_closed += 1
        else:
            newly_missing += 1
        conn.execute(
            """
            UPDATE job_catalog SET
                consecutive_misses = ?,
                listing_state = ?,
                missing_since = CASE WHEN missing_since = '' THEN ? ELSE missing_since END
            WHERE catalog_uid = ?
            """,
            (next_misses, next_state, observed_at, row["catalog_uid"]),
        )
        catalog_row = conn.execute(
            "SELECT company, title, apply_url FROM job_catalog WHERE catalog_uid = ?",
            (row["catalog_uid"],),
        ).fetchone()
        if catalog_row:
            conn.execute(
                """
                UPDATE jobs SET listing_state = ?, last_seen_at = COALESCE(NULLIF(last_seen_at, ''), ?)
                WHERE apply_url = ? OR (
                    LOWER(TRIM(company)) = LOWER(TRIM(?))
                    AND LOWER(TRIM(title)) = LOWER(TRIM(?))
                )
                """,
                (
                    next_state,
                    observed_at,
                    catalog_row["apply_url"],
                    catalog_row["company"],
                    catalog_row["title"],
                ),
            )

    return {
        "source_scope": scope,
        "observed": discovered + changed + refreshed,
        "discovered": discovered,
        "changed": changed,
        "refreshed": refreshed,
        "missing": newly_missing,
        "closed": newly_closed,
    }


def finish_scrape_run(
    conn: sqlite3.Connection,
    run_id: str,
    *,
    source_count: int,
    listing_count: int,
    status: str = "completed",
    error: str = "",
    finished_at: str | None = None,
) -> None:
    conn.execute(
        """
        UPDATE scrape_runs SET finished_at = ?, status = ?, source_count = ?,
            listing_count = ?, error = ? WHERE run_id = ?
        """,
        (finished_at or _now_iso(), status, source_count, listing_count, error[:1000], run_id),
    )


def get_catalog_stats(conn: sqlite3.Connection) -> dict[str, int]:
    rows = conn.execute(
        "SELECT listing_state, COUNT(*) AS count FROM job_catalog GROUP BY listing_state"
    ).fetchall()
    counts = {"active": 0, "missing": 0, "closed": 0}
    counts.update({str(row["listing_state"]): int(row["count"]) for row in rows})
    counts["total"] = sum(counts.values())
    return counts


def get_latest_scrape_run(conn: sqlite3.Connection) -> dict | None:
    row = conn.execute(
        "SELECT * FROM scrape_runs ORDER BY started_at DESC LIMIT 1"
    ).fetchone()
    return dict(row) if row else None


def make_job_uid(job: dict) -> str:
    """Stable unique id for a job, derived from company+title+apply_url.

    The apply URL is normalized (query string + fragment stripped) before
    hashing so the same posting reached via different tracking params
    (e.g. ?utm_campaign=google_jobs_apply) collapses to one id
    instead of creating duplicate dashboard rows.
    """
    from urllib.parse import urlparse, urlunparse

    company = (job.get("company") or "").strip().lower().replace(" ", "-")
    title = (job.get("title") or job.get("role") or "").strip().lower().replace(" ", "-")
    raw = (job.get("apply_url") or job.get("raw_url") or "").strip()
    try:
        parsed = urlparse(raw)
        url = urlunparse((parsed.scheme, parsed.netloc, parsed.path, "", "", "")).rstrip("/")
    except Exception:
        url = raw
    url_hash = hashlib.sha256(url.encode("utf-8")).hexdigest()[:8]
    base_uid = f"{company}|{title}|{url_hash}"
    profile_id = str(job.get("profile_id") or "").strip().lower()
    return f"{profile_id}|{base_uid}" if profile_id else base_uid


def upsert_scraped_job(
    conn: sqlite3.Connection,
    job: dict,
    *,
    check_links: bool = True,
) -> str:
    """Insert or ignore a scraped discovery row. Returns the job_uid.

    Deduplication strategy (layered):
    1. Primary: UID-based ON CONFLICT (company|title|hash(apply_url)).
    2. Secondary: when the same company+title arrives from a different URL
       (another API source), merge into the existing row to prevent duplicates.

    Set ``check_links=False`` to skip the inline network liveness check.
    This makes bulk scrapes faster and lets callers verify links
    asynchronously or on a schedule.
    """
    if "apply_window_score" not in job or "apply_window_label" not in job:
        from ranking.apply_window import annotate_apply_window
        job = annotate_apply_window(job)
    uid = make_job_uid(job)

    # Link liveness check: catch dead/broken apply URLs before they reach the
    # dashboard. Skipped for demo/placeholder rows (no real network target).
    is_demo = bool(job.get("is_demo") or job.get("source") == "sample_data")
    apply_url = job.get("apply_url") or job.get("raw_url") or ""
    if check_links and not is_demo and apply_url:
        try:
            from core.link_check import verify_job_link
            result = verify_job_link(apply_url)
            job["link_status"] = result.get("link_status", "")
            job["link_verified_at"] = result.get("checked_at", "")
        except Exception:
            job["link_status"] = "error"
            job["link_verified_at"] = ""
    else:
        job["link_status"] = job.get("link_status", "placeholder" if is_demo else "")
        job["link_verified_at"] = job.get("link_verified_at", "")

    # Secondary dedup: same company+title from a different URL → merge into existing row
    company = (job.get("company") or "").strip().lower()
    title = (job.get("title") or job.get("role") or "").strip().lower()
    profile_id = str(job.get("profile_id") or "").strip()
    if company and title:
        existing = conn.execute(
            "SELECT job_uid, apply_url, resume_match_score, source FROM jobs "
            "WHERE LOWER(TRIM(company)) = ? AND LOWER(TRIM(title)) = ? "
            "AND COALESCE(profile_id, '') = ?",
            (company, title, profile_id),
        ).fetchone()
        if existing:
            uid = existing["job_uid"]
            _update_existing_job(conn, uid, job)
            return uid

    families = job.get("target_role_families") or []
    if isinstance(families, str):
        families = [f.strip() for f in families.split(",") if f.strip()]
    keywords = job.get("matched_keywords") or []
    if isinstance(keywords, str):
        keywords = [k.strip() for k in keywords.split(",") if k.strip()]
    apply_window_reasons = job.get("apply_window_reasons") or []
    if isinstance(apply_window_reasons, str):
        apply_window_reasons = [r.strip() for r in apply_window_reasons.split(";") if r.strip()]

    if "apply_window_score" not in job or "apply_window_label" not in job:
        from ranking.apply_window import annotate_apply_window

        job = {**annotate_apply_window(job), **job}
        apply_window_reasons = job.get("apply_window_reasons") or []

    conn.execute(
        """
        INSERT INTO jobs (
            job_uid, company, title, location, apply_url, source, ats_type,
            resume_match_score, freshness, freshness_trust, action_tag,
            target_role_families, matched_keywords, why_matches, why_risky,
            opt_signal, best_matching_project, apply_window_score,
            apply_window_label, apply_window_reasons, apply_window_next_action,
            is_demo, link_status, link_verified_at, posted_date, freshness_source,
            status, date_discovered, date_updated, first_seen_at, last_seen_at,
            content_changed_at, listing_state, profile_id, visa_sponsorship
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'discovered', ?, ?, ?, ?, ?, 'active', ?, ?)
        ON CONFLICT(job_uid) DO UPDATE SET
            company = excluded.company,
            title = excluded.title,
            location = excluded.location,
            apply_url = excluded.apply_url,
            source = excluded.source,
            ats_type = excluded.ats_type,
            resume_match_score = excluded.resume_match_score,
            freshness = excluded.freshness,
            freshness_trust = excluded.freshness_trust,
            action_tag = CASE
                WHEN excluded.action_tag = 'apply_now' THEN 'apply_now'
                WHEN excluded.action_tag = 'watch' AND action_tag != 'apply_now' THEN 'watch'
                WHEN excluded.action_tag = 'known_match' AND action_tag = 'pool' THEN 'known_match'
                WHEN excluded.action_tag = 'pool' AND action_tag IN ('apply_now', 'watch', 'known_match', 'skip') THEN action_tag
                ELSE excluded.action_tag
            END,
            target_role_families = excluded.target_role_families,
            matched_keywords = excluded.matched_keywords,
            why_matches = excluded.why_matches,
            why_risky = excluded.why_risky,
            opt_signal = excluded.opt_signal,
            best_matching_project = excluded.best_matching_project,
            apply_window_score = excluded.apply_window_score,
            apply_window_label = excluded.apply_window_label,
            apply_window_reasons = excluded.apply_window_reasons,
            apply_window_next_action = excluded.apply_window_next_action,
            is_demo = excluded.is_demo,
            link_status = excluded.link_status,
            link_verified_at = excluded.link_verified_at,
            posted_date = COALESCE(NULLIF(excluded.posted_date, ''), posted_date),
            freshness_source = COALESCE(NULLIF(excluded.freshness_source, ''), freshness_source),
            date_updated = excluded.date_updated,
            last_seen_at = excluded.last_seen_at,
            profile_id = COALESCE(NULLIF(excluded.profile_id, ''), profile_id),
            visa_sponsorship = CASE
                WHEN excluded.visa_sponsorship IN (0, 1)
                THEN excluded.visa_sponsorship
                ELSE visa_sponsorship
            END,
            listing_state = 'active'
        """,
        (
            uid,
            job.get("company", ""),
            job.get("title") or job.get("role", ""),
            job.get("location", ""),
            job.get("apply_url") or job.get("raw_url", ""),
            job.get("source", ""),
            job.get("ats_type", ""),
            int(job.get("resume_match_score", 0) or 0),
            job.get("freshness", "Unknown"),
            job.get("freshness_trust", "unverified"),
            job.get("action_tag", "watch"),
            json.dumps(families),
            json.dumps(keywords),
            job.get("why_matches", ""),
            job.get("why_risky", ""),
            job.get("opt_signal", "Unknown"),
            job.get("best_matching_project", ""),
            int(job.get("apply_window_score", 0) or 0),
            job.get("apply_window_label", "medium"),
            json.dumps(apply_window_reasons),
            job.get("apply_window_next_action", "Review before applying"),
            1 if is_demo else 0,
            job.get("link_status", ""),
            job.get("link_verified_at", ""),
            job.get("posted_date", ""),
            job.get("freshness_source", ""),
            _today_iso(),
            _now_iso(),
            _now_iso(),
            _now_iso(),
            _now_iso(),
            job.get("profile_id", ""),
            int(job.get("visa_sponsorship", -1)),
        ),
    )
    conn.execute(
        """UPDATE jobs SET
               description = COALESCE(NULLIF(?, ''), description),
               work_mode = COALESCE(NULLIF(?, ''), work_mode),
               experience_level = COALESCE(NULLIF(?, ''), experience_level),
               employment_type = COALESCE(NULLIF(?, ''), employment_type),
               pool_match_reason = COALESCE(NULLIF(?, ''), pool_match_reason)
           WHERE job_uid = ?""",
        (
            job.get("description") or job.get("full_text", ""),
            job.get("work_mode", ""),
            job.get("experience_level", ""),
            job.get("employment_type", ""),
            job.get("pool_match_reason", ""),
            uid,
        ),
    )
    return uid


def dedupe_jobs(conn: sqlite3.Connection) -> int:
    """Collapse duplicate rows within the same profile and company/title.

    Keeps one canonical row per (company, title): the one with a verified
    (non-empty, non-placeholder) link status takes priority, then the most
    recently discovered. Returns the number of rows removed.

    Note: job_uid contains commas, so we must not split a concatenated
    uid string on commas. We resolve the real uids per group via a
    subquery instead of GROUP_CONCAT + split.
    """
    groups = conn.execute(
        """
        SELECT COALESCE(profile_id, '') AS profile_id, company, title
        FROM jobs
        GROUP BY COALESCE(profile_id, ''), company, title
        HAVING COUNT(*) > 1
        """
    ).fetchall()
    removed = 0
    for profile_id, company, title in groups:
        rows = conn.execute(
            "SELECT job_uid, link_status, date_discovered FROM jobs "
            "WHERE COALESCE(profile_id, '') = ? AND company = ? AND title = ?",
            (profile_id, company, title),
        ).fetchall()
        if len(rows) < 2:
            continue

        def _rank(r):
            ls = (r["link_status"] or "")
            verified = 0 if (ls in ("", "placeholder", "dead")) else 1
            return (verified, r["date_discovered"] or "")

        rows_sorted = sorted(rows, key=_rank, reverse=True)
        for r in rows_sorted[1:]:
            conn.execute("DELETE FROM jobs WHERE job_uid = ?", (r["job_uid"],))
            removed += 1
    conn.commit()
    return removed


def set_job_action_tag(
    conn: sqlite3.Connection,
    job_uid: str,
    action_tag: str,
) -> bool:
    """Move a job between dashboard buckets (watch/apply_now/skip/known_match)."""
    cur = conn.execute(
        "UPDATE jobs SET action_tag = ?, date_updated = ? WHERE job_uid = ?",
        (action_tag, _now_iso(), job_uid),
    )
    return cur.rowcount > 0


def set_job_status(
    conn: sqlite3.Connection,
    job_uid: str,
    status: str,
    *,
    note: str | None = None,
    status_date: str | None = None,
) -> bool:
    """Update a job's status. Returns True if the row existed."""
    today = status_date or _today_iso()
    date_applied = today if status in ("applied", "confirmed") else None
    sql = """
        UPDATE jobs SET
            status = ?,
            date_updated = ?,
            date_applied = COALESCE(?, date_applied)
    """
    params: list = [status, _now_iso(), date_applied]
    if note is not None:
        sql += ", note = ?"
        params.append(note)
    sql += " WHERE job_uid = ?"
    params.append(job_uid)
    cur = conn.execute(sql, params)
    return cur.rowcount > 0


def set_job_note(conn: sqlite3.Connection, job_uid: str, note: str) -> bool:
    cur = conn.execute(
        "UPDATE jobs SET note = ?, date_updated = ? WHERE job_uid = ?",
        (note, _now_iso(), job_uid),
    )
    return cur.rowcount > 0


def set_link_status(
    conn: sqlite3.Connection,
    job_uid: str,
    link_status: str,
    link_verified_at: str,
) -> bool:
    """Persist a link-verification result for a stored job."""
    cur = conn.execute(
        "UPDATE jobs SET link_status = ?, link_verified_at = ?, date_updated = ? "
        "WHERE job_uid = ?",
        (link_status, link_verified_at, _now_iso(), job_uid),
    )
    return cur.rowcount > 0


def get_job(conn: sqlite3.Connection, job_uid: str) -> dict | None:
    row = conn.execute("SELECT * FROM jobs WHERE job_uid = ?", (job_uid,)).fetchone()
    return _row_to_dict(row) if row else None


def list_jobs(
    conn: sqlite3.Connection,
    *,
    status: str | None = None,
    action_tag: str | None = None,
    profile_id: str | None = None,
    limit: int = 200,
) -> list[dict]:
    sql = "SELECT * FROM jobs WHERE 1=1"
    params: list = []
    if status:
        sql += " AND status = ?"
        params.append(status)
    if action_tag:
        sql += " AND action_tag = ?"
        params.append(action_tag)
    if profile_id is not None:
        sql += " AND COALESCE(profile_id, '') = ?"
        params.append(profile_id)
    sql += " ORDER BY resume_match_score DESC, date_discovered DESC LIMIT ?"
    params.append(limit)
    rows = conn.execute(sql, params).fetchall()
    return [_row_to_dict(r) for r in rows]


def get_dashboard_model(
    conn: sqlite3.Connection,
    *,
    include_demo: bool = False,
    profile_id: str | None = None,
) -> dict:
    """Return the full dashboard payload grouped by action/status.

    Demo/seed rows (is_demo=1) are excluded from the default view so they never
    masquerade as real scraped results. Pass include_demo=True to show them.
    """
    all_jobs = list_jobs(conn, profile_id=profile_id, limit=5000)
    deduped: dict[tuple[str, str, str], tuple[tuple, dict]] = {}
    active_statuses = {"applied", "confirmed", "interview", "assessment", "offer"}
    for job in all_jobs:
        if job.get("source") == "sample_data":
            job["is_demo"] = 1
        key = (
            str(job.get("profile_id") or "").strip().lower(),
            str(job.get("company") or "").strip().lower(),
            str(job.get("title") or "").strip().lower(),
        )
        status = str(job.get("status") or "discovered")
        quality = (
            2 if status in active_statuses else 1 if status in {"rejected", "closed"} else 0,
            2 if job.get("link_status") == "ok" else 1 if job.get("link_status") else 0,
            int(job.get("apply_window_score") or 0),
            int(job.get("resume_match_score") or 0),
            str(job.get("date_updated") or ""),
        )
        current = deduped.get(key)
        if current is None or quality > current[0]:
            deduped[key] = (quality, job)
    all_jobs = [entry[1] for entry in deduped.values()]
    if not include_demo:
        all_jobs = [j for j in all_jobs if not j.get("is_demo")]
    buckets: dict[str, list[dict]] = {
        "apply_now": [],
        "pool": [],
        "watch": [],
        "known_match": [],
        "skip": [],
        "active_pipeline": [],
        "closed": [],
    }
    real_counts = {key: 0 for key in buckets}
    for job in all_jobs:
        status = job.get("status", "discovered")
        if status in ("applied", "confirmed", "interview", "offer", "assessment"):
            bucket = "active_pipeline"
        elif status in ("rejected", "closed"):
            bucket = "closed"
        else:
            tag = job.get("action_tag", "watch")
            bucket = tag if tag in buckets else "watch"
        buckets[bucket].append(job)
        if not job.get("is_demo"):
            real_counts[bucket] += 1

    stats = {
        "total": sum(real_counts.values()),
        "apply_now": real_counts["apply_now"],
        "pool": real_counts["pool"],
        "watch": real_counts["watch"],
        "known_match": real_counts["known_match"],
        "active_pipeline": real_counts["active_pipeline"],
        "closed": real_counts["closed"],
    }
    return {"stats": stats, "buckets": buckets}


def _update_existing_job(conn: sqlite3.Connection, job_uid: str, incoming: dict) -> None:
    """Update an existing job row with newer data from a duplicate source.

    Preserves the original row's status (applied, rejected, etc.) while
    refreshing scoring and metadata. Prefers the row with a real URL.
    """
    incoming_url = incoming.get("apply_url") or incoming.get("raw_url") or ""
    incoming_score = int(incoming.get("resume_match_score", 0) or 0)
    why_risky = incoming.get("why_risky", "")
    action_tag = incoming.get("action_tag", "watch")
    if "apply_window_score" not in incoming or "apply_window_label" not in incoming:
        from ranking.apply_window import annotate_apply_window
        incoming = annotate_apply_window(incoming)
    reasons = incoming.get("apply_window_reasons") or []
    if isinstance(reasons, str):
        reasons = [r.strip() for r in reasons.split(";") if r.strip()]
    conn.execute(
        """UPDATE jobs SET
            apply_url = CASE WHEN apply_url IS NULL OR apply_url = '' THEN ? ELSE apply_url END,
            location = COALESCE(NULLIF(?, ''), location),
            resume_match_score = MAX(resume_match_score, ?),
            action_tag = CASE
                WHEN ? = 'apply_now' THEN 'apply_now'
                WHEN ? = 'watch' AND action_tag != 'apply_now' THEN 'watch'
                WHEN ? = 'known_match' AND action_tag = 'pool' THEN 'known_match'
                WHEN ? = 'pool' AND action_tag IN ('apply_now', 'watch', 'known_match', 'skip') THEN action_tag
                ELSE ?
            END,
            source = COALESCE(NULLIF(?, ''), source),
            why_risky = CASE WHEN instr(why_risky, ?) = 0 THEN trim(? || ' ' || coalesce(why_risky, '')) ELSE why_risky END,
            description = COALESCE(NULLIF(?, ''), description),
            work_mode = COALESCE(NULLIF(?, ''), work_mode),
            experience_level = COALESCE(NULLIF(?, ''), experience_level),
            employment_type = COALESCE(NULLIF(?, ''), employment_type),
            pool_match_reason = COALESCE(NULLIF(?, ''), pool_match_reason),
            profile_id = COALESCE(NULLIF(?, ''), profile_id),
            visa_sponsorship = CASE WHEN ? IN (0, 1) THEN ? ELSE visa_sponsorship END,
            apply_window_score = MAX(apply_window_score, ?),
            apply_window_label = CASE WHEN ? > apply_window_score THEN ? ELSE apply_window_label END,
            apply_window_reasons = CASE WHEN ? > apply_window_score THEN ? ELSE apply_window_reasons END,
            apply_window_next_action = CASE WHEN ? > apply_window_score THEN ? ELSE apply_window_next_action END,
            date_updated = ?,
            last_seen_at = ?,
            listing_state = 'active'
        WHERE job_uid = ?""",
        (incoming_url, incoming.get("location", ""), incoming_score,
         action_tag, action_tag, action_tag, action_tag, action_tag,
         incoming.get("source", ""), why_risky, why_risky,
         incoming.get("description") or incoming.get("full_text", ""),
         incoming.get("work_mode", ""), incoming.get("experience_level", ""),
         incoming.get("employment_type", ""), incoming.get("pool_match_reason", ""),
         incoming.get("profile_id", ""),
         int(incoming.get("visa_sponsorship", -1)),
         int(incoming.get("visa_sponsorship", -1)),
         int(incoming.get("apply_window_score", 0) or 0),
         int(incoming.get("apply_window_score", 0) or 0), incoming.get("apply_window_label", "medium"),
         int(incoming.get("apply_window_score", 0) or 0), json.dumps(reasons),
         int(incoming.get("apply_window_score", 0) or 0), incoming.get("apply_window_next_action", "Review before applying"),
         _now_iso(), _now_iso(), job_uid),
    )


def _row_to_dict(row: sqlite3.Row) -> dict:
    d = dict(row)
    for key in ("target_role_families", "matched_keywords", "apply_window_reasons"):
        val = d.get(key, "[]")
        if isinstance(val, str):
            try:
                d[key] = json.loads(val)
            except (json.JSONError, ValueError):
                d[key] = []
    return d


def enqueue_enrichment(conn: sqlite3.Connection, job_uids: list[str], priority: int = 0) -> int:
    """Mark jobs for async description enrichment. Returns count enqueued."""
    if not job_uids:
        return 0
    count = 0
    for uid in job_uids:
        try:
            conn.execute(
                """INSERT OR IGNORE INTO enrichment_queue (job_uid, priority)
                   VALUES (?, ?)""",
                (uid, priority),
            )
            if conn.total_changes:
                count += 1
        except Exception:
            pass
    return count


def get_enrichment_backlog(conn: sqlite3.Connection, limit: int = 200) -> list[dict]:
    """Return jobs awaiting enrichment, ordered by priority then age."""
    rows = conn.execute(
        """SELECT eq.job_uid, eq.priority, eq.attempts, eq.last_error, eq.updated_at,
                  j.company, j.title, j.apply_url
           FROM enrichment_queue eq
           JOIN jobs j ON j.job_uid = eq.job_uid
           ORDER BY eq.priority DESC, eq.updated_at ASC
           LIMIT ?""",
        (limit,),
    ).fetchall()
    return [dict(r) for r in rows]


def mark_enriched(conn: sqlite3.Connection, job_uid: str) -> None:
    """Remove a job from the enrichment queue after successful backfill."""
    conn.execute("DELETE FROM enrichment_queue WHERE job_uid = ?", (job_uid,))


def bump_enrichment_failure(conn: sqlite3.Connection, job_uid: str, error: str) -> None:
    """Increment attempt count and record error for a failed enrichment."""
    conn.execute(
        """UPDATE enrichment_queue
           SET attempts = attempts + 1, last_error = ?, updated_at = ?
           WHERE job_uid = ?""",
        (error[:500], _now_iso(), job_uid),
    )


# ── Profile CRUD ──

def create_profile(
    name: str,
    resume_text: str,
    extracted_json: str,
    db_path: Path | None = None,
) -> str:
    """Insert a new profile, set it active, and return its profile_id.

    Any previously active profile is deactivated first so there is always at
    most one active profile at a time. Onboarding calls this only after the user
    approves the final search plan.
    """
    import uuid as _uuid
    profile_id = _uuid.uuid4().hex
    now = _now_iso()
    with connect(db_path) as conn:
        # Deactivate all existing profiles.
        conn.execute("UPDATE profiles SET is_active = 0")
        conn.execute(
            """
            INSERT INTO profiles (profile_id, name, resume_text, extracted_json,
                                  is_active, created_at, last_used_at)
            VALUES (?, ?, ?, ?, 1, ?, ?)
            """,
            (profile_id, name or "", resume_text or "", extracted_json or "{}", now, now),
        )
    # Invalidate the candidate cache so get_profile_config() picks up the
    # new profile immediately without a process restart.
    try:
        from resume.resume_profile import invalidate_candidate_cache  # noqa: PLC0415
        invalidate_candidate_cache()
    except Exception:
        pass
    return profile_id


def get_active_profile(db_path: Path | None = None) -> dict | None:
    """Return the currently active profile row, or None if none exists."""
    path = str(db_path if db_path is not None else get_db_path())
    try:
        conn = sqlite3.connect(path, timeout=5)
        conn.row_factory = sqlite3.Row
        try:
            row = conn.execute(
                "SELECT * FROM profiles WHERE is_active = 1 ORDER BY last_used_at DESC LIMIT 1"
            ).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()
    except Exception:
        return None


def set_active_profile(profile_id: str, db_path: Path | None = None) -> bool:
    """Switch the active profile. Returns True if the profile was found."""
    with connect(db_path) as conn:
        conn.execute("UPDATE profiles SET is_active = 0")
        cur = conn.execute(
            "UPDATE profiles SET is_active = 1, last_used_at = ? WHERE profile_id = ?",
            (_now_iso(), profile_id),
        )
        found = cur.rowcount > 0
    if found:
        try:
            from resume.resume_profile import invalidate_candidate_cache  # noqa: PLC0415
            invalidate_candidate_cache()
        except Exception:
            pass
    return found


def list_profiles(db_path: Path | None = None) -> list[dict]:
    """Return all profiles ordered by creation date descending."""
    path = str(db_path if db_path is not None else get_db_path())
    try:
        conn = sqlite3.connect(path, timeout=5)
        conn.row_factory = sqlite3.Row
        try:
            rows = conn.execute(
                "SELECT profile_id, name, is_active, created_at, last_used_at "
                "FROM profiles ORDER BY created_at DESC"
            ).fetchall()
            # Never leak full resume_text in list view.
            return [dict(r) for r in rows]
        finally:
            conn.close()
    except Exception:
        return []


def save_extraction(profile_id: str, extracted_json: str, db_path: Path | None = None) -> None:
    """Update the extracted_json blob for an existing profile."""
    with connect(db_path) as conn:
        conn.execute(
            "UPDATE profiles SET extracted_json = ?, last_used_at = ? WHERE profile_id = ?",
            (extracted_json or "{}", _now_iso(), profile_id),
        )


def stats_for_profile(
    conn: sqlite3.Connection,
    profile_id: str,
) -> dict:
    """Return aggregate stats for one profile's jobs.

    Used by /api/dashboard to show counts that survive terminal restarts
    (because dashboard.db is a file on disk).
    """
    active_statuses = "'applied','confirmed','interview','assessment','offer'"
    row = conn.execute(
        f"""
        SELECT
            COUNT(*) AS total,
            SUM(CASE WHEN status IN ({active_statuses}) THEN 1 ELSE 0 END) AS in_pipeline,
            SUM(CASE WHEN status IN ('applied','confirmed') THEN 1 ELSE 0 END) AS applied
        FROM jobs
        WHERE profile_id = ? AND is_demo = 0
        """,
        (profile_id,),
    ).fetchone()
    run_row = conn.execute(
        "SELECT MAX(finished_at) AS last_scrape FROM scrape_runs WHERE status = 'completed'"
    ).fetchone()
    return {
        "total": int(row["total"] or 0),
        "in_pipeline": int(row["in_pipeline"] or 0),
        "applied": int(row["applied"] or 0),
        "last_scrape": (run_row["last_scrape"] or "") if run_row else "",
    }


def filter_jobs(
    conn: sqlite3.Connection,
    profile_id: str | None = None,
    *,
    within_hours: int | None = None,
    work_mode: str | None = None,
    experience: str | None = None,
    visa: bool | None = None,
    location: str | None = None,
    source: str | None = None,
    role_family: str | None = None,
    match_band: str | None = None,
    limit: int = 300,
) -> list[dict]:
    """Return jobs filtered by profile and one or more optional criteria.

    All filters are AND-combined.  ``visa=True`` means only jobs that offer
    sponsorship (``visa_sponsorship=1``); ``visa=False`` means no-sponsorship
    only.  Pass ``visa=None`` to skip the filter.
    """
    sql = "SELECT * FROM jobs WHERE is_demo = 0"
    params: list = []

    if profile_id is not None:
        sql += " AND profile_id = ?"
        params.append(profile_id)

    if within_hours is not None:
        from datetime import timedelta
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=within_hours)).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )
        sql += " AND date_discovered >= ?"
        params.append(cutoff)

    if work_mode is not None:
        sql += " AND LOWER(work_mode) = LOWER(?)"
        params.append(work_mode)

    if experience is not None:
        sql += " AND LOWER(experience_level) = LOWER(?)"
        params.append(experience)

    if visa is True:
        sql += " AND visa_sponsorship = 1"
    elif visa is False:
        sql += " AND visa_sponsorship = 0"

    if location is not None:
        sql += " AND LOWER(location) LIKE LOWER(?)"
        params.append(f"%{location}%")

    if source is not None:
        sql += " AND LOWER(source) = LOWER(?)"
        params.append(source)

    if role_family is not None:
        sql += " AND LOWER(target_role_families) LIKE LOWER(?)"
        params.append(f"%{role_family}%")

    if match_band is not None:
        sql += " AND LOWER(apply_window_label) = LOWER(?)"
        params.append(match_band)

    sql += " ORDER BY resume_match_score DESC, date_discovered DESC LIMIT ?"
    params.append(limit)
    rows = conn.execute(sql, params).fetchall()
    return [_row_to_dict(r) for r in rows]
