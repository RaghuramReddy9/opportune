"""Incremental source-snapshot catalog tests."""
import tempfile
import unittest
from pathlib import Path

from dashboard.db import (
    connect,
    get_catalog_stats,
    init_db,
    reconcile_source_snapshot,
    start_scrape_run,
)


class JobCatalogTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmp.name) / "catalog.db"
        init_db(self.db_path)

    def tearDown(self):
        self.tmp.cleanup()

    @staticmethod
    def job(**overrides):
        value = {
            "company": "Example AI",
            "title": "AI Engineer I",
            "location": "Remote, United States",
            "apply_url": "https://boards.example/jobs/123?utm_source=test",
            "job_id": "123",
            "description": "Build reliable RAG services.",
        }
        value.update(overrides)
        return value

    def reconcile(self, conn, jobs, timestamp):
        run_id = start_scrape_run(conn, "morning", started_at=timestamp)
        return reconcile_source_snapshot(
            conn,
            run_id=run_id,
            source_key="greenhouse",
            source_name="Example AI",
            jobs=jobs,
            seen_at=timestamp,
        )

    def test_first_snapshot_discovers_then_repeat_refreshes(self):
        with connect(self.db_path) as conn:
            first = self.reconcile(conn, [self.job()], "2026-07-15T10:00:00Z")
            second = self.reconcile(conn, [self.job()], "2026-07-15T12:00:00Z")
            row = conn.execute("SELECT * FROM job_catalog").fetchone()

        self.assertEqual(first["discovered"], 1)
        self.assertEqual(second["refreshed"], 1)
        self.assertEqual(row["first_seen_at"], "2026-07-15T10:00:00Z")
        self.assertEqual(row["last_seen_at"], "2026-07-15T12:00:00Z")
        self.assertEqual(row["listing_state"], "active")

    def test_content_change_updates_hash_and_change_time(self):
        with connect(self.db_path) as conn:
            self.reconcile(conn, [self.job()], "2026-07-15T10:00:00Z")
            result = self.reconcile(
                conn,
                [self.job(description="Build reliable agent and RAG services.")],
                "2026-07-15T12:00:00Z",
            )
            row = conn.execute("SELECT content_changed_at FROM job_catalog").fetchone()

        self.assertEqual(result["changed"], 1)
        self.assertEqual(row["content_changed_at"], "2026-07-15T12:00:00Z")

    def test_two_successful_omissions_close_and_later_snapshot_reopens(self):
        with connect(self.db_path) as conn:
            self.reconcile(conn, [self.job()], "2026-07-15T10:00:00Z")
            first_miss = self.reconcile(conn, [], "2026-07-15T12:00:00Z")
            state_one = conn.execute("SELECT listing_state FROM job_catalog").fetchone()[0]
            second_miss = self.reconcile(conn, [], "2026-07-15T14:00:00Z")
            state_two = conn.execute("SELECT listing_state FROM job_catalog").fetchone()[0]
            self.reconcile(conn, [self.job()], "2026-07-15T16:00:00Z")
            reopened = conn.execute(
                "SELECT listing_state, consecutive_misses, missing_since FROM job_catalog"
            ).fetchone()

        self.assertEqual(first_miss["missing"], 1)
        self.assertEqual(state_one, "missing")
        self.assertEqual(second_miss["closed"], 1)
        self.assertEqual(state_two, "closed")
        self.assertEqual(tuple(reopened), ("active", 0, ""))

    def test_source_scopes_do_not_close_each_others_jobs(self):
        with connect(self.db_path) as conn:
            run_one = start_scrape_run(conn, "morning")
            reconcile_source_snapshot(
                conn,
                run_id=run_one,
                source_key="greenhouse",
                source_name="Example AI",
                jobs=[self.job()],
            )
            run_two = start_scrape_run(conn, "morning")
            reconcile_source_snapshot(
                conn,
                run_id=run_two,
                source_key="greenhouse",
                source_name="Other AI",
                jobs=[self.job(company="Other AI", job_id="456")],
            )
            states = get_catalog_stats(conn)

        self.assertEqual(states["active"], 2)
        self.assertEqual(states["missing"], 0)


if __name__ == "__main__":
    unittest.main()
