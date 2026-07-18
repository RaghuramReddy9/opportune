"""Privacy-safe GitHub Release update availability checks."""
from __future__ import annotations

import re
import time
from collections.abc import Callable
from typing import Any
from urllib.parse import urlparse

import requests

CURRENT_VERSION = "0.1.1"
LATEST_RELEASE_API = "https://api.github.com/repos/RaghuramReddy9/opportune/releases/latest"
_CACHE_SECONDS = 6 * 60 * 60
_VERSION_PATTERN = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)$")
_cache: tuple[float, dict[str, Any]] | None = None


def _version_tuple(value: str) -> tuple[int, int, int] | None:
    match = _VERSION_PATTERN.fullmatch(str(value or "").strip())
    if not match:
        return None
    return tuple(int(part) for part in match.groups())  # type: ignore[return-value]


def _safe_release_url(value: str) -> str:
    parsed = urlparse(str(value or "").strip())
    expected_prefix = "/RaghuramReddy9/opportune/releases/"
    if parsed.scheme != "https" or parsed.netloc != "github.com":
        return ""
    if not parsed.path.startswith(expected_prefix):
        return ""
    return parsed.geturl()


def _unavailable(current_version: str) -> dict[str, Any]:
    return {
        "ok": True,
        "checked": False,
        "current_version": current_version,
        "latest_version": "",
        "update_available": False,
        "release_url": "",
    }


def check_for_updates(
    *,
    current_version: str = CURRENT_VERSION,
    fetcher: Callable[..., Any] | None = None,
    force: bool = False,
) -> dict[str, Any]:
    """Check the latest stable GitHub Release without exposing provider errors."""
    global _cache

    now = time.monotonic()
    use_cache = fetcher is None
    if use_cache and not force and _cache and _cache[0] > now:
        return dict(_cache[1])

    request = fetcher or requests.get
    try:
        response = request(
            LATEST_RELEASE_API,
            headers={
                "Accept": "application/vnd.github+json",
                "User-Agent": f"opportune/{current_version}",
            },
            timeout=3,
        )
        response.raise_for_status()
        payload = response.json()
        current = _version_tuple(current_version)
        latest = _version_tuple(payload.get("tag_name", ""))
        release_url = _safe_release_url(payload.get("html_url", ""))
        if current is None or latest is None or not release_url:
            result = _unavailable(current_version)
        else:
            latest_version = ".".join(str(part) for part in latest)
            result = {
                "ok": True,
                "checked": True,
                "current_version": current_version,
                "latest_version": latest_version,
                "update_available": latest > current,
                "release_url": release_url,
            }
    except Exception:
        result = _unavailable(current_version)

    if use_cache:
        _cache = (now + _CACHE_SECONDS, dict(result))
    return result
