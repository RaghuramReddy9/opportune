"""
adapters/__init__.py — Adapter registry.

Each adapter module exposes a `scrape(**kwargs) -> dict` function
returning {"jobs": [...], "raw_count": int, "error": str|None}.

Jobs are normalized to a common schema before being returned.
"""
from typing import Callable, Dict

# Registry: source_key -> (module_name, scrape_func_name, default_kwargs)
REGISTRY: Dict[str, dict] = {
    # ATS-based adapters (from source_registry.yaml)
    "greenhouse": {"module": "adapters.greenhouse_adapter", "func": "scrape"},
    "lever":      {"module": "adapters.lever_adapter", "func": "scrape"},
    "ashby":      {"module": "adapters.ashby_adapter", "func": "scrape"},

    # Curated lists
    "github_lists": {"module": "adapters.github_lists_adapter", "func": "scrape"},
    "ycombinator":  {"module": "adapters.ycombinator_adapter", "func": "scrape"},
    "builtin":      {"module": "adapters.builtin_adapter", "func": "scrape"},
    "wellfound":    {"module": "adapters.wellfound_adapter", "func": "scrape"},

    # API-based (need keys)
    "jsearch":  {"module": "adapters.jsearch_adapter", "func": "scrape"},
    "adzuna":   {"module": "adapters.adzuna_adapter", "func": "scrape"},
    "serpapi":  {"module": "adapters.serpapi_adapter", "func": "scrape"},
    "indeed_rss": {"module": "adapters.indeed_rss_adapter", "func": "scrape"},

    # Fallback
    "apify":     {"module": "adapters.apify_fallback_adapter", "func": "scrape"},
    "job_api":   {"module": "adapters.job_api_adapter", "func": "scrape_all"},
}


def get_adapter(source_key: str) -> Callable:
    """Import and return the scrape function for a given source key."""
    import importlib

    entry = REGISTRY.get(source_key)
    if not entry:
        raise KeyError(f"Unknown adapter: {source_key}")

    mod = importlib.import_module(entry["module"])
    return getattr(mod, entry["func"])
