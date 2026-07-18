"""Safe, release-based software update checks."""
from __future__ import annotations

import re
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class FakeResponse:
    def __init__(self, payload: dict, status_code: int = 200):
        self.payload = payload
        self.status_code = status_code

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self) -> dict:
        return self.payload


def test_package_and_runtime_versions_stay_in_sync():
    from core.update_check import CURRENT_VERSION
    from dashapi.server import app

    project_metadata = (PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    version_match = re.search(r'^version = "([^"]+)"$', project_metadata, re.MULTILINE)

    assert version_match is not None
    assert CURRENT_VERSION == version_match.group(1)
    assert app.version == version_match.group(1)


def test_newer_github_release_is_reported_with_safe_release_link():
    from core.update_check import check_for_updates

    result = check_for_updates(
        current_version="0.1.1",
        fetcher=lambda *args, **kwargs: FakeResponse(
            {
                "tag_name": "v0.1.2",
                "html_url": "https://github.com/RaghuramReddy9/opportune/releases/tag/v0.1.2",
            }
        ),
    )

    assert result == {
        "ok": True,
        "checked": True,
        "current_version": "0.1.1",
        "latest_version": "0.1.2",
        "update_available": True,
        "release_url": "https://github.com/RaghuramReddy9/opportune/releases/tag/v0.1.2",
    }


def test_same_or_older_release_does_not_offer_an_update():
    from core.update_check import check_for_updates

    result = check_for_updates(
        current_version="0.1.1",
        fetcher=lambda *args, **kwargs: FakeResponse(
            {
                "tag_name": "v0.1.1",
                "html_url": "https://github.com/RaghuramReddy9/opportune/releases/tag/v0.1.1",
            }
        ),
    )

    assert result["checked"] is True
    assert result["update_available"] is False
    assert result["latest_version"] == "0.1.1"


def test_update_check_failure_is_private_and_non_blocking():
    from core.update_check import check_for_updates

    def unavailable(*args, **kwargs):
        raise RuntimeError("private proxy hostname and token must not leak")

    result = check_for_updates(current_version="0.1.1", fetcher=unavailable)

    assert result == {
        "ok": True,
        "checked": False,
        "current_version": "0.1.1",
        "latest_version": "",
        "update_available": False,
        "release_url": "",
    }
    assert "private" not in str(result)


def test_invalid_release_metadata_fails_closed():
    from core.update_check import check_for_updates

    result = check_for_updates(
        current_version="0.1.1",
        fetcher=lambda *args, **kwargs: FakeResponse(
            {"tag_name": "latest", "html_url": "https://attacker.example/update"}
        ),
    )

    assert result["checked"] is False
    assert result["update_available"] is False
    assert result["release_url"] == ""
