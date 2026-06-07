# tests/llm/test_mock_provider.py
# V1 - Added J1-J6 JSON mode test scenarios alongside existing B1-B6 list mode tests.

import json
import pathlib
import pytest

from src.llm.mock_provider import MockLLMProvider, _MOCK_RESPONSES_PATH, _USER_QUERY_LABEL


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_user_prompt(query: str) -> str:
    """
    Build a realistic rendered user prompt in the same shape that
    PromptBuilder.render_user_prompt() produces.

    This lets JSON mode tests work without needing the real PromptBuilder.
    """
    return (
        "Schema summary:\n"
        "table: Major.Customer [customer, organization]\n"
        "  CustomerCID [Customer id]\n\n"
        f"{_USER_QUERY_LABEL}\n"
        f"{query}"
    )


def _write_json_file(path: pathlib.Path, entries: list[dict]) -> None:
    """Write a mock responses JSON file at the given path."""
    path.write_text(json.dumps(entries, indent=2), encoding="utf-8")


# ---------------------------------------------------------------------------
# B — List mode (old behaviour — all existing tests unchanged)
# ---------------------------------------------------------------------------

class TestMockLLMProviderListMode:
    """Original list mode tests — B1 to B6. Must remain passing unchanged."""

    def test_B1_returns_first_response(self):
        """B1 — single response returned on first call."""
        mock = MockLLMProvider(responses=["response_one"])
        result = mock.complete("sys", "user")
        assert result == "response_one"

    def test_B2_returns_responses_in_order(self):
        """B2 — multiple responses returned in configured order."""
        mock = MockLLMProvider(responses=["first", "second", "third"])
        assert mock.complete("sys", "user") == "first"
        assert mock.complete("sys", "user") == "second"
        assert mock.complete("sys", "user") == "third"

    def test_B3_raises_when_responses_exhausted(self):
        """B3 — ValueError raised when complete() called more times than responses."""
        mock = MockLLMProvider(responses=["only_one"])
        mock.complete("sys", "user")  # consumes the only response
        with pytest.raises(ValueError, match="no more responses"):
            mock.complete("sys", "user")

    def test_B4_raises_on_empty_list(self):
        """B4 — ValueError raised at construction if responses list is empty."""
        with pytest.raises(ValueError, match="at least one response"):
            MockLLMProvider(responses=[])

    def test_B5_provider_name_returns_mock(self):
        """B5 — provider_name() always returns 'mock'."""
        mock = MockLLMProvider(responses=["x"])
        assert mock.provider_name() == "mock"

    def test_B6_system_prompt_ignored_in_list_mode(self):
        """B6 — system_prompt content does not affect which response is returned."""
        mock = MockLLMProvider(responses=["the_response"])
        result = mock.complete("anything here", "anything here too")
        assert result == "the_response"


# ---------------------------------------------------------------------------
# J — JSON file mode (new behaviour)
# ---------------------------------------------------------------------------

class TestMockLLMProviderJsonMode:
    """
    JSON mode tests — J1 to J6.

    These tests redirect _MOCK_RESPONSES_PATH to a tmp_path file so they
    never touch the real config/mock_responses.json. This keeps tests
    hermetic — each test controls exactly what the file contains.

    How the redirect works:
        We use monkeypatch to replace the module-level _MOCK_RESPONSES_PATH
        constant with a temporary path before MockLLMProvider() is constructed.
        MockLLMProvider.__init__ reads _MOCK_RESPONSES_PATH at construction time,
        so patching before construction is sufficient.
    """

    @pytest.fixture(autouse=True)
    def patch_json_path(self, monkeypatch, tmp_path):
        """
        Redirect _MOCK_RESPONSES_PATH to a temporary directory for every test.
        autouse=True means this runs automatically for every test in this class.
        """
        self.tmp_json = tmp_path / "mock_responses.json"
        monkeypatch.setattr(
            "src.llm.mock_provider._MOCK_RESPONSES_PATH",
            self.tmp_json
        )

    def test_J1_matching_user_input_returns_correct_response(self):
        """J1 — user query extracted from prompt matches entry, correct response returned."""
        _write_json_file(self.tmp_json, [
            {
                "user_input": "give me topaccount name for customer CUST01",
                "llm_response": '{"tables": [], "columns": [], "filters": [], "limit": null, "aggregation": null, "sort": []}'
            }
        ])
        mock = MockLLMProvider()
        user_prompt = _make_user_prompt("give me topaccount name for customer CUST01")
        result = mock.complete("sys", user_prompt)
        assert '"tables"' in result

    def test_J2_no_match_raises_value_error(self):
        """J2 — no matching user_input in JSON raises ValueError with clear message."""
        _write_json_file(self.tmp_json, [
            {
                "user_input": "give me something else",
                "llm_response": "{}"
            }
        ])
        mock = MockLLMProvider()
        user_prompt = _make_user_prompt("give me topaccount name for customer CUST01")
        with pytest.raises(ValueError, match="no matching entry"):
            mock.complete("sys", user_prompt)

    def test_J3_missing_json_file_raises_at_construction(self):
        """J3 — file not found raises ValueError at construction time, not at complete()."""
        # tmp_json was never written — file does not exist
        with pytest.raises(ValueError, match="File not found"):
            MockLLMProvider()

    def test_J4_malformed_json_raises_at_construction(self):
        """J4 — invalid JSON in file raises ValueError at construction time."""
        self.tmp_json.write_text("this is not valid json {{{", encoding="utf-8")
        with pytest.raises(ValueError, match="invalid JSON"):
            MockLLMProvider()

    def test_J5_full_prompt_with_schema_preamble_still_matches(self):
        """
        J5 — extraction works correctly when user_prompt contains schema preamble.
        The full rendered prompt (schema + query) must still match on query only.
        """
        _write_json_file(self.tmp_json, [
            {
                "user_input": "give me topaccount name for customer CUST01",
                "llm_response": '{"matched": true}'
            }
        ])
        mock = MockLLMProvider()
        # This is the realistic full prompt shape — schema block before query
        full_prompt = (
            "Schema summary:\n"
            "table: Major.Customer [customer, organization, org]\n"
            "  CustomerID\n"
            "  CustomerCID [Customer id, Customer cid]\n"
            "table: Major.Acc [acc, top acc, sub acc]\n"
            "  AccID\n"
            "  AccName [Acc name]\n\n"
            f"{_USER_QUERY_LABEL}\n"
            "give me topaccount name for customer CUST01"
        )
        result = mock.complete("sys", full_prompt)
        assert result == '{"matched": true}'

    def test_J6_list_mode_still_works_alongside_json_mode(self):
        """
        J6 — old list mode (responses=[...]) is completely unaffected by JSON mode addition.
        Passing responses= skips all JSON file logic entirely.
        """
        # Note: tmp_json does NOT exist — but list mode must never touch the file.
        mock = MockLLMProvider(responses=["list_mode_response"])
        result = mock.complete("sys", "any user prompt — list mode ignores it")
        assert result == "list_mode_response"
