# src/llm/factory.py
# V0 - Initial implementation
#
# LLMProviderFactory — creates and returns the configured LLM provider.
#
# Design:
#   - Static factory method: LLMProviderFactory.create(settings) → LLMProvider
#   - Provider is selected by settings.llm.provider (set via LLM_PROVIDER in .env)
#   - Switching provider = change one line in .env. Zero code change.
#   - Unknown provider string → UnknownProviderError raised immediately.
#   - Real providers (openai, azure_openai, anthropic) are imported lazily inside
#     create() so that missing provider files do not break imports in tests.
#   - MockLLMProvider is imported at module level — always available.
#
# Adding a new provider:
#   1. Create src/llm/{name}_provider.py implementing LLMProvider
#   2. Add one entry to the _PROVIDER_MAP inside create()
#   Zero other changes required.

from src.llm.base import LLMProvider
from src.llm.mock_provider import MockLLMProvider
from src.core.exceptions import UnknownProviderError
from src.config.settings import Settings


class LLMProviderFactory:
    """
    Factory that creates LLM provider instances from configuration.

    Callers never instantiate providers directly — always go through this factory.
    This ensures the provider is always consistent with the active config.
    """

    @staticmethod
    def create(settings: Settings) -> LLMProvider:
        """
        Create and return the LLM provider configured in settings.

        Args:
            settings: Loaded Settings object. Uses settings.llm.provider
                      to select the provider class.

        Returns:
            An instantiated LLMProvider ready to call.

        Raises:
            UnknownProviderError: If settings.llm.provider does not match
                                  any known provider string.
        """
        provider = settings.llm.provider

        # Mock is always available — no extra imports needed
        if provider == "mock":
            # MockLLMProvider requires a responses list.
            # The factory creates a mock with a single placeholder response.
            # Tests that need specific responses construct MockLLMProvider directly.
            return MockLLMProvider(responses=["mock_response"])

        # Real providers are imported lazily — their files may not exist yet
        # during early development. Each import is attempted only when that
        # provider is actually requested.
        if provider == "openai":
            from src.llm.openai_provider import OpenAIProvider  # noqa: PLC0415
            return OpenAIProvider(settings)

        if provider == "azure_openai":
            from src.llm.azure_openai_provider import AzureOpenAIProvider  # noqa: PLC0415
            return AzureOpenAIProvider(settings)

        if provider == "anthropic":
            from src.llm.anthropic_provider import AnthropicProvider  # noqa: PLC0415
            return AnthropicProvider(settings)

        raise UnknownProviderError(
            f"LLM provider '{provider}' is not recognised. "
            f"Valid values are: mock, openai, azure_openai, anthropic. "
            f"Check LLM_PROVIDER in your .env file."
        )
