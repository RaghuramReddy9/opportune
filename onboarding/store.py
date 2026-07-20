"""Persistent SQLite store for onboarding drafts and approvals."""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

from dashboard.db import connect

_SCHEMA = """
CREATE TABLE IF NOT EXISTS onboarding_sessions (
    session_id TEXT PRIMARY KEY,
    status TEXT NOT NULL,
    filename TEXT DEFAULT '',
    resume_text TEXT DEFAULT '',
    provider TEXT DEFAULT 'local',
    analysis_json TEXT DEFAULT '{}',
    questions_json TEXT DEFAULT '[]',
    answers_json TEXT DEFAULT '{}',
    final_config_json TEXT DEFAULT '{}',
    profile_id TEXT DEFAULT '',
    created_at TEXT NOT NULL,
    revision INTEGER NOT NULL DEFAULT 1,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_onboarding_updated ON onboarding_sessions(updated_at);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _loads(value: str, fallback):
    try:
        return json.loads(value or "")
    except (TypeError, ValueError):
        return fallback


class OnboardingRevisionConflict(ValueError):
    """Raised when a stale browser attempts to overwrite a newer draft."""


class OnboardingStore:
    def __init__(self, db_path: Path | None = None):
        self.db_path = db_path
        with connect(self.db_path) as conn:
            conn.executescript(_SCHEMA)
            columns = {
                row["name"] for row in conn.execute("PRAGMA table_info(onboarding_sessions)")
            }
            if "revision" not in columns:
                conn.execute("ALTER TABLE onboarding_sessions ADD COLUMN revision INTEGER NOT NULL DEFAULT 1")

    def create(self, *, filename: str, resume_text: str, provider: str, analysis: dict, questions: list[dict]) -> dict:
        session_id = uuid.uuid4().hex
        now = _now()
        with connect(self.db_path) as conn:
            conn.execute(
                """INSERT INTO onboarding_sessions
                   (session_id, status, filename, resume_text, provider,
                    analysis_json, questions_json, created_at, updated_at)
                   VALUES (?, 'questions', ?, ?, ?, ?, ?, ?, ?)""",
                (
                    session_id,
                    filename,
                    resume_text,
                    provider,
                    json.dumps(analysis, ensure_ascii=False),
                    json.dumps(questions, ensure_ascii=False),
                    now,
                    now,
                ),
            )
        return self.get(session_id)

    def get(self, session_id: str, *, include_resume: bool = False) -> dict:
        with connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT * FROM onboarding_sessions WHERE session_id = ?",
                (session_id,),
            ).fetchone()
        if not row:
            raise ValueError("Onboarding session not found")
        return self._public(dict(row), include_resume=include_resume)

    def latest(self) -> dict | None:
        with connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT * FROM onboarding_sessions ORDER BY updated_at DESC LIMIT 1"
            ).fetchone()
        return self._public(dict(row)) if row else None

    def save_answers(
        self,
        session_id: str,
        answers: dict,
        final_config: dict,
        expected_revision: int,
    ) -> dict:
        with connect(self.db_path) as conn:
            cursor = conn.execute(
                """UPDATE onboarding_sessions
                   SET status = 'review', answers_json = ?, final_config_json = ?,
                       revision = revision + 1, updated_at = ?
                   WHERE session_id = ? AND revision = ? AND status IN ('questions', 'review')""",
                (
                    json.dumps(answers, ensure_ascii=False),
                    json.dumps(final_config, ensure_ascii=False),
                    _now(),
                    session_id,
                    expected_revision,
                ),
            )
        if cursor.rowcount == 0:
            current = self.get(session_id)
            if current["revision"] != expected_revision:
                raise OnboardingRevisionConflict(
                    "This onboarding draft changed in another browser. Reload the newest draft."
                )
            raise ValueError("Onboarding answers cannot be changed in this state")
        return self.get(session_id)

    def mark_approved(self, session_id: str, profile_id: str) -> dict:
        with connect(self.db_path) as conn:
            cursor = conn.execute(
                """UPDATE onboarding_sessions
                   SET status = 'approved', profile_id = ?, updated_at = ?
                   WHERE session_id = ? AND status = 'review'""",
                (profile_id, _now(), session_id),
            )
        if cursor.rowcount == 0:
            raise ValueError("Review the final search plan before approval")
        return self.get(session_id)

    @staticmethod
    def _public(row: dict, *, include_resume: bool = False) -> dict:
        result = {
            "session_id": row["session_id"],
            "status": row["status"],
            "filename": row["filename"],
            "provider": row["provider"],
            "analysis": _loads(row["analysis_json"], {}),
            "questions": _loads(row["questions_json"], []),
            "answers": _loads(row["answers_json"], {}),
            "final_config": _loads(row["final_config_json"], {}),
            "profile_id": row["profile_id"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "revision": int(row.get("revision") or 1),
        }
        if include_resume:
            result["resume_text"] = row["resume_text"]
        return result
