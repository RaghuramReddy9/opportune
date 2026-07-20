"""Approved-profile context safety contracts."""
from __future__ import annotations

import json
from dataclasses import FrozenInstanceError

import pytest

from dashboard.db import create_profile, init_db


def test_context_fails_closed_without_active_profile(tmp_path):
    from profile_context import ProfileApprovalRequired, get_approved_profile_context

    db_path = tmp_path / "empty.db"
    init_db(db_path)

    with pytest.raises(ProfileApprovalRequired, match="approve"):
        get_approved_profile_context(db_path=db_path)


def test_context_is_immutable_and_contains_compiled_config(tmp_path):
    from profile_context import get_approved_profile_context

    db_path = tmp_path / "profile.db"
    init_db(db_path)
    profile_id = create_profile(
        "Candidate",
        "private resume text",
        json.dumps({"roles": ["Applied AI Engineer"], "target_levels": ["entry_level"], "locations": ["United States"], "work_modes": ["remote"], "work_focuses": ["applied_ai"], "visa_policy": "none", "timeline": {"max_age_days": 7}}),
        db_path=db_path,
    )

    context = get_approved_profile_context(db_path=db_path)

    assert context.profile_id == profile_id
    assert context.version_id
    assert context.version_id != profile_id
    assert context.schema_version == 1
    assert context.revision == 1
    assert context.compiled_config["roles"] == ["Applied AI Engineer"]
    assert "resume" not in repr(context).lower()
    with pytest.raises(FrozenInstanceError):
        context.profile_id = "changed"


def test_context_fails_closed_for_malformed_compiled_profile(tmp_path):
    from profile_context import ProfileApprovalRequired, get_approved_profile_context

    db_path = tmp_path / "malformed.db"
    init_db(db_path)
    create_profile("Candidate", "private", "not-json", db_path=db_path)

    with pytest.raises(ProfileApprovalRequired, match="invalid"):
        get_approved_profile_context(db_path=db_path)

def test_context_fails_closed_for_incomplete_compiled_profile(tmp_path):
    from profile_context import ProfileApprovalRequired, get_approved_profile_context

    db_path = tmp_path / "incomplete.db"
    init_db(db_path)
    create_profile(
        "Candidate",
        "private",
        json.dumps({"roles": ["AI Engineer"], "locations": ["United States"]}),
        db_path=db_path,
    )
    with pytest.raises(ProfileApprovalRequired, match="incomplete"):
        get_approved_profile_context(db_path=db_path)
