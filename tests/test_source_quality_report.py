"""Privacy-safe retained source-quality outcome contracts."""
from __future__ import annotations

import json

from core.source_quality import (
    build_snapshot,
    load_history,
    record_snapshot,
    summarize_history,
)
from pipeline.funnel import new_funnel, record_stage


def _result():
    funnel = new_funnel()
    record_stage(funnel, "requests", 3, by_source={"greenhouse": 2, "workable": 1})
    record_stage(funnel, "raw", 8, by_source={"greenhouse": 8})
    record_stage(funnel, "normalized", 7, by_source={"greenhouse": 7})
    record_stage(funnel, "acquisition", 2, by_source={"greenhouse": 2})
    record_stage(funnel, "dashboard", 1, by_source={"greenhouse": 1})
    return {
        "catalog": {"run_id": "run-1"},
        "discovery_funnel": funnel,
        "failed_sources": [
            {"source": "workable", "company": "PrivateCo", "error": "403 blocked secret detail"}
        ],
        "skipped_sources": [],
        "timings_seconds": {"total": 2.5},
    }


def test_source_quality_snapshot_uses_categories_and_never_retains_error_text():
    snapshot = build_snapshot(_result())
    serialized = json.dumps(snapshot)

    assert snapshot["sources"]["greenhouse"]["outcome"] == "success"
    assert snapshot["sources"]["workable"]["outcome"] == "failed"
    assert snapshot["sources"]["workable"]["failure_categories"] == {"blocked": 1}
    assert "secret detail" not in serialized
    assert snapshot["sources"]["greenhouse"]["latency_seconds"] is None
    assert snapshot["sources"]["greenhouse"]["cost_usd"] is None


def test_source_quality_history_is_atomic_bounded_and_reportable(tmp_path):
    path = tmp_path / "source-quality.json"
    snapshot = build_snapshot(_result())

    for index in range(4):
        record_snapshot({**snapshot, "run_id": f"run-{index}"}, path=path, retain=3)

    history = load_history(path)
    report = summarize_history(history)
    assert len(history["runs"]) == 3
    assert report["run_count"] == 3
    assert report["sources"]["greenhouse"]["raw_count"] == 24
    assert report["sources"]["workable"]["failed_runs"] == 3
    assert report["unavailable_metrics"] == ["per_source_latency_seconds", "per_source_cost_usd"]
