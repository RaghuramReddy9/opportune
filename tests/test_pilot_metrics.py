"""Opt-in local pilot metrics privacy contracts."""
from __future__ import annotations

import pytest

import jobhunt
from pilot_metrics import PilotStore


def test_pilot_cli_exposes_all_local_controls():
    parser = jobhunt.build_parser()

    for action in ("enable", "inspect", "export", "disable", "delete"):
        args = parser.parse_args(["pilot", action])
        assert args.command == "pilot"
        assert args.action == action


def test_pilot_metrics_are_off_by_default(tmp_path):
    store = PilotStore(tmp_path / "pilot.db")

    assert store.record("launch_ready", {"duration_seconds": 4}) is False
    assert store.inspect()["events"] == []


def test_pilot_events_reject_private_fields_and_free_text(tmp_path):
    store = PilotStore(tmp_path / "pilot.db")
    store.enable(consent_version="1.0")

    with pytest.raises(ValueError, match="prohibited"):
        store.record("listing_rated", {"email": "person@example.com"})
    with pytest.raises(ValueError, match="scalar counters"):
        store.record("listing_rated", {"detail": "private free text"})  # type: ignore[arg-type]


def test_pilot_inspect_export_disable_and_delete_are_local(tmp_path):
    store = PilotStore(tmp_path / "pilot.db")
    session_id = store.enable(consent_version="1.0")
    assert store.record("onboarding_completed", {"duration_seconds": 600, "fields_corrected": 2}) is True
    assert store.record("listing_rated", {"rating": 4, "relevant": True}) is True

    inspected = store.inspect()
    exported = store.export()

    assert inspected["enabled"] is True
    assert len(inspected["events"]) == 2
    assert exported["schema_version"] == "1.0.0"
    assert exported["pilot_session_id"] == session_id
    assert "events" in exported

    store.disable()
    assert store.record("repeat_discovery", {"count": 1}) is False
    store.delete()
    assert store.inspect()["events"] == []
