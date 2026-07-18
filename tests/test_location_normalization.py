"""Shared location-normalization and production wiring contracts."""
from __future__ import annotations

from unittest.mock import patch

import pytest

from onboarding.compiler import compile_search_config
from pipeline.query_strategy import get_query_set
from core.location_normalization import normalize_location_preference
from ranking.guardrails import location_verdict


@pytest.mark.parametrize(
    "value",
    ["US", "U.S.", "U.S.A.", "USA", "United State", "United States", "unitedstates"],
)
def test_explicit_us_aliases_normalize_to_nationwide_policy(value):
    result = normalize_location_preference(value)

    assert result == {
        "kind": "country",
        "code": "US",
        "display": "United States",
        "validation": "canonical",
        "original": value,
    }


@pytest.mark.parametrize("value", ["Remote US", "remote usa", "Remote United States"])
def test_remote_us_aliases_remain_remote_us(value):
    result = normalize_location_preference(value)

    assert result["kind"] == "remote_region"
    assert result["code"] == "REMOTE_US"
    assert result["display"] == "Remote - United States"
    assert result["validation"] == "canonical"


def test_ambiguous_custom_value_is_stable_and_needs_review():
    first = normalize_location_preference("Portland")
    second = normalize_location_preference("Portland")

    assert first == second
    assert first["kind"] == "custom"
    assert first["code"] == "CUSTOM-402eed114f"
    assert first["validation"] == "needs_review"


def _answers(location: str) -> dict:
    return {
        "role_priorities": ["Applied AI Engineer"],
        "work_focus": "applied_ai",
        "experience_levels": ["entry_level"],
        "location_preferences": {
            "locations": [location],
            "work_modes": ["remote", "hybrid"],
            "willing_to_relocate": False,
        },
        "authorization": {"visa_policy": "none", "employment_types": ["full_time"]},
    }


def test_onboarding_compiler_stores_canonical_location_metadata():
    compiled = compile_search_config({}, _answers("unitedstates"))

    assert compiled["locations"] == ["unitedstates"]
    assert compiled["location_preferences_normalized"][0]["code"] == "US"


def test_guardrail_treats_existing_compact_token_as_us_policy():
    with patch("config.get_profile_config", return_value={"locations": ["unitedstates"]}):
        verdict = location_verdict({"location": "Austin, TX", "source": "greenhouse"})

    assert verdict["allowed"] is True
    assert verdict["status"] == "us_verified"


def test_query_generation_uses_canonical_us_location():
    with patch(
        "config.get_profile_config",
        return_value={"target_roles": ["Applied AI Engineer"], "locations": ["unitedstates"]},
    ):
        queries = get_query_set("morning")

    assert queries == ["Applied AI Engineer United States"]
