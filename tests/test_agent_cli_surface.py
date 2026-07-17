"""Agent-friendly CLI surface tests."""
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import jobhunt
from dashboard.db import connect, init_db, set_db_path, upsert_scraped_job


class AgentCLISurfaceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self.tmp.name)
        self.db_path = self.tmp_path / "dashboard.db"
        init_db(self.db_path)
        set_db_path(self.db_path)
        self.config_path = self.tmp_path / "config.yaml"
        self.example_path = self.tmp_path / "config.example.yaml"
        self.example_path.write_text(
            """
app:
  name: Opportune
profile:
  candidate: {name: '', email: ''}
  timeline: {max_age_days: 7}
sources:
  - name: free_ats_scrape
    label: Free ATS
    enabled: true
    mode: free
    api_key_env: null
  - name: serpapi_google_jobs
    label: SerpAPI
    enabled: true
    mode: paid
    api_key_env: SERPAPI_API_KEY
storage:
  home: tracker
  sqlite_file: dashboard.db
dashboard:
  host: 127.0.0.1
  port: 8770
""".strip(),
            encoding="utf-8",
        )

    def tearDown(self):
        set_db_path(None)
        self.tmp.cleanup()

    def test_doctor_reports_missing_paid_key_and_profile_warning(self):
        with patch("config.CONFIG_PATH", self.config_path), patch("config.CONFIG_EXAMPLE_PATH", self.example_path), patch("config.TRACKER_DIR", self.tmp_path), patch.dict("os.environ", {"SERPAPI_API_KEY": ""}, clear=False):
            result = jobhunt.run_doctor()
        self.assertTrue(result["ok"])
        codes = {item["code"] for item in result["checks"]}
        self.assertIn("config_missing", codes)
        self.assertIn("missing_api_key", codes)
        self.assertIn("profile_missing", codes)

    def test_quickstart_creates_config_and_seeds_demo_when_empty(self):
        with patch("config.CONFIG_PATH", self.config_path), patch("config.CONFIG_EXAMPLE_PATH", self.example_path):
            result = jobhunt.run_quickstart(seed_demo=True)
        self.assertTrue(result["ok"])
        self.assertTrue(self.config_path.exists())
        self.assertGreaterEqual(result["total_jobs"], 3)

    def test_tools_manifest_contains_safe_agent_commands(self):
        manifest = jobhunt.tools_manifest()
        names = {tool["name"] for tool in manifest["tools"]}
        self.assertIn("doctor", names)
        self.assertIn("quickstart", names)
        self.assertIn("smart scrape", names)
        self.assertIn("jobs list", names)
        self.assertIn("jobs update", names)
        self.assertTrue(all("safety" in tool for tool in manifest["tools"]))
        self.assertEqual(manifest["short_command"], "uv run opp")

    def test_start_is_a_first_run_alias_for_dashboard(self):
        args = jobhunt.build_parser().parse_args(
            ["start", "--host", "127.0.0.1", "--port", "8770"]
        )

        self.assertIs(args.func, jobhunt.cmd_dashboard)
        self.assertEqual(args.host, "127.0.0.1")
        self.assertEqual(args.port, 8770)

    def test_resume_bypass_command_is_not_exposed(self):
        help_text = jobhunt.build_parser().format_help()
        self.assertNotIn("resume", help_text)

    def test_config_set_reuses_yaml_loader_and_writes_nested_value(self):
        self.config_path.write_text(self.example_path.read_text(), encoding="utf-8")
        args = SimpleNamespace(
            action="set",
            key="profile.timeline.max_age_days",
            value="3",
            json=False,
        )

        with patch("config.CONFIG_PATH", self.config_path), patch(
            "config.CONFIG_EXAMPLE_PATH", self.example_path
        ):
            jobhunt.cmd_config(args)

        updated = jobhunt._load_yaml_file(self.config_path)
        self.assertEqual(updated["profile"]["timeline"]["max_age_days"], 3)

    def test_jobs_list_and_update_use_local_sqlite(self):
        with connect(self.db_path) as conn:
            uid = upsert_scraped_job(conn, {"company": "Acme", "title": "AI Engineer", "resume_match_score": 91, "action_tag": "apply_now"})
        listed = jobhunt.run_jobs_list(limit=10)
        self.assertEqual(listed["jobs"][0]["job_uid"], uid)
        updated = jobhunt.run_jobs_update(uid, "applied", "sent application")
        self.assertTrue(updated["ok"])
        applied = jobhunt.run_jobs_list(status="applied", limit=10)
        self.assertEqual(applied["jobs"][0]["note"], "sent application")

    def test_smart_scrape_stops_after_enough_high_apply_windows(self):
        fake_result = {
            "jobs": [],
            "raw_count": 2,
            "source_results": {"greenhouse": 2},
            "failed_sources": [],
            "dashboard_jobs": [
                {"company": "A", "title": "RAG Engineer", "apply_url": "https://example.com/a", "source": "greenhouse", "resume_match_score": 92, "freshness": "New (0-24h)", "action_tag": "apply_now", "apply_window_label": "high"},
                {"company": "B", "title": "AI Engineer", "apply_url": "https://example.com/b", "source": "ashby", "resume_match_score": 88, "freshness": "New (0-24h)", "action_tag": "apply_now", "apply_window_label": "high"},
            ],
        }
        with patch("pipeline.smart_scrape.scrape_all", return_value=fake_result) as mocked:
            result = jobhunt.run_smart_scrape(live=False, min_high=2)
        self.assertTrue(result["ok"])
        self.assertEqual(result["windows_run"], ["morning"])
        self.assertEqual(result["high_apply_windows"], 2)
        mocked.assert_called_once()

    def test_cli_json_subcommands_are_valid_json(self):
        # Smoke-check the pure manifest output without relying on subprocesses.
        text = json.dumps(jobhunt.tools_manifest())
        self.assertIn("jobs update", text)


if __name__ == "__main__":
    unittest.main()
