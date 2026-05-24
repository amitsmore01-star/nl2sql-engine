# src/llm/anthropic_provider.py
# V0 - Initial implementation
#
# AnthropicProvider — calls the Anthropic Messages API (Claude Sonnet).
#
# Design:
#   - Implements LLMProvider ABC — complete() and provider_name().
#   - Synchronous — uses httpx.Client (blocking). No async.
#   - Retry loop with exponential backoff on HTTP errors and timeouts.
#   - All config (timeout, retry_max, backoff) read from settings — zero hardcoding.
#   - Model string is a module-level constant — flagged as tech debt for future
#     config-driven approach (see SESSION_CONTEXT.md Story 3.3 decisions).
#   - Raises ValueError at construction if anthropic_api_key is missing.
#   - Raises LLMOutputParseError if all retries are exhausted.
#
# Anthropic Messages API:
#   POST https://api.anthropic.com/v1/messages
#   Headers: x-api-key, anthropic-version, content-type
#   Body:    model, max_tokens, system (string), messages (list)
#   Response: content[0].text  (type: "text")

import time

import httpx

from src.llm.base import LLMProvider
from src.core.exceptions import LLMOutputParseError
from src.config.settings import Settings

# Anthropic Messages API endpoint — never hardcoded in pipeline logic
_ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"

# Model string — tech debt: move to settings.llm.anthropic_model in a future story
# Using claude-sonnet-4-5 as the current stable Claude Sonnet model
_MODEL = "claude-sonnet-4-5"

# Anthropic API version header — required on every request
_API_VERSION = "2023-06-01"


class AnthropicProvider(LLMProvider):
    """
    LLM provider that calls the Anthropic Messages API.

    Uses Claude Sonnet (see _MODEL constant). Synchronous. Retries on HTTP
    errors and timeouts using the same pattern as all other real providers.

    The Anthropic Messages API differs from OpenAI in two ways:
      1. system prompt is a top-level string field, not a message in the list
      2. Response text is at content[0].text, not choices[0].message.content

    Args:
        settings: Loaded Settings object. Reads:
                    settings.anthropic_api_key         — ANTHROPIC_API_KEY from .env
                    settings.llm.timeout_seconds        — per-call timeout
                    settings.llm.retry_max              — max attempts
                    settings.llm.retry_backoff_seconds  — base backoff (exponential)
                    settings.llm.max_tokens             — max tokens in response

    Raises:
        ValueError: At construction if anthropic_api_key is missing or empty.
    """

    def __init__(self, settings: Settings) -> None:
        if not settings.anthropic_api_key:
            raise ValueError(
                "ANTHROPIC_API_KEY is not set. "
                "Add ANTHROPIC_API_KEY=your-key-here to your .env file."
            )
        self._api_key = settings.anthropic_api_key
        self._timeout = settings.llm.timeout_seconds
        self._retry_max = settings.llm.retry_max
        self._retry_backoff = settings.llm.retry_backoff_seconds
        self._max_tokens = settings.llm.max_tokens

    def complete(self, system_prompt: str, user_prompt: str) -> str:
        """
        Send a two-part prompt to Anthropic and return the text response.

        Retries up to retry_max times with exponential backoff on:
          - httpx.TimeoutException  (request timed out)
          - httpx.HTTPStatusError   (4xx/5xx response)

        Args:
            system_prompt: Sets the LLM role and output format instructions.
            user_prompt:   The actual query or data for the LLM to process.

        Returns:
            Raw text content from the LLM response. Typically JSON.
            Parsing is the caller's responsibility.

        Raises:
            LLMOutputParseError: If all retry attempts fail.
        """
        last_error: Exception | None = None

        for attempt in range(self._retry_max):
            try:
                return self._call(system_prompt, user_prompt)
            except (httpx.TimeoutException, httpx.HTTPStatusError) as exc:
                last_error = exc
                if attempt < self._retry_max - 1:
                    wait = self._retry_backoff ** attempt
                    time.sleep(wait)

        raise LLMOutputParseError(
            f"Anthropic API call failed after {self._retry_max} attempt(s). "
            f"Last error: {last_error}"
        )

    def _call(self, system_prompt: str, user_prompt: str) -> str:
        """
        Make a single HTTP call to the Anthropic Messages API.

        Separated from complete() so tests can target the HTTP layer directly
        and the retry loop in complete() stays clean.

        Anthropic-specific request shape:
          - system is a top-level string (not inside messages[])
          - messages[] contains only the user turn
          - Response text is at content[0].text

        Raises:
            httpx.TimeoutException: If the request exceeds timeout_seconds.
            httpx.HTTPStatusError:  If the API returns a 4xx or 5xx status.
        """
        with httpx.Client(timeout=self._timeout) as client:
            response = client.post(
                url=_ANTHROPIC_API_URL,
                headers={
                    "x-api-key": self._api_key,
                    "anthropic-version": _API_VERSION,
                    "Content-Type": "application/json",
                },
                json={
                    "model": _MODEL,
                    "max_tokens": self._max_tokens,
                    "system": system_prompt,
                    "messages": [
                        {"role": "user", "content": user_prompt},
                    ],
                },
            )
            response.raise_for_status()
            return response.json()["content"][0]["text"]

    def provider_name(self) -> str:
        """Return the provider identifier string."""
        return "anthropic"
