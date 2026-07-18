"""Privacy-safe retained source-quality outcomes."""
from __future__ import annotations

import json
import os
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from config import TRACKER_DIR
from core.source_health import classify_error
from pipeline.funnel import FUNNEL_STAGES

SOURCE_QUALITY_VERSION = 1
DEFAULT_PATH = TRACKER_DIR / "source-quality.json"
UNAVAILABLE_METRICS = ["per_source_latency_seconds", "per_source_cost_usd"]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def build_snapshot(result: dict) -> dict:
    """Build one retained report without errors, URLs, companies, or profile data."""
    funnel = result.get("discovery_funnel") or {}
    stages = funnel.get("stages") or {}
    source_names: set[str] = set()
    for stage in stages.values():
        source_names.update(str(name) for name in (stage.get("by_source") or {}))
    failures: dict[str, Counter] = {}
    for failure in result.get("failed_sources") or []:
        source = str(failure.get("source") or "unknown")
        source_names.add(source)
        failures.setdefault(source, Counter())[classify_error(str(failure.get("error") or ""))] += 1
    skipped = Counter(str(item.get("source") or "unknown") for item in result.get("skipped_sources") or [])
    source_names.update(skipped)

    sources = {}
    for source in sorted(source_names):
        counts = {
            stage: int((stages.get(stage, {}).get("by_source") or {}).get(source, 0))
            for stage in FUNNEL_STAGES
        }
        raw_count = counts.get("raw", 0)
        failure_count = sum(failures.get(source, {}).values())
        if skipped[source] and not raw_count:
            outcome = "skipped"
        elif failure_count and raw_count:
            outcome = "partial"
        elif failure_count:
            outcome = "failed"
        elif raw_count:
            outcome = "success"
        else:
            outcome = "empty"
        sources[source] = {
            **{f"{stage}_count": count for stage, count in counts.items()},
            "outcome": outcome,
            "failure_categories": dict(failures.get(source, {})),
            "skipped_count": int(skipped[source]),
            "latency_seconds": None,
            "cost_usd": None,
        }

    return {
        "version": SOURCE_QUALITY_VERSION,
        "run_id": str((result.get("catalog") or {}).get("run_id") or ""),
        "recorded_at": _now(),
        "aggregate_runtime_seconds": (result.get("timings_seconds") or {}).get("total"),
        "unavailable_metrics": list(UNAVAILABLE_METRICS),
        "sources": sources,
    }


def load_history(path: Path | None = None) -> dict:
    target = Path(path or DEFAULT_PATH)
    if not target.exists():
        return {"version": SOURCE_QUALITY_VERSION, "runs": []}
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError):
        return {"version": SOURCE_QUALITY_VERSION, "runs": []}
    if payload.get("version") != SOURCE_QUALITY_VERSION or not isinstance(payload.get("runs"), list):
        return {"version": SOURCE_QUALITY_VERSION, "runs": []}
    return payload


def record_snapshot(snapshot: dict, *, path: Path | None = None, retain: int = 100) -> Path:
    if retain < 1:
        raise ValueError("retain must be positive")
    target = Path(path or DEFAULT_PATH)
    target.parent.mkdir(parents=True, exist_ok=True)
    history = load_history(target)
    history["runs"] = [*history["runs"], snapshot][-retain:]
    temporary = target.with_suffix(target.suffix + ".tmp")
    temporary.write_text(json.dumps(history, indent=2, sort_keys=True), encoding="utf-8")
    os.chmod(temporary, 0o600)
    temporary.replace(target)
    return target


def record_result(result: dict, *, path: Path | None = None, retain: int = 100) -> Path:
    return record_snapshot(build_snapshot(result), path=path, retain=retain)


def summarize_history(history: dict | None = None, *, path: Path | None = None) -> dict:
    payload = history if history is not None else load_history(path)
    summaries: dict[str, dict] = {}
    for run in payload.get("runs", []):
        for source, record in (run.get("sources") or {}).items():
            summary = summaries.setdefault(
                source,
                {
                    "runs": 0,
                    "success_runs": 0,
                    "partial_runs": 0,
                    "failed_runs": 0,
                    "empty_runs": 0,
                    "skipped_runs": 0,
                    "failure_categories": {},
                },
            )
            summary["runs"] += 1
            summary[f"{record.get('outcome', 'failed')}_runs"] += 1
            for stage in FUNNEL_STAGES:
                key = f"{stage}_count"
                summary[key] = summary.get(key, 0) + int(record.get(key, 0))
            for category, count in (record.get("failure_categories") or {}).items():
                summary["failure_categories"][category] = (
                    summary["failure_categories"].get(category, 0) + int(count)
                )
    return {
        "version": SOURCE_QUALITY_VERSION,
        "run_count": len(payload.get("runs", [])),
        "sources": summaries,
        "unavailable_metrics": list(UNAVAILABLE_METRICS),
    }
