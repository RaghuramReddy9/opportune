"""Deterministic tests for the local recurring scheduler."""
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from dashboard.db import create_profile, init_db, set_db_path
from pipeline.scheduler import (
    ScheduleConfig,
    SchedulerLock,
    run_scheduled_once,
)


class SchedulerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.state_path = root / "state.json"
        self.lock_path = root / "scheduler.lock"
        self.db_path = root / "dashboard.db"
        init_db(self.db_path)
        create_profile("Scheduler", "private", json.dumps({"roles": ["AI Engineer"], "target_levels": ["entry_level"], "locations": ["United States"], "work_modes": ["remote"], "work_focuses": ["applied_ai"], "visa_policy": "none", "timeline": {"max_age_days": 7}}), db_path=self.db_path)
        set_db_path(self.db_path)
        self.now = datetime(2026, 7, 15, 12, 0, tzinfo=timezone.utc)
        self.config = ScheduleConfig(180, 360, 0, 30)

    def tearDown(self):
        set_db_path(None)
        self.tmp.cleanup()

    def test_first_run_executes_direct_and_board_then_persists_due_times(self):
        calls = []

        def runner(**kwargs):
            calls.append(kwargs)
            return {"raw_count": 12, "dashboard_jobs": [{"title": "AI Engineer"}], "failed_sources": []}

        result = run_scheduled_once(
            now=self.now,
            schedule=self.config,
            state_path=self.state_path,
            lock_path=self.lock_path,
            scrape_runner=runner,
            jitter_fn=lambda _upper: 0,
        )

        self.assertTrue(result["ok"])
        self.assertEqual(
            calls,
            [
                {"window": "morning", "source_group": "direct"},
                {"window": "morning", "source_group": "board"},
            ],
        )
        state = json.loads(self.state_path.read_text())
        self.assertEqual(state["direct"]["next_run_at"], "2026-07-15T15:00:00Z")
        self.assertEqual(state["board"]["next_run_at"], "2026-07-15T18:00:00Z")
        self.assertFalse(self.lock_path.exists())

    def test_not_due_run_is_a_noop(self):
        self.test_first_run_executes_direct_and_board_then_persists_due_times()
        calls = []
        result = run_scheduled_once(
            now=self.now,
            schedule=self.config,
            state_path=self.state_path,
            lock_path=self.lock_path,
            scrape_runner=lambda **kwargs: calls.append(kwargs) or {},
            jitter_fn=lambda _upper: 0,
        )
        self.assertTrue(result["ok"])
        self.assertEqual(result["skipped"], ["direct", "board"])
        self.assertEqual(calls, [])

    def test_one_task_failure_does_not_prevent_the_other(self):
        calls = []

        def runner(**kwargs):
            calls.append(kwargs["source_group"])
            if kwargs["source_group"] == "direct":
                raise RuntimeError("temporary outage")
            return {"raw_count": 2, "dashboard_jobs": [], "failed_sources": []}

        result = run_scheduled_once(
            now=self.now,
            schedule=self.config,
            state_path=self.state_path,
            lock_path=self.lock_path,
            scrape_runner=runner,
            jitter_fn=lambda _upper: 0,
        )
        self.assertFalse(result["ok"])
        self.assertEqual(calls, ["direct", "board"])
        self.assertEqual([item["status"] for item in result["ran"]], ["failed", "completed"])

    def test_existing_lock_prevents_overlap(self):
        with SchedulerLock(self.lock_path):
            result = run_scheduled_once(
                now=self.now,
                schedule=self.config,
                state_path=self.state_path,
                lock_path=self.lock_path,
                scrape_runner=lambda **_kwargs: {},
            )
        self.assertFalse(result["ok"])
        self.assertTrue(result["already_running"])


if __name__ == "__main__":
    unittest.main()
