"""Explicitly opted-in, local-only pilot counters and ratings."""
from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

EVENT_TYPES = {
    "install_result",
    "launch_ready",
    "onboarding_started",
    "onboarding_section_saved",
    "onboarding_completed",
    "field_corrected",
    "draft_resumed",
    "profile_approved",
    "discovery_started",
    "discovery_completed",
    "first_visible_listing",
    "listing_rated",
    "job_saved",
    "job_hidden",
    "job_applied",
    "repeat_discovery",
    "backup_restored",
    "privacy_answered",
    "export_created",
}
ALLOWED_METRICS = {
    "success",
    "duration_seconds",
    "count",
    "fields_corrected",
    "rating",
    "relevant",
    "correct",
    "total",
    "assistance_required",
}
PROHIBITED_KEYS = {
    "name",
    "email",
    "phone",
    "address",
    "resume",
    "resume_text",
    "title",
    "company",
    "url",
    "path",
    "filename",
    "api_key",
    "prompt",
    "response",
    "notes",
    "comment",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class PilotStore:
    def __init__(self, path: Path):
        self.path = Path(path)

    def _connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS pilot_settings (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                enabled INTEGER NOT NULL,
                session_id TEXT NOT NULL,
                consent_version TEXT NOT NULL,
                enabled_at TEXT NOT NULL,
                disabled_at TEXT
            );
            CREATE TABLE IF NOT EXISTS pilot_events (
                event_id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                event_type TEXT NOT NULL,
                metrics_json TEXT NOT NULL,
                recorded_at TEXT NOT NULL,
                schema_version TEXT NOT NULL
            );
            """
        )
        return connection

    def enable(self, *, consent_version: str) -> str:
        if not consent_version.strip():
            raise ValueError("consent_version is required")
        session_id = str(uuid.uuid4())
        with self._connect() as connection:
            connection.execute(
                "INSERT OR REPLACE INTO pilot_settings "
                "(id, enabled, session_id, consent_version, enabled_at, disabled_at) "
                "VALUES (1, 1, ?, ?, ?, NULL)",
                (session_id, consent_version.strip(), _now()),
            )
        return session_id

    def disable(self) -> None:
        if not self.path.exists():
            return
        with self._connect() as connection:
            connection.execute(
                "UPDATE pilot_settings SET enabled = 0, disabled_at = ? WHERE id = 1",
                (_now(),),
            )

    def record(self, event_type: str, metrics: dict[str, int | float | bool]) -> bool:
        if event_type not in EVENT_TYPES:
            raise ValueError("event type is not allowlisted")
        keys = set(metrics)
        if keys & PROHIBITED_KEYS:
            raise ValueError("pilot event contains prohibited private fields")
        if not keys.issubset(ALLOWED_METRICS) or any(
            not isinstance(value, (int, float, bool)) for value in metrics.values()
        ):
            raise ValueError("pilot events accept scalar counters and ratings only")
        if not self.path.exists():
            return False
        with self._connect() as connection:
            settings = connection.execute(
                "SELECT enabled, session_id FROM pilot_settings WHERE id = 1"
            ).fetchone()
            if not settings or not bool(settings["enabled"]):
                return False
            connection.execute(
                "INSERT INTO pilot_events VALUES (?, ?, ?, ?, ?, '1.0.0')",
                (
                    str(uuid.uuid4()),
                    settings["session_id"],
                    event_type,
                    json.dumps(metrics, sort_keys=True),
                    _now(),
                ),
            )
        return True

    def inspect(self) -> dict:
        if not self.path.exists():
            return {"enabled": False, "session_id": None, "events": []}
        with self._connect() as connection:
            settings = connection.execute("SELECT * FROM pilot_settings WHERE id = 1").fetchone()
            rows = connection.execute(
                "SELECT event_type, metrics_json, recorded_at, schema_version "
                "FROM pilot_events ORDER BY recorded_at, event_id"
            ).fetchall()
        return {
            "enabled": bool(settings["enabled"]) if settings else False,
            "session_id": settings["session_id"] if settings else None,
            "events": [
                {
                    "event_type": row["event_type"],
                    "metrics": json.loads(row["metrics_json"]),
                    "recorded_at": row["recorded_at"],
                    "schema_version": row["schema_version"],
                }
                for row in rows
            ],
        }

    def export(self) -> dict:
        inspected = self.inspect()
        return {
            "schema_version": "1.0.0",
            "exported_at": _now(),
            "pilot_session_id": inspected["session_id"],
            "events": inspected["events"],
            "redaction": {
                "rules_version": "1.0.0",
                "removed_categories": sorted(PROHIBITED_KEYS),
            },
        }

    def delete(self) -> None:
        if self.path.exists():
            self.path.unlink()
