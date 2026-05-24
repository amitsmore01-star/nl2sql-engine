# tests/llm/test_base.py
# V0 - Initial implementation
#
# Tests for src/llm/base.py — LLMProvider abstract base class.
#
# Scenarios:
#   A1 — Concrete class implementing both abstract methods can be instantiated
#   A2 — Class missing complete() raises TypeError on instantiation
#   A3 — Class missing provider_name() raises TypeError on instantiation

import pytest
from src.llm.base import LLMProvider


# ---------------------------------------------------------------------------
# Minimal concrete implementation used only in these tests
# ---------------------------------------------------------------------------

class _ConcreteProvider(LLMProvider):
    """Minimal valid implementation — satisfies both abstract methods."""

    def complete(self, system_prompt: str, user_prompt: str) -> str:
        return "response"

    def provider_name(self) -> str:
        return "concrete"


class _MissingComplete(LLMProvider):
    """Implements provider_name only — missing complete()."""

    def provider_name(self) -> str:
        return "bad"


class _MissingProviderName(LLMProvider):
    """Implements complete() only — missing provider_name()."""

    def complete(self, system_prompt: str, user_prompt: str) -> str:
        return "response"


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestLLMProviderABC:
    """Tests for the LLMProvider abstract base class contract."""

    def test_a1_concrete_class_can_be_instantiated(self):
        """A1 — A class implementing both abstract methods instantiates without error."""
        provider = _ConcreteProvider()
        assert provider is not None

    def test_a2_missing_complete_raises_type_error(self):
        """A2 — A class missing complete() raises TypeError on instantiation."""
        with pytest.raises(TypeError):
            _MissingComplete()

    def test_a3_missing_provider_name_raises_type_error(self):
        """A3 — A class missing provider_name() raises TypeError on instantiation."""
        with pytest.raises(TypeError):
            _MissingProviderName()
