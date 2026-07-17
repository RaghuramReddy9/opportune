import time
import unittest
from unittest.mock import patch

from pipeline.scrape import _execute_source_tasks, _scrape_with_retry, _within_timeline


class PipelineExecutionTests(unittest.TestCase):
    def test_retry_wrapper_calls_independent_source_without_argument(self):
        calls = []

        def scrape():
            calls.append(True)
            return {"jobs": [{"title": "AI Engineer"}], "raw_count": 1, "error": None}

        result = _scrape_with_retry(scrape, None)

        self.assertEqual(result["raw_count"], 1)
        self.assertEqual(calls, [True])

    def test_source_execution_uses_one_global_deadline(self):
        def slow_scrape():
            time.sleep(0.15)
            return {"jobs": [], "raw_count": 0, "error": None}

        tasks = [("slow", "slow", slow_scrape, None)]
        with (
            patch("core.source_health.filter_runnable_tasks", return_value=(tasks, [])),
            patch("core.source_health.record_source_failure") as failure,
            patch("core.source_health.record_source_success"),
        ):
            started = time.monotonic()
            completed, failures, skipped = _execute_source_tasks(
                tasks, max_workers=1, timeout_seconds=0.01
            )
            elapsed = time.monotonic() - started

        self.assertLess(elapsed, 0.1)
        self.assertEqual(completed, [])
        self.assertEqual(skipped, [])
        self.assertEqual(failures[0]["source"], "slow")
        failure.assert_called_once()

    def test_source_execution_reports_circuit_breaker_skips(self):
        tasks = [("blocked", "blocked", lambda: {}, None)]
        skip = {"source": "blocked", "reason": "circuit_open"}
        with patch("core.source_health.filter_runnable_tasks", return_value=([], [skip])):
            completed, failures, skipped = _execute_source_tasks(
                tasks, max_workers=1, timeout_seconds=1
            )

        self.assertEqual(completed, [])
        self.assertEqual(failures, [])
        self.assertEqual(skipped, [skip])

    def test_configured_timeline_controls_dated_job_window(self):
        job = {"posted_date": "2026-07-10", "freshness": "This Week (3-7d)"}

        with patch("core.freshness.datetime") as clock:
            from datetime import datetime, timezone

            clock.now.return_value = datetime(2026, 7, 14, tzinfo=timezone.utc)
            clock.fromisoformat.side_effect = datetime.fromisoformat
            self.assertFalse(_within_timeline(job, 3))
            self.assertTrue(_within_timeline(job, 7))


if __name__ == "__main__":
    unittest.main()
