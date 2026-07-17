"""Apply Window scoring tests."""

from ranking.apply_window import score_apply_window


def test_high_apply_window_rewards_fresh_strong_trusted_job():
    result = score_apply_window({
        "company": "Acme AI",
        "title": "Entry-Level RAG Engineer",
        "apply_url": "https://job-boards.greenhouse.io/acme/jobs/1",
        "source": "greenhouse",
        "resume_match_score": 91,
        "freshness": "New (0-24h)",
        "freshness_trust": "confirmed_posted_date",
        "action_tag": "apply_now",
        "target_role_families": ["genai_llm_rag"],
        "location_verdict": {"status": "us_verified"},
    })
    assert result["apply_window_label"] == "high"
    assert result["apply_window_score"] >= 80
    assert result["apply_window_next_action"] == "Apply today"
    assert any("fresh" in reason.lower() for reason in result["apply_window_reasons"])


def test_low_apply_window_penalizes_old_untrusted_missing_apply_url():
    result = score_apply_window({
        "company": "UnknownCo",
        "title": "AI Engineer",
        "source": "linkedin_public",
        "resume_match_score": 62,
        "freshness": "Stale (15d+)",
        "freshness_trust": "unverified",
        "action_tag": "watch",
        "why_risky": "Unknown sponsorship and location.",
    })
    assert result["apply_window_label"] == "low"
    assert result["apply_window_score"] < 60
    assert result["apply_window_next_action"] == "Skip unless manually interested"
    assert any("apply link" in reason.lower() for reason in result["apply_window_reasons"])


def test_medium_apply_window_surfaces_review_jobs():
    result = score_apply_window({
        "company": "VectorWorks",
        "title": "Junior AI Agents Engineer",
        "apply_url": "https://example.com/apply",
        "source": "wellfound",
        "resume_match_score": 76,
        "freshness": "This Week (3-7d)",
        "freshness_trust": "unverified",
        "action_tag": "watch",
        "target_role_families": ["ai_agents"],
    })
    assert result["apply_window_label"] == "medium"
    assert result["apply_window_next_action"] == "Review before applying"


def test_newly_discovered_is_not_scored_as_a_fresh_posting():
    result = score_apply_window({
        "company": "UnknownDateCo",
        "title": "Applied AI Engineer",
        "apply_url": "https://jobs.example.com/1",
        "source": "greenhouse",
        "resume_match_score": 91,
        "freshness": "Newly Discovered",
        "freshness_trust": "discovered_not_posted",
        "action_tag": "watch",
        "target_role_families": ["applied_ai"],
    })

    assert "Fresh posting" not in result["apply_window_reasons"]
    assert "Freshness unverified" in result["apply_window_reasons"]
    assert result["apply_window_next_action"] != "Apply today"
