"""Ordered SQLite migrations and safe legacy-path relocation."""
from __future__ import annotations

import hashlib
import os
import sqlite3
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterable


@dataclass(frozen=True)
class Migration:
    version: int
    name: str
    apply: Callable[[sqlite3.Connection], object]


def _integrity_check(connection: sqlite3.Connection) -> None:
    result = connection.execute("PRAGMA integrity_check").fetchone()
    if not result or result[0] != "ok":
        raise RuntimeError(f"SQLite integrity check failed: {result[0] if result else 'no result'}")


def _backup_database(
    source: sqlite3.Connection,
    db_path: Path,
    backup_dir: Path,
    version: int,
) -> Path:
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-%f")
    backup_path = backup_dir / f"{db_path.stem}-v{version}-{stamp}.db"
    target = sqlite3.connect(backup_path)
    try:
        source.backup(target)
        _integrity_check(target)
    finally:
        target.close()
    return backup_path


def _compute_file_checksum(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def migrate_database(
    db_path: Path,
    migrations: Iterable[Migration],
    *,
    backup_dir: Path,
) -> dict:
    """Apply pending strictly ordered migrations in one transaction."""
    ordered = tuple(migrations)
    versions = [item.version for item in ordered]
    if versions != sorted(set(versions)):
        raise ValueError("migration versions must be unique and strictly increasing")

    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(db_path, timeout=10, isolation_level=None)
    try:
        _integrity_check(connection)
        current = int(connection.execute("PRAGMA user_version").fetchone()[0])
        if versions and current > versions[-1]:
            raise RuntimeError(
                f"database schema version {current} is newer than supported "
                f"version {versions[-1]}"
            )
        pending = [item for item in ordered if item.version > current]
        if not pending:
            return {
                "from_version": current,
                "to_version": current,
                "applied": [],
                "backup_path": "",
            }

        backup_path = _backup_database(connection, db_path, Path(backup_dir), current)
        connection.execute("BEGIN IMMEDIATE")
        try:
            applied = []
            for migration in pending:
                migration.apply(connection)
                connection.execute(f"PRAGMA user_version = {migration.version}")
                applied.append(migration.version)
            _integrity_check(connection)
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        return {
            "from_version": current,
            "to_version": applied[-1],
            "applied": applied,
            "backup_path": str(backup_path),
        }
    finally:
        connection.close()


def _sqlite_snapshot(source_path: Path, destination_path: Path) -> None:
    source = sqlite3.connect(f"file:{source_path}?mode=ro", uri=True, timeout=10)
    target = sqlite3.connect(destination_path)
    try:
        source.backup(target)
        _integrity_check(target)
    finally:
        target.close()
        source.close()


def migrate_legacy_source_checkout_to_platform_data(
    *,
    legacy_db_path: Path,
    platform_db_path: Path,
    dry_run: bool = False,
    create_backup: bool = True,
    verify_checksum: bool = True,
    backup_dir: Path | None = None,
) -> dict:
    """Relocate one legacy database without mutating or overwriting user data."""
    legacy = Path(legacy_db_path).expanduser().resolve()
    platform = Path(platform_db_path).expanduser().resolve()
    base = {
        "dry_run": dry_run,
        "legacy_db_path": str(legacy),
        "platform_db_path": str(platform),
        "backup_path": "",
        "checksum_verified": False,
        "bytes_copied": 0,
        "rollback_performed": False,
    }
    if not legacy.is_file():
        return {**base, "ok": False, "error": f"Legacy database not found: {legacy}"}
    if legacy == platform:
        return {**base, "ok": True, "message": "source and destination are identical"}
    if platform.exists():
        return {**base, "ok": False, "error": "platform database already exists; refusing to overwrite"}
    if dry_run:
        return {
            **base,
            "ok": True,
            "bytes_to_copy": legacy.stat().st_size,
            "backup_would_be_created": create_backup,
        }

    platform.parent.mkdir(parents=True, exist_ok=True)
    backup_root = Path(backup_dir or platform.parent / "backups")
    temporary: Path | None = None
    backup_path: Path | None = None
    try:
        descriptor, raw_temporary = tempfile.mkstemp(
            prefix=f".{platform.name}.", suffix=".migrating", dir=platform.parent
        )
        os.close(descriptor)
        temporary = Path(raw_temporary)
        temporary.unlink()
        _sqlite_snapshot(legacy, temporary)
        snapshot_checksum = _compute_file_checksum(temporary)

        if create_backup:
            backup_root.mkdir(parents=True, exist_ok=True)
            stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-%f")
            backup_path = backup_root / f"legacy-migration-{stamp}.db"
            _sqlite_snapshot(legacy, backup_path)
            if _compute_file_checksum(backup_path) != snapshot_checksum:
                raise RuntimeError("verified backup checksum mismatch")

        os.replace(temporary, platform)
        temporary = None
        checksum_verified = not verify_checksum or _compute_file_checksum(platform) == snapshot_checksum
        if not checksum_verified:
            platform.unlink(missing_ok=True)
            raise RuntimeError("destination checksum mismatch")
        with sqlite3.connect(f"file:{platform}?mode=ro", uri=True) as connection:
            _integrity_check(connection)
        return {
            **base,
            "ok": True,
            "backup_path": str(backup_path or ""),
            "checksum_verified": checksum_verified,
            "checksum": snapshot_checksum,
            "bytes_copied": platform.stat().st_size,
        }
    except Exception as exc:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
        if platform.exists():
            platform.unlink(missing_ok=True)
        return {
            **base,
            "ok": False,
            "backup_path": str(backup_path or ""),
            "error": str(exc),
        }
