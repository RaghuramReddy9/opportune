"""Blocking dashboard launch with bounded readiness and browser opening."""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import threading
import time
import webbrowser
from pathlib import Path
from typing import Literal

import requests

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8770
DEFAULT_TIMEOUT = 30.0
HEALTH_POLL_INTERVAL = 0.25
LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1"}
HealthState = Literal["opportune", "foreign", "unavailable"]


def _is_loopback(host: str) -> bool:
    return host.lower().strip().strip("[]") in LOOPBACK_HOSTS


def probe_health(url: str) -> HealthState:
    """Classify the service at a health URL without treating foreign ports as ready."""
    try:
        response = requests.get(url, timeout=1)
    except requests.RequestException:
        return "unavailable"
    try:
        payload = response.json()
    except ValueError:
        return "foreign"
    if (
        response.status_code == 200
        and payload.get("ok") is True
        and payload.get("service") == "opportune"
    ):
        return "opportune"
    return "foreign"


def wait_for_health(url: str, timeout: float = DEFAULT_TIMEOUT) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        state = probe_health(url)
        if state == "opportune":
            return True
        if state == "foreign":
            return False
        time.sleep(HEALTH_POLL_INTERVAL)
    return False


def _open_browser(url: str, browser: str | None = None) -> bool:
    try:
        controller = webbrowser.get(browser) if browser else webbrowser
        return bool(controller.open(url, new=2))
    except webbrowser.Error:
        return False


def find_chrome_or_edge() -> tuple[str | None, str | None]:
    candidates = [
        ("chrome", "google-chrome-stable"),
        ("chrome", "google-chrome"),
        ("edge", "microsoft-edge-stable"),
        ("edge", "microsoft-edge"),
        ("chromium", "chromium"),
        ("chromium", "chromium-browser"),
    ]
    for name, executable in candidates:
        found = shutil.which(executable)
        if found:
            return found, name

    extras: list[Path] = []
    if sys.platform == "win32":
        for root_name in ("PROGRAMFILES", "PROGRAMFILES(X86)", "LOCALAPPDATA"):
            root = os.environ.get(root_name)
            if root:
                extras.extend(
                    [
                        Path(root) / "Google/Chrome/Application/chrome.exe",
                        Path(root) / "Microsoft/Edge/Application/msedge.exe",
                    ]
                )
    elif sys.platform == "darwin":
        extras.extend(
            [
                Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"),
                Path("/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge"),
                Path("/Applications/Chromium.app/Contents/MacOS/Chromium"),
            ]
        )
    for candidate in extras:
        if candidate.is_file() and os.access(candidate, os.X_OK):
            name = "edge" if "edge" in str(candidate).lower() else "chrome"
            return str(candidate), name
    return None, None


def _open_app_window(url: str) -> tuple[bool, str]:
    executable, _ = find_chrome_or_edge()
    if executable:
        try:
            subprocess.Popen(
                [executable, f"--app={url}", "--start-maximized", "--new-window"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return True, "app"
        except OSError:
            pass
    opened = _open_browser(url)
    return opened, "browser" if opened else "none"


def _run_dashboard_server(host: str, port: int) -> None:
    from dashapi.server import run

    run(host=host, port=port)


def _open_when_ready(
    health_url: str,
    url: str,
    *,
    browser: str | None = None,
    desktop: bool = False,
) -> None:
    if not wait_for_health(health_url):
        return
    if desktop:
        _open_app_window(url)
    else:
        _open_browser(url, browser)


def _launch(
    *,
    host: str,
    port: int,
    no_open: bool,
    allow_non_loopback: bool,
    browser: str | None,
    desktop: bool,
) -> dict:
    url = f"http://{host}:{port}"
    health_url = f"{url}/api/health"
    if not _is_loopback(host) and not allow_non_loopback:
        return {"ok": False, "url": url, "error": "Non-loopback binding requires --allow-non-loopback"}

    state = probe_health(health_url)
    if state == "foreign":
        return {"ok": False, "url": url, "error": f"Port {port} is occupied by a non-Opportune service"}
    if state == "opportune":
        opened, mode = (False, "none")
        if not no_open:
            if desktop:
                opened, mode = _open_app_window(url)
            else:
                opened, mode = _open_browser(url, browser), "browser"
        return {"ok": True, "url": url, "attached": True, "opened": opened, "mode": mode}

    if not no_open:
        threading.Thread(
            target=_open_when_ready,
            args=(health_url, url),
            kwargs={"browser": browser, "desktop": desktop},
            daemon=True,
        ).start()
    _run_dashboard_server(host, port)
    return {"ok": True, "url": url, "attached": False, "opened": not no_open, "mode": "desktop" if desktop else "browser"}


def run_server_with_browser_launch(
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
    no_open: bool = False,
    browser: str | None = None,
    allow_non_loopback: bool = False,
) -> dict:
    return _launch(
        host=host,
        port=port,
        no_open=no_open,
        allow_non_loopback=allow_non_loopback,
        browser=browser,
        desktop=False,
    )


def launch_desktop_app_mode(
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
    no_open: bool = False,
    allow_non_loopback: bool = False,
) -> dict:
    return _launch(
        host=host,
        port=port,
        no_open=no_open,
        allow_non_loopback=allow_non_loopback,
        browser=None,
        desktop=True,
    )
