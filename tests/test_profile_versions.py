"""Immutable approved-profile version contracts."""
from __future__ import annotations

import json
import sqlite3

from fastapi.testclient import TestClient

from dashboard.db import (
    approve_version,
    create_draft_version,
    create_profile,
    get_active_profile,
    get_active_version,
    get_profile_versions,
    init_db,
    list_profiles,
    set_db_path,
    set_active_profile,
)
from dashapi.server import app


def _create(db_path, name="Candidate", skills=None):
    return create_profile(
        name,
        "private resume",
        json.dumps({"roles": ["AI Engineer"], "skills": skills or ["Python"]}),
        db_path=db_path,
    )


def test_onboarding_approval_creates_and_activates_approved_v1(tmp_path):
    db = tmp_path / "profile.db"
    init_db(db)

    profile_id = _create(db)
    versions = get_profile_versions(profile_id, db_path=db)
    active = get_active_profile(db_path=db)

    assert len(versions) == 1
    assert versions[0]["revision"] == 1
    assert versions[0]["status"] == "approved"
    assert versions[0]["approved_at"]
    assert active["profile_id"] == profile_id
    assert active["version_id"] == versions[0]["version_id"]


def test_edit_creates_draft_without_mutating_active_approved_snapshot(tmp_path):
    db = tmp_path / "profile.db"
    init_db(db)
    profile_id = _create(db)
    before = get_active_profile(db_path=db)

    draft_id = create_draft_version(
        profile_id,
        "updated private resume",
        json.dumps({"roles": ["AI Engineer"], "skills": ["Python", "Go"]}),
        db_path=db,
    )

    active = get_active_profile(db_path=db)
    versions = get_profile_versions(profile_id, db_path=db)
    assert active["version_id"] == before["version_id"]
    assert active["resume_text"] == "private resume"
    assert [version["status"] for version in versions] == ["approved", "draft"]
    assert versions[1]["version_id"] == draft_id


def test_approving_draft_atomically_supersedes_and_activates(tmp_path):
    db = tmp_path / "profile.db"
    init_db(db)
    profile_id = _create(db)
    old_version = get_active_version(profile_id, db_path=db)
    draft_id = create_draft_version(
        profile_id,
        "updated private resume",
        json.dumps({"roles": ["AI Engineer"], "skills": ["Go"]}),
        db_path=db,
    )

    assert approve_version(profile_id, draft_id, db_path=db) is True

    active = get_active_profile(db_path=db)
    versions = get_profile_versions(profile_id, db_path=db)
    assert active["version_id"] == draft_id
    assert active["resume_text"] == "updated private resume"
    assert json.loads(active["extracted_json"])["skills"] == ["Go"]
    assert versions[0]["version_id"] == old_version["version_id"]
    assert versions[0]["status"] == "superseded"
    assert versions[0]["resume_text"] == "private resume"
    assert versions[1]["status"] == "approved"


def test_failed_approval_preserves_prior_approved_version(tmp_path):
    db = tmp_path / "profile.db"
    init_db(db)
    profile_id = _create(db)
    before = get_active_profile(db_path=db)

    assert approve_version(profile_id, "missing-version", db_path=db) is False
    after = get_active_profile(db_path=db)

    assert after["version_id"] == before["version_id"]
    assert get_profile_versions(profile_id, db_path=db)[0]["status"] == "approved"


def test_legacy_approved_profile_is_backfilled_idempotently(tmp_path):
    db = tmp_path / "legacy.db"
    connection = sqlite3.connect(db)
    connection.execute(
        """CREATE TABLE profiles (
               profile_id TEXT PRIMARY KEY, name TEXT, resume_text TEXT,
               extracted_json TEXT, is_active INTEGER, created_at TEXT,
               last_used_at TEXT
           )"""
    )
    connection.execute(
        "INSERT INTO profiles VALUES (?, ?, ?, ?, 1, ?, ?)",
        (
            "legacy",
            "Legacy",
            "private",
            '{"roles":["AI Engineer"]}',
            "2026-01-01T00:00:00Z",
            "2026-01-02T00:00:00Z",
        ),
    )
    connection.commit()
    connection.close()

    init_db(db)
    init_db(db)

    active = get_active_profile(db_path=db)
    versions = get_profile_versions("legacy", db_path=db)
    assert active["profile_id"] == "legacy"
    assert len(versions) == 1
    assert versions[0]["status"] == "approved"


def test_switching_profiles_requires_existing_approved_version(tmp_path):
    db = tmp_path / "profile.db"
    init_db(db)
    first = _create(db, name="First")
    second = _create(db, name="Second")

    assert get_active_profile(db_path=db)["profile_id"] == second
    assert set_active_profile(first, db_path=db) is True
    assert get_active_profile(db_path=db)["profile_id"] == first
    assert set_active_profile("missing", db_path=db) is False
    assert sum(profile["is_active"] for profile in list_profiles(db_path=db)) == 1


def test_profile_version_api_keeps_draft_inactive_until_explicit_approval(tmp_path):
    db = tmp_path / "api.db"
    set_db_path(db)
    init_db()
    try:
        profile_id = _create(db)
        active_before = get_active_profile(db_path=db)
        with TestClient(app) as client:
            draft = client.post(
                f"/api/profiles/{profile_id}/drafts",
                json={
                    "resume_text": "updated private resume",
                    "extracted": {"roles": ["Agent Engineer"], "skills": ["Python"]},
                },
            )
            assert draft.status_code == 200
            draft_id = draft.json()["version_id"]
            assert get_active_profile(db_path=db)["version_id"] == active_before["version_id"]

            versions = client.get(f"/api/profiles/{profile_id}/versions")
            assert versions.status_code == 200
            assert [item["status"] for item in versions.json()["versions"]] == ["approved", "draft"]

            approved = client.post(
                f"/api/profiles/{profile_id}/versions/{draft_id}/approve"
            )
            assert approved.status_code == 200
            assert get_active_profile(db_path=db)["version_id"] == draft_id
    finally:
        set_db_path(None)
