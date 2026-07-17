import unittest

from pipeline.scrape import build_watch_candidates


class WatchCandidateSurfacingTests(unittest.TestCase):
    def test_builds_watch_pool_from_near_matches_before_strict_ranking(self):
        raw_jobs = [
            {
                "company": "NearAI",
                "title": "Entry Level Generative AI Engineer",
                "description": "Build LLM applications, RAG pipelines, LangChain agents, FastAPI services, and evaluation workflows.",
                "location": "Remote, United States",
                "source": "api_jsearch",
                "apply_url": "https://example.com/near-ai",
            },
            {
                "company": "AgentOps",
                "title": "Entry Level Forward Deployed AI Engineer",
                "description": "Customer-facing agentic AI automation, tool execution, RAG, and backend integrations. Early career candidates welcome.",
                "location": "New York, NY",
                "source": "wellfound",
                "apply_url": "https://example.com/agentops",
            },
        ]

        watch = build_watch_candidates(raw_jobs, already_selected=[], limit=10)

        self.assertEqual([job["company"] for job in watch], ["NearAI", "AgentOps"])
        self.assertTrue(all(job["dashboard_watch_reason"] for job in watch))
        self.assertTrue(all(job["resume_match_score"] >= 35 for job in watch))
        self.assertTrue(all(job["target_role_families"] for job in watch))

    def test_watch_pool_rejects_senior_plain_data_and_existing_urls(self):
        raw_jobs = [
            {
                "company": "SeniorAI",
                "title": "Senior Generative AI Engineer",
                "description": "Lead LLM platform work with 8+ years required.",
                "source": "ashby",
                "apply_url": "https://example.com/senior",
            },
            {
                "company": "PlainData",
                "title": "Entry Level Data Engineer",
                "description": "SQL dashboards and ETL reporting. No AI, LLM, RAG, or agent work.",
                "source": "greenhouse",
                "apply_url": "https://example.com/plain-data",
            },
            {
                "company": "KnownAI",
                "title": "Entry Level Applied AI Engineer",
                "description": "LLM apps and RAG systems.",
                "source": "api_jsearch",
                "apply_url": "https://example.com/known",
            },
        ]
        already = [{"apply_url": "https://example.com/known"}]

        watch = build_watch_candidates(raw_jobs, already_selected=already, limit=10)

        self.assertEqual(watch, [])

    def test_watch_pool_respects_configured_timeline(self):
        raw = {
            "company": "OldAI",
            "title": "Entry Level Applied AI Engineer",
            "description": "Build production LLM and RAG systems with Python.",
            "posted_date": "2026-07-01",
            "location": "New York, NY",
            "source": "ashby",
            "apply_url": "https://example.com/old-ai",
        }

        watch = build_watch_candidates(
            [raw], already_selected=[], limit=10, max_age_days=1
        )

        self.assertEqual(watch, [])

    def test_watch_pool_rejects_non_ai_research_title_with_ai_boilerplate(self):
        raw = {
            "company": "ResearchCo",
            "title": "Research Associate, Biology",
            "description": "Our company builds AI systems, but this role runs biology assays.",
            "location": "New York, NY",
            "source": "greenhouse",
            "apply_url": "https://example.com/biology",
        }

        watch = build_watch_candidates([raw], already_selected=[], limit=10)

        self.assertEqual(watch, [])


if __name__ == "__main__":
    unittest.main()
