import unittest
from unittest.mock import patch

from ranking.guardrails import (
    apply_freshness_trust,
    is_us_location_allowed,
    is_research_engineering_role,
    source_quality_weight,
)
from ranking.eligibility import evaluate_ready_to_apply
from ranking.score import filter_and_rank, is_excluded
from ranking.targeting import classify_role_families, classify_target_level, target_level_score

from core.job_description import extract_visible_text
from resume.resume_profile import load_candidate_preferences, validate_candidate_preferences
from pipeline.scrape import filter_ready_to_apply_jobs, _merge_duplicate_job


class GuardrailTests(unittest.TestCase):
    def test_unknown_freshness_is_newly_discovered_not_confirmed_new(self):
        job = {"title": "AI Engineer Intern", "freshness": "Unknown", "source": "github_list"}

        updated = apply_freshness_trust(job.copy())

        self.assertEqual(updated["freshness"], "Newly Discovered")
        self.assertEqual(updated["freshness_trust"], "discovered_not_posted")
        self.assertFalse(updated["confirmed_posted_date"])

    def test_confirmed_dated_freshness_is_trusted(self):
        job = {"title": "AI Engineer Intern", "freshness": "New (0-24h)", "source": "api_jsearch"}

        updated = apply_freshness_trust(job.copy())

        self.assertEqual(updated["freshness"], "New (0-24h)")
        self.assertEqual(updated["freshness_trust"], "confirmed_posted_date")
        self.assertTrue(updated["confirmed_posted_date"])

    def test_canada_location_is_excluded_without_remote_us_signal(self):
        self.assertFalse(is_us_location_allowed("Kitchener, ON, Canada"))
        self.assertFalse(is_us_location_allowed("Toronto, ON"))

    def test_remote_us_location_allowed(self):
        self.assertTrue(is_us_location_allowed("Remote in USA"))
        self.assertTrue(is_us_location_allowed("United States"))
        self.assertTrue(is_us_location_allowed("Philadelphia, PA"))

    def test_configured_non_us_location_is_respected(self):
        from ranking.guardrails import location_verdict

        with patch("config.get_profile_config", return_value={"locations": ["Toronto, Canada"]}):
            accepted = location_verdict({"location": "Toronto, Canada", "source": "api_jsearch"})
            rejected = location_verdict({"location": "New York, NY", "source": "api_jsearch"})

        self.assertTrue(accepted["allowed"])
        self.assertEqual(accepted["status"], "configured_verified")
        self.assertFalse(rejected["allowed"])

    def test_no_sponsorship_posting_is_allowed_when_sponsorship_not_needed(self):
        job = {
            "title": "Entry Level AI Engineer",
            "description": "Applicants must not require visa sponsorship now or in the future.",
            "source": "greenhouse",
        }

        result = evaluate_ready_to_apply(job, preferences={"visa_policy": "none"})

        self.assertNotIn("visa_or_opt_risk", result["reason_codes"])
        self.assertTrue(result["ready_to_apply"])

    def test_clearance_posting_is_allowed_when_authorization_filter_is_disabled(self):
        job = {
            "title": "Entry Level AI Engineer",
            "description": "Applicants must be U.S. citizens and obtain a security clearance.",
            "source": "greenhouse",
        }

        result = evaluate_ready_to_apply(job, preferences={"visa_policy": "none"})

        self.assertNotIn("citizenship_or_clearance", result["reason_codes"])
        self.assertTrue(result["ready_to_apply"])

    def test_seniority_words_in_company_copy_do_not_exclude_entry_level_title(self):
        excluded, reason = is_excluded(
            "Entry Level AI Engineer Work with managers and the leadership team.",
            title="Entry Level AI Engineer",
        )

        self.assertFalse(excluded, reason)

    def test_senior_title_is_still_excluded(self):
        excluded, reason = is_excluded(
            "Senior AI Engineer Build production services.",
            title="Senior AI Engineer",
        )

        self.assertTrue(excluded)
        self.assertEqual(reason, "senior")

    def test_filter_honors_ranking_exclusion_before_ready_gate(self):
        job = {
            "title": "Research Scientist",
            "excluded": True,
            "exclude_reason": "Research Scientist",
        }

        ready, needs_review, excluded = filter_ready_to_apply_jobs([job])

        self.assertEqual(ready, [])
        self.assertEqual(needs_review, [])
        self.assertEqual(excluded, [job])
        self.assertIn("ranking_excluded", job["eligibility_reason_codes"])

    def test_apply_now_requires_verified_posting_date(self):
        job = {
            "title": "Applied AI Engineer New Grad",
            "company": "FreshUnknownCo",
            "description": "Build production RAG and agent systems. Recent graduates welcome.",
            "resume_match_score": 92,
            "score_caps": [],
            "location_verdict": {"status": "us_verified"},
            "freshness": "Newly Discovered",
            "freshness_trust": "discovered_not_posted",
        }

        ready, needs_review, excluded = filter_ready_to_apply_jobs([job])

        self.assertEqual(ready, [])
        self.assertEqual(excluded, [])
        self.assertEqual(needs_review, [job])
        self.assertIn("posting_date_unverified", job["eligibility_reason_codes"])

    def test_research_title_only_is_not_engineering_enough(self):
        self.assertFalse(is_research_engineering_role("AI/ML Researcher Intern", ""))
        self.assertFalse(is_research_engineering_role("Robotics Research Co-op", ""))

    def test_research_role_with_product_engineering_description_can_pass(self):
        self.assertTrue(is_research_engineering_role(
            "Applied ML Research Intern",
            "Build production Python APIs, model deployment pipelines, evaluation, and monitoring for customer features.",
        ))

    def test_source_quality_prefers_direct_ats_over_repost(self):
        self.assertGreater(source_quality_weight("greenhouse"), source_quality_weight("github_list"))
        self.assertGreater(source_quality_weight("ashby"), source_quality_weight("api_jsearch"))
        self.assertEqual(source_quality_weight("workable"), source_quality_weight("greenhouse"))


    def test_newly_discovered_freshness_keeps_discovered_trust(self):
        job = {"title": "AI Engineer Intern", "freshness": "Newly Discovered", "freshness_trust": "discovered_not_posted"}

        updated = apply_freshness_trust(job.copy())

        self.assertEqual(updated["freshness"], "Newly Discovered")
        self.assertEqual(updated["freshness_trust"], "discovered_not_posted")
        self.assertFalse(updated["confirmed_posted_date"])

    def test_description_extraction_removes_script_noise(self):
        html = "<html><script>bad()</script><body><h1>AI Intern</h1><p>OPT students welcome. Build Python APIs.</p></body></html>"

        text = extract_visible_text(html)

        self.assertIn("AI Intern", text)
        self.assertIn("OPT students welcome", text)
        self.assertNotIn("bad()", text)

    def test_candidate_preferences_prioritize_new_grad_entry_junior_for_ram(self):
        prefs = load_candidate_preferences()

        self.assertIn("new_grad", prefs["target_levels"])
        self.assertIn("entry_level", prefs["target_levels"])
        self.assertIn("junior", prefs["target_levels"])
        self.assertIn("associate", prefs["target_levels"])
        self.assertIn("engineer_i", prefs["target_levels"])
        self.assertIn("zero_to_two_years", prefs["target_levels"])
        self.assertEqual(prefs["secondary_levels"], [])
        self.assertEqual(prefs["internship_policy"], "explicit_graduate_eligibility_required")

    def test_candidate_preferences_validation_rejects_empty_target_levels(self):
        errors = validate_candidate_preferences({"target_levels": []})

        self.assertTrue(any("At least one target level" in e for e in errors))

    def test_entry_junior_new_grad_titles_are_primary_targets(self):
        self.assertEqual(classify_target_level("AI Engineer New Grad"), "new_grad")
        self.assertEqual(classify_target_level("Junior Machine Learning Engineer"), "junior")
        self.assertEqual(classify_target_level("Entry Level Data Engineer"), "entry_level")

    def test_senior_staff_titles_are_not_target_levels(self):
        self.assertEqual(classify_target_level("Senior Machine Learning Engineer"), "not_target")
        self.assertEqual(classify_target_level("Staff AI Engineer"), "not_target")

    def test_internship_is_not_a_default_target_for_completed_masters(self):
        job = {"title": "AI Software Engineer Intern", "description": "Open to recent graduates and master's graduates."}

        score = target_level_score(job, {"target_levels": ["new_grad", "entry_level", "junior"], "secondary_levels": []})

        self.assertLess(score, 0)

    def test_applied_ai_role_families_exclude_plain_ml_and_data_engineering(self):
        plain_ml = {
            "title": "Machine Learning Engineer New Grad",
            "description": "Build model training pipelines and offline experiments.",
        }
        plain_data = {
            "title": "Data Engineer I",
            "description": "Build SQL, Spark, and ETL pipelines for analytics reporting.",
        }
        rag_agent = {
            "title": "Applied AI Engineer New Grad",
            "description": "Build RAG applications, LLM agents, tool use, and LangGraph workflows.",
        }

        self.assertEqual(classify_role_families(plain_ml), [])
        self.assertEqual(classify_role_families(plain_data), [])
        self.assertIn("applied_ai", classify_role_families(rag_agent))
        self.assertIn("genai_llm_rag", classify_role_families(rag_agent))

    def test_filter_and_rank_keeps_applied_ai_not_plain_ml_or_data_engineer(self):
        jobs = [
            {
                "source": "github_list",
                "company": "PlainMLCo",
                "title": "Machine Learning Engineer New Grad",
                "description": "Build model training pipelines, offline experiments, Python services, and machine learning systems.",
                "full_text": "Machine Learning Engineer New Grad Build model training pipelines Python services machine learning systems.",
                "location": "United States",
                "apply_url": "https://example.com/ml",
            },
            {
                "source": "github_list",
                "company": "PlainDataCo",
                "title": "Data Engineer I",
                "description": "Build SQL, Spark, ETL pipelines, Python data workflows, and analytics reporting systems.",
                "full_text": "Data Engineer I SQL Spark ETL Python data workflows analytics reporting systems.",
                "location": "United States",
                "apply_url": "https://example.com/data",
            },
            {
                "source": "github_list",
                "company": "AppliedAICo",
                "title": "Applied AI Engineer New Grad",
                "description": "Build RAG systems, LLM agents, LangGraph workflows, vector retrieval, Python FastAPI services, and production AI tools.",
                "full_text": "Applied AI Engineer New Grad RAG LLM agents LangGraph vector retrieval Python FastAPI production AI tools.",
                "location": "United States",
                "apply_url": "https://example.com/applied-ai",
            },
        ]

        ranked = filter_and_rank(jobs)

        self.assertEqual([job["company"] for job in ranked], ["AppliedAICo"])

    def test_associate_engineer_i_and_zero_to_two_years_are_primary_targets(self):
        self.assertEqual(classify_target_level("Associate Machine Learning Engineer"), "associate")
        self.assertEqual(classify_target_level("Software Engineer I, AI Systems"), "engineer_i")
        self.assertEqual(classify_target_level("Data Engineer I - ML Platform"), "engineer_i")
        self.assertEqual(classify_target_level("Machine Learning Engineer, 0-2 years"), "zero_to_two_years")

    def test_internship_without_graduate_eligibility_is_not_ready(self):
        job = {
            "title": "AI Software Engineer Intern",
            "company": "InternCo",
            "description": "Work on Python APIs and machine learning systems with our engineering team.",
            "location": "United States",
        }

        result = evaluate_ready_to_apply(job)

        self.assertFalse(result["ready_to_apply"])
        self.assertEqual(result["severity"], "excluded")
        self.assertIn("internship_without_graduate_eligibility", result["reason_codes"])

    def test_internship_with_masters_graduate_eligibility_is_ready(self):
        job = {
            "title": "AI Software Engineer Intern",
            "company": "GraduateFriendlyCo",
            "description": "Recent graduates and Master's graduates are eligible. Build Python APIs and ML systems.",
            "location": "United States",
            "opt_signal": "Yes",
        }

        result = evaluate_ready_to_apply(job)

        self.assertTrue(result["ready_to_apply"])
        self.assertEqual(result["severity"], "ready")

    def test_co_op_without_graduate_eligibility_is_not_ready(self):
        job = {
            "title": "Machine Learning Engineer Co-op",
            "company": "CoopCo",
            "description": "Build ML evaluation pipelines with Python.",
            "location": "United States",
        }

        result = evaluate_ready_to_apply(job)

        self.assertFalse(result["ready_to_apply"])
        self.assertIn("internship_without_graduate_eligibility", result["reason_codes"])

    def test_more_than_two_years_required_is_excluded_when_not_junior(self):
        job = {
            "title": "Machine Learning Engineer",
            "company": "ExperienceCo",
            "description": "Requires 3+ years of professional machine learning engineering experience.",
            "location": "United States",
        }

        result = evaluate_ready_to_apply(job)

        self.assertFalse(result["ready_to_apply"])
        self.assertIn("experience_over_two_years", result["reason_codes"])

    def test_two_years_required_is_allowed_for_entry_ml_engineer(self):
        job = {
            "title": "Entry Level Machine Learning Engineer",
            "company": "EntryCo",
            "description": "0-2 years of experience. Build Python ML pipelines.",
            "location": "United States",
        }

        result = evaluate_ready_to_apply(job)

        self.assertTrue(result["ready_to_apply"])

    def test_daily_queries_are_applied_ai_not_plain_ml_or_data_engineering(self):
        from pipeline.scrape import _ROLE_FAMILY_QUERIES

        query_text = "\n".join(_ROLE_FAMILY_QUERIES).lower()
        self.assertNotIn("intern", query_text)
        self.assertNotIn("machine learning engineer", query_text)
        self.assertNotIn("data engineer", query_text)
        self.assertTrue(any("rag" in q.lower() for q in _ROLE_FAMILY_QUERIES))
        self.assertTrue(any("agent" in q.lower() for q in _ROLE_FAMILY_QUERIES))
        self.assertTrue(any("llm" in q.lower() for q in _ROLE_FAMILY_QUERIES))
        self.assertTrue(any("applied ai" in q.lower() for q in _ROLE_FAMILY_QUERIES))

    def test_external_source_queries_are_applied_ai_not_plain_ml_or_data_engineering(self):
        from adapters.builtin_adapter import _SEARCH_URLS as builtin_urls
        from adapters.wellfound_adapter import _SEARCH_URLS as wellfound_urls
        from adapters.github_lists_adapter import SOURCES as github_sources

        search_text = "\n".join(builtin_urls + wellfound_urls).lower()
        self.assertNotIn("internship", search_text)
        self.assertNotIn("intern", search_text)
        self.assertNotIn("machine%20learning%20engineer", search_text)
        self.assertNotIn("data%20engineer", search_text)
        self.assertTrue(any(source["type"] == "new_grad" for source in github_sources))

    def test_security_clearance_role_is_not_ready_to_apply(self):
        job = {
            "title": "AI Software Engineer Intern",
            "company": "DefenseCo",
            "description": "Applicants must be U.S. Citizens and be able to obtain a security clearance.",
            "location": "Virginia, USA",
        }

        result = evaluate_ready_to_apply(job)

        self.assertFalse(result["ready_to_apply"])
        self.assertIn("citizenship_or_clearance", result["reason_codes"])

    def test_currently_enrolled_internship_is_not_ready_after_graduation(self):
        job = {
            "title": "Data Engineer Intern",
            "company": "Tesla",
            "description": "Internship program requirements: must be currently enrolled in a degree program and returning to school after the internship.",
            "location": "Palo Alto, CA",
        }

        result = evaluate_ready_to_apply(job)

        self.assertFalse(result["ready_to_apply"])
        self.assertIn("current_enrollment_required", result["reason_codes"])

    def test_graduation_window_in_future_is_not_ready_after_masters_completion(self):
        job = {
            "title": "Machine Learning Intern",
            "company": "ExampleCo",
            "description": "Candidates must have an expected graduation date between December 2026 and June 2027.",
            "location": "United States",
        }

        result = evaluate_ready_to_apply(job)

        self.assertFalse(result["ready_to_apply"])
        self.assertIn("future_graduation_window", result["reason_codes"])

    def test_recent_graduate_new_grad_role_is_ready_if_no_disqualifier(self):
        job = {
            "title": "AI Engineer New Grad",
            "company": "StartupCo",
            "description": "Open to recent graduates with Master's or Bachelor's degree. OPT candidates welcome. Build Python APIs and ML systems.",
            "location": "Remote in USA",
            "opt_signal": "Yes",
        }

        result = evaluate_ready_to_apply(job)

        self.assertTrue(result["ready_to_apply"])
        self.assertEqual(result["severity"], "ready")
        self.assertEqual(result["reason_codes"], [])

    def test_unknown_description_internship_is_excluded_not_ready(self):
        job = {
            "title": "AI Intern",
            "company": "UnknownDescriptionCo",
            "description": "",
            "location": "United States",
            "source": "github_list",
        }

        result = evaluate_ready_to_apply(job)

        self.assertFalse(result["ready_to_apply"])
        self.assertEqual(result["severity"], "excluded")
        self.assertIn("internship_without_graduate_eligibility", result["reason_codes"])

    def test_tesla_style_internship_return_to_school_is_excluded(self):
        job = {
            "title": "Data Engineer Intern - Multiple Teams",
            "company": "Tesla",
            "description": "This internship requires the candidate to be currently enrolled in a degree program and able to return to school after the internship ends.",
            "location": "Palo Alto, CA",
            "source": "github_list",
        }

        result = evaluate_ready_to_apply(job)

        self.assertFalse(result["ready_to_apply"])
        self.assertIn("current_enrollment_required", result["reason_codes"])

    def test_pipeline_splits_ready_needs_review_and_excluded(self):
        ready_job = {
            "title": "AI Engineer New Grad",
            "company": "ReadyCo",
            "description": "Recent graduates welcome. OPT candidates welcome.",
        }
        review_job = {"title": "AI Engineer", "company": "ReviewCo", "description": "", "source": "github_list"}
        excluded_job = {
            "title": "AI Intern",
            "company": "DefenseCo",
            "description": "Applicants must be U.S. Citizens and able to obtain a security clearance.",
        }

        ready, needs_review, excluded = filter_ready_to_apply_jobs([ready_job, review_job, excluded_job])

        self.assertEqual([j["company"] for j in ready], ["ReadyCo"])
        self.assertEqual([j["company"] for j in needs_review], ["ReviewCo"])
        self.assertEqual([j["company"] for j in excluded], ["DefenseCo"])
        self.assertTrue(ready[0]["ready_to_apply"])
        self.assertEqual(needs_review[0]["eligibility_severity"], "needs_review")
        self.assertEqual(excluded[0]["eligibility_severity"], "excluded")

    def test_scored_job_needs_explicit_sponsorship_evidence_for_apply_now(self):
        job = {
            "title": "Entry Level Applied AI Engineer",
            "company": "ReviewCo",
            "description": "Build production RAG systems. Work authorization details are discussed later.",
            "resume_match_score": 90,
            "score_caps": [],
            "location_verdict": {"status": "us_verified"},
            "freshness_trust": "confirmed_posted_date",
            "opt_signal": "Yes",
        }
        with patch(
            "resume.resume_profile.load_candidate_preferences",
            return_value={"visa_policy": "opt_cpt"},
        ):
            ready, needs_review, excluded = filter_ready_to_apply_jobs([job])

        self.assertEqual(ready, [])
        self.assertEqual(excluded, [])
        self.assertEqual(needs_review[0]["eligibility_severity"], "needs_review")
        self.assertIn("sponsorship_not_confirmed", needs_review[0]["eligibility_reason_codes"])

    def test_scrape_all_enriches_all_non_duplicates_before_candidate_cut(self):
        from pipeline import scrape as scrape_mod

        jobs = []
        for idx in range(4):
            jobs.append({
                "title": f"Applied AI Engineer {idx}",
                "company": f"Company{idx}",
                "description": "Build LLM, RAG, agents, Python, and FastAPI systems.",
                "full_text": "Build LLM, RAG, agents, Python, and FastAPI systems.",
                "location": "San Francisco, CA",
                "source": "greenhouse",
                "apply_url": f"https://jobs.example.com/{idx}",
                "priority": "A",
                "freshness": "New (0-24h)",
                "resume_match_score": 90 - idx,
                "source_quality_weight": 10,
                "target_role_families": ["applied_ai"],
                "target_level": "entry_level",
            })
        captured = []

        def fake_enrich(candidates):
            captured.append([job["company"] for job in candidates])
            return 0

        with patch("pipeline.scrape.load_registry", return_value=[]), \
             patch("pipeline.scrape.get_enabled_companies", return_value=[]), \
             patch("pipeline.scrape.get_companies_by_ats", return_value=[]), \
             patch("pipeline.scrape.get_unknown_ats_companies", return_value=[]), \
             patch("pipeline.scrape.can_run_apify", return_value=False), \
             patch("pipeline.query_strategy.source_enabled", side_effect=lambda source, _window: source == "github_lists"), \
             patch("pipeline.scrape._scrape_github_lists", return_value={"jobs": jobs, "raw_count": len(jobs)}), \
             patch("ranking.guardrails.filter_jobs_by_location", side_effect=lambda items: items), \
             patch("pipeline.scrape.filter_and_rank", side_effect=lambda items: items), \
             patch("pipeline.scrape.enrich_candidates_before_eligibility", side_effect=fake_enrich), \
             patch("ranking.score.rank_job", side_effect=lambda job: job), \
             patch("pipeline.scrape.evaluate_ready_to_apply", return_value={"ready_to_apply": True, "severity": "ready", "reason_codes": [], "reasons": []}), \
             patch("core.skill_extractor.extract_skills", return_value=[]), \
             patch("core.skill_matcher.load_user_profile", return_value={}), \
             patch("core.skill_matcher.skill_match", return_value=(0.9, [])), \
             patch("core.temporal_scorer.combined_weight", return_value=1.0), \
             patch("pipeline.scrape.build_watch_candidates", return_value=[]):
            scrape_mod.scrape_all(max_selected=1, dry_run=True, max_workers=1)

        self.assertGreaterEqual(len(captured), 1)
        self.assertEqual(captured[0], ["Company0", "Company1", "Company2", "Company3"])

    def test_candidate_pool_enrichment_exposes_disqualifier_before_eligibility(self):
        from pipeline.scrape import enrich_candidates_before_eligibility

        job = {
            "title": "Applied AI Engineer",
            "company": "DefenseCo",
            "description": "",
            "full_text": "",
            "location": "United States",
            "source": "greenhouse",
            "apply_url": "https://jobs.example.com/defense-ai",
        }
        with patch(
            "core.job_description.fetch_job_description",
            return_value=(
                "Build production RAG systems. Applicants must be U.S. citizens "
                "and eligible for a security clearance."
            ),
        ):
            enrich_candidates_before_eligibility([job])

        ready, needs_review, excluded = filter_ready_to_apply_jobs([job])
        self.assertEqual(ready, [])
        self.assertEqual(needs_review, [])
        self.assertEqual([item["company"] for item in excluded], ["DefenseCo"])
        self.assertIn("citizenship_or_clearance", excluded[0]["eligibility_reason_codes"])

    def test_watch_builder_does_not_reintroduce_experience_excluded_role(self):
        from pipeline.scrape import build_watch_candidates

        raw = {
            "title": "Entry Level Applied AI Engineer",
            "company": "Scale AI",
            "description": (
                "Build production LLM agents. Requires 3+ years of building with "
                "LLMs in production and recent top-conference publications."
            ),
            "full_text": "",
            "location": "San Francisco, CA",
            "source": "greenhouse",
            "apply_url": "https://jobs.example.com/scale-research",
            "target_role_families": ["applied_ai", "ai_agents"],
            "target_level": "entry_level",
            "resume_match_score": 80,
            "matched_keywords": ["llm", "agents", "python"],
        }

        watch = build_watch_candidates([raw], already_selected=[])
        self.assertEqual(watch, [])

    def test_watch_builder_enriches_incomplete_snippet_before_eligibility(self):
        from pipeline.scrape import build_watch_candidates

        raw = {
            "title": "Entry Level Applied AI Engineer",
            "company": "Scale AI",
            "description": "Build production LLM agents and synthetic data systems. " * 12,
            "full_text": "",
            "location": "San Francisco, CA",
            "source": "greenhouse",
            "apply_url": "https://jobs.example.com/scale-research",
            "target_role_families": ["applied_ai", "ai_agents"],
            "target_level": "entry_level",
            "resume_match_score": 80,
            "matched_keywords": ["llm", "agents", "python"],
            "posted_date": "2026-07-13",
        }
        employer_page = (
            "Build production LLM agents and synthetic data systems. " * 15
            + "Applicants must be U.S. citizens and eligible for a security clearance."
        )
        with patch(
            "core.job_description.fetch_job_description", return_value=employer_page
        ) as fetch:
            watch = build_watch_candidates([raw], already_selected=[], max_age_days=7)

        fetch.assert_called_once_with(raw["apply_url"])
        self.assertEqual(watch, [])

    def test_watch_builder_excludes_security_researcher_and_compliance_analyst_titles(self):
        from pipeline.scrape import build_watch_candidates

        def candidate(company, title, suffix):
            return {
                "title": title,
                "company": company,
                "description": "Work on agentic AI, LLM systems, evaluation, and privacy.",
                "location": "San Francisco, CA",
                "source": "ashby",
                "apply_url": f"https://jobs.example.com/{suffix}",
                "target_role_families": ["applied_ai", "ai_agents"],
                "target_level": "unknown",
                "resume_match_score": 80,
                "matched_keywords": ["llm", "agents", "evaluation"],
            }

        raw = [
            candidate("OpenAI", "Security Researcher, Agentic AI Threats", "researcher"),
            candidate("LangChain", "Security Compliance Analyst, Privacy", "analyst"),
        ]
        with patch(
            "core.job_description.fetch_job_description",
            side_effect=lambda _url: "Work on agentic AI, LLM systems, evaluation, and privacy.",
        ):
            watch = build_watch_candidates(raw, already_selected=[])
        self.assertEqual(watch, [])

    def test_duplicate_merge_preserves_github_new_grad_signal(self):
        existing = {
            "source": "greenhouse",
            "title": "Software Engineer",
            "company": "ExampleCo",
            "description": "Build AI systems.",
            "apply_url": "https://example.com/apply/1",
            "full_text": "Software Engineer ExampleCo Build AI systems.",
        }
        incoming = {
            "source": "github_list",
            "title": "Software Engineer New Grad - AI",
            "company": "ExampleCo",
            "description": "",
            "apply_url": "https://example.com/apply/1",
            "full_text": "Software Engineer New Grad - AI ExampleCo",
        }

        _merge_duplicate_job(existing, incoming)

        self.assertEqual(existing["title"], "Software Engineer New Grad - AI")
        self.assertEqual(existing["source"], "github_list")
        self.assertIn("greenhouse", existing["source_aliases"])


if __name__ == "__main__":
    unittest.main()
