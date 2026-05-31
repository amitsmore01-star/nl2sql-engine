# tests/llm/test_openai_provider.py
# V0 - Initial implementation
#
# Tests for src/llm/openai_provider.py — OpenAIProvider.
#
# Uses respx to mock httpx at the transport layer — no real API calls.
#
# Scenarios:
#   D1 — provider_name() returns "openai"
#   D2 — OpenAIProvider is an instance of LLMProvider
#   D3 — complete() returns text content from a mocked HTTP 200 response
#   D4 — HTTP 500 error is retried — succeeds on second attempt
#   D5 — All retries exhausted after HTTP 500s → raises LLMOutputParseError
#   D6 — Timeout is retried — succeeds on second attempt
#   D7 — All retries exhausted after timeouts → raises LLMOutputParseError
#   D8 — Missing openai_api_key in settings → raises ValueError at construction

import httpx
import pytest
import respx

from src.llm.base import LLMProvider
from src.llm.openai_provider import OpenAIProvider, _OPENAI_API_URL
from src.core.exceptions import LLMOutputParseError


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_settings(api_key: str | None = "test-openai-key"):
    """Build a minimal settings-like object for OpenAIProvider construction."""

    class _LLM:
        provider = "openai"
        max_tokens = 1000
        timeout_seconds = 30
        retry_max = 3
        retry_backoff_seconds = 2
        temperature = 0.0

    class _FakeSettings:
        llm = _LLM()
        openai_api_key = api_key

    return _FakeSettings()


def _openai_response(content: str) -> dict:
    """Build a minimal OpenAI-shaped response body."""
    return {
        "choices": [
            {"message": {"content": content}}
        ]
    }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestOpenAIProvider:
    """Tests for OpenAIProvider — mocked HTTP, zero real API calls."""

    # --- Construction ---

    def test_d1_provider_name_returns_openai(self):
        """D1 — provider_name() returns the string 'openai'."""
        provider = OpenAIProvider(_make_settings())
        assert provider.provider_name() == "openai"

    def test_d2_is_instance_of_llm_provider(self):
        """D2 — OpenAIProvider satisfies the LLMProvider interface."""
        provider = OpenAIProvider(_make_settings())
        assert isinstance(provider, LLMProvider)

    def test_d8_missing_api_key_raises_value_error(self):
        """D8 — Missing openai_api_key raises ValueError at construction."""
        with pytest.raises(ValueError, match="OPENAI_API_KEY"):
            OpenAIProvider(_make_settings(api_key=None))

    # --- Happy path ---

    @respx.mock
    def test_d3_complete_returns_content_from_200_response(self):
        """D3 — complete() returns the text content from a mocked HTTP 200 response."""
        respx.post(_OPENAI_API_URL).mock(
            return_value=httpx.Response(200, json=_openai_response("intent json"))
        )
        provider = OpenAIProvider(_make_settings())
        result = provider.complete("system prompt", "user prompt")
        assert result == "intent json"

    # --- Retry on HTTP error ---

    @respx.mock
    def test_d4_http_500_retried_succeeds_on_second_attempt(self):
        """D4 — HTTP 500 on first call is retried; second attempt succeeds."""
        settings = _make_settings()
        settings.llm.retry_backoff_seconds = 0   # no sleep in tests

        respx.post(_OPENAI_API_URL).mock(
            side_effect=[
                httpx.Response(500, json={"error": "server error"}),
                httpx.Response(200, json=_openai_response("success after retry")),
            ]
        )
        provider = OpenAIProvider(settings)
        result = provider.complete("sys", "user")
        assert result == "success after retry"

    @respx.mock
    def test_d5_all_retries_exhausted_raises_llm_output_parse_error(self):
        """D5 — All retry attempts fail with HTTP 500 → raises LLMOutputParseError."""
        settings = _make_settings()
        settings.llm.retry_max = 3
        settings.llm.retry_backoff_seconds = 0   # no sleep in tests

        respx.post(_OPENAI_API_URL).mock(
            return_value=httpx.Response(500, json={"error": "server error"})
        )
        provider = OpenAIProvider(settings)
        with pytest.raises(LLMOutputParseError, match="3 attempt"):
            provider.complete("sys", "user")

    # --- Retry on timeout ---

    @respx.mock
    def test_d6_timeout_retried_succeeds_on_second_attempt(self):
        """D6 — Timeout on first call is retried; second attempt succeeds."""
        settings = _make_settings()
        settings.llm.retry_backoff_seconds = 0   # no sleep in tests

        respx.post(_OPENAI_API_URL).mock(
            side_effect=[
                httpx.TimeoutException("timed out"),
                httpx.Response(200, json=_openai_response("success after timeout")),
            ]
        )
        provider = OpenAIProvider(settings)
        result = provider.complete("sys", "user")
        assert result == "success after timeout"

    @respx.mock
    def test_d7_all_timeouts_exhausted_raises_llm_output_parse_error(self):
        """D7 — All retry attempts time out → raises LLMOutputParseError."""
        settings = _make_settings()
        settings.llm.retry_max = 3
        settings.llm.retry_backoff_seconds = 0   # no sleep in tests

        respx.post(_OPENAI_API_URL).mock(
            side_effect=httpx.TimeoutException("timed out")
        )
        provider = OpenAIProvider(settings)
        with pytest.raises(LLMOutputParseError, match="3 attempt"):
            provider.complete("sys", "user")
