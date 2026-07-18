"""Safe relocation, reset, full-wipe, and migration contracts."""
from __future__ import annotations

import sqlite3
from pathlib import Path
from unittest.mock import patch

import pytest

import config as cfg
from dashboard.db import connect, create_profile, init_db, set_db_path
from dashboard.migrations import (
    Migration,
    migrate_database,
    migrate_legacy_source_checkout_to_platform_data,
)
from public_ops import delete_backups, full_wipe, reset_jobs


@pytest.fixture(autouse=True)
def _reset_database_override():
    yield
    set_db_path(None)


def _sqlite(path: Path, value: str = "kept") -> None:
    connection = sqlite3.connect(path)
    connection.execute("CREATE TABLE evidence (value TEXT)")
    connection.execute("INSERT INTO evidence VALUES (?)", (value,))
    connection.commit()
    connection.close()


def test_legacy_relocation_supports_dry_run_verified_copy_and_no_overwrite(tmp_path):
    legacy = tmp_path / "legacy.db"
    destination = tmp_path / "platform" / "dashboard.db"
    _sqlite(legacy)

    dry = migrate_legacy_source_checkout_to_platform_data(
        legacy_db_path=legacy,
        platform_db_path=destination,
        dry_run=True,
    )
    assert dry["ok"] is True
    assert dry["bytes_to_copy"] > 0
    assert not destination.exists()

    moved = migrate_legacy_source_checkout_to_platform_data(
        legacy_db_path=legacy,
        platform_db_path=destination,
    )
    assert moved["ok"] is True
    assert moved["checksum_verified"] is True
    assert Path(moved["backup_path"]).exists()
    with sqlite3.connect(destination) as connection:
        assert connection.execute("SELECT value FROM evidence").fetchone()[0] == "kept"

    refused = migrate_legacy_source_checkout_to_platform_data(
        legacy_db_path=legacy,
        platform_db_path=destination,
    )
    assert refused["ok"] is False
    assert "refusing to overwrite" in refused["error"]
    with sqlite3.connect(destination) as connection:
        assert connection.execute("SELECT value FROM evidence").fetchone()[0] == "kept"


def test_reset_jobs_clears_all_discovery_state_but_preserves_profile(tmp_path):
    db = tmp_path / "dashboard.db"
    set_db_path(db)
    init_db()
    profile_id = create_profile("Candidate", "private", "{}", db_path=db)
    with connect() as connection:
        connection.execute("INSERT INTO jobs (job_uid, company, title) VALUES ('j1', 'A', 'AI Engineer')")
        connection.execute(
            "INSERT INTO job_catalog (catalog_uid, source_scope, source, company, title, "
            "content_hash, first_seen_at, last_seen_at, content_changed_at, last_seen_run_id) "
            "VALUES ('c1', 'scope', 'greenhouse', 'A', 'AI Engineer', 'hash', 't', 't', 't', 'run')"
        )
        connection.execute(
            "INSERT INTO scrape_runs (run_id, started_at) VALUES ('run', '2026-07-18T00:00:00Z')"
        )
        connection.execute(
            "INSERT INTO discovery_funnel (run_id, stage, count) VALUES ('run', 'raw', 1)"
        )

    result = reset_jobs("RESET_JOBS")

    assert result["backup_created"] is True
    assert Path(result["backup_path"]).exists()
    with connect() as connection:
        for table in ("jobs", "job_catalog", "scrape_runs", "discovery_funnel"):
            assert connection.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0] == 0
        assert connection.execute(
            "SELECT COUNT(*) FROM profiles WHERE profile_id = ?", (profile_id,)
        ).fetchone()[0] == 1
        assert connection.execute("SELECT COUNT(*) FROM profile_versions").fetchone()[0] == 1


def test_full_wipe_removes_private_state_but_preserves_mandatory_backup_and_defaults(
    tmp_path, monkeypatch
):
    data = tmp_path / "data"
    config_dir = tmp_path / "config"
    cache = tmp_path / "cache"
    config_path = config_dir / "config.yaml"
    for directory in (data, config_dir, cache, data / "logs", data / "exports"):
        directory.mkdir(parents=True, exist_ok=True)
    config_path.write_text("profile: {}\n", encoding="utf-8")
    (data / "pilot_metrics.db").write_text("private", encoding="utf-8")
    (data / "source_health.json").write_text("{}", encoding="utf-8")
    (cache / "private.cache").write_text("private", encoding="utf-8")
    (data / "exports" / "private.json").write_text("private", encoding="utf-8")
    default = tmp_path / "config.example.yaml"
    default.write_text("profile: {}\n", encoding="utf-8")

    monkeypatch.setattr(cfg, "CONFIG_PATH", config_path)
    monkeypatch.setattr(cfg, "JOB_AGENT_HOME", data)
    monkeypatch.setattr(cfg, "CACHE_DIR", cache)
    monkeypatch.setattr(cfg, "LOG_DIR", data / "logs")
    monkeypatch.setattr(cfg, "EXPORT_DIR", data / "exports")
    db = data / "dashboard.db"
    set_db_path(db)
    init_db()
    create_profile("Candidate", "private resume", "{}", db_path=db)
    with connect() as connection:
        connection.execute("INSERT INTO jobs (job_uid, company, title) VALUES ('j1', 'A', 'AI Engineer')")
        connection.execute(
            "INSERT INTO onboarding_sessions (session_id, status, created_at, updated_at) "
            "VALUES ('s1', 'review', 't', 't')"
        )

    with pytest.raises(ValueError, match="FULL_WIPE_CONFIRMED"):
        full_wipe("FULL_WIPE")
    result = full_wipe("FULL_WIPE_CONFIRMED")

    assert result["backup_created"] is True
    assert Path(result["backup_path"]).exists()
    assert not config_path.exists()
    assert default.exists()
    assert not cache.exists()
    assert not (data / "exports").exists()
    assert not (data / "pilot_metrics.db").exists()
    with connect() as connection:
        for table in ("jobs", "profiles", "profile_versions", "onboarding_sessions"):
            assert connection.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0] == 0


def test_full_wipe_stops_before_deletion_when_backup_fails(tmp_path, monkeypatch):
    config_path = tmp_path / "config.yaml"
    config_path.write_text("profile: {}\n", encoding="utf-8")
    monkeypatch.setattr(cfg, "CONFIG_PATH", config_path)
    db = tmp_path / "dashboard.db"
    set_db_path(db)
    init_db()
    profile_id = create_profile("Candidate", "private resume", "{}", db_path=db)

    with patch("public_ops.backup_local_state", side_effect=PermissionError("denied")):
        with pytest.raises(PermissionError, match="denied"):
            full_wipe("FULL_WIPE_CONFIRMED")

    assert config_path.exists()
    with connect() as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM profiles WHERE profile_id = ?", (profile_id,)
        ).fetchone()[0] == 1


def test_backup_deletion_is_a_separate_exactly_confirmed_operation(tmp_path, monkeypatch):
    backup_dir = tmp_path / "backups"
    backup_dir.mkdir()
    (backup_dir / "one.db").write_bytes(b"one")
    (backup_dir / "two.zip").write_bytes(b"two")
    monkeypatch.setattr(cfg, "BACKUP_DIR", backup_dir)

    with pytest.raises(ValueError, match="DELETE BACKUPS"):
        delete_backups("FULL WIPE")
    assert len(list(backup_dir.iterdir())) == 2

    result = delete_backups("DELETE BACKUPS")
    assert result == {"ok": True, "deleted": 2, "backup_dir": str(backup_dir)}
    assert list(backup_dir.iterdir()) == []


def test_ordered_migration_is_idempotent_and_rolls_back_failure(tmp_path):
    db = tmp_path / "migration.db"
    _sqlite(db, "original")
    migrations = (
        Migration(1, "add column", lambda c: c.execute("ALTER TABLE evidence ADD COLUMN extra TEXT DEFAULT 'ok'")),
        Migration(2, "add index", lambda c: c.execute("CREATE INDEX idx_evidence_extra ON evidence(extra)")),
    )
    first = migrate_database(db, migrations, backup_dir=tmp_path / "backups")
    second = migrate_database(db, migrations, backup_dir=tmp_path / "backups")
    assert first["applied"] == [1, 2]
    assert second["applied"] == []

    failing_db = tmp_path / "failing.db"
    _sqlite(failing_db, "original")

    def fail(connection):
        connection.execute("UPDATE evidence SET value = 'changed'")
        raise RuntimeError("migration failed")

    with pytest.raises(RuntimeError, match="migration failed"):
        migrate_database(
            failing_db,
            (Migration(1, "fail", fail),),
            backup_dir=tmp_path / "backups",
        )
    with sqlite3.connect(failing_db) as connection:
        assert connection.execute("SELECT value FROM evidence").fetchone()[0] == "original"
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 0
