"""Smart scrape orchestration.

Runs small scrape windows and stops early once there are enough high-value
Apply Window cards. This keeps latency and paid/API usage down.
"""
from __future__ import annotations

from typing import Any

from pipeline.scrape import scrape_all
from ranking.apply_window import annotate_apply_window

WINDOWS = ("morning", "afternoon", "evening")


def _annotated_cards(result: dict[str, Any]) -> list[dict[str, Any]]:
    cards = []
    for job in result.get("dashboard_jobs", []):
        cards.append(job if job.get("apply_window_label") else annotate_apply_window(job))
    return cards


def _high_count(cards: list[dict[str, Any]]) -> int:
    return sum(1 for job in cards if job.get("apply_window_label") == "high")


def smart_scrape(*, live: bool = False, min_high: int = 3, max_selected: int = 15, max_windows: int = 3) -> dict[str, Any]:
    """Run windowed scraping and stop when enough high apply windows exist."""
    windows = list(WINDOWS[: max(1, min(max_windows, len(WINDOWS)))])
    aggregate: dict[str, Any] = {
        "ok": True,
        "mode": "smart_scrape",
        "live": live,
        "windows_run": [],
        "raw_count": 0,
        "source_results": {},
        "failed_sources": [],
        "dashboard_jobs": [],
        "high_apply_windows": 0,
        "stopped_reason": "windows_exhausted",
    }
    seen: set[str] = set()

    for window in windows:
        result = scrape_all(max_selected=max_selected, dry_run=not live, run_window=window)
        aggregate["windows_run"].append(window)
        aggregate["raw_count"] += int(result.get("raw_count", 0) or 0)
        aggregate["failed_sources"].extend(result.get("failed_sources", []) or [])
        for source, count in (result.get("source_results", {}) or {}).items():
            aggregate["source_results"][source] = aggregate["source_results"].get(source, 0) + count

        for job in _annotated_cards(result):
            key = job.get("apply_url") or f"{job.get('company')}|{job.get('title')}"
            if key in seen:
                continue
            seen.add(key)
            aggregate["dashboard_jobs"].append(job)

        aggregate["high_apply_windows"] = _high_count(aggregate["dashboard_jobs"])
        if aggregate["high_apply_windows"] >= min_high:
            aggregate["stopped_reason"] = "enough_high_apply_windows"
            break

    return aggregate
