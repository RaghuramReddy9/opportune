"""
source_registry.py — Load, query, and update the source registry.
"""
import sys
import yaml
import logging
from datetime import date
from pathlib import Path

from config import PROJECT_ROOT, TRACKER_DIR

logger = logging.getLogger("source_registry")

_LOCAL_REGISTRY_PATH = TRACKER_DIR / "source_registry.yaml"
_PROJECT_REGISTRY_PATH = PROJECT_ROOT / "source_registry.yaml"
_INSTALLED_REGISTRY_PATH = Path(sys.prefix) / "source_registry.yaml"
_TEMPLATE_REGISTRY_PATH = _PROJECT_REGISTRY_PATH if _PROJECT_REGISTRY_PATH.exists() else _INSTALLED_REGISTRY_PATH


def get_registry_path() -> Path:
    """Use a user-owned registry when present, otherwise the shipped template."""
    return _LOCAL_REGISTRY_PATH if _LOCAL_REGISTRY_PATH.exists() else _TEMPLATE_REGISTRY_PATH


def load_registry() -> dict:
    """Load the source registry YAML."""
    path = get_registry_path()
    if not path.exists():
        logger.warning("Source registry not found: %s", path)
        return {"companies": [], "source_health": {}}
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {"companies": [], "source_health": {}}


def save_registry(registry: dict):
    """Save user changes locally without modifying the shipped template."""
    _LOCAL_REGISTRY_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(_LOCAL_REGISTRY_PATH, "w", encoding="utf-8") as f:
        yaml.safe_dump(registry, f, default_flow_style=False, sort_keys=False)
    logger.info("Registry saved: %s", _LOCAL_REGISTRY_PATH)


def get_enabled_companies(registry: dict = None) -> list:
    """Get all enabled companies."""
    if registry is None:
        registry = load_registry()
    return [c for c in registry.get("companies", []) if c.get("enabled", True)]


def get_companies_by_ats(ats_type: str, registry: dict = None) -> list:
    """Get companies by ATS type."""
    return [c for c in get_enabled_companies(registry) if c.get("ats_type") == ats_type]


def get_unknown_ats_companies(registry: dict = None) -> list:
    """Get companies with unknown ATS type."""
    return [c for c in get_enabled_companies(registry)
            if c.get("ats_type", "unknown") == "unknown" or not c.get("ats_slug")]


def update_company(company_name: str, updates: dict, registry: dict = None) -> dict:
    """Update a company's fields in the registry."""
    if registry is None:
        registry = load_registry()
    for company in registry.get("companies", []):
        if company["company_name"] == company_name:
            company.update(updates)
            break
    save_registry(registry)
    return registry


def update_source_health(updates: dict, registry: dict = None) -> dict:
    """Update source health tracking."""
    if registry is None:
        registry = load_registry()
    health = registry.get("source_health", {})
    health.update(updates)
    health["last_updated"] = date.today().isoformat()
    registry["source_health"] = health
    save_registry(registry)
    return registry


def get_apify_runs_today(registry: dict = None) -> int:
    """Get today's Apify fallback run count."""
    if registry is None:
        registry = load_registry()
    health = registry.get("source_health", {})
    last_updated = health.get("last_updated", "")
    if last_updated != date.today().isoformat():
        return 0  # Reset for new day
    return health.get("apify_fallback_runs_today", 0)


def increment_apify_runs(registry: dict = None) -> dict:
    """Increment Apify fallback run count."""
    if registry is None:
        registry = load_registry()
    health = registry.get("source_health", {})
    today = date.today().isoformat()
    if health.get("last_updated") != today:
        health["apify_fallback_runs_today"] = 0
    health["apify_fallback_runs_today"] = health.get("apify_fallback_runs_today", 0) + 1
    health["last_updated"] = today
    registry["source_health"] = health
    save_registry(registry)
    return registry


def can_run_apify(registry: dict = None) -> bool:
    """Check if Apify fallback is still within daily budget."""
    if registry is None:
        registry = load_registry()
    health = registry.get("source_health", {})
    max_runs = health.get("apify_fallback_runs_max", 3)
    return get_apify_runs_today(registry) < max_runs


def get_registry_stats(registry: dict = None) -> dict:
    """Get summary stats about the registry."""
    if registry is None:
        registry = load_registry()
    companies = registry.get("companies", [])
    enabled = [c for c in companies if c.get("enabled", True)]
    ats_types = {}
    unknown = 0
    for c in enabled:
        ats = c.get("ats_type", "unknown")
        if ats == "unknown" or not c.get("ats_slug"):
            unknown += 1
        ats_types[ats] = ats_types.get(ats, 0) + 1
    return {
        "total_companies": len(companies),
        "enabled_companies": len(enabled),
        "known_ats": len(enabled) - unknown,
        "unknown_ats": unknown,
        "ats_breakdown": ats_types,
    }
