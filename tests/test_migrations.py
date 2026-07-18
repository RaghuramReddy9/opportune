"""Ordered SQLite migration runner contracts."""
from __future__ import annotations

import sqlite3

import pytest


def _create_legacy(path):
    connection = sqlite3.connect(path)
    connection.execute("CREATE TABLE records (id INTEGER PRIMARY KEY, value TEXT)")
    connection.execute("INSERT INTO records(value) VALUES ('kept')")
    connection.commit()
    connection.close()


def test_migrations_run_in_order_and_are_idempotent(tmp_path):
    from dashboard.migrations import Migration, migrate_database

    db_path = tmp_path / "dashboard.db"
    _create_legacy(db_path)
    migrations = (
        Migration(1, "add status", lambda conn: conn.execute("ALTER TABLE records ADD COLUMN status TEXT DEFAULT 'new'")),
        Migration(2, "add index", lambda conn: conn.execute("CREATE INDEX idx_records_status ON records(status)")),
    )

    first = migrate_database(db_path, migrations, backup_dir=tmp_path / "backups")
    second = migrate_database(db_path, migrations, backup_dir=tmp_path / "backups")

    assert first["from_version"] == 0
    assert first["to_version"] == 2
    assert first["applied"] == [1, 2]
    assert first["backup_path"]
    assert second["applied"] == []
    assert second["backup_path"] == ""
    with sqlite3.connect(db_path) as conn:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 2
        assert conn.execute("SELECT value, status FROM records").fetchone() == ("kept", "new")


def test_failed_migration_rolls_back_schema_data_and_version(tmp_path):
    from dashboard.migrations import Migration, migrate_database

    db_path = tmp_path / "dashboard.db"
    _create_legacy(db_path)

    def fail_after_write(conn):
        conn.execute("UPDATE records SET value = 'changed'")
        raise RuntimeError("boom")

    migrations = (Migration(1, "failing", fail_after_write),)

    with pytest.raises(RuntimeError, match="boom"):
        migrate_database(db_path, migrations, backup_dir=tmp_path / "backups")

    with sqlite3.connect(db_path) as conn:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 0
        assert conn.execute("SELECT value FROM records").fetchone()[0] == "kept"


def test_migration_versions_must_be_unique_and_monotonic(tmp_path):
    from dashboard.migrations import Migration, migrate_database

    db_path = tmp_path / "dashboard.db"
    _create_legacy(db_path)
    duplicate = (
        Migration(1, "one", lambda conn: None),
        Migration(1, "duplicate", lambda conn: None),
    )

    with pytest.raises(ValueError, match="strictly increasing"):
        migrate_database(db_path, duplicate, backup_dir=tmp_path / "backups")
