"""RED tests for the dashboard SQLite data layer."""
import sqlite3
import tempfile
import unittest
from pathlib import Path

from dashboard.db import (
    connect,
    get_dashboard_model,
    init_db,
    list_jobs,
    make_job_uid,
    set_job_note,
    set_job_status,
    upsert_scraped_job,
)


class DashboardDBTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmp.name) / "test_dashboard.db"
        init_db(self.db_path)

    def tearDown(self):
        self.tmp.cleanup()

    def _sample_job(self, **overrides):
        job = {
            "company": "Stripe",
            "title": "Applied AI Engineer, New Grad",
            "location": "New York, NY",
            "apply_url": "https://stripe.com/jobs/123",
            "source": "greenhouse",
            "ats_type": "greenhouse",
            "resume_match_score": 95,
            "freshness": "New (0-24h)",
            "freshness_trust": "confirmed_posted_date",
            "action_tag": "apply_now",
            "target_role_families": ["applied_ai", "genai_llm_rag"],
            "matched_keywords": ["rag", "llm", "fastapi"],
            "why_matches": "Strong RAG + FastAPI fit",
            "why_risky": "",
            "opt_signal": "Strong",
            "best_matching_project": "Multi-Agent RAG Pipeline",
        }
        job.update(overrides)
        return job

    def test_init_db_creates_schema(self):
        with connect(self.db_path) as conn:
            tables = [
                row[0]
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            ]
        self.assertIn("jobs", tables)

    def test_upsert_inserts_and_returns_uid(self):
        with connect(self.db_path) as conn:
            uid = upsert_scraped_job(conn, self._sample_job())
        self.assertTrue(uid)
        with connect(self.db_path) as conn:
            job = conn.execute("SELECT * FROM jobs WHERE job_uid = ?", (uid,)).fetchone()
        self.assertEqual(job["company"], "Stripe")
        self.assertEqual(job["status"], "discovered")

    def test_upsert_is_idempotent(self):
        job = self._sample_job()
        with connect(self.db_path) as conn:
            uid1 = upsert_scraped_job(conn, job)
        with connect(self.db_path) as conn:
            uid2 = upsert_scraped_job(conn, job)
        self.assertEqual(uid1, uid2)
        with connect(self.db_path) as conn:
            count = conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
        self.assertEqual(count, 1)

    def test_connection_rolls_back_when_operation_fails(self):
        with self.assertRaisesRegex(RuntimeError, "abort"):
            with connect(self.db_path) as conn:
                upsert_scraped_job(conn, self._sample_job())
                raise RuntimeError("abort")

        with connect(self.db_path) as conn:
            count = conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
        self.assertEqual(count, 0)

    def test_upsert_updates_score_on_rerun(self):
        job = self._sample_job(resume_match_score=80)
        with connect(self.db_path) as conn:
            uid = upsert_scraped_job(conn, job)
        job["resume_match_score"] = 95
        with connect(self.db_path) as conn:
            upsert_scraped_job(conn, job)
        with connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT resume_match_score FROM jobs WHERE job_uid = ?", (uid,)
            ).fetchone()
        self.assertEqual(row[0], 95)

    def test_pool_metadata_is_persisted_and_visible_in_pool_bucket(self):
        job = self._sample_job(
            action_tag="pool",
            description="Build customer-facing AI systems.",
            work_mode="hybrid",
            experience_level="mid_level",
            employment_type="full_time",
            pool_match_reason="Title matches configured role: AI Engineer",
        )
        with connect(self.db_path) as conn:
            uid = upsert_scraped_job(conn, job, check_links=False)
            stored = conn.execute("SELECT * FROM jobs WHERE job_uid = ?", (uid,)).fetchone()
            model = get_dashboard_model(conn)

        self.assertEqual(stored["work_mode"], "hybrid")
        self.assertEqual(stored["experience_level"], "mid_level")
        self.assertIn("customer-facing", stored["description"])
        self.assertEqual(model["stats"]["pool"], 1)
        self.assertEqual(model["buckets"]["pool"][0]["job_uid"], uid)

    def test_pool_refresh_does_not_downgrade_strict_watch_bucket(self):
        strict = self._sample_job(action_tag="watch", resume_match_score=80)
        with connect(self.db_path) as conn:
            uid = upsert_scraped_job(conn, strict, check_links=False)
            upsert_scraped_job(
                conn,
                {**strict, "action_tag": "pool", "resume_match_score": 70},
                check_links=False,
            )
            stored = conn.execute("SELECT action_tag FROM jobs WHERE job_uid = ?", (uid,)).fetchone()
        self.assertEqual(stored["action_tag"], "watch")

    def test_upsert_updates_location_and_source_metadata_on_rerun(self):
        job = self._sample_job(location="", source="api_serpapi", action_tag="watch")
        with connect(self.db_path) as conn:
            uid = upsert_scraped_job(conn, job)
        job.update({"location": "Remote, United States", "source": "greenhouse", "action_tag": "apply_now"})
        with connect(self.db_path) as conn:
            upsert_scraped_job(conn, job)
        with connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT location, source, action_tag FROM jobs WHERE job_uid = ?", (uid,)
            ).fetchone()
        self.assertEqual(row["location"], "Remote, United States")
        self.assertEqual(row["source"], "greenhouse")
        self.assertEqual(row["action_tag"], "apply_now")

    def test_set_job_status_to_applied(self):
        with connect(self.db_path) as conn:
            uid = upsert_scraped_job(conn, self._sample_job())
            ok = set_job_status(conn, uid, "applied")
        self.assertTrue(ok)
        with connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT status, date_applied FROM jobs WHERE job_uid = ?", (uid,)
            ).fetchone()
        self.assertEqual(row["status"], "applied")
        self.assertTrue(row["date_applied"])

    def test_set_job_status_unknown_uid_returns_false(self):
        with connect(self.db_path) as conn:
            ok = set_job_status(conn, "nonexistent|uid|00000000", "applied")
        self.assertFalse(ok)

    def test_set_job_note(self):
        with connect(self.db_path) as conn:
            uid = upsert_scraped_job(conn, self._sample_job())
            set_job_note(conn, uid, "Applied via referral")
            row = conn.execute("SELECT note FROM jobs WHERE job_uid = ?", (uid,)).fetchone()
        self.assertEqual(row["note"], "Applied via referral")

    def test_get_dashboard_model_groups_buckets(self):
        with connect(self.db_path) as conn:
            upsert_scraped_job(conn, self._sample_job(action_tag="apply_now"))
            upsert_scraped_job(
                conn, self._sample_job(company="Airbnb", title="AI Engineer", action_tag="watch")
            )
            upsert_scraped_job(
                conn, self._sample_job(company="BadCo", title="Old Role", action_tag="skip")
            )
            model = get_dashboard_model(conn)
        self.assertEqual(model["stats"]["apply_now"], 1)
        self.assertEqual(model["stats"]["watch"], 1)
        skip_companies = {j["company"] for j in model["buckets"]["skip"]}
        self.assertIn("BadCo", skip_companies)

    def test_active_pipeline_shows_applied(self):
        with connect(self.db_path) as conn:
            uid = upsert_scraped_job(conn, self._sample_job())
            set_job_status(conn, uid, "applied")
            model = get_dashboard_model(conn)
        self.assertEqual(model["stats"]["active_pipeline"], 1)
        self.assertEqual(model["buckets"]["active_pipeline"][0]["company"], "Stripe")

    def test_list_jobs_filters_by_status(self):
        with connect(self.db_path) as conn:
            uid = upsert_scraped_job(conn, self._sample_job())
            upsert_scraped_job(
                conn, self._sample_job(company="Brex", title="AI Engineer 2")
            )
            set_job_status(conn, uid, "applied")
            applied = list_jobs(conn, status="applied")
        self.assertEqual(len(applied), 1)
        self.assertEqual(applied[0]["company"], "Stripe")

    def test_keywords_parsed_as_list(self):
        with connect(self.db_path) as conn:
            upsert_scraped_job(conn, self._sample_job())
            jobs = list_jobs(conn)
        self.assertIsInstance(jobs[0]["matched_keywords"], list)
        self.assertIn("rag", jobs[0]["matched_keywords"])

    def test_apply_window_fields_are_persisted_and_parsed(self):
        with connect(self.db_path) as conn:
            uid = upsert_scraped_job(conn, self._sample_job(
                apply_window_score=93,
                apply_window_label="high",
                apply_window_reasons=["Fresh posting", "Strong skill match"],
                apply_window_next_action="Apply today",
            ))
            job = conn.execute("SELECT * FROM jobs WHERE job_uid = ?", (uid,)).fetchone()
        self.assertEqual(job["apply_window_score"], 93)
        with connect(self.db_path) as conn:
            jobs = list_jobs(conn)
        self.assertEqual(jobs[0]["apply_window_label"], "high")
        self.assertEqual(jobs[0]["apply_window_reasons"], ["Fresh posting", "Strong skill match"])

    def test_init_db_migrates_existing_db_with_apply_window_columns(self):
        legacy = Path(self.tmp.name) / "legacy.db"
        raw = sqlite3.connect(legacy)
        raw.execute("CREATE TABLE jobs (id INTEGER PRIMARY KEY AUTOINCREMENT, job_uid TEXT UNIQUE NOT NULL, company TEXT NOT NULL, title TEXT NOT NULL)")
        raw.commit()
        raw.close()
        init_db(legacy)
        with connect(legacy) as conn:
            columns = {row["name"] for row in conn.execute("PRAGMA table_info(jobs)").fetchall()}
        self.assertIn("apply_window_score", columns)
        self.assertIn("apply_window_reasons", columns)

    def test_init_db_upgrades_existing_db_with_enrichment_queue_and_demo_flags(self):
        legacy = Path(self.tmp.name) / "legacy_aux.db"
        raw = sqlite3.connect(legacy)
        raw.execute(
            """CREATE TABLE jobs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_uid TEXT UNIQUE NOT NULL,
                company TEXT NOT NULL,
                title TEXT NOT NULL,
                source TEXT DEFAULT '',
                is_demo INTEGER DEFAULT 0
            )"""
        )
        raw.execute(
            "INSERT INTO jobs (job_uid, company, title, source, is_demo) VALUES (?, ?, ?, ?, 0)",
            ("sample|role|00000000", "SampleCo", "Sample Role", "sample_data"),
        )
        raw.commit()
        raw.close()

        init_db(legacy)

        with connect(legacy) as conn:
            tables = {
                row["name"]
                for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
            }
            is_demo = conn.execute(
                "SELECT is_demo FROM jobs WHERE job_uid = 'sample|role|00000000'"
            ).fetchone()[0]
        self.assertIn("enrichment_queue", tables)
        self.assertEqual(is_demo, 1)

    def test_make_job_uid_stable(self):
        job = self._sample_job()
        self.assertEqual(make_job_uid(job), make_job_uid(dict(job)))
        self.assertEqual(
            make_job_uid(job),
            "stripe|applied-ai-engineer,-new-grad|4985e4db",
        )
        tracked = dict(job, apply_url=f"{job['apply_url']}?utm_source=google#apply")
        self.assertEqual(make_job_uid(job), make_job_uid(tracked))

    def test_upsert_merges_same_company_title_even_when_url_changes(self):
        first = self._sample_job(apply_url="https://jobs.example.com/first")
        second = self._sample_job(apply_url="https://jobs.example.com/second")
        with connect(self.db_path) as conn:
            uid1 = upsert_scraped_job(conn, first)
            uid2 = upsert_scraped_job(conn, second)
            count = conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
        self.assertEqual(uid1, uid2)
        self.assertEqual(count, 1)

    def test_upsert_merges_company_title_despite_surrounding_whitespace(self):
        first = self._sample_job(
            company="Scale AI",
            title=" Machine Learning Research Engineer",
            apply_url="https://jobs.example.com/first",
        )
        second = self._sample_job(
            company=" Scale AI ",
            title="Machine Learning Research Engineer ",
            apply_url="https://jobs.example.com/second",
        )
        with connect(self.db_path) as conn:
            uid1 = upsert_scraped_job(conn, first)
            uid2 = upsert_scraped_job(conn, second)
            count = conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
        self.assertEqual(uid1, uid2)
        self.assertEqual(count, 1)

    def test_dashboard_model_collapses_legacy_duplicate_rows(self):
        job = self._sample_job()
        with connect(self.db_path) as conn:
            uid = upsert_scraped_job(conn, job)
            conn.execute(
                """INSERT INTO jobs (
                    job_uid, company, title, location, apply_url, source,
                    resume_match_score, action_tag, status, date_updated
                ) SELECT ?, company, title, location, apply_url, source,
                    resume_match_score, action_tag, status, date_updated
                  FROM jobs WHERE job_uid = ?""",
                ("legacy-randomized-uid", uid),
            )
            model = get_dashboard_model(conn)
        visible = [item for bucket in model["buckets"].values() for item in bucket]
        self.assertEqual(model["stats"]["total"], 1)
        self.assertEqual(len(visible), 1)


if __name__ == "__main__":
    unittest.main()
