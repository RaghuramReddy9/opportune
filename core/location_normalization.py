"""Strict deterministic normalization for user-confirmed locations."""
from __future__ import annotations

import hashlib
import re
from collections.abc import Iterable

_US_KEYS = {
    "us",
    "usa",
    "unitedstate",
    "unitedstates",
    "unitedstatesofamerica",
}
_REMOTE_US_KEYS = {
    "remoteus",
    "remoteusa",
    "remoteunitedstate",
    "remoteunitedstates",
    "remoteinus",
    "remoteinusa",
    "remoteinunitedstates",
}


def _key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").strip().lower())


def normalize_location_preference(value: str) -> dict:
    """Return canonical metadata without fuzzy matching or silent broadening."""
    original = value
    cleaned = str(value or "").strip()
    key = _key(cleaned)
    if key in _US_KEYS:
        return {
            "kind": "country",
            "code": "US",
            "display": "United States",
            "validation": "canonical",
            "original": original,
        }
    if key in _REMOTE_US_KEYS:
        return {
            "kind": "remote_region",
            "code": "REMOTE_US",
            "display": "Remote - United States",
            "validation": "canonical",
            "original": original,
        }

    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()[:10] if key else "empty"
    return {
        "kind": "custom",
        "code": f"CUSTOM-{digest}",
        "display": cleaned,
        "validation": "needs_review",
        "original": original,
    }


def normalize_location_preferences(values: Iterable[str]) -> list[dict]:
    """Normalize values while preserving user order and removing duplicate codes."""
    normalized: list[dict] = []
    seen: set[str] = set()
    for value in values:
        item = normalize_location_preference(value)
        identity = item["code"]
        if identity in seen:
            continue
        seen.add(identity)
        normalized.append(item)
    return normalized
