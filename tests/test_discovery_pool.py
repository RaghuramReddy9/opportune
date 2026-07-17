import tempfile
from pathlib import Path
from unittest.mock import patch

from dashboard.db import (
    connect,
    create_profile,
    init_db,
    reconcile_source_snapshot,
    start_scrape_run,
)
from pipeline.discovery_pool import (
    build_discovery_pool,
    classify_experience_level,
    classify_work_mode,
    materialize_catalog_pool,
    match_role_preference,
)


ROLES = [
    "AI Engineer",
    "FDE",
    "LLM Engineer",
    "Agents Engineer",
    "Data + AI Engineer",
]


def _job(**overrides):
    job = {
        "company": "Acme",
        "title": "AI Engineer",
        "location": "New York, NY",
        "description": "Build customer products.",
        "apply_url": "https://example.com/jobs/1",
        "source": "greenhouse",
    }
    job.update(overrides)
    return job


def test_role_matching_uses_title_without_requiring_ai_description():
    assert match_role_preference(_job(description="Maintain customer workflows."), ROLES) == "AI Engineer"
    assert match_role_preference(_job(title="Forward Deployed Engineer"), ROLES) == "FDE"
    assert match_role_preference(_job(title="Data Platform Engineer"), ROLES) == "Data + AI Engineer"


def test_pool_keeps_us_role_matches_and_rejects_non_us_locations():
    jobs = [
        _job(),
        _job(company="LondonCo", location="London, UK", apply_url="https://example.com/jobs/2"),
        _job(company="BlankCo", location="", apply_url="https://example.com/jobs/3"),
    ]
    with patch("pipeline.discovery_pool.get_profile_config", return_value={"locations": ["United States"]}):
        pool = build_discovery_pool(jobs, ROLES)
    assert [job["company"] for job in pool] == ["Acme"]
    assert pool[0]["action_tag"] == "pool"


def test_pool_does_not_reject_senior_or_old_jobs_before_browser_filters():
    job = _job(
        title="Senior AI Engineer",
        posted_date="2025-01-01",
        description="Requires 8+ years. On-site five days per week.",
    )
    with patch("pipeline.discovery_pool.get_profile_config", return_value={"locations": ["United States"]}):
        pool = build_discovery_pool([job], ROLES)
    assert len(pool) == 1
    assert pool[0]["experience_level"] == "senior"
    assert pool[0]["work_mode"] == "onsite"


def test_work_mode_and_experience_metadata_support_browser_filters():
    assert classify_work_mode(_job(location="Remote, United States")) == "remote"
    assert classify_work_mode(_job(description="Hybrid, 3 days per week in office")) == "hybrid"
    assert classify_experience_level(_job(title="AI Engineer, New Grad")) == "entry_level"
    assert classify_experience_level(_job(title="AI Engineer II", description="3+ years")) == "mid_level"


def test_active_catalog_can_be_materialized_without_another_scrape():
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "pool.db"
        init_db(path)
        profile_id = create_profile("Catalog", "resume", "{}", db_path=path)
        with connect(path) as conn:
            run_id = start_scrape_run(conn, "direct")
            reconcile_source_snapshot(
                conn,
                run_id=run_id,
                source_key="greenhouse",
                source_name="acme",
                jobs=[
                    _job(),
                    _job(company="GlobalCo", location="London, UK", apply_url="https://example.com/global"),
                ],
            )
            with patch("pipeline.discovery_pool.get_profile_config", return_value={"target_roles": ROLES, "locations": ["United States"]}):
                result = materialize_catalog_pool(conn)
            stored = conn.execute(
                "SELECT company, action_tag, profile_id FROM jobs"
            ).fetchall()

    assert result["catalog_active"] == 2
    assert result["pool_matches"] == 1
    assert [tuple(row) for row in stored] == [("Acme", "pool", profile_id)]
