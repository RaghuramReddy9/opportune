from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
import requests

from onboarding.providers import (
    OpenAICompatibleAnalyzer,
    ProviderConfigStore,
    normalize_provider_settings,
    test_provider_connection as check_provider_connection,
)


SECRET = "test-secret-provider-key"
RESUME = "Taylor Candidate\nApplied AI Engineer with Python and RAG."


def _analyzer() -> OpenAICompatibleAnalyzer:
    settings = normalize_provider_settings(
        {
            "provider": "custom",
            "base_url": "https://models.example.test/v1",
            "model": "resume-model",
            "requires_api_key": True,
        }
    )
    return OpenAICompatibleAnalyzer(settings, api_key=SECRET, timeout=2)


@pytest.mark.parametrize(
    ("error", "message"),
    [
        (requests.Timeout(f"timed out with {SECRET}"), "timed out"),
        (requests.ConnectionError(f"cannot reach {SECRET}"), "could not reach"),
    ],
)
def test_analyzer_returns_secret_safe_network_errors(error, message):
    with patch("onboarding.providers.requests.post", side_effect=error):
        with pytest.raises(ValueError, match=message) as caught:
            _analyzer().analyze(RESUME)

    assert SECRET not in str(caught.value)


@pytest.mark.parametrize(
    ("status", "message"),
    [
        (401, "rejected the connection"),
        (403, "rejected the connection"),
        (404, "model or endpoint was not found"),
        (429, "rate-limiting"),
        (503, "temporarily unavailable"),
    ],
)
def test_analyzer_maps_http_errors_without_response_body_or_secret(status, message):
    response = MagicMock()
    response.status_code = status
    response.raise_for_status.side_effect = requests.HTTPError(
        f"upstream body leaked {SECRET}", response=response
    )

    with patch("onboarding.providers.requests.post", return_value=response):
        with pytest.raises(ValueError, match=message) as caught:
            _analyzer().analyze(RESUME)

    assert SECRET not in str(caught.value)
    assert "upstream body" not in str(caught.value)


def test_analyzer_rejects_malformed_model_response_with_safe_message():
    response = MagicMock()
    response.raise_for_status.return_value = None
    response.json.return_value = {"choices": []}

    with patch("onboarding.providers.requests.post", return_value=response):
        with pytest.raises(ValueError, match="invalid resume analysis") as caught:
            _analyzer().analyze(RESUME)

    assert SECRET not in str(caught.value)


def test_provider_settings_reject_credentials_embedded_in_base_url():
    with pytest.raises(ValueError, match="must not contain credentials"):
        normalize_provider_settings(
            {
                "provider": "custom",
                "base_url": "https://user:password@models.example.test/v1",
                "model": "resume-model",
            }
        )


def test_connection_check_uses_same_secret_safe_timeout_error(tmp_path):
    store = ProviderConfigStore(
        settings_path=tmp_path / "provider.json",
        secret_path=tmp_path / "provider.key",
    )
    settings = normalize_provider_settings(
        {
            "provider": "custom",
            "base_url": "https://models.example.test/v1",
            "model": "resume-model",
            "requires_api_key": True,
        }
    )
    store.save(settings, api_key=SECRET)

    with patch(
        "onboarding.providers.requests.get",
        side_effect=requests.Timeout(f"timeout {SECRET}"),
    ):
        with pytest.raises(ValueError, match="timed out") as caught:
            check_provider_connection(store)

    assert SECRET not in str(caught.value)
