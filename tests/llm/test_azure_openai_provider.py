# tests/llm/test_azure_openai_provider.py
# V0 - Initial implementation
#
# Tests for src/llm/azure_openai_provider.py — AzureOpenAIProvider.
#
# Uses respx to mock httpx at the transport layer — no real API calls.
#
# Scenarios:
#   E1  — provider_name() returns "azure_openai"
#   E2  — AzureOpenAIProvider is an instance of LLMProvider
#   E3  — complete() returns text content from a mocked HTTP 200 response
#   E4  — HTTP 500 error is retried — succeeds on second attempt
#   E5  — All retries exhausted after HTTP 500s → raises LLMOutputParseError
#   E6  — Timeout is retried — succeeds on second attempt
#   E7  — All timeouts exhausted → raises LLMOutputParseError
#   E8  — Missing azure_openai_api_key → raises ValueError at construction
#   E9  — Missing azure_openai_endpoint → raises ValueError at construction
#   E10 — Missing azure_openai_deployment_name → raises ValueError at construction
#   E11 — Missing azure_openai_api_version → raises ValueError at construction

import httpx
import pytest
import respx

from src.llm.base import LLMProvider
from src.llm.azure_openai_provider import AzureOpenAIProvider
from src.core.exceptions import LLMOutputParseError


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# Canonical test URL — matches what AzureOpenAIProvider builds from _make_settings()
_TEST_ENDPOINT = "https://test-resource.openai.azure.com"
_TEST_DEPLOYMENT = "test-deployment"
_TEST_API_VERSION = "2024-02-01"
_TEST_URL = (
    f"{_TEST_ENDPOINT}/openai/deployments/{_TEST_DEPLOYMENT}"
    f"/chat/completions?api-version={_TEST_API_VERSION}"
)


def _make_settings(
    api_key: str | None = "test-azure-key",
    endpoint: str | None = _TEST_ENDPOINT,
    deployment: str | None = _TEST_DEPLOYMENT,
    api_version: str | None = _TEST_API_VERSION,
):
    """
    Build a minimal settings-like object for AzureOpenAIProvider construction.

    Each credential can be set to None individually to test missing-field errors.
    Uses a simple namespace object — avoids loading real YAML/env in tests.
    """

    class _LLM:
        provider = "azure_openai"
        max_tokens = 1000
        timeout_seconds = 30
        retry_max = 3
        retry_backoff_seconds = 2

    class _FakeSettings:
        llm = _LLM()
        azure_openai_api_key = api_key
        azure_openai_endpoint = endpoint
        azure_openai_deployment_name = deployment
        azure_openai_api_version = api_version

    return _FakeSettings()


def _azure_response(content: str) -> dict:
    """
    Build a minimal Azure OpenAI response body.

    Azure OpenAI uses the same response shape as OpenAI Chat Completions:
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

class TestAzureOpenAIProvider:
    """Tests for AzureOpenAIProvider — mocked HTTP, zero real API calls."""

    # --- Construction ---

    def test_e1_provider_name_returns_azure_openai(self):
        """E1 — provider_name() returns the string 'azure_openai'."""
        provider = AzureOpenAIProvider(_make_settings())
        assert provider.provider_name() == "azure_openai"

    def test_e2_is_instance_of_llm_provider(self):
        """E2 — AzureOpenAIProvider satisfies the LLMProvider interface."""
        provider = AzureOpenAIProvider(_make_settings())
        assert isinstance(provider, LLMProvider)

    def test_e8_missing_api_key_raises_value_error(self):
        """E8 — Missing azure_openai_api_key raises ValueError at construction."""
        with pytest.raises(ValueError, match="AZURE_OPENAI_API_KEY"):
            AzureOpenAIProvider(_make_settings(api_key=None))

    def test_e9_missing_endpoint_raises_value_error(self):
        """E9 — Missing azure_openai_endpoint raises ValueError at construction."""
        with pytest.raises(ValueError, match="AZURE_OPENAI_ENDPOINT"):
            AzureOpenAIProvider(_make_settings(endpoint=None))

    def test_e10_missing_deployment_raises_value_error(self):
        """E10 — Missing azure_openai_deployment_name raises ValueError at construction."""
        with pytest.raises(ValueError, match="AZURE_OPENAI_DEPLOYMENT_NAME"):
            AzureOpenAIProvider(_make_settings(deployment=None))

    def test_e11_missing_api_version_raises_value_error(self):
        """E11 — Missing azure_openai_api_version raises ValueError at construction."""
        with pytest.raises(ValueError, match="AZURE_OPENAI_API_VERSION"):
            AzureOpenAIProvider(_make_settings(api_version=None))

    # --- Happy path ---

    @respx.mock
    def test_e3_complete_returns_content_from_200_response(self):
        """E3 — complete() returns text content from a mocked HTTP 200 response."""
        respx.post(_TEST_URL).mock(
            return_value=httpx.Response(200, json=_azure_response("intent json"))
        )
        provider = AzureOpenAIProvider(_make_settings())
        result = provider.complete("system prompt", "user prompt")
        assert result == "intent json"

    # --- Retry on HTTP error ---

    @respx.mock
    def test_e4_http_500_retried_succeeds_on_second_attempt(self):
        """E4 — HTTP 500 on first call is retried; second attempt succeeds."""
        settings = _make_settings()
        settings.llm.retry_backoff_seconds = 0  # no sleep in tests

        respx.post(_TEST_URL).mock(
            side_effect=[
                httpx.Response(500, json={"error": "server error"}),
                httpx.Response(200, json=_azure_response("success after retry")),
            ]
        )
        provider = AzureOpenAIProvider(settings)
        result = provider.complete("sys", "user")
        assert result == "success after retry"

    @respx.mock
    def test_e5_all_retries_exhausted_raises_llm_output_parse_error(self):
        """E5 — All retry attempts fail with HTTP 500 → raises LLMOutputParseError."""
        settings = _make_settings()
        settings.llm.retry_max = 3
        settings.llm.retry_backoff_seconds = 0  # no sleep in tests

        respx.post(_TEST_URL).mock(
            return_value=httpx.Response(500, json={"error": "server error"})
        )
        provider = AzureOpenAIProvider(settings)
        with pytest.raises(LLMOutputParseError, match="3 attempt"):
            provider.complete("sys", "user")

    # --- Retry on timeout ---

    @respx.mock
    def test_e6_timeout_retried_succeeds_on_second_attempt(self):
        """E6 — Timeout on first call is retried; second attempt succeeds."""
        settings = _make_settings()
        settings.llm.retry_backoff_seconds = 0  # no sleep in tests

        respx.post(_TEST_URL).mock(
            side_effect=[
                httpx.TimeoutException("timed out"),
                httpx.Response(200, json=_azure_response("success after timeout")),
            ]
        )
        provider = AzureOpenAIProvider(settings)
        result = provider.complete("sys", "user")
        assert result == "success after timeout"

    @respx.mock
    def test_e7_all_timeouts_exhausted_raises_llm_output_parse_error(self):
        """E7 — All retry attempts time out → raises LLMOutputParseError."""
        settings = _make_settings()
        settings.llm.retry_max = 3
        settings.llm.retry_backoff_seconds = 0  # no sleep in tests

        respx.post(_TEST_URL).mock(
            side_effect=httpx.TimeoutException("timed out")
        )
        provider = AzureOpenAIProvider(settings)
        with pytest.raises(LLMOutputParseError, match="3 attempt"):
            provider.complete("sys", "user")
