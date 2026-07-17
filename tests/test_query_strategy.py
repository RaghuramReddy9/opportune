"""Tests for pipeline/query_strategy.source_enabled config intersection."""
import unittest
from unittest.mock import patch
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class QueryStrategyTests(unittest.TestCase):
    def test_queries_use_configured_roles_without_resume_or_experience_terms(self):
        from pipeline.query_strategy import get_query_set

        profile = {
            "target_roles": ["AI Engineer", "FDE", "Data + AI Engineer"],
            "locations": ["United States", "Remote US"],
        }
        with patch("config.get_profile_config", return_value=profile):
            queries = get_query_set("morning")

        self.assertEqual(
            queries,
            [
                "AI Engineer United States",
                "FDE United States",
                "Data AI Engineer United States",
            ],
        )
        joined = " ".join(queries).lower()
        self.assertNotIn("new grad", joined)
        self.assertNotIn("remote", joined)
        self.assertNotIn("rag", joined)

    def test_source_enabled_respects_config_disabled(self):
        """When config says serpapi_google_jobs is disabled, api_serpapi must
        not be enabled even if the window plan includes it."""
        from pipeline.query_strategy import source_enabled

        fake_sources = [{"name": "serpapi_google_jobs", "enabled": False}]
        with patch("config.load_config", return_value={"sources": fake_sources}):
            self.assertFalse(source_enabled("api_serpapi", "morning"))

    def test_source_enabled_respects_config_enabled(self):
        """When config enables serpapi and the window plan includes it, source
        is enabled."""
        from pipeline.query_strategy import source_enabled

        fake_sources = [{"name": "serpapi_google_jobs", "enabled": True}]
        with patch("config.load_config", return_value={"sources": fake_sources}):
            self.assertTrue(source_enabled("api_serpapi", "morning"))

    def test_ats_disabled_when_free_ats_scrape_off(self):
        """When free_ats_scrape is disabled in config, all ATS sources are
        disabled."""
        from pipeline.query_strategy import source_enabled

        fake_sources = [{"name": "free_ats_scrape", "enabled": False}]
        with patch("config.load_config", return_value={"sources": fake_sources}):
            self.assertFalse(source_enabled("greenhouse", "morning"))
            self.assertFalse(source_enabled("ashby", "morning"))

    def test_ats_enabled_when_free_ats_scrape_on(self):
        """When free_ats_scrape is enabled and window plan includes direct_ats,
        ATS sources are enabled."""
        from pipeline.query_strategy import source_enabled

        fake_sources = [{"name": "free_ats_scrape", "enabled": True}]
        with patch("config.load_config", return_value={"sources": fake_sources}):
            self.assertTrue(source_enabled("greenhouse", "morning"))
            self.assertTrue(source_enabled("ashby", "morning"))
            self.assertTrue(source_enabled("workable", "morning"))

    def test_ats_off_when_window_excludes_direct_ats(self):
        """ATS sources are disabled when the window plan excludes direct_ats
        even if config enables free_ats_scrape."""
        from pipeline.query_strategy import source_enabled

        fake_sources = [{"name": "free_ats_scrape", "enabled": True}]
        with patch("config.load_config", return_value={"sources": fake_sources}):
            self.assertFalse(source_enabled("greenhouse", "afternoon"))

    def test_source_absent_from_config_is_disabled(self):
        from pipeline.query_strategy import source_enabled

        with patch("config.load_config", return_value={"sources": []}):
            self.assertFalse(source_enabled("github_lists", "morning"))
            self.assertFalse(source_enabled("builtin", "afternoon"))

    def test_optional_free_source_requires_config_enablement_and_window(self):
        from pipeline.query_strategy import source_enabled

        sources = [{"name": "github_lists", "enabled": True}]
        with patch("config.load_config", return_value={"sources": sources}):
            self.assertTrue(source_enabled("github_lists", "morning"))
            self.assertFalse(source_enabled("github_lists", "afternoon"))

    def test_optional_paid_source_cannot_run_only_because_key_exists(self):
        from pipeline.query_strategy import source_enabled

        sources = [{"name": "jsearch_api", "enabled": False}]
        with patch("config.load_config", return_value={"sources": sources}):
            self.assertFalse(source_enabled("api_jsearch", "morning"))


if __name__ == "__main__":
    unittest.main()
