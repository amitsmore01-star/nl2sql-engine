# src/llm/base.py
# V0 - Initial implementation
#
# Abstract base class for all LLM providers.
# Every provider (Mock, OpenAI, Azure OpenAI, Anthropic) must implement this interface.
#
# Design:
#   - LLMProvider is an ABC — cannot be instantiated directly.
#   - Two abstract methods: complete() and provider_name().
#   - Pipeline stages call complete() only — they never know which provider is active.
#   - All implementations are synchronous (def, not async def).
#     uvicorn worker processes handle concurrency — no async needed in application code.

from abc import ABC, abstractmethod


class LLMProvider(ABC):
    """
    Interface that all LLM providers must implement.

    The pipeline calls complete() to get a text response from the LLM.
    Which provider is active is determined by config — zero code change to switch.
    """

    @abstractmethod
    def complete(self, system_prompt: str, user_prompt: str) -> str:
        """
        Send a prompt to the LLM and return the text response.

        Synchronous — blocks until the response is received.
        All retry and timeout logic is the responsibility of the concrete provider.

        Args:
            system_prompt: Instructions that set the LLM's role and output format.
            user_prompt:   The actual query or data the LLM should process.

        Returns:
            Raw text response from the LLM. Typically JSON — parsing is the
            caller's responsibility.

        Raises:
            LLMOutputParseError: If the provider cannot get a usable response
                                 after all retries are exhausted.
        """
        ...

    @abstractmethod
    def provider_name(self) -> str:
        """
        Return a short identifier string for this provider.

        Used in logs and error messages to identify which provider was active.

        Returns:
            One of: "mock", "openai", "azure_openai", "anthropic"
        """
        ...
