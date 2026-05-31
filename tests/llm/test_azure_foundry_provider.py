# tests/llm/test_azure_foundry_provider.py
# V0 - Initial implementation
#
# Tests for src/llm/azure_foundry_provider.py — AzureFoundryProvider.
#
# Uses respx to mock httpx at the transport layer — no real API calls.
#
# Scenarios:
#   F1  — provider_name() returns "azure_foundry"
#   F2  — AzureFoundryProvider is an instance of LLMProvider
#   F3  — complete() returns text content from a mocked HTTP 200 response
#   F4  — HTTP 500 error is retried — succeeds on second attempt
#   F5  — All retries exhausted after HTTP 500s → raises LLMOutputParseError
#   F6  — Timeout is retried — succeeds on second attempt
#   F7  — All timeouts exhausted → raises LLMOutputParseError
#   F8  — Missing AZURE_FOUNDRY_API_KEY → raises ValueError at construction
#   F9  — Missing AZURE_FOUNDRY_ENDPOINT → raises ValueError at construction
#   F10 — Missing AZURE_FOUNDRY_DEPLOYMENT_NAME → raises ValueError at construction
#   F11 — Request body contains "model" field with deployment name

import httpx
import pytest
import respx

from src.llm.base import LLMProvider
from src.llm.azure_foundry_provider import AzureFoundryProvider
from src.core.exceptions import LLMOutputParseError


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# Canonical test values — match what AzureFoundryProvider builds from _make_settings()
_TEST_ENDPOINT = "https://test-foundry.services.ai.azure.com/openai/v1"
_TEST_DEPLOYMENT = "gpt-4o-mini"

# URL built by provider: endpoint.rstrip("/") + "/chat/completions"
_TEST_URL = f"{_TEST_ENDPOINT}/chat/completions"


def _make_settings(
    api_key: str | None = "test-foundry-key",
    endpoint: str | None = _TEST_ENDPOINT,
    deployment: str | None = _TEST_DEPLOYMENT,
):
    """
    Build a minimal settings-like object for AzureFoundryProvider construction.

    Each credential can be set to None individually to test missing-field errors.
    Uses a simple namespace object — avoids loading real YAML/env in tests.

    Note: Only 3 credentials needed (no api_version — Foundry does not use it).
    """

    class _LLM:
        provider = "azure_foundry"
        max_tokens = 1000
        timeout_seconds = 30
        retry_max = 3
        retry_backoff_seconds = 2
        temperature = 0.0

    class _FakeSettings:
        llm = _LLM()
        azure_foundry_api_key = api_key
        azure_foundry_endpoint = endpoint
        azure_foundry_deployment_name = deployment

    return _FakeSettings()


def _foundry_response(content: str) -> dict:
    """
    Build a minimal Azure AI Foundry response body.

    Foundry uses the OpenAI-compatible response shape:
      choices[0].message.content
    """
    return {
        "choices": [
            {"message": {"content": content}}
        ]
    }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestAzureFoundryProvider:
    """Tests for AzureFoundryProvider — mocked HTTP, zero real API calls."""

    # --- Construction ---

    def test_f1_provider_name_returns_azure_foundry(self):
        """F1 — provider_name() returns the string 'azure_foundry'."""
        provider = AzureFoundryProvider(_make_settings())
        assert provider.provider_name() == "azure_foundry"

    def test_f2_is_instance_of_llm_provider(self):
        """F2 — AzureFoundryProvider satisfies the LLMProvider interface."""
        provider = AzureFoundryProvider(_make_settings())
        assert isinstance(provider, LLMProvider)

    def test_f8_missing_api_key_raises_value_error(self):
        """F8 — Missing AZURE_FOUNDRY_API_KEY raises ValueError at construction."""
        with pytest.raises(ValueError, match="AZURE_FOUNDRY_API_KEY"):
            AzureFoundryProvider(_make_settings(api_key=None))

    def test_f9_missing_endpoint_raises_value_error(self):
        """F9 — Missing AZURE_FOUNDRY_ENDPOINT raises ValueError at construction."""
        with pytest.raises(ValueError, match="AZURE_FOUNDRY_ENDPOINT"):
            AzureFoundryProvider(_make_settings(endpoint=None))

    def test_f10_missing_deployment_raises_value_error(self):
        """F10 — Missing AZURE_FOUNDRY_DEPLOYMENT_NAME raises ValueError at construction."""
        with pytest.raises(ValueError, match="AZURE_FOUNDRY_DEPLOYMENT_NAME"):
            AzureFoundryProvider(_make_settings(deployment=None))

    # --- Happy path ---

    @respx.mock
    def test_f3_complete_returns_content_from_200_response(self):
        """F3 — complete() returns text content from a mocked HTTP 200 response."""
        respx.post(_TEST_URL).mock(
            return_value=httpx.Response(200, json=_foundry_response("some ir json"))
        )
        provider = AzureFoundryProvider(_make_settings())
        result = provider.complete("system prompt", "user prompt")
        assert result == "some ir json"

    # --- Request body verification ---

    @respx.mock
    def test_f11_request_body_contains_model_field(self):
        """F11 — Request body includes 'model' field with the deployment name."""
        captured = {}

        def capture(request):
            import json
            captured["body"] = json.loads(request.content)
            return httpx.Response(200, json=_foundry_response("ok"))

        respx.post(_TEST_URL).mock(side_effect=capture)
        provider = AzureFoundryProvider(_make_settings())
        provider.complete("sys", "user")

        assert "model" in captured["body"], "Request body must contain 'model' field"
        assert captured["body"]["model"] == _TEST_DEPLOYMENT

    # --- Retry on HTTP error ---

    @respx.mock
    def test_f4_http_500_retried_succeeds_on_second_attempt(self):
        """F4 — HTTP 500 on first call is retried; second attempt succeeds."""
        settings = _make_settings()
        settings.llm.retry_backoff_seconds = 0  # no sleep in tests

        respx.post(_TEST_URL).mock(
            side_effect=[
                httpx.Response(500, json={"error": "server error"}),
                httpx.Response(200, json=_foundry_response("success after retry")),
            ]
        )
        provider = AzureFoundryProvider(settings)
        result = provider.complete("sys", "user")
        assert result == "success after retry"

    @respx.mock
    def test_f5_all_retries_exhausted_raises_llm_output_parse_error(self):
        """F5 — All retry attempts fail with HTTP 500 → raises LLMOutputParseError."""
        settings = _make_settings()
        settings.llm.retry_max = 3
        settings.llm.retry_backoff_seconds = 0  # no sleep in tests

        respx.post(_TEST_URL).mock(
            return_value=httpx.Response(500, json={"error": "server error"})
        )
        provider = AzureFoundryProvider(settings)
        with pytest.raises(LLMOutputParseError, match="3 attempt"):
            provider.complete("sys", "user")

    # --- Retry on timeout ---

    @respx.mock
    def test_f6_timeout_retried_succeeds_on_second_attempt(self):
        """F6 — Timeout on first call is retried; second attempt succeeds."""
        settings = _make_settings()
        settings.llm.retry_backoff_seconds = 0  # no sleep in tests

        respx.post(_TEST_URL).mock(
            side_effect=[
                httpx.TimeoutException("timed out"),
                httpx.Response(200, json=_foundry_response("success after timeout")),
            ]
        )
        provider = AzureFoundryProvider(settings)
        result = provider.complete("sys", "user")
        assert result == "success after timeout"

    @respx.mock
    def test_f7_all_timeouts_exhausted_raises_llm_output_parse_error(self):
        """F7 — All retry attempts time out → raises LLMOutputParseError."""
        settings = _make_settings()
        settings.llm.retry_max = 3
        settings.llm.retry_backoff_seconds = 0  # no sleep in tests
        

        respx.post(_TEST_URL).mock(
            side_effect=httpx.TimeoutException("timed out")
        )
        provider = AzureFoundryProvider(settings)
        with pytest.raises(LLMOutputParseError, match="3 attempt"):
            provider.complete("sys", "user")
