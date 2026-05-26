# src/llm/azure_foundry_provider.py
# V0 - Initial implementation
#
# AzureFoundryProvider — calls the Azure AI Foundry Chat Completions API.
#
# Design:
#   - Implements LLMProvider ABC — complete() and provider_name().
#   - Synchronous — uses httpx.Client (blocking). No async.
#   - Retry loop with exponential backoff on HTTP errors and timeouts.
#   - All config (timeout, retry_max, backoff) read from settings — zero hardcoding.
#   - URL built at construction time from endpoint only — no deployment in URL.
#   - Model (deployment) name sent in request body — this is the Foundry pattern.
#   - Raises ValueError at construction if any required credential is missing.
#   - Raises LLMOutputParseError if all retries are exhausted.
#
# Azure AI Foundry URL pattern:
#   {endpoint}/chat/completions
#   e.g. https://<name>-foundry.services.ai.azure.com/openai/v1/chat/completions
#
# Key difference from AzureOpenAIProvider:
#   - No deployment name or api-version in the URL
#   - Model name goes in the request body as "model" field
#   - Endpoint already includes the /openai/v1 path — stored as-is

import time

import httpx

from src.llm.base import LLMProvider
from src.core.exceptions import LLMOutputParseError
from src.config.settings import Settings

# Foundry appends /chat/completions to the base endpoint
_CHAT_PATH = "/chat/completions"


class AzureFoundryProvider(LLMProvider):
    """
    LLM provider that calls the Azure AI Foundry Chat Completions API.

    Azure AI Foundry exposes an OpenAI-compatible endpoint but differs from
    Azure OpenAI Service in two ways:
      1. The URL does not include the deployment name — it is flat /chat/completions
      2. The model (deployment) name is passed in the request body as "model"

    Auth uses the same api-key header as Azure OpenAI — no bearer token needed.

    Args:
        settings: Loaded Settings object. Reads:
                    settings.azure_foundry_endpoint        — full base URL
                                                             (e.g. https://<name>.services.ai.azure.com/openai/v1)
                    settings.azure_foundry_api_key         — static API key
                    settings.azure_foundry_deployment_name — model/deployment name (e.g. gpt-4o-mini)
                    settings.llm.timeout_seconds           — per-call timeout
                    settings.llm.retry_max                 — max attempts
                    settings.llm.retry_backoff_seconds     — base backoff (exponential)
                    settings.llm.max_tokens                — max tokens in response

    Raises:
        ValueError: At construction if any required credential is missing.
    """

    def __init__(self, settings: Settings) -> None:
        # Validate all required Foundry credentials up front — fail fast
        missing = []
        if not settings.azure_foundry_endpoint:
            missing.append("AZURE_FOUNDRY_ENDPOINT")
        if not settings.azure_foundry_api_key:
            missing.append("AZURE_FOUNDRY_API_KEY")
        if not settings.azure_foundry_deployment_name:
            missing.append("AZURE_FOUNDRY_DEPLOYMENT_NAME")

        if missing:
            raise ValueError(
                f"Azure AI Foundry provider is missing required setting(s): "
                f"{', '.join(missing)}. "
                f"Add them to your .env file."
            )

        # Build the full URL once at construction — reused on every call.
        # Strip trailing slash from endpoint then append /chat/completions.
        self._url = settings.azure_foundry_endpoint.rstrip("/") + _CHAT_PATH
        self._api_key = settings.azure_foundry_api_key
        self._model = settings.azure_foundry_deployment_name
        self._timeout = settings.llm.timeout_seconds
        self._retry_max = settings.llm.retry_max
        self._retry_backoff = settings.llm.retry_backoff_seconds
        self._max_tokens = settings.llm.max_tokens

    def complete(self, system_prompt: str, user_prompt: str) -> str:
        """
        Send a two-part prompt to Azure AI Foundry and return the text response.

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
            f"Azure AI Foundry API call failed after {self._retry_max} attempt(s). "
            f"Last error: {last_error}"
        )

    def _call(self, system_prompt: str, user_prompt: str) -> str:
        """
        Make a single HTTP call to the Azure AI Foundry API.

        Separated from complete() so tests can target the HTTP layer directly
        and the retry loop in complete() stays clean.

        Key difference from AzureOpenAIProvider._call():
          - "model" field included in request body (not in URL)
          - No api-version query parameter

        Response shape is OpenAI-compatible:
          choices[0].message.content

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
                    "model": self._model,
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
        return "azure_foundry"
