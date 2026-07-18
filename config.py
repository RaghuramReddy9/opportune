"""config.py — Configuration for the local-first Opportune agent.

Loads settings from a config.yaml (single source of truth) with env overrides.
Secrets (API keys) are read from .env / environment only — never logged.

Open-source defaults are generic. Personal values (name, email, target roles)
are loaded from config.yaml and fall back to neutral placeholders so a fresh
clone runs without personal data.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

from core.paths import resolve_app_paths, resolve_runtime_paths

# --- Project root & .env ---
PROJECT_ROOT = Path(__file__).resolve().parent
_LOCAL_ENV = PROJECT_ROOT / ".env"
if _LOCAL_ENV.exists():
    load_dotenv(_LOCAL_ENV, override=False)

# --- Config file (single source of truth) ---
_APP_PATHS = resolve_app_paths()
_PROJECT_CONFIG_PATH = PROJECT_ROOT / "config.yaml"
CONFIG_PATH = Path(
    os.getenv(
        "OPPORTUNE_CONFIG_PATH",
        str(_PROJECT_CONFIG_PATH if _PROJECT_CONFIG_PATH.exists() else _APP_PATHS.config_dir / "config.yaml"),
    )
).expanduser()
_PROJECT_CONFIG_EXAMPLE = PROJECT_ROOT / "config.example.yaml"
_INSTALLED_CONFIG_EXAMPLE = Path(sys.prefix) / "config.example.yaml"
CONFIG_EXAMPLE_PATH = _PROJECT_CONFIG_EXAMPLE if _PROJECT_CONFIG_EXAMPLE.exists() else _INSTALLED_CONFIG_EXAMPLE
_CONFIG_CACHE_KEY: tuple | None = None
_CONFIG_CACHE_VALUE: dict | None = None

def load_config() -> dict:
    """Read the current config from disk.

    Runtime callers use this instead of the import-time snapshot so dashboard
    Settings changes take effect without restarting the process.
    """
    src = CONFIG_PATH if CONFIG_PATH.exists() else CONFIG_EXAMPLE_PATH
    if not src.exists():
        return {}
    global _CONFIG_CACHE_KEY, _CONFIG_CACHE_VALUE
    try:
        content = src.read_text(encoding="utf-8")
        cache_key = (src.resolve(), content)
        if cache_key == _CONFIG_CACHE_KEY and _CONFIG_CACHE_VALUE is not None:
            return _CONFIG_CACHE_VALUE
        value = yaml.safe_load(content) or {}
        _CONFIG_CACHE_KEY = cache_key
        _CONFIG_CACHE_VALUE = value
        return value
    except Exception:
        return {}


def get_profile_config() -> dict:
    """Return profile config merged from config.yaml and the active DB profile.

    Priority (highest wins):
      1. Active profile's extracted fields (roles, skills, locations, etc.)
      2. config.yaml ``profile:`` section

    Source keys (``sources``, ``apis``) and secrets always come from yaml only.
    Safe to call at any point — gracefully falls back to yaml-only if the DB
    doesn't exist yet or has no active profile.
    """
    profile = load_config().get("profile") or {}
    if not isinstance(profile, dict):
        profile = {}

    # Lazy import to avoid circular dependency (dashboard.db imports config).
    try:
        from dashboard.db import get_active_profile  # noqa: PLC0415
        active = get_active_profile()
    except Exception:
        active = None

    if not active:
        return profile

    extracted: dict = {}
    try:
        import json as _json
        extracted = _json.loads(active.get("extracted_json") or "{}")
    except Exception:
        pass

    merged = dict(profile)

    # Overlay extracted fields. Use list() so callers get a copy.
    if extracted.get("roles"):
        merged["target_roles"] = list(extracted["roles"])
    if extracted.get("skills"):
        merged["skills"] = list(extracted["skills"])
    if extracted.get("locations"):
        merged["locations"] = list(extracted["locations"])
    if extracted.get("experience_level"):
        merged["experience_level"] = extracted["experience_level"]
        _level = extracted["experience_level"]
        _level_map = {
            "entry_level": ["new_grad", "entry_level", "junior", "associate", "early_career"],
            "mid_level": ["mid_level", "associate"],
            "senior": ["senior", "lead", "staff", "principal"],
        }
        merged["target_levels"] = _level_map.get(_level, merged.get("target_levels", []))
    if extracted.get("target_levels"):
        merged["target_levels"] = list(extracted["target_levels"])
    if extracted.get("work_modes"):
        merged["work_modes"] = list(extracted["work_modes"])
    # Confirmed onboarding choices outrank inference from the resume.
    if extracted.get("visa_policy"):
        merged["visa_policy"] = extracted["visa_policy"]
    else:
        visa_needed = extracted.get("visa_needed")
        if visa_needed is True:
            merged["visa_policy"] = "needs_sponsorship"
        elif visa_needed is False and "visa_policy" not in merged:
            merged["visa_policy"] = "none"
    if isinstance(extracted.get("timeline"), dict):
        merged["timeline"] = dict(extracted["timeline"])

    return merged

_CFG = load_config()


def _cfg_get(*keys, default=None):
    cur: Any = _CFG
    for k in keys:
        if not isinstance(cur, dict) or k not in cur:
            return default
        cur = cur[k]
    return cur


# --- Secrets (env only) ---
SERPAPI_API_KEY = os.getenv("SERPAPI_API_KEY", os.getenv("SERPAPI_KEY", ""))

# --- Storage (local-first) ---
_STORAGE = _cfg_get("storage", default={}) or {}
DEFAULT_HOME = "tracker"
_RUNTIME_PATHS = resolve_runtime_paths(
    project_root=PROJECT_ROOT,
    project_config_exists=CONFIG_PATH == _PROJECT_CONFIG_PATH and _PROJECT_CONFIG_PATH.exists(),
    storage_home=_STORAGE.get("home", DEFAULT_HOME),
)
JOB_AGENT_HOME = _RUNTIME_PATHS.data_dir
DB_FILENAME = _STORAGE.get("sqlite_file", "dashboard.db")
JOB_DB_PATH = Path(os.getenv("JOB_DB_PATH", str(JOB_AGENT_HOME / DB_FILENAME))).expanduser()
TRACKER_DIR = JOB_DB_PATH.parent
DASHBOARD_DB_PATH = Path(
    os.getenv("DASHBOARD_DB_PATH", str(TRACKER_DIR / DB_FILENAME))
).expanduser()
CONFIG_DIR = CONFIG_PATH.parent
CACHE_DIR = _RUNTIME_PATHS.cache_dir
LOG_DIR = _RUNTIME_PATHS.logs
EXPORT_DIR = _RUNTIME_PATHS.exports
BACKUP_DIR = _RUNTIME_PATHS.backups

# --- Dashboard ---
_DASH = _cfg_get("dashboard", default={}) or {}
DASHBOARD_HOST = os.getenv("DASHBOARD_HOST", _DASH.get("host", "127.0.0.1"))
DASHBOARD_PORT = int(os.getenv("DASHBOARD_PORT", _DASH.get("port", 8770)))

# --- Source / API enablement (config-driven free vs paid) ---
SOURCES = _cfg_get("sources", default=[]) or []
APIS = _cfg_get("apis", default={}) or {}


def enabled_sources(mode: str | None = None) -> list[dict]:
    """Return enabled sources, optionally filtered by mode ('free'|'paid')."""
    out = []
    for s in load_config().get("sources", []) or []:
        if not s.get("enabled", False):
            continue
        if mode and s.get("mode") != mode:
            continue
        out.append(s)
    return out


# Ensure local dirs exist
for _d in [JOB_AGENT_HOME, TRACKER_DIR]:
    try:
        _d.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass
