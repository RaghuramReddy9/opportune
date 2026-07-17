import unittest

from pipeline.scrape import build_watch_candidates
from ranking.score import compute_resume_score


class WatchQualityTests(unittest.TestCase):
    def test_watch_pool_caps_repeated_company_variants(self):
        raw_jobs = []
        for idx in range(8):
            raw_jobs.append({
                "company": "Databricks",
                "title": f"AI Engineer - FDE Variant {idx}",
                "description": "Forward deployed AI engineer building LLM, RAG, Databricks, FastAPI, and agent systems. Early career welcome.",
                "location": "United States",
                "source": "greenhouse",
                "apply_url": f"https://example.com/databricks-{idx}",
            })
        raw_jobs.extend([
            {
                "company": "Stripe",
                "title": "Backend Engineer I, AI Security",
                "description": "AI security, guardrails, LLM systems, Python, FastAPI, logging, and observability.",
                "location": "San Francisco, CA",
                "source": "greenhouse",
                "apply_url": "https://example.com/stripe-ai",
            },
            {
                "company": "Airbnb",
                "title": "Early Career Software Engineer, Python LLM GenAI",
                "description": "Python, LLM, GenAI, FastAPI, backend AI systems, and RAG workflows.",
                "location": "Remote, United States",
                "source": "greenhouse",
                "apply_url": "https://example.com/airbnb-ai",
            },
        ])

        watch = build_watch_candidates(raw_jobs, already_selected=[], limit=10)
        company_counts = {company: 0 for company in {job["company"] for job in watch}}
        for job in watch:
            company_counts[job["company"]] += 1

        self.assertLessEqual(company_counts.get("Databricks", 0), 3)
        self.assertIn("Stripe", company_counts)
        self.assertIn("Airbnb", company_counts)

    def test_databricks_is_not_reported_as_missing_skill_when_azure_databricks_is_in_resume(self):
        score = compute_resume_score({
            "company": "Databricks",
            "title": "AI Engineer - FDE",
            "description": "Build Databricks, Delta Lake, LLM, RAG, Python, and FastAPI systems.",
        })

        self.assertNotIn("databricks", score["candidate_missing_skills"])
        self.assertNotIn("spark", score["candidate_missing_skills"])


if __name__ == "__main__":
    unittest.main()
