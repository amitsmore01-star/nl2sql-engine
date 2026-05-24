# tests/llm/test_anthropic_provider.py
# V0 - Initial implementation
#
# Tests for src/llm/anthropic_provider.py — AnthropicProvider.
#
# Uses respx to mock httpx at the transport layer — no real API calls.
#
# Scenarios:
#   F1 — provider_name() returns "anthropic"
#   F2 — AnthropicProvider is an instance of LLMProvider
#   F3 — complete() returns text content from a mocked HTTP 200 response
#   F4 — HTTP 500 error is retried — succeeds on second attempt
#   F5 — All retries exhausted after HTTP 500s → raises LLMOutputParseError
#   F6 — Timeout is retried — succeeds on second attempt
#   F7 — All timeouts exhausted → raises LLMOutputParseError
#   F8 — Missing anthropic_api_key → raises ValueError at construction

import httpx
import pytest
import respx

from src.llm.base import LLMProvider
from src.llm.anthropic_provider import AnthropicProvider, _ANTHROPIC_API_URL
from src.core.exceptions import LLMOutputParseError


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_settings(api_key: str | None = "test-anthropic-key"):
    """Build a minimal settings-like object for AnthropicProvider construction."""

    class _LLM:
        provider = "anthropic"
        max_tokens = 1000
        timeout_seconds = 30
        retry_max = 3
        retry_backoff_seconds = 2

    class _FakeSettings:
        llm = _LLM()
        anthropic_api_key = api_key

    return _FakeSettings()


def _anthropic_response(text: str) -> dict:
    """
    Build a minimal Anthropic Messages API response body.

    Anthropic response shape differs from OpenAI:
      content[0].text   (not choices[0].message.content)
    """
    return {
        "content": [
            {"type": "text", "text": text}
        ]
    }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestAnthropicProvider:
    """Tests for AnthropicProvider — mocked HTTP, zero real API calls."""

    # --- Construction ---

    def test_f1_provider_name_returns_anthropic(self):
        """F1 — provider_name() returns the string 'anthropic'."""
        provider = AnthropicProvider(_make_settings())
        assert provider.provider_name() == "anthropic"

    def test_f2_is_instance_of_llm_provider(self):
        """F2 — AnthropicProvider satisfies the LLMProvider interface."""
        provider = AnthropicProvider(_make_settings())
        assert isinstance(provider, LLMProvider)

    def test_f8_missing_api_key_raises_value_error(self):
        """F8 — Missing anthropic_api_key raises ValueError at construction."""
        with pytest.raises(ValueError, match="ANTHROPIC_API_KEY"):
            AnthropicProvider(_make_settings(api_key=None))

    # --- Happy path ---

    @respx.mock
    def test_f3_complete_returns_content_from_200_response(self):
        """F3 — complete() returns text content from a mocked HTTP 200 response."""
        respx.post(_ANTHROPIC_API_URL).mock(
            return_value=httpx.Response(200, json=_anthropic_response("intent json"))
        )
        provider = AnthropicProvider(_make_settings())
        result = provider.complete("system prompt", "user prompt")
        assert result == "intent json"

    # --- Retry on HTTP error ---

    @respx.mock
    def test_f4_http_500_retried_succeeds_on_second_attempt(self):
        """F4 — HTTP 500 on first call is retried; second attempt succeeds."""
        settings = _make_settings()
        settings.llm.retry_backoff_seconds = 0  # no sleep in tests

        respx.post(_ANTHROPIC_API_URL).mock(
            side_effect=[
                httpx.Response(500, json={"error": "server error"}),
                httpx.Response(200, json=_anthropic_response("success after retry")),
            ]
        )
        provider = AnthropicProvider(settings)
        result = provider.complete("sys", "user")
        assert result == "success after retry"

    @respx.mock
    def test_f5_all_retries_exhausted_raises_llm_output_parse_error(self):
        """F5 — All retry attempts fail with HTTP 500 → raises LLMOutputParseError."""
        settings = _make_settings()
        settings.llm.retry_max = 3
        settings.llm.retry_backoff_seconds = 0  # no sleep in tests

        respx.post(_ANTHROPIC_API_URL).mock(
            return_value=httpx.Response(500, json={"error": "server error"})
        )
        provider = AnthropicProvider(settings)
        with pytest.raises(LLMOutputParseError, match="3 attempt"):
            provider.complete("sys", "user")

    # --- Retry on timeout ---

    @respx.mock
    def test_f6_timeout_retried_succeeds_on_second_attempt(self):
        """F6 — Timeout on first call is retried; second attempt succeeds."""
        settings = _make_settings()
        settings.llm.retry_backoff_seconds = 0  # no sleep in tests

        respx.post(_ANTHROPIC_API_URL).mock(
            side_effect=[
                httpx.TimeoutException("timed out"),
                httpx.Response(200, json=_anthropic_response("success after timeout")),
            ]
        )
        provider = AnthropicProvider(settings)
        result = provider.complete("sys", "user")
        assert result == "success after timeout"

    @respx.mock
    def test_f7_all_timeouts_exhausted_raises_llm_output_parse_error(self):
        """F7 — All retry attempts time out → raises LLMOutputParseError."""
        settings = _make_settings()
        settings.llm.retry_max = 3
        settings.llm.retry_backoff_seconds = 0  # no sleep in tests

        respx.post(_ANTHROPIC_API_URL).mock(
            side_effect=httpx.TimeoutException("timed out")
        )
        provider = AnthropicProvider(settings)
        with pytest.raises(LLMOutputParseError, match="3 attempt"):
            provider.complete("sys", "user")
