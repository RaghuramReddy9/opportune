"""
core/http.py — Shared HTTP session with retry logic.
"""
import socket

import requests
from ipaddress import ip_address
from requests.adapters import HTTPAdapter
from urllib.parse import urlparse
from urllib3.util.retry import Retry

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/html, */*",
    "Accept-Language": "en-US,en;q=0.9",
}

SESSION = requests.Session()
SESSION.headers.update(DEFAULT_HEADERS)

_retries = Retry(
    total=3,
    backoff_factor=1,
    status_forcelist=[429, 500, 502, 503, 504],
)
SESSION.mount("https://", HTTPAdapter(max_retries=_retries))
SESSION.mount("http://", HTTPAdapter(max_retries=_retries))

DEFAULT_TIMEOUT = 20


def sanitize_url(url: str) -> str:
    """Sanitize and validate a scraped URL. Ensures correct scheme and formatting."""
    if not url:
        return ""
    u = url.strip()
    if u.startswith("//"):
        u = "https:" + u
    elif u.startswith("http://"):
        u = "https://" + u[7:]
    elif not u.startswith("https://") and not u.startswith("http://"):
        if "." in u:
            u = "https://" + u

    # Remove backslashes and trailing/leading space
    u = u.replace("\\", "")
    parsed = urlparse(u)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        return ""
    return u


def is_safe_public_url(url: str | None, *, resolve_dns: bool = False) -> bool:
    """Reject malformed URLs and local/private destinations.

    ``resolve_dns`` is reserved for code that is about to make a network request.
    It fails closed when a hostname does not resolve or any resolved address is not
    globally routable.
    """
    if not url:
        return False
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower().rstrip(".")
    if parsed.scheme not in {"http", "https"} or not host or parsed.username or parsed.password:
        return False
    if host == "localhost" or host.endswith(".localhost"):
        return False
    try:
        return ip_address(host).is_global
    except ValueError:
        if not resolve_dns:
            return True
    try:
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        addresses = {
            sockaddr[0]
            for _family, _kind, _proto, _canonname, sockaddr in socket.getaddrinfo(
                host,
                port,
                type=socket.SOCK_STREAM,
            )
        }
    except (OSError, ValueError):
        return False
    return bool(addresses) and all(
        ip_address(str(address).split("%", 1)[0]).is_global for address in addresses
    )
