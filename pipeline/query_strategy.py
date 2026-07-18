"""Windowed query strategy for job scraping.

The scraper should run smaller, targeted windows across the day instead of one
large broad scrape. This keeps API usage controlled and improves freshness.
"""
from __future__ import annotations

VALID_WINDOWS = {"morning", "afternoon", "evening"}

_FALLBACK_QUERIES: dict[str, list[str]] = {
    "morning": [
        "AI Engineer United States",
        "LLM Engineer United States",
        "Forward Deployed Engineer United States",
    ],
    "afternoon": [
        "Agent Engineer United States",
        "RAG Systems Engineer United States",
        "AI Solutions Engineer United States",
    ],
    "evening": [
        "Applied AI Engineer United States",
        "Generative AI Engineer United States",
        "Backend AI Systems Engineer United States",
    ],
}

_SOURCE_PLANS: dict[str, set[str]] = {
    "morning": {"direct_ats", "api_jsearch", "api_serpapi", "github_lists"},
    "afternoon": {"api_jsearch", "api_adzuna", "builtin", "wellfound", "ycombinator"},
    "evening": {"direct_ats", "api_serpapi", "api_adzuna", "github_lists"},
}


def get_default_query_corpus() -> list[str]:
    """Return built-in query defaults without reading an active user profile."""
    return [
        query
        for window in ("morning", "afternoon", "evening")
        for query in _FALLBACK_QUERIES[window]
    ]


def normalize_window(window: str | None) -> str:
    if not window:
        return "morning"
    w = window.strip().lower()
    if w not in VALID_WINDOWS:
        raise ValueError(f"unknown scrape window: {window!r}; expected one of {sorted(VALID_WINDOWS)}")
    return w


def get_query_set(window: str | None = None) -> list[str]:
    """Build broad board/API queries from configured roles and location.

    Experience, freshness, work mode, and resume keywords intentionally stay
    out of acquisition queries; those are browser/ranking filters applied after
    the source results have been stored locally.
    """
    selected_window = normalize_window(window)
    from config import get_profile_config

    profile = get_profile_config()
    from core.location_normalization import normalize_location_preferences

    roles = [str(role).strip() for role in profile.get("target_roles", []) if str(role).strip()]
    if not roles:
        return list(_FALLBACK_QUERIES[selected_window])
    normalized_locations = normalize_location_preferences(profile.get("locations", []))
    uses_us = not normalized_locations or any(
        item["code"] in {"US", "REMOTE_US"} for item in normalized_locations
    )
    location = "United States" if uses_us else normalized_locations[0]["display"]
    window_index = ("morning", "afternoon", "evening").index(selected_window)
    count = min(3, len(roles))
    start = window_index * count
    chosen = [roles[(start + offset) % len(roles)] for offset in range(count)]
    return [f"{' '.join(role.replace('+', ' ').split())} {location}" for role in chosen]


def get_query(window: str | None = None, *, offset: int = 0) -> str:
    queries = get_query_set(window)
    return queries[offset % len(queries)]


def source_plan_for_window(window: str | None = None) -> set[str]:
    return set(_SOURCE_PLANS[normalize_window(window)])


def _config_source_enabled(source_key: str) -> bool:
    """Return whether the internal source is explicitly enabled in config."""
    import config as cfg

    config_name_map = {
        "api_serpapi": "serpapi_google_jobs",
        "api_jsearch": "jsearch_api",
        "api_adzuna": "adzuna_api",
        "github_lists": "github_lists",
        "greenhouse": "free_ats_scrape",
        "ashby": "free_ats_scrape",
        "lever": "free_ats_scrape",
        "workable": "free_ats_scrape",
        "workday": "free_ats_scrape",
        "smartrecruiters": "free_ats_scrape",
        "builtin": "builtin_scrape",
        "wellfound": "wellfound_scrape",
        "ycombinator": "ycombinator_jobs",
    }
    config_name = config_name_map.get(source_key)
    if config_name is None:
        return False
    for s in (cfg.load_config().get("sources") or []):
        if s.get("name") == config_name:
            return bool(s.get("enabled", False))
    return False


def source_enabled(source_key: str, window: str | None = None) -> bool:
    plan = source_plan_for_window(window)
    if source_key in {"greenhouse", "ashby", "lever", "workable", "workday", "smartrecruiters"}:
        return "direct_ats" in plan and _config_source_enabled(source_key)
    if source_key in plan:
        return _config_source_enabled(source_key)
    return False
