"""Lightweight job-link liveness check (stdlib only, no new dependency).

Used to verify scraped apply URLs actually resolve before they reach the
dashboard, so dead/broken links (e.g. 404) never masquerade as real roles.
"""
from __future__ import annotations

import ssl
import urllib.error
import urllib.request
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse

from core.http import is_safe_public_url

_PLACEHOLDER_HOSTS = {"example.com", "example.org", "localhost", "test.com"}

# Use the default SSL context (cert verification ON). A cert failure is an
# honest "unreachable" signal, not something we should mask for a link check.
_CTX = ssl.create_default_context()

_TIMEOUT = 12


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def verify_job_link(url: str | None, *, timeout: int = _TIMEOUT) -> dict[str, Any]:
    """Return a small status dict for a job apply URL.

    Keys: ok (bool), link_status (str), checked_at (str), detail (str)
    link_status values: placeholder | ok | dead | unreachable | error
    """
    if not url:
        return {"ok": False, "link_status": "dead", "checked_at": _now_iso(), "detail": "missing url"}

    if not is_safe_public_url(url):
        return {"ok": False, "link_status": "unsafe", "checked_at": _now_iso(), "detail": "non-public or malformed url"}

    host = urlparse(url).netloc.lower().replace("www.", "")
    if host in _PLACEHOLDER_HOSTS:
        return {"ok": False, "link_status": "placeholder", "checked_at": _now_iso(), "detail": f"placeholder host {host}"}

    headers = {"User-Agent": "Mozilla/5.0 (Opportune link-check)"}
    for method in ("HEAD", "GET"):
        try:
            req = urllib.request.Request(url, method=method, headers=headers)
            with urllib.request.urlopen(req, timeout=timeout, context=_CTX) as resp:
                final = resp.geturl()
                redirected = final.rstrip("/") != url.rstrip("/")
                return {
                    "ok": True,
                    "link_status": "ok",
                    "checked_at": _now_iso(),
                    "detail": f"{resp.status}{' redirected' if redirected else ''}",
                }
        except urllib.error.HTTPError as e:
            if method == "HEAD":
                # Some hosts block HEAD; retry with GET before giving up.
                continue
            return {"ok": False, "link_status": "dead", "checked_at": _now_iso(), "detail": f"HTTP {e.code}"}
        except Exception as e:  # network/DNS/SSL
            if method == "HEAD":
                continue
            return {"ok": False, "link_status": "unreachable", "checked_at": _now_iso(), "detail": str(e)[:80]}

    return {"ok": False, "link_status": "error", "checked_at": _now_iso(), "detail": "no response"}
