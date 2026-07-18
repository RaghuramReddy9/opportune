"""Persistent source health and circuit-breaker state for scraper adapters.

The source registry is durable configuration; this module stores runtime health in
tracker/source_health.json so noisy quota/403/429 sources do not spam every cron
run while direct ATS sources continue normally.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable

from config import TRACKER_DIR

DEFAULT_HEALTH_PATH = TRACKER_DIR / "source_health.json"
RATE_LIMIT_COOLDOWN_HOURS = 24
SERVER_ERROR_COOLDOWN_HOURS = 6
GLOBAL_CIRCUIT_SOURCES = {"api_serpapi", "api_jsearch", "api_adzuna", "wellfound", "builtin", "ycombinator", "github_lists"}


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def parse_time(value: str) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed
    except Exception:
        return None


def _resolve_path(path: Path | None) -> Path:
    return path if path is not None else DEFAULT_HEALTH_PATH


def load_health(path: Path | None = None) -> dict:
    path = _resolve_path(path)
    if not path.exists():
        return {"sources": {}, "last_updated": ""}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return {"sources": {}, "last_updated": ""}
        data.setdefault("sources", {})
        return data
    except Exception:
        return {"sources": {}, "last_updated": ""}


def save_health(data: dict, path: Path | None = None) -> None:
    path = _resolve_path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    data["last_updated"] = now_utc().isoformat()
    path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")


def health_key(source: str, name: str = "") -> str:
    """Return a circuit-breaker key.

    API/board sources are global; ATS company tasks are per-company so one bad
    company board never disables the whole adapter family.
    """
    source = source or "unknown"
    if source in GLOBAL_CIRCUIT_SOURCES:
        return source
    clean_name = re.sub(r"[^a-z0-9]+", "-", (name or source).lower()).strip("-")
    return f"{source}:{clean_name or source}"


def classify_error(error: str) -> str:
    text = (error or "").lower()
    if not text:
        return "none"
    if any(token in text for token in ("429", "rate limit", "rate-limit", "too many requests", "quota", "402")):
        return "rate_limited"
    if any(token in text for token in ("403", "forbidden", "cloudflare", "captcha", "blocked")):
        return "blocked"
    if any(token in text for token in ("500", "502", "503", "504", "timeout", "temporarily unavailable")):
        return "server_or_timeout"
    return "failed"


def cooldown_until_for(category: str, at: datetime | None = None) -> str:
    at = at or now_utc()
    if category in {"rate_limited", "blocked"}:
        return (at + timedelta(hours=RATE_LIMIT_COOLDOWN_HOURS)).isoformat()
    if category == "server_or_timeout":
        return (at + timedelta(hours=SERVER_ERROR_COOLDOWN_HOURS)).isoformat()
    return ""


def should_skip_source(source: str, name: str = "", path: Path | None = None, at: datetime | None = None) -> tuple[bool, dict]:
    path = _resolve_path(path)
    at = at or now_utc()
    data = load_health(path)
    key = health_key(source, name)
    record = data.get("sources", {}).get(key, {})
    until = parse_time(record.get("circuit_open_until", ""))
    if until and until > at:
        return True, {**record, "health_key": key}
    return False, {**record, "health_key": key}


def record_source_success(source: str, name: str = "", jobs: int = 0, path: Path | None = None) -> None:
    path = _resolve_path(path)
    data = load_health(path)
    key = health_key(source, name)
    sources = data.setdefault("sources", {})
    record = sources.setdefault(key, {"source": source, "name": name})
    record.update({
        "source": source,
        "name": name,
        "status": "ok" if jobs > 0 else "empty_ok",
        "last_success_at": now_utc().isoformat(),
        "last_job_count": jobs,
        "consecutive_failures": 0,
        "circuit_open_until": "",
        "last_error": "",
        "last_error_category": "none",
    })
    save_health(data, path)


def record_source_failure(source: str, name: str = "", error: str = "", path: Path | None = None) -> dict:
    path = _resolve_path(path)
    data = load_health(path)
    key = health_key(source, name)
    sources = data.setdefault("sources", {})
    record = sources.setdefault(key, {"source": source, "name": name})
    category = classify_error(error)
    failures = int(record.get("consecutive_failures", 0)) + 1
    record.update({
        "source": source,
        "name": name,
        "status": category,
        "last_failure_at": now_utc().isoformat(),
        "last_error": "[redacted]",
        "last_error_category": category,
        "consecutive_failures": failures,
    })
    until = cooldown_until_for(category)
    if until:
        record["circuit_open_until"] = until
    save_health(data, path)
    return {**record, "health_key": key}


def record_source_skip(source: str, name: str = "", reason: str = "circuit_open", path: Path | None = None) -> dict:
    path = _resolve_path(path)
    data = load_health(path)
    key = health_key(source, name)
    sources = data.setdefault("sources", {})
    record = sources.setdefault(key, {"source": source, "name": name})
    record.update({
        "source": source,
        "name": name,
        "status": reason,
        "last_skipped_at": now_utc().isoformat(),
    })
    save_health(data, path)
    return {**record, "health_key": key}


def filter_runnable_tasks(tasks: Iterable[tuple], path: Path | None = None) -> tuple[list[tuple], list[dict]]:
    path = _resolve_path(path)
    runnable: list[tuple] = []
    skipped: list[dict] = []
    for task in tasks:
        source_key, name = task[0], task[1]
        skip, record = should_skip_source(source_key, name, path=path)
        if skip:
            skipped_record = record_source_skip(source_key, name, path=path)
            skipped.append({
                "source": source_key,
                "company": name,
                "reason": "circuit_open",
                "health_key": skipped_record.get("health_key"),
                "circuit_open_until": skipped_record.get("circuit_open_until", ""),
                "last_error_category": skipped_record.get("last_error_category", ""),
            })
        else:
            runnable.append(task)
    return runnable, skipped


def summarize_health(path: Path | None = None) -> dict:
    path = _resolve_path(path)
    data = load_health(path)
    sources = data.get("sources", {})
    open_circuits = []
    at = now_utc()
    for key, record in sources.items():
        until = parse_time(record.get("circuit_open_until", ""))
        if until and until > at:
            open_circuits.append({"health_key": key, **record})
    return {
        "tracked_sources": len(sources),
        "open_circuits": len(open_circuits),
        "open_circuit_samples": open_circuits[:10],
        "last_updated": data.get("last_updated", ""),
    }
