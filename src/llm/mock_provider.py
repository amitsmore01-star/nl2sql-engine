# src/llm/mock_provider.py
# V0 - Initial implementation
#
# MockLLMProvider — used in ALL tests. Zero real API calls.
#
# Design:
#   - Accepts a list of canned response strings at construction time.
#   - Each call to complete() returns the next string from the list, in order.
#   - This supports the two-step LLM pattern:
#       Call 1 (Intent Extractor) → responses[0]  e.g. intent JSON
#       Call 2 (Schema Mapper)    → responses[1]  e.g. mapping JSON
#   - Raises ValueError if the list is empty (misconfigured test).
#   - Raises ValueError if complete() is called more times than responses available.
#     This surfaces test bugs early — a stage calling complete() unexpectedly.

from src.llm.base import LLMProvider


class MockLLMProvider(LLMProvider):
    """
    Test-only LLM provider. Returns pre-written strings in call order.

    Never makes network calls. Always returns instantly.
    Used in every test that touches pipeline stages or the full pipeline.

    Args:
        responses: Ordered list of strings to return on successive complete() calls.
                   Must contain at least one entry.

    Example:
        mock = MockLLMProvider(responses=["intent json", "mapping json"])
        mock.complete("sys", "user")  # → "intent json"
        mock.complete("sys", "user")  # → "mapping json"
    """

    def __init__(self, responses: list[str]) -> None:
        if not responses:
            raise ValueError(
                "MockLLMProvider requires at least one response string. "
                "Pass a non-empty list to responses=[]."
            )
        self._responses = responses
        self._call_count = 0

    def complete(self, system_prompt: str, user_prompt: str) -> str:
        """
        Return the next canned response in order.

        Args:
            system_prompt: Ignored — mock does not inspect prompts.
            user_prompt:   Ignored — mock does not inspect prompts.

        Returns:
            Next string from the responses list.

        Raises:
            ValueError: If called more times than there are responses configured.
        """
        if self._call_count >= len(self._responses):
            raise ValueError(
                f"MockLLMProvider has no more responses. "
                f"complete() was called {self._call_count + 1} time(s) "
                f"but only {len(self._responses)} response(s) were configured. "
                f"Add more entries to the responses list."
            )
        response = self._responses[self._call_count]
        self._call_count += 1
        return response

    def provider_name(self) -> str:
        """Return the provider identifier string."""
        return "mock"
