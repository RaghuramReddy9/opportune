"""Fail-closed approved-profile enforcement at side-effect boundaries."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from dashboard.db import create_profile, init_db, set_db_path
from pipeline.discovery_pool import materialize_catalog_pool
from pipeline.scheduler import ScheduleConfig, run_scheduled_once
from pipeline.scrape import scrape_all
from profile_context import ProfileApprovalRequired, get_approved_profile_context


def test_scrape_stops_before_any_source_or_registry_call_without_approval(tmp_path):
    db = tmp_path / "empty.db"
    init_db(db)
    set_db_path(db)
    try:
        with (
            patch("pipeline.scrape.load_registry") as registry,
            patch("pipeline.scrape._execute_source_tasks") as source_calls,
            pytest.raises(ProfileApprovalRequired),
        ):
            scrape_all(dry_run=True)
        registry.assert_not_called()
        source_calls.assert_not_called()
    finally:
        set_db_path(None)


def test_scheduler_stops_before_runner_without_approval(tmp_path):
    db = tmp_path / "empty.db"
    init_db(db)
    set_db_path(db)
    runner = MagicMock()
    try:
        with pytest.raises(ProfileApprovalRequired):
            run_scheduled_once(
                now=datetime(2026, 7, 18, 12, 0, tzinfo=timezone.utc),
                schedule=ScheduleConfig(180, 360, 0, 30),
                state_path=tmp_path / "scheduler-state.json",
                lock_path=tmp_path / "scheduler.lock",
                scrape_runner=runner,
                jitter_fn=lambda _: 0,
            )
        runner.assert_not_called()
    finally:
        set_db_path(None)


def test_catalog_materialization_stops_before_writes_without_approval(tmp_path):
    from dashboard.db import connect

    db = tmp_path / "empty.db"
    init_db(db)
    set_db_path(db)
    try:
        with connect(db) as connection:
            with pytest.raises(ProfileApprovalRequired):
                materialize_catalog_pool(connection)
            assert connection.execute("SELECT COUNT(*) FROM jobs").fetchone()[0] == 0
            assert connection.execute("SELECT COUNT(*) FROM job_catalog").fetchone()[0] == 0
    finally:
        set_db_path(None)


def test_approved_context_uses_immutable_version_and_excludes_resume_from_repr(tmp_path):
    db = tmp_path / "approved.db"
    init_db(db)
    profile_id = create_profile(
        "Candidate",
        "super secret resume text",
        json.dumps({"roles": ["AI Engineer"], "locations": ["United States"]}),
        db_path=db,
    )

    context = get_approved_profile_context(db_path=db)

    assert context.profile_id == profile_id
    assert context.version_id != profile_id
    assert context.revision == 1
    assert context.compiled_config["roles"] == ["AI Engineer"]
    assert "resume" not in repr(context).lower()
    assert "super secret" not in repr(context).lower()
