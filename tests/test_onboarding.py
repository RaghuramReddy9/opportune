"""First-release onboarding guarantees for resume → questions → approved profile."""
from __future__ import annotations

import json

import pytest

from dashboard.db import get_active_profile, init_db
from onboarding.compiler import compile_search_config
from onboarding.providers import (
    LocalResumeAnalyzer,
    ProviderConfigStore,
    normalize_provider_settings,
)
from onboarding.questions import build_questions
from onboarding.resume_reader import extract_resume_text
from onboarding.sanitizer import sanitize_resume_for_remote
from onboarding.service import OnboardingService


ANALYSIS = {
    "name": "Taylor Candidate",
    "headline": "Applied AI and backend engineer",
    "summary": "Builds user-facing AI systems and reliable APIs.",
    "roles": ["Applied AI Engineer", "Backend AI Engineer"],
    "suggested_roles": [
        {
            "title": "Applied AI Engineer",
            "confidence": 0.94,
            "reason": "Built production RAG and agent applications.",
        },
        {
            "title": "LLM Applications Engineer",
            "confidence": 0.88,
            "reason": "Strong retrieval, evaluation, and FastAPI evidence.",
        },
        {
            "title": "AI Solutions Engineer",
            "confidence": 0.72,
            "reason": "Projects show product and integration work.",
        },
    ],
    "skills": ["Python", "FastAPI", "RAG", "LangGraph", "Docker"],
    "projects": [
        {
            "name": "Support Copilot",
            "evidence": "Built a RAG assistant with evaluation and citations.",
        }
    ],
    "locations": ["United States", "Remote US"],
    "experience_level": "entry_level",
    "years_experience": 1.5,
    "work_modes": ["remote", "hybrid"],
    "visa_needed": None,
    "missing": ["work authorization"],
    "source": "test",
}

ANSWERS = {
    "role_priorities": ["Applied AI Engineer", "LLM Applications Engineer"],
    "work_focus": "ai_product_engineering",
    "experience_levels": ["new_grad", "entry_level", "junior"],
    "location_preferences": {
        "locations": ["United States", "Remote US"],
        "work_modes": ["remote", "hybrid"],
        "willing_to_relocate": False,
    },
    "authorization": {
        "visa_policy": "opt_cpt",
        "employment_types": ["full_time"],
        "exclusions": ["security clearance required", "unpaid roles"],
    },
}


class FakeAnalyzer:
    provider_name = "fake"

    def analyze(self, resume_text: str) -> dict:
        assert "taylor@example.com" not in resume_text.lower()
        assert "(555) 222-1212" not in resume_text
        return dict(ANALYSIS)


def test_remote_resume_sanitizer_removes_contact_details_but_keeps_career_evidence():
    text = """Taylor Candidate
    taylor@example.com | (555) 222-1212
    12 Market Street, Boston, MA 02110
    Applied AI Engineer
    Built a production RAG service with FastAPI and Docker.
    """

    sanitized = sanitize_resume_for_remote(text)

    assert "taylor@example.com" not in sanitized
    assert "555" not in sanitized
    assert "12 Market Street" not in sanitized
    assert "production RAG service" in sanitized


def test_local_analysis_deduplicates_locations_and_preserves_ai_acronym():
    analysis = LocalResumeAnalyzer().analyze(
        "Taylor Candidate\nApplied AI Engineer in the United States. "
        "Built AI products with Python and RAG. Open to remote work in the United States."
    )

    assert "Applied AI Engineer" in analysis["roles"]
    assert "Applied Ai Engineer" not in analysis["roles"]
    assert len(analysis["locations"]) == len(
        {item.casefold() for item in analysis["locations"]}
    )


def test_resume_reader_supports_text_docx_and_pdf():
    from io import BytesIO

    import pymupdf
    from docx import Document

    text = "Taylor Candidate\nApplied AI Engineer with Python, RAG, and evaluation experience."
    assert extract_resume_text("resume.txt", text.encode()) == text

    docx_buffer = BytesIO()
    document = Document()
    document.add_paragraph(text)
    document.save(docx_buffer)
    assert "Applied AI Engineer" in extract_resume_text(
        "resume.docx", docx_buffer.getvalue()
    )

    pdf = pymupdf.open()
    page = pdf.new_page()
    page.insert_text((72, 72), text)
    pdf_bytes = pdf.tobytes()
    pdf.close()
    assert "Applied AI Engineer" in extract_resume_text("resume.pdf", pdf_bytes)


def test_provider_store_never_returns_or_embeds_raw_api_key(tmp_path):
    store = ProviderConfigStore(
        settings_path=tmp_path / "llm.json",
        secret_path=tmp_path / "llm.key",
    )
    settings = normalize_provider_settings(
        {
            "provider": "openrouter",
            "model": "openai/gpt-4.1-mini",
        }
    )

    store.save(settings, api_key="sk-private-value")
    public = store.public_settings()
    on_disk = (tmp_path / "llm.json").read_text(encoding="utf-8")

    assert public["provider"] == "openrouter"
    assert public["base_url"] == "https://openrouter.ai/api/v1"
    assert public["has_api_key"] is True
    assert "api_key" not in public
    assert "sk-private-value" not in json.dumps(public)
    assert "sk-private-value" not in on_disk
    assert (tmp_path / "llm.key").read_text(encoding="utf-8") == "sk-private-value"


def test_provider_settings_support_local_and_custom_openai_compatible_models():
    ollama = normalize_provider_settings(
        {"provider": "ollama", "model": "qwen2.5:7b"}
    )
    custom = normalize_provider_settings(
        {
            "provider": "custom",
            "base_url": "https://models.example.test/v1/",
            "model": "resume-model",
        }
    )

    assert ollama.base_url == "http://127.0.0.1:11434/v1"
    assert ollama.requires_api_key is False
    assert custom.base_url == "https://models.example.test/v1"
    assert custom.model == "resume-model"


def test_question_builder_returns_exactly_five_required_clear_questions():
    questions = build_questions(ANALYSIS)

    assert [question["id"] for question in questions] == [
        "role_priorities",
        "work_focus",
        "experience_levels",
        "location_preferences",
        "authorization",
    ]
    assert len(questions) == 5
    assert all(question["required"] is True for question in questions)
    role_options = questions[0]["options"]
    assert role_options[0]["label"] == "Applied AI Engineer"
    assert "Built production RAG" in role_options[0]["description"]


def test_work_focus_question_allows_up_to_three_choices():
    question = build_questions(ANALYSIS)[1]

    assert question["id"] == "work_focus"
    assert question["kind"] == "multi"
    assert question["max_selections"] == 3


def test_config_compiler_preserves_all_work_focus_choices_and_primary_focus():
    answers = json.loads(json.dumps(ANSWERS))
    answers.pop("work_focus")
    answers["work_focuses"] = [
        "ai_product_engineering",
        "customer_facing",
        "platform_infrastructure",
    ]

    config = compile_search_config(ANALYSIS, answers)

    assert config["work_focus"] == "ai_product_engineering"
    assert config["work_focuses"] == answers["work_focuses"]


def test_config_compiler_uses_answers_as_final_authority():
    config = compile_search_config(ANALYSIS, ANSWERS)

    assert config["roles"] == ANSWERS["role_priorities"]
    assert config["target_levels"] == ANSWERS["experience_levels"]
    assert config["locations"] == ["United States", "Remote US"]
    assert config["work_modes"] == ["remote", "hybrid"]
    assert config["visa_policy"] == "opt_cpt"
    assert config["visa_needed"] is True
    assert config["skills"] == ANALYSIS["skills"]
    assert config["work_focus"] == "ai_product_engineering"
    assert config["timeline"] == {"max_age_days": 7}


def test_config_compiler_records_provenance_and_rejected_inferences():
    answers = json.loads(json.dumps(ANSWERS))
    answers["role_priorities"] = ["Applied AI Engineer"]
    config = compile_search_config(ANALYSIS, answers)
    metadata = config["_field_metadata"]

    required = {"value", "source", "evidence", "confidence", "status", "user_modified_at"}
    assert required.issubset(metadata["roles"])
    assert metadata["roles"]["status"] == "confirmed"
    assert metadata["roles"]["source"] == "user"
    assert metadata["skills"]["status"] == "extracted"
    rejected = metadata["roles"]["rejected_values"]
    assert any(item["value"] == "LLM Applications Engineer" for item in rejected)
    assert all(item["status"] == "rejected" for item in rejected)


def test_config_compiler_rejects_missing_required_answers():
    incomplete = dict(ANSWERS)
    incomplete.pop("authorization")

    with pytest.raises(ValueError, match="authorization"):
        compile_search_config(ANALYSIS, incomplete)


def test_onboarding_does_not_activate_profile_until_explicit_approval(tmp_path):
    db_path = tmp_path / "onboarding.db"
    init_db(db_path)
    service = OnboardingService(db_path=db_path, analyzer=FakeAnalyzer())
    resume = """Taylor Candidate
taylor@example.com | (555) 222-1212
Applied AI Engineer with production RAG, FastAPI, and Docker experience.
"""

    analyzed = service.analyze_resume(resume, filename="taylor.txt")

    assert analyzed["status"] == "questions"
    assert len(analyzed["questions"]) == 5
    assert get_active_profile(db_path=db_path) is None

    reviewed = service.submit_answers(analyzed["session_id"], ANSWERS)
    assert reviewed["status"] == "review"
    assert get_active_profile(db_path=db_path) is None

    approved = service.approve(analyzed["session_id"])
    active = get_active_profile(db_path=db_path)

    assert approved["status"] == "approved"
    assert approved["profile_id"] == active["profile_id"]
    extracted = json.loads(active["extracted_json"])
    assert extracted["roles"] == ANSWERS["role_priorities"]
    assert extracted["visa_policy"] == "opt_cpt"


def test_onboarding_session_survives_service_restart(tmp_path):
    db_path = tmp_path / "onboarding.db"
    init_db(db_path)
    first = OnboardingService(db_path=db_path, analyzer=FakeAnalyzer())
    session = first.analyze_resume(
        "Taylor Candidate\nApplied AI Engineer with Python, RAG, FastAPI, and Docker.",
        filename="resume.txt",
    )

    second = OnboardingService(db_path=db_path, analyzer=FakeAnalyzer())
    restored = second.get_session(session["session_id"])

    assert restored["session_id"] == session["session_id"]
    assert restored["analysis"]["headline"] == ANALYSIS["headline"]
    assert "resume_text" not in restored


def test_approved_answers_become_exact_effective_scraper_config(tmp_path):
    import config
    from dashboard import db

    db_path = tmp_path / "effective.db"
    db.set_db_path(db_path)
    init_db(db_path)
    service = OnboardingService(db_path=db_path, analyzer=FakeAnalyzer())
    session = service.analyze_resume(
        "Taylor Candidate\nApplied AI Engineer with Python, RAG, FastAPI, and Docker.",
        filename="resume.txt",
    )
    service.submit_answers(session["session_id"], ANSWERS)
    service.approve(session["session_id"])

    effective = config.get_profile_config()

    assert effective["target_roles"] == ANSWERS["role_priorities"]
    assert effective["target_levels"] == ANSWERS["experience_levels"]
    assert effective["visa_policy"] == "opt_cpt"
    assert effective["timeline"] == {"max_age_days": 7}


def test_onboarding_api_starts_empty_and_does_not_echo_provider_key(tmp_path):
    from dashboard import db
    from dashapi.server import app
    from onboarding import providers
    from tests.asgi_client import ASGITestClient

    db_path = tmp_path / "api.db"
    db.set_db_path(db_path)
    init_db(db_path)
    providers.set_provider_paths(
        tmp_path / "provider.json",
        tmp_path / "provider.key",
    )
    client = ASGITestClient(app)

    status = client.get("/api/onboarding")
    saved = client.post(
        "/api/onboarding/provider",
        json={
            "provider": "openrouter",
            "model": "openai/gpt-4.1-mini",
            "api_key": "sk-api-secret",
        },
    )

    assert status.status_code == 200
    assert status.json()["needs_onboarding"] is True
    assert saved.status_code == 200
    payload = saved.json()
    assert payload["provider"]["has_api_key"] is True
    assert "api_key" not in payload["provider"]
    assert "sk-api-secret" not in saved.text


def test_scrape_api_is_blocked_until_profile_is_approved(tmp_path):
    from dashboard import db
    from dashapi.server import app
    from tests.asgi_client import ASGITestClient

    db_path = tmp_path / "api.db"
    db.set_db_path(db_path)
    init_db(db_path)
    client = ASGITestClient(app)

    response = client.post("/api/scrape?dry_run=true")

    assert response.status_code == 409
    assert "Complete onboarding" in response.text


def test_onboarding_revision_rejects_stale_write(tmp_path):
    from onboarding.store import OnboardingRevisionConflict, OnboardingStore

    store = OnboardingStore(tmp_path / "revision.db")
    session = store.create(
        filename="resume.txt",
        resume_text="private",
        provider="local",
        analysis={},
        questions=[],
    )
    first = store.save_answers(
        session["session_id"],
        {"role_priorities": ["AI Engineer"]},
        {"roles": ["AI Engineer"]},
        session["revision"],
    )
    assert first["revision"] == session["revision"] + 1
    with pytest.raises(OnboardingRevisionConflict, match="Reload"):
        store.save_answers(
            session["session_id"],
            {"role_priorities": ["Stale Role"]},
            {"roles": ["Stale Role"]},
            session["revision"],
        )
    assert store.get(session["session_id"])["answers"]["role_priorities"] == ["AI Engineer"]
