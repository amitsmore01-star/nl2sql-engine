# tests/llm/test_mock_provider.py
# V0 - Initial implementation
#
# Tests for src/llm/mock_provider.py — MockLLMProvider.
#
# Scenarios:
#   B1 — provider_name() returns "mock"
#   B2 — First complete() call returns first response in list
#   B3 — Second complete() call returns second response in list
#   B4 — MockLLMProvider is instance of LLMProvider
#   B5 — Constructing MockLLMProvider with empty list raises ValueError
#   B6 — Calling complete() more times than responses raises ValueError

import pytest
from src.llm.base import LLMProvider
from src.llm.mock_provider import MockLLMProvider


class TestMockLLMProvider:
    """Tests for MockLLMProvider — test-only provider, zero API calls."""

    def test_b1_provider_name_returns_mock(self):
        """B1 — provider_name() returns the string 'mock'."""
        mock = MockLLMProvider(responses=["any response"])
        assert mock.provider_name() == "mock"

    def test_b2_first_call_returns_first_response(self):
        """B2 — First complete() call returns the first string in the responses list."""
        mock = MockLLMProvider(responses=["intent json", "mapping json"])
        result = mock.complete("system prompt", "user prompt")
        assert result == "intent json"

    def test_b3_second_call_returns_second_response(self):
        """B3 — Second complete() call returns the second string in the responses list."""
        mock = MockLLMProvider(responses=["intent json", "mapping json"])
        mock.complete("system prompt 1", "user prompt 1")   # consume first
        result = mock.complete("system prompt 2", "user prompt 2")
        assert result == "mapping json"

    def test_b4_is_instance_of_llm_provider(self):
        """B4 — MockLLMProvider satisfies the LLMProvider interface."""
        mock = MockLLMProvider(responses=["response"])
        assert isinstance(mock, LLMProvider)

    def test_b5_empty_responses_list_raises_value_error(self):
        """B5 — Constructing MockLLMProvider with an empty list raises ValueError."""
        with pytest.raises(ValueError, match="at least one response"):
            MockLLMProvider(responses=[])

    def test_b6_too_many_calls_raises_value_error(self):
        """B6 — Calling complete() more times than configured responses raises ValueError."""
        mock = MockLLMProvider(responses=["only one response"])
        mock.complete("sys", "user")   # valid — consumes the only response
        with pytest.raises(ValueError, match="no more responses"):
            mock.complete("sys", "user")  # second call — no response left
