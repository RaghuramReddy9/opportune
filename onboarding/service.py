"""Application service for draft → clarified → approved onboarding."""
from __future__ import annotations

import json
from pathlib import Path

from dashboard.db import create_profile, get_active_profile
from onboarding.compiler import compile_search_config
from onboarding.providers import ProviderConfigStore, ResumeAnalyzer, build_analyzer
from onboarding.questions import build_questions
from onboarding.sanitizer import sanitize_resume_for_remote
from onboarding.store import OnboardingStore


class OnboardingService:
    def __init__(
        self,
        *,
        db_path: Path | None = None,
        analyzer: ResumeAnalyzer | None = None,
        provider_store: ProviderConfigStore | None = None,
    ):
        self.db_path = db_path
        self.store = OnboardingStore(db_path)
        self.provider_store = provider_store or ProviderConfigStore()
        self._analyzer = analyzer

    def analyze_resume(self, resume_text: str, *, filename: str = "resume.txt") -> dict:
        raw = str(resume_text or "").strip()
        if len(raw) < 20:
            raise ValueError("Your resume is too short to analyze. Add more career detail and try again.")
        analyzer = self._analyzer or build_analyzer(self.provider_store)
        sanitized = sanitize_resume_for_remote(raw)
        analysis = analyzer.analyze(sanitized)
        questions = build_questions(analysis)
        return self.store.create(
            filename=filename,
            resume_text=raw,
            provider=getattr(analyzer, "provider_name", "unknown"),
            analysis=analysis,
            questions=questions,
        )

    def submit_answers(self, session_id: str, answers: dict) -> dict:
        session = self.store.get(session_id)
        final_config = compile_search_config(session["analysis"], answers)
        return self.store.save_answers(session_id, answers, final_config)

    def approve(self, session_id: str) -> dict:
        session = self.store.get(session_id, include_resume=True)
        if session["status"] != "review" or not session["final_config"]:
            raise ValueError("Review the final search plan before approval")
        profile_name = (
            session["final_config"].get("name")
            or session["analysis"].get("name")
            or Path(session["filename"]).stem
            or "Candidate"
        )
        profile_id = create_profile(
            name=profile_name,
            resume_text=session["resume_text"],
            extracted_json=json.dumps(session["final_config"], ensure_ascii=False),
            db_path=self.db_path,
        )
        return self.store.mark_approved(session_id, profile_id)

    def get_session(self, session_id: str) -> dict:
        return self.store.get(session_id)

    def status(self) -> dict:
        active = get_active_profile(db_path=self.db_path)
        latest = self.store.latest()
        return {
            "needs_onboarding": active is None,
            "active_profile_id": active["profile_id"] if active else None,
            "session": latest,
            "provider": self.provider_store.public_settings(),
        }
