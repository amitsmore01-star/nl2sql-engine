# src/llm/azure_foundry_provider.py
# V0 - Initial implementation
# V1 - Story 5.9: Read settings.llm.temperature at construction and pass it
#      in the request body. temperature=0 ensures deterministic SQL output.

import time

import httpx

from src.llm.base import LLMProvider
from src.core.exceptions import LLMOutputParseError
from src.config.settings import Settings

_CHAT_PATH = "/chat/completions"


class AzureFoundryProvider(LLMProvider):
    """
    LLM provider that calls the Azure AI Foundry Chat Completions API.

    Args:
        settings: Loaded Settings object. Reads:
                    settings.azure_foundry_endpoint        — full base URL
                    settings.azure_foundry_api_key         — static API key
                    settings.azure_foundry_deployment_name — model/deployment name
                    settings.llm.timeout_seconds           — per-call timeout
                    settings.llm.retry_max                 — max attempts
                    settings.llm.retry_backoff_seconds     — base backoff (exponential)
                    settings.llm.max_tokens                — max tokens in response
                    settings.llm.temperature               — sampling temperature (default 0)

    Raises:
        ValueError: At construction if any required credential is missing.
    """

    def __init__(self, settings: Settings) -> None:
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

        self._url = settings.azure_foundry_endpoint.rstrip("/") + _CHAT_PATH
        self._api_key = settings.azure_foundry_api_key
        self._model = settings.azure_foundry_deployment_name
        self._timeout = settings.llm.timeout_seconds
        self._retry_max = settings.llm.retry_max
        self._retry_backoff = settings.llm.retry_backoff_seconds
        self._max_tokens = settings.llm.max_tokens
        self._temperature = settings.llm.temperature

    def complete(self, system_prompt: str, user_prompt: str) -> str:
        """
        Send a two-part prompt to Azure AI Foundry and return the text response.

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
        """Make a single HTTP call to the Azure AI Foundry API."""
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
                    "temperature": self._temperature,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user",   "content": user_prompt},
                    ],
                },
            )
            response.raise_for_status()
            return response.json()["choices"][0]["message"]["content"]

    def provider_name(self) -> str:
        return "azure_foundry"
