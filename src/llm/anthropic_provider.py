# src/llm/anthropic_provider.py
# V0 - Initial implementation
# V1 - Story 5.9: Read settings.llm.temperature at construction and pass it
#      in the request body. temperature=0 ensures deterministic SQL output.
#      Anthropic temperature range: 0.0–1.0 (vs 0.0–2.0 for OpenAI/Azure).

import time

import httpx

from src.llm.base import LLMProvider
from src.core.exceptions import LLMOutputParseError
from src.config.settings import Settings

_ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"
_MODEL = "claude-sonnet-4-5"
_API_VERSION = "2023-06-01"


class AnthropicProvider(LLMProvider):
    """
    LLM provider that calls the Anthropic Messages API (Claude Sonnet).

    Args:
        settings: Loaded Settings object. Reads:
                    settings.anthropic_api_key         — ANTHROPIC_API_KEY from .env
                    settings.llm.timeout_seconds        — per-call timeout
                    settings.llm.retry_max              — max attempts
                    settings.llm.retry_backoff_seconds  — base backoff (exponential)
                    settings.llm.max_tokens             — max tokens in response
                    settings.llm.temperature            — sampling temperature (default 0)

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
        self._temperature = settings.llm.temperature

    def complete(self, system_prompt: str, user_prompt: str) -> str:
        """
        Send a two-part prompt to Anthropic and return the text response.

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

        Anthropic-specific request shape:
          - system is a top-level string (not inside messages[])
          - messages[] contains only the user turn
          - temperature is a top-level field (same as OpenAI — range 0.0–1.0)
          - Response text is at content[0].text
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
                    "temperature": self._temperature,
                    "system": system_prompt,
                    "messages": [
                        {"role": "user", "content": user_prompt},
                    ],
                },
            )
            response.raise_for_status()
            return response.json()["content"][0]["text"]

    def provider_name(self) -> str:
        return "anthropic"
