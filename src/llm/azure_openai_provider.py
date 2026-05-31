# src/llm/azure_openai_provider.py
# V0 - Initial implementation
# V1 - Story 5.9: Read settings.llm.temperature at construction and pass it
#      in the request body. temperature=0 ensures deterministic SQL output.

import time

import httpx

from src.llm.base import LLMProvider
from src.core.exceptions import LLMOutputParseError
from src.config.settings import Settings

_URL_TEMPLATE = "{endpoint}/openai/deployments/{deployment}/chat/completions"


class AzureOpenAIProvider(LLMProvider):
    """
    LLM provider that calls the Azure OpenAI Chat Completions API.

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
                    settings.llm.temperature                — sampling temperature (default 0)

    Raises:
        ValueError: At construction if any required Azure credential is missing.
    """

    def __init__(self, settings: Settings) -> None:
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
        self._temperature = settings.llm.temperature

    def complete(self, system_prompt: str, user_prompt: str) -> str:
        """
        Send a two-part prompt to Azure OpenAI and return the text response.

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
        """Make a single HTTP call to the Azure OpenAI API."""
        with httpx.Client(timeout=self._timeout) as client:
            response = client.post(
                url=self._url,
                headers={
                    "api-key": self._api_key,
                    "Content-Type": "application/json",
                },
                json={
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
        return "azure_openai"
