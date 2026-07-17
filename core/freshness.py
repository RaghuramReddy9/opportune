"""
core/freshness.py — Shared freshness normalization.

All adapters produce date strings in various formats. This module
converts them to a single set of freshness buckets used by the
ranking and selection pipeline.

Buckets:
    New (0-24h)       — posted today
    Recent (24-48h)   — posted yesterday
    This Week (3-7d)  — posted within a week
    Old (8-14d)       — posted within two weeks
    Stale (15d+)      — older than two weeks
    Unknown           — no date information
"""
from datetime import datetime, timezone


def days_ago_to_freshness(days: int) -> str:
    """Convert a days-ago integer to a freshness bucket string."""
    if days <= 1:
        return "New (0-24h)"
    elif days <= 2:
        return "Recent (24-48h)"
    elif days <= 7:
        return "This Week (3-7d)"
    elif days <= 14:
        return "Old (8-14d)"
    return "Stale (15d+)"


def parse_iso_date(date_str: str) -> str:
    """Parse an ISO 8601 date string and return a freshness bucket.

    Handles formats like:
        2026-06-16T00:00:00.000Z
        2026-06-10T01:31:17Z
        2026-06-16
    """
    if not date_str:
        return "Unknown"
    try:
        dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        days = (datetime.now(timezone.utc) - dt).days
        return days_ago_to_freshness(days)
    except (ValueError, TypeError):
        return "Unknown"


def parse_relative_text(text: str) -> str:
    """Parse relative date text like '3 days ago', 'Just posted', '2 weeks ago'."""
    import re

    if not text:
        return "Unknown"

    text_lower = text.lower().strip()

    if any(w in text_lower for w in ("just", "today", "hour", "minute")):
        return "New (0-24h)"

    nums = re.findall(r"\d+", text_lower)
    if not nums:
        return "Unknown"

    n = int(nums[0])
    if "week" in text_lower:
        return days_ago_to_freshness(n * 7)
    if "month" in text_lower:
        return "Stale (15d+)"
    return days_ago_to_freshness(n)


def get_age_days(job: dict) -> int:
    """Return the number of days old a job is based on its posted_date or freshness bucket.
    If age is unknown, returns -1.
    """
    posted_date = job.get("posted_date", "")
    if posted_date:
        try:
            # Handle formats like YYYY-MM-DD
            date_clean = posted_date.split("T")[0].strip()
            dt = datetime.fromisoformat(date_clean)
            days = (datetime.now(timezone.utc).date() - dt.date()).days
            return max(0, days)
        except Exception:
            pass

    freshness = job.get("freshness", "Unknown")
    if freshness == "New (0-24h)":
        return 0
    elif freshness == "Recent (24-48h)":
        return 2
    elif freshness == "This Week (3-7d)":
        return 5
    elif freshness == "Old (8-14d)":
        return 10
    elif freshness == "Stale (15d+)":
        return 20

    return -1  # Unknown
