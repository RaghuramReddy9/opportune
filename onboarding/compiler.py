"""Deterministically turn confirmed onboarding answers into scraper configuration."""
from __future__ import annotations

from datetime import datetime, timezone

from core.location_normalization import normalize_location_preferences

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


def _metadata(
    value,
    *,
    source: str,
    evidence: str,
    status: str,
    confidence: float,
    modified_at: str = "",
    rejected_values: list | None = None,
) -> dict:
    return {
        "value": value,
        "source": source,
        "evidence": evidence,
        "confidence": confidence,
        "status": status,
        "user_modified_at": modified_at,
        "rejected_values": [
            {
                "value": item,
                "source": "resume_analysis",
                "evidence": evidence,
                "confidence": 0.5,
                "status": "rejected",
                "user_modified_at": modified_at,
            }
            for item in (rejected_values or [])
        ],
    }


def compile_search_config(analysis: dict, answers: dict) -> dict:
    """Validate answers and produce the active profile's extracted JSON."""
    missing = [key for key in _REQUIRED if not answers.get(key)]
    if missing:
        raise ValueError("Missing required onboarding answers: " + ", ".join(missing))

    roles = [str(item).strip() for item in answers["role_priorities"] if str(item).strip()]
    levels = [str(item).strip() for item in answers["experience_levels"] if str(item).strip()]
    location = answers["location_preferences"]
    authorization = answers["authorization"]
    raw_locations = [str(item).strip() for item in location.get("locations", []) if str(item).strip()]
    normalized_locations = normalize_location_preferences(raw_locations)
    locations = raw_locations
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

    config = {
        "name": str(analysis.get("name") or "").strip(),
        "roles": roles,
        "skills": list(analysis.get("skills") or []),
        "projects": list(analysis.get("projects") or []),
        "locations": locations,
        "location_preferences_normalized": normalized_locations,
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
    modified_at = datetime.now(timezone.utc).isoformat()
    suggested_roles = [
        str(item.get("title") if isinstance(item, dict) else item).strip()
        for item in (analysis.get("suggested_roles") or analysis.get("roles") or [])
    ]
    rejected_roles = [item for item in suggested_roles if item and item not in roles]
    analyzed_locations = [str(item).strip() for item in analysis.get("locations") or []]
    rejected_locations = [item for item in analyzed_locations if item and item not in locations]
    config["_field_metadata"] = {
        "name": _metadata(config["name"], source="resume_analysis", evidence="analysis:name", status="extracted", confidence=0.7),
        "roles": _metadata(roles, source="user", evidence="answer:role_priorities", status="confirmed", confidence=1.0, modified_at=modified_at, rejected_values=rejected_roles),
        "skills": _metadata(config["skills"], source="resume_analysis", evidence="analysis:skills", status="extracted", confidence=0.7),
        "projects": _metadata(config["projects"], source="resume_analysis", evidence="analysis:projects", status="extracted", confidence=0.7),
        "locations": _metadata(locations, source="user", evidence="answer:location_preferences.locations", status="confirmed", confidence=1.0, modified_at=modified_at, rejected_values=rejected_locations),
        "target_levels": _metadata(levels, source="user", evidence="answer:experience_levels", status="confirmed", confidence=1.0, modified_at=modified_at),
        "work_modes": _metadata(work_modes, source="user", evidence="answer:location_preferences.work_modes", status="confirmed", confidence=1.0, modified_at=modified_at),
        "willing_to_relocate": _metadata(config["willing_to_relocate"], source="user", evidence="answer:location_preferences.willing_to_relocate", status="confirmed", confidence=1.0, modified_at=modified_at),
        "visa_policy": _metadata(visa_policy, source="user", evidence="answer:authorization.visa_policy", status="confirmed", confidence=1.0, modified_at=modified_at),
        "work_focus": _metadata(config["work_focus"], source="user", evidence="answer:work_focus", status="confirmed", confidence=1.0, modified_at=modified_at),
        "employment_types": _metadata(config["employment_types"], source="user", evidence="answer:authorization.employment_types", status="confirmed", confidence=1.0, modified_at=modified_at),
        "exclusions": _metadata(config["exclusions"], source="user", evidence="answer:authorization.exclusions", status="confirmed", confidence=1.0, modified_at=modified_at),
    }
    return config
