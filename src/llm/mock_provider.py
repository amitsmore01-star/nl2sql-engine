# src/llm/mock_provider.py
# V0 - Initial implementation
# V1 - Added JSON file mode. Constructor now accepts optional responses= list (old mode)
#      or no argument (new mode — loads from config/mock_responses.json).
#      Matching in JSON mode: extracts user query from rendered user_prompt by splitting
#      on "User query:\n", strips whitespace, matches exactly against user_input entries.
#      Old list mode behaviour is completely unchanged.

import json
import pathlib
from src.llm.base import LLMProvider

# Hardcoded path to the mock responses JSON file.
# This file lives at the project root level under config/.
_MOCK_RESPONSES_PATH = pathlib.Path("config/mock_responses.json")

# The label used in the user_template to separate schema summary from user query.
# Must match exactly what prompts.yaml user_template uses before <USER_QUERY>.
_USER_QUERY_LABEL = "User query:"


class MockLLMProvider(LLMProvider):
    """
    Test-only LLM provider. Never makes network calls. Always returns instantly.
    Used in every test that touches pipeline stages or the full pipeline.

    Two modes — choose one at construction time:

    OLD MODE (list):
        Pass a non-empty list of strings. Each complete() call returns the next
        string in order. Existing tests use this mode and are unaffected.

        Example:
            mock = MockLLMProvider(responses=["ir json string"])
            mock.complete("sys", "user")  # → "ir json string"

    NEW MODE (JSON file):
        Pass no arguments. Loads config/mock_responses.json at construction time.
        Each complete() call extracts the user query from the rendered user_prompt,
        matches it exactly against user_input entries in the JSON file, and returns
        the corresponding llm_response.

        Example:
            mock = MockLLMProvider()
            mock.complete("sys", "Schema summary:\\n...\\nUser query:\\ngive me customers")
            # → llm_response matched to "give me customers" in the JSON file

    JSON file format (config/mock_responses.json):
        [
          {
            "user_input": "give me topaccount name for customer ASA",
            "llm_response": "{ ... IR JSON string ... }"
          }
        ]
    """

    def __init__(self, responses: list[str] | None = None) -> None:
        """
        Initialise in either list mode or JSON file mode.

        Args:
            responses: If provided, use list mode (old behaviour).
                       If None (default), use JSON file mode.

        Raises:
            ValueError: In list mode — if the list is empty.
            ValueError: In JSON file mode — if the file is missing or contains invalid JSON.
        """
        if responses is not None:
            # --- OLD MODE ---
            # Validate the list is not empty — misconfigured test fails fast.
            if not responses:
                raise ValueError(
                    "MockLLMProvider requires at least one response string. "
                    "Pass a non-empty list to responses=[]."
                )
            self._responses = responses
            self._call_count = 0
            self._json_mode = False

        else:
            # --- NEW MODE ---
            # Load the JSON file at construction time so missing/broken files
            # are caught immediately, not mid-test.
            if not _MOCK_RESPONSES_PATH.exists():
                raise ValueError(
                    f"MockLLMProvider JSON mode requires the mock responses file at "
                    f"'{_MOCK_RESPONSES_PATH}'. File not found. "
                    f"Create the file or pass responses=[] to use list mode."
                )
            try:
                raw = _MOCK_RESPONSES_PATH.read_text(encoding="utf-8")
                self._json_entries: list[dict] = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise ValueError(
                    f"MockLLMProvider could not parse '{_MOCK_RESPONSES_PATH}'. "
                    f"File contains invalid JSON: {exc}"
                ) from exc

            self._responses = []   # unused in JSON mode — kept for type consistency
            self._call_count = 0   # unused in JSON mode
            self._json_mode = True

    def complete(self, system_prompt: str, user_prompt: str) -> str:
        """
        Return a mock LLM response.

        In LIST mode:
            Returns the next string from the responses list in call order.
            Raises ValueError if called more times than responses configured.

        In JSON mode:
            Extracts the user query from user_prompt by splitting on "User query:"
            and taking everything after it, stripped of whitespace.
            Matches extracted query exactly (case-sensitive) against user_input
            entries in the loaded JSON file.
            Raises ValueError if no entry matches.

        Args:
            system_prompt: Ignored in both modes — mock does not inspect system prompt.
            user_prompt:   In list mode: ignored.
                           In JSON mode: must contain "User query:\\n<query text>".

        Returns:
            The matched or next-in-order response string.

        Raises:
            ValueError: List mode — no more responses available.
            ValueError: JSON mode — no matching user_input entry found.
            ValueError: JSON mode — user_prompt does not contain the expected label.
        """
        if not self._json_mode:
            # --- OLD MODE ---
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

        else:
            # --- NEW MODE ---
            extracted_query = self._extract_user_query(user_prompt)

            for entry in self._json_entries:
                if entry.get("user_input") == extracted_query:
                    return entry["llm_response"]

            raise ValueError(
                f"MockLLMProvider (JSON mode) found no matching entry for user query: "
                f"'{extracted_query}'. "
                f"Add a matching 'user_input' entry to '{_MOCK_RESPONSES_PATH}'."
            )

    def provider_name(self) -> str:
        """Return the provider identifier string."""
        return "mock"

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _extract_user_query(self, user_prompt: str) -> str:
        """
        Extract the user query portion from a fully rendered user prompt.

        The user_template in prompts.yaml always produces a prompt in this shape:

            Schema summary:
            <schema text>

            User query:
            <user query text>

        This method splits on "User query:" and takes everything after it,
        stripped of leading/trailing whitespace.

        Args:
            user_prompt: The full rendered prompt string passed to complete().

        Returns:
            The extracted user query string, whitespace-stripped.

        Raises:
            ValueError: If the expected label is not found in user_prompt.
        """
        if _USER_QUERY_LABEL not in user_prompt:
            raise ValueError(
                f"MockLLMProvider (JSON mode) could not extract user query from "
                f"user_prompt. Expected to find the label '{_USER_QUERY_LABEL}' "
                f"in the prompt. Check that the user_template in prompts.yaml "
                f"contains this label before <USER_QUERY>."
            )
        # Split on the label and take everything after it.
        # maxsplit=1 ensures we only split on the first occurrence.
        after_label = user_prompt.split(_USER_QUERY_LABEL, maxsplit=1)[1]
        return after_label.strip()
