"""Temporal weighting for job freshness and user availability.

Provides:
  - load_availability(): reads profile/availability.yaml (HH:MM:SS)
  - freshness_score(freshness_str): maps pipeline freshness strings to 0‑1.
  - time_weight(now=None): returns 1.0 when now is inside the user's
    availability window, otherwise decays linearly to 0 at 2 hours outside.
  - combined_weight(freshness_str, now=None): freshness_score * time_weight.
"""

import sys
from datetime import datetime, time, timezone
from pathlib import Path
from typing import Tuple, Optional

import yaml


def load_availability() -> Tuple[time, time]:
    """Read profile/availability.yaml and return (start, end) as time objects."""
    project_path = Path(__file__).resolve().parents[1] / "profile" / "availability.yaml"
    installed_path = Path(sys.prefix) / "profile" / "availability.yaml"
    path = project_path if project_path.exists() else installed_path
    if not path.exists():
        # sensible default: 08:00‑11:00
        return time(8, 0, 0), time(11, 0, 0)
    with open(path, "rt", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    start_str = data.get("start", "08:00:00")
    end_str = data.get("end", "11:00:00")
    return time.fromisoformat(start_str), time.fromisoformat(end_str)


# Mapping from pipeline freshness strings to a 0‑1 score.
# These strings come from core/freshness.py and notion sync.
_FRESHNESS_MAP = {
    "New (0-24h)": 1.0,
    "Newly Discovered": 1.0,   # treat as fresh
    "Recent (24-48h)": 0.8,
    "This Week (3-7d)": 0.6,
    "Old (8-14d)": 0.3,
    # fallback for anything else
    "Unknown": 0.0,
}


def freshness_score(freshness_str: str) -> float:
    """Convert a freshness string from the pipeline to a 0‑1 score."""
    return _FRESHNESS_MAP.get(freshness_str.strip(), 0.0)


def time_weight(now: Optional[datetime] = None) -> float:
    """Return a weight based on the current time vs. the user's availability window.

    If now is inside the window → 1.0.
    Otherwise, compute minutes to the nearest window edge and apply linear decay
    reaching 0 at 120 minutes outside the window.
    """
    now = now or datetime.now(timezone.utc)
    start, end = load_availability()
    t = now.time()
    if start <= t <= end:
        return 1.0
    # Compute minutes to closest edge (using seconds difference)
    def minutes_to(target: time) -> float:
        dt = datetime.combine(now.date(), target) - datetime.combine(now.date(), t)
        return abs(dt.total_seconds()) / 60.0

    minutes_to_start = minutes_to(start)
    minutes_to_end = minutes_to(end)
    minutes_to_edge = min(minutes_to_start, minutes_to_end)
    # Linear decay: weight = max(0, 1 - minutes_to_edge / 120)
    return max(0.0, 1.0 - minutes_to_edge / 120.0)


def combined_weight(freshness_str: str, now: Optional[datetime] = None) -> float:
    """Return freshness_score * time_weight."""
    return freshness_score(freshness_str) * time_weight(now)


if __name__ == "__main__":  # pragma: no cover
    # Quick sanity checks
    print("Freshness scores:")
    for k, v in _FRESHNESS_MAP.items():
        print(f"  {k}: {v}")
    print("\nTime weight now:", time_weight())
    print("Combined weight example (New (0-24h)):", combined_weight("New (0-24h)"))