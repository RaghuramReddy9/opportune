import tempfile
import unittest
from pathlib import Path

from core.source_health import (
    DEFAULT_HEALTH_PATH,
    classify_error,
    filter_runnable_tasks,
    health_key,
    record_source_failure,
    record_source_success,
    should_skip_source,
    summarize_health,
)
from config import TRACKER_DIR


class SourceHealthTests(unittest.TestCase):
    def test_default_health_state_lives_directly_in_tracker(self):
        self.assertEqual(DEFAULT_HEALTH_PATH, TRACKER_DIR / "source_health.json")

    def test_classifies_quota_and_blocked_errors(self):
        self.assertEqual(classify_error("HTTP 429 rate limit"), "rate_limited")
        self.assertEqual(classify_error("HTTP 402 quota exhausted"), "rate_limited")
        self.assertEqual(classify_error("HTTP 403 Cloudflare forbidden"), "blocked")
        self.assertEqual(classify_error("HTTP 503 temporarily unavailable"), "server_or_timeout")
        self.assertEqual(classify_error("bad parse"), "failed")

    def test_health_key_is_global_for_board_sources_and_per_company_for_ats(self):
        self.assertEqual(health_key("api_serpapi", "api_serpapi"), "api_serpapi")
        self.assertEqual(health_key("greenhouse", "Stripe"), "greenhouse:stripe")

    def test_rate_limit_failure_opens_circuit_and_skips_future_task(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "source_health.json"
            record_source_failure("api_serpapi", "api_serpapi", "429 quota exhausted", path=path)

            skip, record = should_skip_source("api_serpapi", "api_serpapi", path=path)

            self.assertTrue(skip)
            self.assertEqual(record["last_error_category"], "rate_limited")
            self.assertTrue(record["circuit_open_until"])

    def test_failure_state_never_persists_raw_provider_error_text(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "source_health.json"
            raw_secret = "provider-secret-value"
            record = record_source_failure(
                "api_serpapi",
                "api_serpapi",
                f"HTTP 401 response leaked {raw_secret}",
                path=path,
            )

            self.assertNotIn(raw_secret, path.read_text(encoding="utf-8"))
            self.assertEqual(record["last_error"], "[redacted]")
            self.assertEqual(record["last_error_category"], "failed")

    def test_success_clears_open_circuit(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "source_health.json"
            record_source_failure("wellfound", "wellfound", "HTTP 403", path=path)
            record_source_success("wellfound", "wellfound", jobs=12, path=path)

            skip, record = should_skip_source("wellfound", "wellfound", path=path)

            self.assertFalse(skip)
            self.assertEqual(record["status"], "ok")
            self.assertEqual(record["circuit_open_until"], "")

    def test_filter_runnable_tasks_returns_skipped_circuit_sources(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "source_health.json"
            record_source_failure("api_serpapi", "api_serpapi", "429", path=path)
            tasks = [
                ("api_serpapi", "api_serpapi", lambda: None, None),
                ("greenhouse", "Stripe", lambda: None, {"company_name": "Stripe"}),
            ]

            runnable, skipped = filter_runnable_tasks(tasks, path=path)

            self.assertEqual([t[0] for t in runnable], ["greenhouse"])
            self.assertEqual(len(skipped), 1)
            self.assertEqual(skipped[0]["source"], "api_serpapi")

    def test_summarize_health_counts_open_circuits(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "source_health.json"
            record_source_failure("api_serpapi", "api_serpapi", "429", path=path)
            summary = summarize_health(path=path)

            self.assertEqual(summary["tracked_sources"], 1)
            self.assertEqual(summary["open_circuits"], 1)


if __name__ == "__main__":
    unittest.main()
