"""Versioned discovery-funnel schema, aggregation, and persistence contracts."""
from __future__ import annotations

import json
from unittest.mock import patch

import jobhunt
from dashboard.db import connect, get_discovery_funnel, init_db, save_discovery_funnel, set_db_path
from pipeline.funnel import first_zero_stage, merge_funnels, new_funnel, record_stage
from pipeline.smart_scrape import smart_scrape


def _sample_funnel(raw: int, dashboard: int) -> dict:
    funnel = new_funnel()
    record_stage(funnel, "tasks", 2, by_source={"greenhouse": 2})
    record_stage(funnel, "requests", 2, by_source={"greenhouse": 2})
    record_stage(funnel, "raw", raw, by_source={"greenhouse": raw})
    record_stage(funnel, "normalized", raw)
    record_stage(funnel, "location", raw)
    record_stage(funnel, "acquisition", dashboard)
    record_stage(funnel, "ranking", dashboard)
    record_stage(funnel, "freshness", dashboard)
    record_stage(funnel, "link", dashboard)
    record_stage(funnel, "lifecycle", dashboard)
    record_stage(funnel, "buckets", dashboard)
    record_stage(funnel, "persistence", dashboard)
    record_stage(funnel, "dashboard", dashboard)
    return funnel


def test_funnel_has_one_versioned_ordered_schema_and_finds_first_zero():
    funnel = new_funnel()
    record_stage(funnel, "tasks", 3, reason_codes={"enabled": 3})
    record_stage(funnel, "requests", 0, reason_codes={"circuit_open": 3})

    assert funnel["version"] == 1
    assert funnel["stages"]["tasks"]["count"] == 3
    assert first_zero_stage(funnel) == "requests"


def test_merge_funnels_sums_counts_reasons_and_sources():
    merged = merge_funnels([_sample_funnel(4, 1), _sample_funnel(6, 2)])

    assert merged["stages"]["raw"]["count"] == 10
    assert merged["stages"]["raw"]["by_source"] == {"greenhouse": 10}
    assert merged["stages"]["dashboard"]["count"] == 3


def test_smart_scrape_merges_versioned_window_funnels():
    results = [
        {"raw_count": 4, "dashboard_jobs": [], "discovery_funnel": _sample_funnel(4, 1)},
        {"raw_count": 6, "dashboard_jobs": [], "discovery_funnel": _sample_funnel(6, 2)},
    ]
    with patch("pipeline.smart_scrape.scrape_all", side_effect=results):
        result = smart_scrape(min_high=99, max_windows=2)

    assert result["discovery_funnel"]["version"] == 1
    assert result["discovery_funnel"]["stages"]["raw"]["count"] == 10


def test_database_round_trip_preserves_stage_order_and_envelope(tmp_path):
    database = tmp_path / "dashboard.db"
    init_db(database)
    funnel = _sample_funnel(5, 1)
    with connect(database) as connection:
        connection.execute(
            "INSERT INTO scrape_runs (run_id, run_window, status, started_at) "
            "VALUES ('run-1', 'morning', 'completed', '2026-07-18T00:00:00Z')"
        )
        save_discovery_funnel(connection, "run-1", funnel)
        loaded = get_discovery_funnel(connection, "run-1")

    assert loaded == funnel


def test_cli_diagnose_reports_first_zero_stage_without_network(tmp_path, capsys):
    database = tmp_path / "dashboard.db"
    init_db(database)
    funnel = new_funnel()
    record_stage(funnel, "tasks", 2)
    with connect(database) as connection:
        connection.execute(
            "INSERT INTO scrape_runs (run_id, run_window, status, started_at) "
            "VALUES ('run-1', 'morning', 'completed', '2026-07-18T00:00:00Z')"
        )
        save_discovery_funnel(connection, "run-1", funnel)
    set_db_path(database)
    try:
        args = jobhunt.build_parser().parse_args(["diagnose", "--json"])
        args.func(args)
    finally:
        set_db_path(None)

    output = json.loads(capsys.readouterr().out)
    assert output["first_zero_stage"] == "requests"
    assert output["funnel"]["version"] == 1
