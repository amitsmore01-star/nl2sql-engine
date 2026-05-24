# src/llm/openai_provider.py
# V0 - Initial implementation
#
# OpenAIProvider — calls the OpenAI Chat Completions API (GPT-4o-mini).
#
# Design:
#   - Implements LLMProvider ABC — complete() and provider_name().
#   - Synchronous — uses httpx.Client (blocking). No async.
#   - Retry loop with exponential backoff on HTTP errors and timeouts.
#   - All config (timeout, retry_max, backoff) read from settings — zero hardcoding.
#   - Raises ValueError at construction if OPENAI_API_KEY is missing.
#   - Raises LLMOutputParseError if all retries are exhausted.

import time

import httpx

from src.llm.base import LLMProvider
from src.core.exceptions import LLMOutputParseError
from src.config.settings import Settings

# OpenAI Chat Completions endpoint — never hardcoded in pipeline logic
_OPENAI_API_URL = "https://api.openai.com/v1/chat/completions"
_MODEL = "gpt-4o-mini"


class OpenAIProvider(LLMProvider):
    """
    LLM provider that calls the OpenAI Chat Completions API.

    Uses GPT-4o-mini. Synchronous. Retries on HTTP errors and timeouts.

    Args:
        settings: Loaded Settings object. Reads:
                    settings.openai_api_key        — OPENAI_API_KEY from .env
                    settings.llm.timeout_seconds   — per-call timeout
                    settings.llm.retry_max         — max attempts
                    settings.llm.retry_backoff_seconds — base backoff (exponential)
                    settings.llm.max_tokens        — max tokens in response

    Raises:
        ValueError: At construction if openai_api_key is missing or empty.
    """

    def __init__(self, settings: Settings) -> None:
        if not settings.openai_api_key:
            raise ValueError(
                "OPENAI_API_KEY is not set. "
                "Add OPENAI_API_KEY=your-key-here to your .env file."
            )
        self._api_key = settings.openai_api_key
        self._timeout = settings.llm.timeout_seconds
        self._retry_max = settings.llm.retry_max
        self._retry_backoff = settings.llm.retry_backoff_seconds
        self._max_tokens = settings.llm.max_tokens

    def complete(self, system_prompt: str, user_prompt: str) -> str:
        """
        Send a two-part prompt to OpenAI and return the text response.

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
            f"OpenAI API call failed after {self._retry_max} attempt(s). "
            f"Last error: {last_error}"
        )

    def _call(self, system_prompt: str, user_prompt: str) -> str:
        """
        Make a single HTTP call to the OpenAI API.

        Separated from complete() so tests can target the HTTP layer directly
        and the retry loop in complete() stays clean.

        Raises:
            httpx.TimeoutException: If the request exceeds timeout_seconds.
            httpx.HTTPStatusError:  If the API returns a 4xx or 5xx status.
        """
        with httpx.Client(timeout=self._timeout) as client:
            response = client.post(
                url=_OPENAI_API_URL,
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": _MODEL,
                    "max_tokens": self._max_tokens,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user",   "content": user_prompt},
                    ],
                },
            )
            response.raise_for_status()
            return response.json()["choices"][0]["message"]["content"]

    def provider_name(self) -> str:
        """Return the provider identifier string."""
        return "openai"
