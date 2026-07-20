"""Public-v1 local operations: config, onboarding, demo data, privacy tools.

All functions are local-only. They read/write config.yaml and the configured
SQLite database. No network calls and no external services.
"""
from __future__ import annotations

import json
import shutil
import sqlite3
import stat
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

import config as cfg
from dashboard.db import connect, get_dashboard_model, get_db_path, init_db, upsert_scraped_job



def load_config() -> dict[str, Any]:
    path = cfg.CONFIG_PATH if cfg.CONFIG_PATH.exists() else cfg.CONFIG_EXAMPLE_PATH
    if not path.exists():
        return {}
    return yaml.safe_load(path.read_text()) or {}


def save_config(data: dict[str, Any]) -> dict[str, Any]:
    _validate_config(data)
    cfg.CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = cfg.CONFIG_PATH.with_suffix(".yaml.tmp")
    tmp_path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    tmp_path.chmod(0o600)
    tmp_path.replace(cfg.CONFIG_PATH)
    cfg._CONFIG_CACHE_KEY = None
    cfg._CONFIG_CACHE_VALUE = None

    # Ranking preferences are cached for a scrape, but Settings changes must
    # take effect on the next run without restarting the dashboard.
    from resume import resume_profile

    resume_profile._candidate_preferences = None
    return {"ok": True, "path": str(cfg.CONFIG_PATH), "config": data}


def _validate_string_list(value: Any, field: str) -> None:
    if value is not None and (
        not isinstance(value, list)
        or any(not isinstance(item, str) or not item.strip() for item in value)
    ):
        raise ValueError(f"{field} must be a list of non-empty strings")


def _validate_config(data: dict[str, Any]) -> None:
    if not isinstance(data, dict):
        raise ValueError("config must be an object")
    profile = data.get("profile") or {}
    if not isinstance(profile, dict):
        raise ValueError("profile must be an object")
    for key in ("target_roles", "target_levels", "locations"):
        _validate_string_list(profile.get(key), f"profile.{key}")

    visa_policy = profile.get("visa_policy", "none")
    if visa_policy not in {"none", "needs_sponsorship", "opt_cpt", "custom"}:
        raise ValueError("profile.visa_policy is invalid")
    timeline = profile.get("timeline") or {}
    if not isinstance(timeline, dict):
        raise ValueError("profile.timeline must be an object")
    max_age = timeline.get("max_age_days", 7)
    if isinstance(max_age, bool) or not isinstance(max_age, int) or not 1 <= max_age <= 30:
        raise ValueError("profile.timeline.max_age_days must be an integer from 1 to 30")

    sources = data.get("sources") or []
    if not isinstance(sources, list) or any(not isinstance(source, dict) for source in sources):
        raise ValueError("sources must be a list of objects")
    names = [str(source.get("name") or "").strip() for source in sources]
    if any(not name for name in names) or len(names) != len(set(names)):
        raise ValueError("every source needs a unique non-empty name")
    for source in sources:
        if not isinstance(source.get("enabled", False), bool):
            raise ValueError("source enabled values must be boolean")
        if source.get("mode", "free") not in {"free", "paid"}:
            raise ValueError("source mode must be free or paid")


SAMPLE_JOBS = [
    {
        "company": "Acme AI",
        "title": "Entry-Level RAG Engineer",
        "location": "Remote US",
        "apply_url": "https://example.com/jobs/rag-engineer",
        "source": "sample_data",
        "ats_type": "demo",
        "resume_match_score": 88,
        "freshness": "New (0-24h)",
        "freshness_trust": "sample",
        "action_tag": "apply_now",
        "target_role_families": ["genai_llm_rag", "backend_ai_systems"],
        "matched_keywords": ["python", "fastapi", "rag pipelines", "embeddings"],
        "why_matches": "Sample role with strong overlap for an early-career AI/backend profile.",
        "why_risky": "Sample data only — replace with live scrape results.",
        "opt_signal": "Unknown",
        "best_matching_project": "AI Retrieval Inspector",
    },
    {
        "company": "VectorWorks",
        "title": "Junior AI Agents Engineer",
        "location": "New York, NY",
        "apply_url": "https://example.com/jobs/agents-engineer",
        "source": "sample_data",
        "ats_type": "demo",
        "resume_match_score": 81,
        "freshness": "This Week (3-7d)",
        "freshness_trust": "sample",
        "action_tag": "watch",
        "target_role_families": ["ai_agents", "applied_ai"],
        "matched_keywords": ["agentic ai", "function calling", "testing"],
        "why_matches": "Sample agent workflow role for users evaluating the dashboard.",
        "why_risky": "Check experience and location requirements before applying.",
        "opt_signal": "Unknown",
        "best_matching_project": "Multi-Agent Support Assistant",
    },
    {
        "company": "LocalStack Labs",
        "title": "Backend AI Systems Engineer I",
        "location": "Austin, TX",
        "apply_url": "https://example.com/jobs/backend-ai-systems",
        "source": "sample_data",
        "ats_type": "demo",
        "resume_match_score": 74,
        "freshness": "Recent (24-48h)",
        "freshness_trust": "sample",
        "action_tag": "known_match",
        "target_role_families": ["backend_ai_systems"],
        "matched_keywords": ["python", "sqlite", "api design", "observability"],
        "why_matches": "Sample backend-heavy AI systems role.",
        "why_risky": "Sample data only.",
        "opt_signal": "Unknown",
        "best_matching_project": "Local-first Opportune",
    },
]


def seed_demo_data(clear_first: bool = False) -> dict[str, Any]:
    init_db()
    with connect() as conn:
        if clear_first:
            if conn.execute("SELECT 1 FROM jobs LIMIT 1").fetchone():
                backup_local_state()
            conn.execute("DELETE FROM jobs")
        for job in SAMPLE_JOBS:
            upsert_scraped_job(conn, job, check_links=False)
        model = get_dashboard_model(conn, include_demo=True)
    return {"ok": True, "inserted": len(SAMPLE_JOBS), "dashboard": model}


def _delete_existing_tables(conn: sqlite3.Connection, table_names: tuple[str, ...]) -> None:
    existing = {
        row["name"]
        for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
    }
    for table_name in table_names:
        if table_name in existing:
            conn.execute(f'DELETE FROM "{table_name}"')


def _clear_job_state(conn: sqlite3.Connection) -> None:
    _delete_existing_tables(
        conn,
        (
            "discovery_funnel",
            "scrape_runs",
            "enrichment_queue",
            "seen_jobs",
            "jobs",
            "job_catalog",
        ),
    )


def wipe_local_data(confirm: str) -> dict[str, Any]:
    if confirm != "WIPE":
        raise ValueError("confirm must be WIPE")
    backup_path = backup_local_state()
    init_db()
    with connect() as conn:
        _clear_job_state(conn)

    return {
        "ok": True,
        "message": "local job data wiped; config and search profile kept",
        "backup_path": str(backup_path),
    }


def delete_backups(confirm: str) -> dict[str, Any]:
    """Delete retained backups only after a separate exact confirmation."""
    if confirm != "DELETE BACKUPS":
        raise ValueError("backup deletion requires exact confirmation: DELETE BACKUPS")
    backup_dir = Path(cfg.BACKUP_DIR)
    deleted = 0
    if backup_dir.exists():
        for child in backup_dir.iterdir():
            if child.is_symlink() or child.is_file():
                child.unlink()
            elif child.is_dir():
                shutil.rmtree(child)
            deleted += 1
    return {"ok": True, "deleted": deleted, "backup_dir": str(backup_dir)}

def export_data() -> Path:
    out_dir = cfg.EXPORT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    path = out_dir / f"opportune-export-{stamp}.json"
    init_db()
    with connect() as conn:
        rows = [dict(r) for r in conn.execute("SELECT * FROM jobs ORDER BY date_updated DESC, id DESC").fetchall()]
    path.write_text(json.dumps({"jobs": rows}, indent=2), encoding="utf-8")
    return path


def restore_local_state(archive_path: Path, *, confirm: str) -> dict[str, Any]:
    """Validate and atomically restore the SQLite snapshot from a local backup."""
    if confirm != "RESTORE":
        raise ValueError("confirm must be RESTORE")
    archive_path = Path(archive_path).expanduser().resolve()
    if not archive_path.is_file():
        raise ValueError("backup archive not found")

    primary_db = get_db_path().resolve()
    primary_db.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="opportune-restore-", dir=primary_db.parent) as tmp:
        candidate = Path(tmp) / primary_db.name
        with zipfile.ZipFile(archive_path) as archive:
            if archive.testzip() is not None:
                raise ValueError("backup archive is corrupt")
            db_members = []
            restorable_members: dict[str, bytes] = {}
            total_size = 0
            for info in archive.infolist():
                member = Path(info.filename)
                mode = info.external_attr >> 16
                if member.is_absolute() or ".." in member.parts or stat.S_ISLNK(mode):
                    raise ValueError("backup archive contains an unsafe member")
                total_size += int(info.file_size)
                if total_size > 2 * 1024 * 1024 * 1024:
                    raise ValueError("backup archive is too large")
                if len(member.parts) == 2 and member.parts[0] == "tracker" and member.suffix == ".db":
                    db_members.append(info)
                if member == Path("config.yaml") or (
                    member.parts and member.parts[0] == "onboarding"
                ):
                    restorable_members[info.filename] = archive.read(info)
            if len(db_members) != 1:
                raise ValueError("backup archive must contain exactly one tracker database")
            candidate.write_bytes(archive.read(db_members[0]))

        connection = sqlite3.connect(f"file:{candidate}?mode=ro", uri=True, timeout=10)
        try:
            integrity = connection.execute("PRAGMA integrity_check").fetchone()
            if not integrity or integrity[0] != "ok":
                raise ValueError("backup database failed integrity check")
        finally:
            connection.close()

        pre_restore_backup = backup_local_state()
        candidate.replace(primary_db)
        primary_db.with_name(primary_db.name + "-wal").unlink(missing_ok=True)
        primary_db.with_name(primary_db.name + "-shm").unlink(missing_ok=True)

        for member_name, contents in restorable_members.items():
            member = Path(member_name)
            target = (
                cfg.CONFIG_PATH
                if member == Path("config.yaml")
                else cfg.JOB_AGENT_HOME / member
            )
            target.parent.mkdir(parents=True, exist_ok=True)
            temporary = target.with_name(target.name + ".restore")
            temporary.write_bytes(contents)
            temporary.chmod(0o600)
            temporary.replace(target)
    return {
        "ok": True,
        "restored_path": str(primary_db),
        "pre_restore_backup_path": str(pre_restore_backup),
    }


def backup_local_state() -> Path:
    primary_db = get_db_path().resolve()
    tracker_dir = primary_db.parent
    backup_dir = tracker_dir / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-%f")
    path = backup_dir / f"opportune-backup-{stamp}.zip"
    db_paths = {primary_db}

    with tempfile.TemporaryDirectory(prefix="opportune-backup-") as tmp:
        snapshot_dir = Path(tmp)
        with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
            for index, db_path in enumerate(sorted(db_paths)):
                if not db_path.exists():
                    continue
                snapshot = snapshot_dir / f"{index}-{db_path.name}"
                source = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=10)
                target = sqlite3.connect(snapshot)
                try:
                    source.backup(target)
                    integrity = target.execute("PRAGMA integrity_check").fetchone()
                    if not integrity or integrity[0] != "ok":
                        raise RuntimeError("backup database failed integrity check")
                finally:
                    target.close()
                    source.close()
                z.write(snapshot, f"tracker/{db_path.name}")

            if cfg.CONFIG_PATH.exists():
                z.write(cfg.CONFIG_PATH, "config.yaml")

            onboarding_dir = cfg.JOB_AGENT_HOME / "onboarding"
            if onboarding_dir.exists():
                for private_path in sorted(onboarding_dir.rglob("*")):
                    if private_path.is_symlink():
                        raise RuntimeError("provider state contains an unsafe symlink")
                    if private_path.is_file():
                        relative = private_path.relative_to(onboarding_dir)
                        z.write(private_path, Path("onboarding") / relative)
    with zipfile.ZipFile(path) as z:
        bad_member = z.testzip()
        if bad_member:
            path.unlink(missing_ok=True)
            raise RuntimeError(f"backup verification failed for {bad_member}")
    path.chmod(0o600)
    return path


# --- Lifecycle primitives for CLI/API wiring ---

def reset_jobs(confirm: str) -> dict[str, Any]:
    """Reset job data only: wipe jobs, enrichment_queue, seen_jobs.

    Preserves: profiles, onboarding data, config.yaml, source checkout defaults.
    Requires exact confirmation string "RESET_JOBS".
    Creates a backup by default before wiping.
    """
    if confirm != "RESET_JOBS":
        raise ValueError("confirm must be RESET_JOBS")

    backup_path = backup_local_state()
    init_db()

    with connect() as conn:
        _clear_job_state(conn)

    return {
        "ok": True,
        "message": "job data wiped; profiles, onboarding, and config preserved",
        "backup_path": str(backup_path),
        "profiles_preserved": True,
        "config_preserved": True,
        "backup_created": True,
    }


def full_wipe(confirm: str) -> dict[str, Any]:
    """Full wipe: destroy ALL local state including profiles, onboarding, config.yaml.

    Requires exact confirmation "FULL_WIPE_CONFIRMED".
    MANDATORY backup created before any deletion (cannot be disabled).
    Preserves source checkout defaults (config.example.yaml) only.
    """
    if confirm != "FULL_WIPE_CONFIRMED":
        raise ValueError("confirm must be FULL_WIPE_CONFIRMED")

    # Mandatory backup before any destruction
    backup_path = backup_local_state()
    init_db()

    with connect() as conn:
        _clear_job_state(conn)
        _delete_existing_tables(
            conn,
            ("onboarding_sessions", "profile_versions", "profiles"),
        )

    config_wiped = False
    if cfg.CONFIG_PATH.exists():
        cfg.CONFIG_PATH.unlink()
        config_wiped = True

    for private_file in (
        cfg.JOB_AGENT_HOME / "pilot_metrics.db",
        cfg.JOB_AGENT_HOME / "source_health.json",
        cfg.JOB_AGENT_HOME / "source-quality.json",
        cfg.JOB_AGENT_HOME / "scheduler-state.json",
        cfg.JOB_AGENT_HOME / "scheduler.lock",
    ):
        private_file.unlink(missing_ok=True)
    for private_dir in (cfg.JOB_AGENT_HOME / "onboarding", cfg.CACHE_DIR, cfg.LOG_DIR, cfg.EXPORT_DIR):
        if private_dir.exists():
            shutil.rmtree(private_dir)

    cfg._CONFIG_CACHE_KEY = None
    cfg._CONFIG_CACHE_VALUE = None

    return {
        "ok": True,
        "message": "full wipe complete; all local state destroyed; source checkout defaults preserved",
        "backup_path": str(backup_path),
        "backup_created": True,
        "jobs_wiped": True,
        "profiles_wiped": True,
        "config_wiped": config_wiped,
    }
