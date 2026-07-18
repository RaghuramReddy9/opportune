"""One-command dashboard and app-window launcher contracts."""
from __future__ import annotations

from unittest.mock import Mock, patch

import jobhunt
from desktop_launcher import (
    launch_desktop_app_mode,
    probe_health,
    run_server_with_browser_launch,
    wait_for_health,
)


def test_run_and_desktop_commands_are_packaged_cli_routes():
    run_args = jobhunt.build_parser().parse_args(["run", "--no-open"])
    desktop_args = jobhunt.build_parser().parse_args(["desktop", "--no-open"])

    assert run_args.command == "run"
    assert run_args.no_open is True
    assert desktop_args.command == "desktop"
    assert desktop_args.no_open is True


def test_cli_run_passes_configured_launch_options():
    args = jobhunt.build_parser().parse_args(
        ["run", "--host", "127.0.0.1", "--port", "8999", "--browser", "firefox"]
    )
    with patch("desktop_launcher.run_server_with_browser_launch", return_value={"ok": True} ) as launch:
        args.func(args)

    launch.assert_called_once_with(
        host="127.0.0.1",
        port=8999,
        no_open=False,
        browser="firefox",
        allow_non_loopback=False,
    )


def test_non_loopback_bind_requires_explicit_opt_in():
    with patch("desktop_launcher._run_dashboard_server") as server:
        result = run_server_with_browser_launch(host="0.0.0.0")

    assert result["ok"] is False
    assert "non-loopback" in result["error"].lower()
    server.assert_not_called()


def test_foreign_service_on_port_fails_without_starting_server():
    with (
        patch("desktop_launcher.probe_health", return_value="foreign"),
        patch("desktop_launcher._run_dashboard_server") as server,
    ):
        result = run_server_with_browser_launch()

    assert result["ok"] is False
    assert "non-Opportune" in result["error"]
    server.assert_not_called()


def test_existing_opportune_service_is_reused_and_opened():
    with (
        patch("desktop_launcher.probe_health", return_value="opportune"),
        patch("desktop_launcher._open_browser", return_value=True) as opener,
        patch("desktop_launcher._run_dashboard_server") as server,
    ):
        result = run_server_with_browser_launch(browser="firefox")

    assert result["ok"] is True
    assert result["attached"] is True
    opener.assert_called_once_with("http://127.0.0.1:8770", "firefox")
    server.assert_not_called()


def test_new_server_runs_in_calling_thread_and_browser_waits_in_background():
    thread = Mock()
    with (
        patch("desktop_launcher.probe_health", return_value="unavailable"),
        patch("desktop_launcher.threading.Thread", return_value=thread) as thread_factory,
        patch("desktop_launcher._run_dashboard_server") as server,
    ):
        result = run_server_with_browser_launch(no_open=False)

    assert result["ok"] is True
    assert result["attached"] is False
    thread_factory.assert_called_once()
    thread.start.assert_called_once()
    server.assert_called_once_with("127.0.0.1", 8770)


def test_no_open_starts_blocking_server_without_opener_thread():
    with (
        patch("desktop_launcher.probe_health", return_value="unavailable"),
        patch("desktop_launcher.threading.Thread") as thread_factory,
        patch("desktop_launcher._run_dashboard_server") as server,
    ):
        result = run_server_with_browser_launch(no_open=True)

    assert result["ok"] is True
    thread_factory.assert_not_called()
    server.assert_called_once_with("127.0.0.1", 8770)


def test_desktop_prefers_chromium_app_mode_when_attaching():
    process = Mock()
    with (
        patch("desktop_launcher.probe_health", return_value="opportune"),
        patch("desktop_launcher.find_chrome_or_edge", return_value=("/usr/bin/chromium", "chromium")),
        patch("desktop_launcher.subprocess.Popen", return_value=process) as popen,
    ):
        result = launch_desktop_app_mode()

    assert result["mode"] == "app"
    command = popen.call_args.args[0]
    assert "--app=http://127.0.0.1:8770" in command
    assert "--start-maximized" in command


def test_probe_health_distinguishes_opportune_foreign_and_unavailable():
    response = Mock(status_code=200)
    response.json.return_value = {"ok": True, "service": "opportune"}
    with patch("desktop_launcher.requests.get", return_value=response):
        assert probe_health("http://local/api/health") == "opportune"

    response.json.return_value = {"ok": True, "service": "other"}
    with patch("desktop_launcher.requests.get", return_value=response):
        assert probe_health("http://local/api/health") == "foreign"

    import requests

    with patch("desktop_launcher.requests.get", side_effect=requests.ConnectionError("closed")):
        assert probe_health("http://local/api/health") == "unavailable"


def test_wait_for_health_is_bounded_and_rejects_foreign_service():
    with patch("desktop_launcher.probe_health", return_value="foreign") as probe:
        assert wait_for_health("http://local/api/health", timeout=1) is False

    probe.assert_called_once()
