"""Deterministically turn confirmed onboarding answers into scraper configuration."""
from __future__ import annotations

_REQUIRED = (
    "role_priorities",
    "work_focus",
    "experience_levels",
    "location_preferences",
    "authorization",
)


def _primary_experience(levels: list[str]) -> str:
    if any(level in {"new_grad", "entry_level", "junior", "internship"} for level in levels):
        return "entry_level"
    if "mid_level" in levels:
        return "mid_level"
    if any(level in {"senior", "lead", "staff", "principal"} for level in levels):
        return "senior"
    return "entry_level"


def compile_search_config(analysis: dict, answers: dict) -> dict:
    """Validate answers and produce the active profile's extracted JSON."""
    missing = [key for key in _REQUIRED if not answers.get(key)]
    if missing:
        raise ValueError("Missing required onboarding answers: " + ", ".join(missing))

    roles = [str(item).strip() for item in answers["role_priorities"] if str(item).strip()]
    levels = [str(item).strip() for item in answers["experience_levels"] if str(item).strip()]
    location = answers["location_preferences"]
    authorization = answers["authorization"]
    locations = [str(item).strip() for item in location.get("locations", []) if str(item).strip()]
    work_modes = [str(item).strip() for item in location.get("work_modes", []) if str(item).strip()]
    visa_policy = str(authorization.get("visa_policy") or "").strip()
    if not roles:
        raise ValueError("Choose at least one priority role")
    if not levels:
        raise ValueError("Choose at least one experience level")
    if not locations:
        raise ValueError("Add at least one work location")
    if not work_modes:
        raise ValueError("Choose at least one work mode")
    if visa_policy not in {"none", "needs_sponsorship", "opt_cpt", "custom"}:
        raise ValueError("Choose a valid work authorization option")

    return {
        "name": str(analysis.get("name") or "").strip(),
        "roles": roles,
        "skills": list(analysis.get("skills") or []),
        "projects": list(analysis.get("projects") or []),
        "locations": locations,
        "experience_level": _primary_experience(levels),
        "target_levels": levels,
        "work_modes": work_modes,
        "willing_to_relocate": bool(location.get("willing_to_relocate", False)),
        "visa_policy": visa_policy,
        "visa_needed": visa_policy in {"needs_sponsorship", "opt_cpt", "custom"},
        "work_focus": str(answers["work_focus"]),
        "employment_types": list(authorization.get("employment_types") or ["full_time"]),
        "exclusions": list(authorization.get("exclusions") or []),
        "authorization_note": str(authorization.get("note") or "").strip(),
        "timeline": {"max_age_days": 7},
        "verified": {
            "roles": True,
            "experience_level": True,
            "locations": True,
            "work_modes": True,
            "visa_needed": True,
        },
        "missing": [],
        "analysis_summary": str(analysis.get("summary") or "").strip(),
    }
