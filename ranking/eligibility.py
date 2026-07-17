"""
ranking/eligibility.py — Ready-to-apply eligibility gate.

This module answers one question before local sync:
Should the candidate spend time applying to this role?
"""
from __future__ import annotations

import re
from typing import Any


UNCERTAIN_SOURCES = {"github_list", "github_lists", "api_jsearch", "api_adzuna", "api_serpapi", "jsearch", "adzuna", "serpapi"}


def _job_text(job: dict[str, Any]) -> str:
    parts = [
        job.get("title", ""),
        job.get("company", ""),
        job.get("location", ""),
        job.get("description", ""),
        job.get("raw_description", ""),
        job.get("full_text", ""),
        job.get("details", ""),
        job.get("notes", ""),
    ]
    return "\n".join(str(p) for p in parts if p).lower()


def _has_any(patterns: list[str], text: str) -> bool:
    return any(re.search(pattern, text, flags=re.IGNORECASE) for pattern in patterns)


def _is_internship_or_coop(text: str) -> bool:
    return _has_any([
        r"\b(intern|internship)\b",
        r"\bco[-\s]?op\b",
        r"\bcoop\b",
    ], text)


def _requires_over_two_years(text: str) -> bool:
    return _has_any([
        r"\b(?:at\s+least\s+|minimum\s+of\s+)?(?:[3-9]|1\d)\+?\s+years?\b",
        r"\b(?:[3-9]|1\d)\+?\s+years?\s+of\s+(professional\s+)?experience\b",
    ], text)


def evaluate_ready_to_apply(job: dict[str, Any], preferences: dict[str, Any] | None = None) -> dict[str, Any]:
    """Return structured eligibility for ready-to-apply jobs.

    States:
    - ready: safe enough to push to the main local apply queue
    - needs_review: potentially relevant, but not verified enough for ready queue
    - excluded: known disqualifier for the candidate's current search
    """
    text = _job_text(job)
    description = str(job.get("description") or job.get("raw_description") or job.get("full_text") or "").strip()
    reason_codes: list[str] = []
    reasons: list[str] = []
    needs_review_codes: list[str] = []
    needs_review_reasons: list[str] = []
    if preferences is None:
        from resume.resume_profile import load_candidate_preferences

        preferences = load_candidate_preferences()

    visa_policy = str(preferences.get("visa_policy") or "custom").lower()
    needs_sponsorship = visa_policy in {"needs_sponsorship", "opt_cpt", "custom"}

    citizenship_or_clearance_patterns = [
        r"\bu\.?s\.?\s+citizen(s|ship)?\s+(only|required)\b",
        r"\bu\.?s\.?\s+citizen(s)?\b.*\bsecurity\s+clearance\b",
        r"\bmust\s+be\s+(a\s+)?u\.?s\.?\s+citizen\b",
        r"\brequires?\s+u\.?s\.?\s+citizenship\b",
        r"\bsecurity\s+clearance\s+(required|eligible|eligibility)\b",
        r"\b(active|current)\s+(secret|top\s+secret|ts/sci|ts\/?sci)\b",
        r"\bability\s+to\s+obtain\s+(and\s+maintain\s+)?(a\s+)?security\s+clearance\b",
        r"\bitar\s+(restricted|requirements?|controlled)\b",
        r"\bexport\s+control\s+(laws?|requirements?)\b.*\bu\.?s\.?\s+(person|citizen)\b",
    ]
    if needs_sponsorship and _has_any(citizenship_or_clearance_patterns, text):
        reason_codes.append("citizenship_or_clearance")
        reasons.append("Requires U.S. citizenship, U.S. person status, export-control eligibility, or security clearance.")

    visa_risk_patterns = [
        r"\b(no|not)\s+(visa\s+)?sponsorship\b",
        r"\b(no|not)\s+sponsor(ship)?\s+(now|in\s+the\s+future)\b",
        r"\bmust\s+not\s+require\s+sponsorship\b",
        r"\bwithout\s+employer\s+sponsorship\b",
        r"\b(no|not)\s+(f-1|opt|cpt)\b",
        r"\bgreen\s+card\s+(only|required)\b",
        r"\bpermanent\s+resident\s+(only|required)\b",
    ]
    opt_signal = str(job.get("opt_signal", "")).lower()
    if needs_sponsorship and (opt_signal == "high risk" or _has_any(visa_risk_patterns, text)):
        reason_codes.append("visa_or_opt_risk")
        reasons.append("Posting indicates sponsorship/OPT/F-1 risk.")

    current_enrollment_patterns = [
        r"\bmust\s+be\s+(currently\s+)?enrolled\b",
        r"\bcurrently\s+enrolled\s+in\b",
        r"\bactively\s+enrolled\b",
        r"\breturn(ing)?\s+to\s+(school|college|university|degree\s+program)\b",
        r"\bmust\s+return\s+to\s+school\b",
        r"\bcontinuing\s+student\b",
        r"\bfor\s+students\s+currently\s+enrolled\b",
    ]
    graduate_eligible_patterns = [
        r"\brecent\s+graduates?\b",
        r"\bnew\s+grads?\b",
        r"\bnew\s+graduates?\b",
        r"\bgraduates?\s+welcome\b",
        r"\bmaster'?s\s+graduates?\b",
        r"\bgraduate\s+students?\s+and\s+recent\s+graduates?\b",
        r"\bfinal[-\s]?year\s+graduates?\b",
        r"\bgraduated\s+within\s+the\s+last\s+\d+\s+(months|years)\b",
        r"\balumni\b",
        r"\bearly[-\s]?career\s+candidates?\b",
        r"\bnon[-\s]?current[-\s]?student\b",
    ]
    if _has_any(current_enrollment_patterns, text) and not _has_any(graduate_eligible_patterns, text):
        reason_codes.append("current_enrollment_required")
        reasons.append("Internship appears to require current enrollment or return-to-school after internship.")

    future_graduation_patterns = [
        r"\bexpected\s+graduation\s+(date\s+)?(of|between|after)\b",
        r"\bgraduat(?:e|ing|ion)\s+(date\s+)?(between|after)\b",
        r"\bclass\s+of\s+20\d{2}\b",
    ]
    if _has_any(future_graduation_patterns, text) and not _has_any(graduate_eligible_patterns, text):
        reason_codes.append("future_graduation_window")
        reasons.append("Posting appears targeted to students with a future graduation date.")

    # the candidate has completed his Master's. Internships/co-ops are not useful unless
    # the posting positively states recent/Master's/final-year graduate or
    # early-career non-current-student eligibility. This avoids current-student
    # internship leakage when the posting omits return-to-school wording.
    if _is_internship_or_coop(text) and not _has_any(graduate_eligible_patterns, text):
        reason_codes.append("internship_without_graduate_eligibility")
        reasons.append("Internship/co-op does not explicitly say recent graduates, Master's graduates, final-year graduates, or non-current-student early-career candidates are eligible.")

    if _requires_over_two_years(text):
        reason_codes.append("experience_over_two_years")
        reasons.append("Posting requires more than 2 years of experience.")

    if not description and job.get("source") in UNCERTAIN_SOURCES:
        needs_review_codes.append("insufficient_description")
        needs_review_reasons.append("Description unavailable, so eligibility restrictions cannot be verified.")

    if reason_codes:
        return {
            "ready_to_apply": False,
            "severity": "excluded",
            "reason_codes": reason_codes,
            "reasons": reasons,
        }

    if needs_review_codes:
        return {
            "ready_to_apply": False,
            "severity": "needs_review",
            "reason_codes": needs_review_codes,
            "reasons": needs_review_reasons,
        }

    return {
        "ready_to_apply": True,
        "severity": "ready",
        "reason_codes": [],
        "reasons": [],
    }
