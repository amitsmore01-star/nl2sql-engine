# tests/llm/test_factory.py
# V0 - Initial implementation
# V1 - Un-skipped C3 (OpenAIProvider now built — Story 3.2)
# V2 - Un-skipped C4 (AzureOpenAIProvider now built — Story 3.3)
#      Un-skipped C5 (AnthropicProvider now built — Story 3.3)
#      _make_settings() updated to carry azure + anthropic credential fields
#
# Tests for src/llm/factory.py — LLMProviderFactory.
#
# Scenarios:
#   C1 — provider=mock → returns MockLLMProvider instance
#   C2 — provider=mock → result is instance of LLMProvider
#   C3 — provider=openai → returns OpenAIProvider instance
#   C4 — provider=azure_openai → returns AzureOpenAIProvider instance
#   C5 — provider=anthropic → returns AnthropicProvider instance
#   C6 — Unknown provider string → raises UnknownProviderError
#   C7 — UnknownProviderError.code matches UNKNOWN_PROVIDER constant

import pytest

from src.llm.factory import LLMProviderFactory
from src.llm.base import LLMProvider
from src.llm.mock_provider import MockLLMProvider
from src.llm.openai_provider import OpenAIProvider
from src.llm.azure_openai_provider import AzureOpenAIProvider
from src.llm.anthropic_provider import AnthropicProvider
from src.core.exceptions import UnknownProviderError
from src.core.constants import UNKNOWN_PROVIDER


# ---------------------------------------------------------------------------
# Fixture — settings object with llm.provider overridden per test
# ---------------------------------------------------------------------------

def _make_settings(
    provider: str,
    openai_api_key: str | None = "test-openai-key",
    azure_openai_api_key: str | None = "test-azure-key",
    azure_openai_endpoint: str | None = "https://test.openai.azure.com",
    azure_openai_deployment_name: str | None = "test-deployment",
    azure_openai_api_version: str | None = "2024-02-01",
    anthropic_api_key: str | None = "test-anthropic-key",
):
    """
    Build a minimal Settings-like object with llm.provider set.
    Uses a simple namespace object — avoids loading real YAML/env in tests.
    Carries all provider credentials so each provider's construction succeeds.
    """
    class _LLM:
        pass

    class _FakeSettings:
        pass

    llm = _LLM()
    llm.provider = provider
    llm.max_tokens = 1000
    llm.timeout_seconds = 30
    llm.retry_max = 3
    llm.retry_backoff_seconds = 2
    llm.temperature = 0.0

    settings = _FakeSettings()
    settings.llm = llm
    settings.openai_api_key = openai_api_key
    settings.azure_openai_api_key = azure_openai_api_key
    settings.azure_openai_endpoint = azure_openai_endpoint
    settings.azure_openai_deployment_name = azure_openai_deployment_name
    settings.azure_openai_api_version = azure_openai_api_version
    settings.anthropic_api_key = anthropic_api_key
    return settings


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestLLMProviderFactory:
    """Tests for LLMProviderFactory.create() — provider selection from config."""

    def test_c1_mock_provider_returns_mock_llm_provider(self):
        """C1 — settings.llm.provider='mock' returns a MockLLMProvider instance."""
        settings = _make_settings("mock")
        result = LLMProviderFactory.create(settings)
        assert isinstance(result, MockLLMProvider)

    def test_c2_mock_provider_is_llm_provider(self):
        """C2 — MockLLMProvider returned by factory satisfies LLMProvider interface."""
        settings = _make_settings("mock")
        result = LLMProviderFactory.create(settings)
        assert isinstance(result, LLMProvider)

    def test_c3_openai_provider_returns_openai_provider(self):
        """C3 — settings.llm.provider='openai' returns an OpenAIProvider instance."""
        settings = _make_settings("openai")
        result = LLMProviderFactory.create(settings)
        assert isinstance(result, OpenAIProvider)

    def test_c4_azure_openai_provider_returns_azure_openai_provider(self):
        """C4 — settings.llm.provider='azure_openai' returns an AzureOpenAIProvider instance."""
        settings = _make_settings("azure_openai")
        result = LLMProviderFactory.create(settings)
        assert isinstance(result, AzureOpenAIProvider)

    def test_c5_anthropic_provider_returns_anthropic_provider(self):
        """C5 — settings.llm.provider='anthropic' returns an AnthropicProvider instance."""
        settings = _make_settings("anthropic")
        result = LLMProviderFactory.create(settings)
        assert isinstance(result, AnthropicProvider)

    def test_c6_unknown_provider_raises_unknown_provider_error(self):
        """C6 — Unrecognised provider string raises UnknownProviderError."""
        settings = _make_settings("not_a_real_provider")
        with pytest.raises(UnknownProviderError):
            LLMProviderFactory.create(settings)

    def test_c7_unknown_provider_error_code_matches_constant(self):
        """C7 — UnknownProviderError.code matches the UNKNOWN_PROVIDER constant."""
        settings = _make_settings("typo_provider")
        with pytest.raises(UnknownProviderError) as exc_info:
            LLMProviderFactory.create(settings)
        assert exc_info.value.code == UNKNOWN_PROVIDER
