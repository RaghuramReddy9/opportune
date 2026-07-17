import unittest

from pipeline.scrape import build_dashboard_jobs, merge_pool_and_ranked_jobs


class ScrapeDashboardPayloadTests(unittest.TestCase):
    def test_ranked_rows_upgrade_pool_without_strict_skip_removing_it(self):
        pool = [
            {"company": "Acme", "title": "Senior AI Engineer", "action_tag": "pool"},
            {"company": "GoodCo", "title": "AI Engineer", "action_tag": "pool"},
        ]
        ranked = [
            {"company": "Acme", "title": "Senior AI Engineer", "action_tag": "skip"},
            {"company": "GoodCo", "title": "AI Engineer", "action_tag": "watch"},
        ]

        merged = merge_pool_and_ranked_jobs(pool, ranked)
        tags = {job["company"]: job["action_tag"] for job in merged}
        self.assertEqual(tags, {"Acme": "pool", "GoodCo": "watch"})

    def test_dashboard_payload_includes_apply_watch_known_and_skip_buckets(self):
        ready = [
            {
                "company": "FreshAI",
                "title": "Applied AI Engineer",
                "resume_match_score": 82,
                "priority": "A",
                "freshness": "New (0-24h)",
                "freshness_trust": "confirmed_posted_date",
                "freshness_source": "employer_page",
                "posted_date": "2026-07-14",
                "location": "Remote, United States",
                "source": "greenhouse",
                "apply_url": "https://example.com/fresh",
                "matched_keywords": ["rag", "agents"],
                "target_role_families": ["applied_ai"],
                "why_matches": "Strong applied AI fit",
                "why_risky": "",
            }
        ]
        needs_review = [
            {
                "company": "MaybeLabs",
                "title": "AI Engineer",
                "resume_match_score": 58,
                "priority": "B",
                "freshness": "Recent (24-48h)",
                "apply_url": "https://example.com/watch",
                "matched_keywords": ["llm"],
                "target_role_families": ["genai_llm_rag"],
                "eligibility_reason_codes": ["insufficient_description"],
                "why_matches": "Potential LLM role",
                "why_risky": "Description unavailable",
            }
        ]
        excluded = [
            {
                "company": "RiskyCo",
                "title": "AI Engineer Intern",
                "resume_match_score": 52,
                "priority": "B",
                "freshness": "Newly Discovered",
                "apply_url": "https://example.com/skip",
                "eligibility_reason_codes": ["current_enrollment_required"],
                "eligibility_reasons": ["Requires current enrollment"],
            }
        ]
        duplicates = [
            {
                "company": "KnownCo",
                "title": "Software Engineer I, AI Platform",
                "resume_match_score": 76,
                "priority": "A",
                "freshness": "Newly Discovered",
                "apply_url": "https://example.com/known",
                "matched_keywords": ["ai", "platform"],
                "target_role_families": ["applied_ai"],
            }
        ]

        payload = build_dashboard_jobs(
            ready_jobs=ready,
            needs_review_jobs=needs_review,
            excluded_jobs=excluded,
            duplicate_jobs=duplicates,
            limit_per_bucket=5,
        )

        tags = {item["company"]: item["action_tag"] for item in payload}
        self.assertEqual(tags["FreshAI"], "apply_now")
        self.assertEqual(tags["MaybeLabs"], "watch")
        self.assertEqual(tags["RiskyCo"], "skip")
        self.assertEqual(tags["KnownCo"], "known_match")
        self.assertIn("reason_codes", payload[1])
        self.assertIn("apply_url", payload[0])
        self.assertEqual(payload[0]["location"], "Remote, United States")
        self.assertEqual(payload[0]["source"], "greenhouse")
        self.assertEqual(payload[0]["posted_date"], "2026-07-14")
        self.assertEqual(payload[0]["freshness_source"], "employer_page")


if __name__ == "__main__":
    unittest.main()
