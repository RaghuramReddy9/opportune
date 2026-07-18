"""Stable discovery-funnel schema shared by pipeline, API, CLI, and UI."""
from __future__ import annotations

DISCOVERY_FUNNEL_VERSION = 1
FUNNEL_STAGES = (
    "tasks",
    "requests",
    "raw",
    "normalized",
    "location",
    "acquisition",
    "ranking",
    "freshness",
    "link",
    "lifecycle",
    "buckets",
    "persistence",
    "dashboard",
)


def new_funnel() -> dict:
    return {
        "version": DISCOVERY_FUNNEL_VERSION,
        "stages": {
            stage: {"count": 0, "reason_codes": {}, "by_source": {}}
            for stage in FUNNEL_STAGES
        },
    }


def record_stage(
    funnel: dict,
    stage: str,
    count: int,
    *,
    reason_codes: dict[str, int] | None = None,
    by_source: dict[str, int] | None = None,
) -> None:
    if funnel.get("version") != DISCOVERY_FUNNEL_VERSION:
        raise ValueError("unsupported discovery-funnel version")
    if stage not in FUNNEL_STAGES:
        raise ValueError(f"unknown discovery-funnel stage: {stage}")
    funnel["stages"][stage] = {
        "count": max(0, int(count)),
        "reason_codes": {str(key): int(value) for key, value in (reason_codes or {}).items()},
        "by_source": {str(key): int(value) for key, value in (by_source or {}).items()},
    }


def _sum_mapping(target: dict[str, int], source: dict[str, int]) -> None:
    for key, value in source.items():
        target[key] = target.get(key, 0) + int(value)


def merge_funnels(funnels: list[dict]) -> dict:
    merged = new_funnel()
    for funnel in funnels:
        if not funnel:
            continue
        if funnel.get("version") != DISCOVERY_FUNNEL_VERSION:
            raise ValueError("unsupported discovery-funnel version")
        for stage in FUNNEL_STAGES:
            source = funnel.get("stages", {}).get(stage, {})
            target = merged["stages"][stage]
            target["count"] += int(source.get("count", 0))
            _sum_mapping(target["reason_codes"], source.get("reason_codes", {}))
            _sum_mapping(target["by_source"], source.get("by_source", {}))
    return merged


def first_zero_stage(funnel: dict) -> str | None:
    for stage in FUNNEL_STAGES:
        if int(funnel.get("stages", {}).get(stage, {}).get("count", 0)) == 0:
            return stage
    return None
