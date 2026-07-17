"""Tests for strict pipeline-level geo guardrails.

These tests prove that jobs with non-U.S. location signals are hard-excluded
before they reach scoring/Watch/Apply buckets. The pipeline must never rely
only on scoring to suppress non-U.S. jobs: scoring bonuses are too weak to
prevent global jobs from flooding the Watch pool when board adapters return
globally.
"""
import unittest

from ranking.guardrails import allow_job_location, filter_jobs_by_location


class PipelineGeoGuardrailTests(unittest.TestCase):
    def test_us_locations_are_allowed(self):
        self.assertTrue(allow_job_location("New York, NY"))
        self.assertTrue(allow_job_location("Remote, United States"))
        self.assertTrue(allow_job_location("San Francisco, CA"))
        self.assertTrue(allow_job_location("Remote in US"))
        self.assertTrue(allow_job_location("Austin, TX"))
        # Empty/unknown is rejected at the strict pipeline gate (board sources only).
        self.assertFalse(allow_job_location(""))
        self.assertFalse(allow_job_location(None))

    def test_known_non_us_locations_are_rejected(self):
        for loc in [
            "Kitchener, ON, Canada",
            "Toronto, ON",
            "London, UK",
            "Bangalore, India",
            "Remote, Australia",
            "Berlin, Germany",
            "Singapore",
            "Sydney, Australia",
            "Hyderabad",
        ]:
            self.assertFalse(allow_job_location(loc), f"expected {loc!r} to be rejected")

    def test_ambiguous_location_with_non_us_signal_is_rejected(self):
        # No US state + a non-US city → reject.
        self.assertFalse(allow_job_location("Remote / Onsite"))
        self.assertFalse(allow_job_location("Remote / Berlin"))

    def test_filter_jobs_by_location_drops_non_us_before_scoring(self):
        jobs = [
            {"company": "Stripe", "title": "Applied AI Engineer", "location": "New York, NY", "source": "greenhouse"},
            {"company": "TrustedATS", "title": "Applied AI Engineer", "location": "", "source": "ashby"},
            {"company": "BadCo", "title": "Applied AI Engineer", "location": "Bangalore, India", "source": "api_jsearch"},
            {"company": "GlobalCo", "title": "Applied AI Engineer", "location": "", "source": "github_lists"},
        ]
        kept = filter_jobs_by_location(jobs)
        companies = {j["company"] for j in kept}
        self.assertIn("Stripe", companies)
        self.assertIn("TrustedATS", companies)
        self.assertNotIn("BadCo", companies)
        self.assertNotIn("GlobalCo", companies)

    def test_ambiguous_but_us_state_signals_are_kept(self):
        # "Remote / Onsite, Denver, CO" is ambiguous but has US state → keep.
        jobs = [
            {"company": "AmbCo", "title": "Applied AI Engineer", "location": "Remote / Onsite, Denver, CO", "source": "wellfound"},
        ]
        kept = filter_jobs_by_location(jobs)
        self.assertEqual(len(kept), 1)


if __name__ == "__main__":
    unittest.main()
