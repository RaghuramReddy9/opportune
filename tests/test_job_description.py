"""Tests for core/job_description enrichment (posted_date + location extraction)."""
import unittest
from unittest.mock import patch

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


FAKE_GREENHOUSE_HTML = """
<html><body>
<h1>Machine Learning Research Engineer</h1>
<div>Location: San Francisco, CA</div>
<p>Posted: June 16, 2026</p>
<p>We are looking for an engineer with 3+ years of production LLM experience.</p>
</body></html>
"""

FAKE_LINKEDIN_HTML = """
<html><body>
<h1>Generative AI Applications Engineer</h1>
<div>Job location: Seattle, WA</div>
<p>Date posted: 2026-07-01</p>
<p>U.S. citizenship required.</p>
</body></html>
"""


class JobDescriptionEnrichTests(unittest.TestCase):
    def _job(self, **overrides):
        job = {
            "title": "Test Role",
            "company": "TestCo",
            "apply_url": "https://example.com/job/1",
            "location": "",
            "description": "",
            "full_text": "",
        }
        job.update(overrides)
        return job

    def test_extract_posted_date_month(self):
        from core.job_description import _extract_posted_date

        self.assertEqual(
            _extract_posted_date("Posted: June 16, 2026"), "2026-06-16"
        )

    def test_extract_posted_date_iso(self):
        from core.job_description import _extract_posted_date

        self.assertEqual(
            _extract_posted_date("date posted: 2026-07-01"), "2026-07-01"
        )

    def test_extract_location(self):
        from core.job_description import _extract_location

        self.assertEqual(
            _extract_location("Location: San Francisco, CA"),
            "San Francisco, CA",
        )

    def test_enrich_recovers_date_and_location(self):
        from core.job_description import enrich_jobs_with_details

        def fake_fetch(url):
            if "greenhouse" in url:
                return (
                    "Machine Learning Research Engineer "
                    "Location: San Francisco, CA "
                    "Posted: June 16, 2026"
                )
            return ""

        jobs = [self._job(apply_url="https://example.com/greenhouse/1")]
        with patch(
            "core.job_description.fetch_job_description", side_effect=fake_fetch
        ):
            updated = enrich_jobs_with_details(jobs)
        self.assertGreaterEqual(updated, 3)
        self.assertEqual(jobs[0]["posted_date"], "2026-06-16")
        self.assertEqual(jobs[0]["location"], "San Francisco, CA")

    def test_enrich_upgrades_freshness_trust_when_date_found(self):
        from core.job_description import enrich_jobs_with_details
        from ranking.guardrails import apply_freshness_trust

        def fake_fetch(url):
            return "Posted: June 16, 2026"

        jobs = [self._job(apply_url="https://example.com/job/1")]
        with patch(
            "core.job_description.fetch_job_description", side_effect=fake_fetch
        ):
            enrich_jobs_with_details(jobs)
            apply_freshness_trust(jobs[0])
        self.assertEqual(jobs[0]["freshness_trust"], "confirmed_posted_date")
        self.assertEqual(jobs[0]["posted_date"], "2026-06-16")

    def test_enrich_does_not_clobber_existing_date(self):
        from core.job_description import enrich_jobs_with_details

        def fake_fetch(url):
            return "Posted: January 01, 2099"

        jobs = [self._job(apply_url="https://example.com/job/1", posted_date="2026-03-03")]
        with patch(
            "core.job_description.fetch_job_description", side_effect=fake_fetch
        ):
            enrich_jobs_with_details(jobs)
        self.assertEqual(jobs[0]["posted_date"], "2026-03-03")

    def test_enrich_replaces_long_board_snippet_with_full_employer_requirements(self):
        from core.job_description import enrich_jobs_with_details
        from ranking.eligibility import evaluate_ready_to_apply

        board_snippet = "Build enterprise GenAI agents and synthetic data pipelines. " * 12
        employer_page = (
            "Build enterprise GenAI agents and synthetic data pipelines. " * 15
            + "Ideally you have 3+ years of building with LLMs in production "
            + "and publications at NeurIPS, ICLR, or ICML."
        )
        job = self._job(
            title="Machine Learning Research Engineer",
            company="Scale AI",
            source="greenhouse",
            description=board_snippet,
            full_text=board_snippet,
            posted_date="2026-07-13",
            location="San Francisco, CA",
        )

        with patch(
            "core.job_description.fetch_job_description", return_value=employer_page
        ) as fetch:
            enrich_jobs_with_details([job])

        fetch.assert_called_once_with(job["apply_url"])
        self.assertIn("3+ years", job["description"])
        eligibility = evaluate_ready_to_apply(job)
        self.assertEqual(eligibility["severity"], "excluded")
        self.assertIn("experience_over_two_years", eligibility["reason_codes"])


if __name__ == "__main__":
    unittest.main()
