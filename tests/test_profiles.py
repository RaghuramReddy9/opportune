"""tests/test_profiles.py — Profile system verification tests.

Covers the acceptance criteria from PROFILE_SYSTEM_CHECKLIST.md:
  1. Profile storage (create, activate, no two active)
  2. jobs.profile_id column present after init_db()
  3. Deduplication isolation per profile
  4. extract_profile_from_text on non-AI resumes
  5. get_profile_config() overlay with active profile
  6. API endpoints: /api/profiles and /api/profiles/{id}/activate
"""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from dashboard.db import (
    connect,
    create_profile,
    filter_jobs,
    get_active_profile,
    get_dashboard_model,
    init_db,
    list_profiles,
    set_active_profile,
    upsert_scraped_job,
)
from resume.resume_profile import extract_profile_from_text


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _tmp_db() -> Path:
    tmp = tempfile.mkdtemp()
    db_path = Path(tmp) / "test_profiles.db"
    init_db(db_path)
    return db_path


def _sample_job(company: str = "Acme", title: str = "Software Engineer", **kw) -> dict:
    return {
        "company": company,
        "title": title,
        "location": "Remote",
        "apply_url": "https://" + company.lower() + ".com/jobs/1",
        "source": "test_source",
        "ats_type": "greenhouse",
        "resume_match_score": 80,
        "freshness": "New",
        "freshness_trust": "confirmed_posted_date",
        "action_tag": "watch",
        "target_role_families": ["software"],
        "matched_keywords": ["python"],
        "why_matches": "test",
        "why_risky": "",
        "opt_signal": "Unknown",
        "best_matching_project": "",
        **kw,
    }


# ---------------------------------------------------------------------------
# 1. Profile storage
# ---------------------------------------------------------------------------

class TestProfileStorage:
    def test_create_profile_inserts_and_sets_active(self):
        db = _tmp_db()
        pid = create_profile("Alice", "resume text", "{}", db_path=db)
        assert pid

        active = get_active_profile(db_path=db)
        assert active is not None
        assert active["profile_id"] == pid
        assert active["is_active"] == 1

    def test_set_active_profile_flips_flag(self):
        db = _tmp_db()
        pid1 = create_profile("Alice", "resume 1", "{}", db_path=db)
        create_profile("Bob", "resume 2", "{}", db_path=db)

        # Bob is now active (created last). Flip back to Alice.
        ok = set_active_profile(pid1, db_path=db)
        assert ok

        active = get_active_profile(db_path=db)
        assert active["profile_id"] == pid1

    def test_only_one_profile_active_at_a_time(self):
        db = _tmp_db()
        create_profile("A", "", "{}", db_path=db)
        create_profile("B", "", "{}", db_path=db)
        create_profile("C", "", "{}", db_path=db)

        profiles = list_profiles(db_path=db)
        active_count = sum(1 for p in profiles if p["is_active"] == 1)
        assert active_count == 1

    def test_second_create_deactivates_first(self):
        db = _tmp_db()
        create_profile("First", "", "{}", db_path=db)
        pid2 = create_profile("Second", "", "{}", db_path=db)

        active = get_active_profile(db_path=db)
        assert active["profile_id"] == pid2

    def test_list_profiles_excludes_resume_text(self):
        db = _tmp_db()
        create_profile("Alice", "LONG RESUME TEXT", "{}", db_path=db)
        profiles = list_profiles(db_path=db)
        assert len(profiles) == 1
        # resume_text must not be included in list view
        assert "resume_text" not in profiles[0]


# ---------------------------------------------------------------------------
# 2. jobs schema columns
# ---------------------------------------------------------------------------

class TestJobsSchema:
    def test_profile_id_column_exists(self):
        db = _tmp_db()
        with connect(db) as conn:
            columns = {
                row[1]
                for row in conn.execute("PRAGMA table_info(jobs)").fetchall()
            }
        assert "profile_id" in columns

    def test_visa_sponsorship_column_exists(self):
        db = _tmp_db()
        with connect(db) as conn:
            columns = {
                row[1]
                for row in conn.execute("PRAGMA table_info(jobs)").fetchall()
            }
        assert "visa_sponsorship" in columns

    def test_profiles_table_exists(self):
        db = _tmp_db()
        with connect(db) as conn:
            tables = {
                row[0]
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }
        assert "profiles" in tables


# ---------------------------------------------------------------------------
# 3. Deduplication isolation per profile
# ---------------------------------------------------------------------------

class TestDeduplicationIsolation:
    def test_same_job_twice_is_one_row(self):
        db = _tmp_db()
        job = _sample_job()
        with connect(db) as conn:
            upsert_scraped_job(conn, job)
            upsert_scraped_job(conn, job)
            count = conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
        assert count == 1

    def test_filter_jobs_isolates_by_profile_id(self):
        """filter_jobs with profile_id returns only that profile's jobs."""
        db = _tmp_db()
        pid_a = create_profile("A", "resume a", "{}", db_path=db)
        pid_b = create_profile("B", "resume b", "{}", db_path=db)

        job_a = _sample_job(
            company="BigCorp",
            title="Data Engineer",
            apply_url="https://bigcorp.com/jobs/42",
            profile_id=pid_a,
        )
        with connect(db) as conn:
            upsert_scraped_job(conn, job_a)

        with connect(db) as conn:
            jobs_a = filter_jobs(conn, pid_a)
            jobs_b = filter_jobs(conn, pid_b)

        assert len(jobs_a) >= 1
        assert len(jobs_b) == 0

    def test_same_posting_is_stored_once_per_profile(self):
        db = _tmp_db()
        pid_a = create_profile("A", "resume a", "{}", db_path=db)
        pid_b = create_profile("B", "resume b", "{}", db_path=db)
        base = {
            "company": "SharedCorp",
            "title": "Data Engineer",
            "apply_url": "https://sharedcorp.com/jobs/42",
        }

        with connect(db) as conn:
            upsert_scraped_job(conn, _sample_job(**base, profile_id=pid_a))
            upsert_scraped_job(conn, _sample_job(**base, profile_id=pid_b))
            rows = conn.execute(
                "SELECT profile_id FROM jobs ORDER BY profile_id"
            ).fetchall()

        assert [row["profile_id"] for row in rows] == sorted([pid_a, pid_b])

    def test_visa_signal_survives_upsert_and_filter(self):
        db = _tmp_db()
        pid = create_profile("Visa", "resume", "{}", db_path=db)
        job = _sample_job(profile_id=pid, visa_sponsorship=1)

        with connect(db) as conn:
            uid = upsert_scraped_job(conn, job, check_links=False)
            stored = conn.execute(
                "SELECT visa_sponsorship FROM jobs WHERE job_uid = ?", (uid,)
            ).fetchone()
            sponsored = filter_jobs(conn, pid, visa=True)

        assert stored["visa_sponsorship"] == 1
        assert len(sponsored) == 1

    def test_dashboard_model_can_be_scoped_to_one_profile(self):
        db = _tmp_db()
        pid_a = create_profile("A", "resume a", "{}", db_path=db)
        pid_b = create_profile("B", "resume b", "{}", db_path=db)

        with connect(db) as conn:
            upsert_scraped_job(
                conn,
                _sample_job(company="OnlyA", profile_id=pid_a),
                check_links=False,
            )
            upsert_scraped_job(
                conn,
                _sample_job(company="OnlyB", profile_id=pid_b),
                check_links=False,
            )
            model = get_dashboard_model(conn, profile_id=pid_a)

        visible = [job for bucket in model["buckets"].values() for job in bucket]
        assert {job["company"] for job in visible} == {"OnlyA"}
        assert model["stats"]["total"] == 1


# ---------------------------------------------------------------------------
# 4. extract_profile_from_text
# ---------------------------------------------------------------------------

class TestExtractProfileFromText:
    def test_mechanical_engineer_resume(self):
        resume = (
            "Jane Smith\n"
            "Mechanical Engineer with 3 years of experience.\n"
            "Skills: CAD, SolidWorks, Python, MATLAB\n"
            "Working remotely from Boston, MA.\n"
            "Authorized to work in the United States.\n"
        )
        result = extract_profile_from_text(resume)
        assert "mechanical engineer" in result["roles"]
        assert "python" in result["skills"]
        assert "matlab" in result["skills"]
        assert result["visa_needed"] is False

    def test_nurse_resume_visa_needed(self):
        resume = (
            "Robert Chen - Registered Nurse, BSN\n"
            "5+ years of experience in ICU settings.\n"
            "Available for hybrid positions in New York.\n"
            "Will require H-1B visa sponsorship.\n"
        )
        result = extract_profile_from_text(resume)
        assert "nurse" in result["roles"]
        assert result["visa_needed"] is True

    def test_data_scientist_entry_level(self):
        resume = (
            "Maria Lopez - Data Scientist\n"
            "Skills: Python, PyTorch, SQL, Scikit-learn, AWS\n"
            "Entry-level candidate, recent graduate.\n"
            "Looking for remote roles in the United States.\n"
        )
        result = extract_profile_from_text(resume)
        assert any("data scientist" in r or "ml engineer" in r for r in result["roles"])
        assert "python" in result["skills"]
        assert result["experience_level"] == "entry_level"

    def test_missing_reported_when_roles_not_found(self):
        resume = "John Doe. 10 years of experience. Python, SQL."
        result = extract_profile_from_text(resume)
        assert "roles" in result["missing"]
        assert result["verified"]["roles"] is False

    def test_no_network_calls(self, monkeypatch):
        """Extraction must never make network calls."""
        import urllib.request

        calls = []

        def _track(*args, **kwargs):
            calls.append(args)
            raise AssertionError("network call made during extraction")

        monkeypatch.setattr(urllib.request, "urlopen", _track)
        result = extract_profile_from_text("Software Engineer at Acme. Python, AWS.")
        assert isinstance(result, dict)
        assert calls == [], "no network calls expected"

    def test_returns_required_keys(self):
        result = extract_profile_from_text("Data Engineer. Python, SQL, Spark.")
        required = {
            "roles", "skills", "locations", "experience_level",
            "visa_needed", "work_modes", "verified", "missing",
        }
        assert required.issubset(result.keys())


# ---------------------------------------------------------------------------
# 5. get_profile_config() overlay
# ---------------------------------------------------------------------------

class TestProfileConfigOverlay:
    def test_no_active_profile_returns_yaml_defaults(self, monkeypatch, tmp_path):
        import config
        (tmp_path / "config.yaml").write_text(
            "profile:\n  target_roles:\n    - ai engineer\n  locations:\n    - United States\n",
            encoding="utf-8",
        )
        monkeypatch.setattr(config, "CONFIG_PATH", tmp_path / "config.yaml")
        config._CONFIG_CACHE_KEY = None
        config._CONFIG_CACHE_VALUE = None

        import dashboard.db as db_mod
        monkeypatch.setattr(db_mod, "get_active_profile", lambda **_: None)

        from config import get_profile_config
        result = get_profile_config()
        assert result.get("target_roles") == ["ai engineer"]

    def test_active_profile_overlays_roles(self, monkeypatch, tmp_path):
        import config
        (tmp_path / "config.yaml").write_text(
            "profile:\n  target_roles:\n    - ai engineer\n",
            encoding="utf-8",
        )
        monkeypatch.setattr(config, "CONFIG_PATH", tmp_path / "config.yaml")
        config._CONFIG_CACHE_KEY = None
        config._CONFIG_CACHE_VALUE = None

        extracted = {
            "roles": ["mechanical engineer", "product manager"],
            "skills": ["python", "cad"],
            "locations": ["Texas"],
            "experience_level": "mid_level",
            "visa_needed": False,
            "work_modes": ["hybrid"],
        }
        import dashboard.db as db_mod
        monkeypatch.setattr(
            db_mod,
            "get_active_profile",
            lambda **_: {
                "profile_id": "test-pid",
                "name": "test",
                "extracted_json": json.dumps(extracted),
            },
        )

        from config import get_profile_config
        result = get_profile_config()
        assert result["target_roles"] == ["mechanical engineer", "product manager"]
        assert result["skills"] == ["python", "cad"]

    def test_visa_needed_sets_needs_sponsorship(self, monkeypatch, tmp_path):
        import config
        (tmp_path / "config.yaml").write_text(
            "profile:\n  target_roles: []\n",
            encoding="utf-8",
        )
        monkeypatch.setattr(config, "CONFIG_PATH", tmp_path / "config.yaml")
        config._CONFIG_CACHE_KEY = None
        config._CONFIG_CACHE_VALUE = None

        extracted = {
            "roles": ["nurse"],
            "skills": [],
            "locations": ["New York"],
            "experience_level": "senior",
            "visa_needed": True,
            "work_modes": ["hybrid"],
        }
        import dashboard.db as db_mod
        monkeypatch.setattr(
            db_mod,
            "get_active_profile",
            lambda **_: {
                "profile_id": "p2",
                "name": "nurse",
                "extracted_json": json.dumps(extracted),
            },
        )

        from config import get_profile_config
        result = get_profile_config()
        assert result.get("visa_policy") == "needs_sponsorship"


# ---------------------------------------------------------------------------
# 6. API endpoints
# ---------------------------------------------------------------------------

class TestProfileAPIEndpoints:
    @pytest.fixture
    def client(self):
        from tests.asgi_client import ASGITestClient
        from dashapi.server import app
        from dashboard.db import get_db_path, init_db
        # init_db is normally called by the FastAPI lifespan, which the
        # ASGITestClient bypasses. Call it explicitly so the profiles table
        # exists before requests hit the API.
        init_db(get_db_path())
        return ASGITestClient(app)

    def test_get_profiles_empty(self, client):
        resp = client.get("/api/profiles")
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert isinstance(data["profiles"], list)


    def test_activate_nonexistent_profile_returns_404(self, client):
        resp = client.post("/api/profiles/nonexistent-id/activate")
        assert resp.status_code == 404

    def test_dashboard_includes_profile_when_active(self, client):
        from dashboard.db import get_db_path

        profile_id = create_profile(
            "ML search",
            "ML Engineer. Python, PyTorch.",
            json.dumps({"roles": ["ML Engineer"], "skills": ["Python", "PyTorch"]}),
            db_path=get_db_path(),
        )
        set_active_profile(profile_id, db_path=get_db_path())
        resp = client.get("/api/dashboard")
        assert resp.status_code == 200
        data = resp.json()
        assert "profile" in data
        assert "profile_id" in data["profile"]

    def test_dashboard_returns_only_active_profile_jobs(self, client):
        from dashboard.db import get_db_path

        db_path = get_db_path()
        pid_a = create_profile("A", "resume a", "{}", db_path=db_path)
        pid_b = create_profile("B", "resume b", "{}", db_path=db_path)
        set_active_profile(pid_a, db_path=db_path)
        with connect(db_path) as conn:
            upsert_scraped_job(
                conn,
                _sample_job(company="OnlyA", profile_id=pid_a),
                check_links=False,
            )
            upsert_scraped_job(
                conn,
                _sample_job(company="OnlyB", profile_id=pid_b),
                check_links=False,
            )

        data = client.get("/api/dashboard").json()
        visible = [job for bucket in data["buckets"].values() for job in bucket]
        assert {job["company"] for job in visible} == {"OnlyA"}


# ---------------------------------------------------------------------------
# 7. Regression: a real scrape stamps profile_id + visa_sponsorship
# ---------------------------------------------------------------------------

class TestScrapeStampsProfileId:
    """Guard against the gap where scrape stored jobs with blank profile_id.

    This test runs the full scrape_all assembly with network disabled so it is
    fast and deterministic.
    """

    def test_scrape_all_tags_dashboard_jobs_with_active_profile(self, monkeypatch):
        from dashboard.db import create_profile, get_active_profile, init_db
        from pipeline import scrape as scrape_mod
        from pipeline import query_strategy

        init_db()
        pid = create_profile(
            "ScrapeTester",
            "AI Engineer. Python.",
            json.dumps(
                {
                    "roles": ["ai engineer"],
                    "skills": ["python"],
                    "locations": ["United States", "Remote"],
                    "experience_level": "entry_level",
                    "visa_needed": True,
                    "work_modes": ["remote"],
                }
            ),
        )

        # Disable every source so no network tasks are built.
        monkeypatch.setattr(query_strategy, "source_enabled", lambda *a, **k: False)
        monkeypatch.setattr(
            scrape_mod, "get_enabled_companies", lambda *a, **k: []
        )
        # No ATS companies => no apify fallback either.
        monkeypatch.setattr(
            scrape_mod, "get_unknown_ats_companies", lambda *a, **k: []
        )
        # Make the parallel executor return one synthetic completed task so the
        # pipeline has at least one raw job to assemble.
        def _fake_execute(tasks, *, max_workers, timeout_seconds):
            fake_job = {
                "company": "TestCo",
                "title": "AI Engineer",
                "location": "Remote, United States",
                "apply_url": "https://testco.com/jobs/1",
                "source": "greenhouse",
                "ats_type": "greenhouse",
                "resume_match_score": 88,
                "freshness": "New",
                "freshness_trust": "confirmed_posted_date",
                "action_tag": "watch",
                "target_role_families": ["software"],
                "matched_keywords": ["python"],
                "why_matches": "ai engineer",
                "why_risky": "",
                "opt_signal": "Unknown",
                "best_matching_project": "",
                "apply_window_score": 80,
                "apply_window_label": "high",
                "apply_window_reasons": ["x"],
                "apply_window_next_action": "Review",
                "description": "We sponsor H-1B visas for this role.",
                "full_text": "",
            }
            completed = [
                (
                    "greenhouse",
                    "TestCo",
                    {"jobs": [fake_job], "error": None},
                )
            ]
            return completed, [], []

        monkeypatch.setattr(
            scrape_mod, "_execute_source_tasks", _fake_execute
        )
        # Persisting snapshots touches the registry/disk; stub it.
        monkeypatch.setattr(
            scrape_mod, "_persist_direct_source_snapshots", lambda *a, **k: {}
        )

        result = scrape_mod.scrape_all(
            max_selected=5, dry_run=True, max_workers=1, run_window="morning"
        )
        assert get_active_profile()["profile_id"] == pid

        jobs = result.get("dashboard_jobs", [])
        assert jobs, "expected at least one assembled dashboard job"
        for job in jobs:
            assert job.get("profile_id") == pid, (
                f"dashboard job missing profile_id: {job.get('company')}"
            )
            # Visa sponsorship text in the description must be detected.
            assert job.get("visa_sponsorship") == 1


# ---------------------------------------------------------------------------
# 8. detect_visa_sponsorship
# ---------------------------------------------------------------------------

class TestDetectVisaSponsorship:
    def test_explicit_support_detected(self):
        from ranking.guardrails import detect_visa_sponsorship

        job = {
            "title": "AI Engineer",
            "description": "We sponsor H-1B visas for this role.",
        }
        assert detect_visa_sponsorship(job) == 1

    def test_no_text_is_not_support(self):
        from ranking.guardrails import detect_visa_sponsorship

        assert detect_visa_sponsorship({"title": "AI Engineer"}) == 0

    def test_no_support_mentioned(self):
        from ranking.guardrails import detect_visa_sponsorship

        job = {
            "title": "Backend Engineer",
            "description": "No sponsorship available for this position.",
        }
        # Only explicit *support* counts; this is not support.
        assert detect_visa_sponsorship(job) == 0
