import unittest

from pipeline.scrape import build_watch_candidates
from ranking.score import compute_resume_score, detect_opt_signal, rank_job
from ranking.guardrails import location_verdict


class ScoringRubricTests(unittest.TestCase):
    def test_explicit_supported_sponsorship_phrases_are_strong_evidence(self):
        for phrase in (
            "Visa sponsorship is available.",
            "F-1 OPT sponsorship is supported.",
            "STEM OPT sponsorship is provided.",
        ):
            self.assertEqual(detect_opt_signal(phrase)["signal"], "Strong", phrase)

    def test_strong_rag_agent_role_scores_high_but_not_saturated(self):
        score = compute_resume_score({
            "company": "Useful AI",
            "title": "Entry Level Applied AI Engineer, RAG Agents",
            "location": "Remote, United States",
            "source": "greenhouse",
            "description": (
                "Build production LLM applications with RAG pipelines, LangGraph agents, "
                "FastAPI services, vector retrieval, evaluation, observability, and Docker. "
                "Open to early career and 0-2 years candidates."
            ),
        })

        self.assertGreaterEqual(score["resume_match_score"], 82)
        self.assertLess(score["resume_match_score"], 100)
        self.assertIn("score_components", score)
        self.assertEqual(score["location_verdict"]["status"], "us_verified")

    def test_plain_data_engineer_is_not_a_fake_perfect_match(self):
        score = compute_resume_score({
            "company": "WarehouseCo",
            "title": "Data Engineer I",
            "location": "New York, NY",
            "source": "greenhouse",
            "description": "Build SQL, Spark, ETL, dbt, dashboards, warehouse tables, and reporting pipelines.",
        })

        self.assertLess(score["resume_match_score"], 55)
        self.assertNotIn("applied_ai", score["target_role_families"])

    def test_blank_location_direct_ats_is_capped_and_not_apply_now_quality(self):
        score = compute_resume_score({
            "company": "BlankLoc AI",
            "title": "Applied AI Engineer, RAG Agents",
            "location": "",
            "source": "greenhouse",
            "description": "Build LLM apps, RAG, LangGraph agents, FastAPI, vector search, and evaluation.",
        })

        self.assertEqual(score["location_verdict"]["status"], "trusted_company_unknown")
        self.assertLessEqual(score["resume_match_score"], 65)
        self.assertIn("unknown_location_cap", score["score_caps"])

    def test_blank_location_board_source_does_not_enter_watch(self):
        raw_jobs = [{
            "company": "BoardCo",
            "title": "Entry Level Applied AI Engineer RAG",
            "location": "",
            "source": "api_jsearch",
            "apply_url": "https://example.com/boardco-ai",
            "description": "LLM, RAG, agents, FastAPI, Python, LangGraph. Entry level.",
        }]

        self.assertFalse(location_verdict(raw_jobs[0])["allowed"])
        self.assertEqual(build_watch_candidates(raw_jobs, already_selected=[], limit=5), [])

    def test_blank_location_direct_ats_does_not_enter_watch_without_us_proof(self):
        raw_jobs = [{
            "company": "BlankLoc AI",
            "title": "Entry Level Applied AI Engineer RAG",
            "location": "",
            "source": "greenhouse",
            "apply_url": "https://example.com/blank-direct-ai",
            "description": "LLM, RAG, agents, FastAPI, Python, LangGraph. Entry level.",
        }]

        self.assertEqual(build_watch_candidates(raw_jobs, already_selected=[], limit=5), [])

    def test_scoring_spread_has_multiple_bands(self):
        jobs = [
            {
                "company": "A",
                "title": "Entry Level Applied AI Engineer RAG Agents",
                "location": "Remote, United States",
                "source": "greenhouse",
                "description": "RAG pipelines, LangGraph agents, FastAPI, vector search, LLM evaluation, observability, Docker, early career.",
            },
            {
                "company": "B",
                "title": "Junior Backend Engineer, AI Systems",
                "location": "Philadelphia, PA",
                "source": "greenhouse",
                "description": "Python APIs, FastAPI, Docker, CI/CD, some LLM applications and embeddings.",
            },
            {
                "company": "C",
                "title": "Machine Learning Engineer I",
                "location": "United States",
                "source": "api_serpapi",
                "description": "Model training, PyTorch, TensorFlow, scikit-learn, batch ML pipelines.",
            },
            {
                "company": "D",
                "title": "Data Engineer I",
                "location": "New York, NY",
                "source": "greenhouse",
                "description": "SQL, Spark, ETL, dbt, warehousing, Tableau dashboards.",
            },
        ]

        scores = [rank_job(dict(job))["resume_match_score"] for job in jobs]
        self.assertGreaterEqual(len(set(scores)), 4, scores)
        self.assertEqual(scores, sorted(scores, reverse=True), scores)


if __name__ == "__main__":
    unittest.main()
