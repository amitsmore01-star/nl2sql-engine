# src/llm/azure_openai_provider.py
# V0 - Initial implementation
#
# AzureOpenAIProvider — calls the Azure OpenAI Chat Completions API.
#
# Design:
#   - Implements LLMProvider ABC — complete() and provider_name().
#   - Synchronous — uses httpx.Client (blocking). No async.
#   - Retry loop with exponential backoff on HTTP errors and timeouts.
#   - All config (timeout, retry_max, backoff) read from settings — zero hardcoding.
#   - URL built at runtime from endpoint + deployment + api_version — never hardcoded.
#   - Raises ValueError at construction if any required Azure credential is missing.
#   - Raises LLMOutputParseError if all retries are exhausted.
#
# Azure OpenAI URL pattern:
#   {endpoint}/openai/deployments/{deployment_name}/chat/completions?api-version={api_version}

import time

import httpx

from src.llm.base import LLMProvider
from src.core.exceptions import LLMOutputParseError
from src.config.settings import Settings

# Path template — endpoint and query param are injected at construction time
_URL_TEMPLATE = "{endpoint}/openai/deployments/{deployment}/chat/completions"


class AzureOpenAIProvider(LLMProvider):
    """
    LLM provider that calls the Azure OpenAI Chat Completions API.

    The Azure OpenAI API is compatible with the OpenAI Chat Completions shape
    but uses a different URL structure and authenticates via Ocp-Apim-Subscription-Key
    (or api-key header) rather than a Bearer token.

    Args:
        settings: Loaded Settings object. Reads:
                    settings.azure_openai_endpoint          — base URL
                    settings.azure_openai_api_key           — API key
                    settings.azure_openai_deployment_name   — deployment name
                    settings.azure_openai_api_version       — API version string
                    settings.llm.timeout_seconds            — per-call timeout
                    settings.llm.retry_max                  — max attempts
                    settings.llm.retry_backoff_seconds      — base backoff (exponential)
                    settings.llm.max_tokens                 — max tokens in response

    Raises:
        ValueError: At construction if any required Azure credential is missing.
    """

    def __init__(self, settings: Settings) -> None:
        # Validate all required Azure credentials up front — fail fast
        missing = []
        if not settings.azure_openai_endpoint:
            missing.append("AZURE_OPENAI_ENDPOINT")
        if not settings.azure_openai_api_key:
            missing.append("AZURE_OPENAI_API_KEY")
        if not settings.azure_openai_deployment_name:
            missing.append("AZURE_OPENAI_DEPLOYMENT_NAME")
        if not settings.azure_openai_api_version:
            missing.append("AZURE_OPENAI_API_VERSION")

        if missing:
            raise ValueError(
                f"Azure OpenAI provider is missing required setting(s): "
                f"{', '.join(missing)}. "
                f"Add them to your .env file."
            )

        # Build the full URL once at construction — reused on every call
        base_url = _URL_TEMPLATE.format(
            endpoint=settings.azure_openai_endpoint.rstrip("/"),
            deployment=settings.azure_openai_deployment_name,
        )
        self._url = f"{base_url}?api-version={settings.azure_openai_api_version}"
        self._api_key = settings.azure_openai_api_key
        self._timeout = settings.llm.timeout_seconds
        self._retry_max = settings.llm.retry_max
        self._retry_backoff = settings.llm.retry_backoff_seconds
        self._max_tokens = settings.llm.max_tokens

    def complete(self, system_prompt: str, user_prompt: str) -> str:
        """
        Send a two-part prompt to Azure OpenAI and return the text response.

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
            f"Azure OpenAI API call failed after {self._retry_max} attempt(s). "
            f"Last error: {last_error}"
        )

    def _call(self, system_prompt: str, user_prompt: str) -> str:
        """
        Make a single HTTP call to the Azure OpenAI API.

        Separated from complete() so tests can target the HTTP layer directly
        and the retry loop in complete() stays clean.

        Azure OpenAI authenticates via the api-key header (not Bearer token).
        The request body shape is identical to the OpenAI Chat Completions API.

        Raises:
            httpx.TimeoutException: If the request exceeds timeout_seconds.
            httpx.HTTPStatusError:  If the API returns a 4xx or 5xx status.
        """
        with httpx.Client(timeout=self._timeout) as client:
            response = client.post(
                url=self._url,
                headers={
                    "api-key": self._api_key,
                    "Content-Type": "application/json",
                },
                json={
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
        return "azure_openai"
