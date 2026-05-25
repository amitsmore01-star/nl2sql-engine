# tests/pipeline/test_prompt_builder.py
# V0 - Initial implementation
#
# Tests for src/pipeline/prompt_builder.py
# Covers validate(), build_system_prompt(), and render_user_prompt().
# Uses minimal in-memory StrategyPromptSpec fixtures — no file I/O.

import pytest

from src.config.prompts_models import PromptExample, PromptRules, StrategyPromptSpec
from src.pipeline.prompt_builder import PromptBuilder, _RULE_ORDER


# ---------------------------------------------------------------------------
# Shared fixture helpers
# ---------------------------------------------------------------------------

def _make_example(
    schema_: str = "table: Major.Customer [customer]\n  CustomerID",
    query: str = "get customers",
    correct: str = '{"tables": [], "columns": [], "filters": [], "limit": null, "aggregation": null, "sort": []}',
    incorrect: str | None = None,
    why_wrong: str | None = None,
) -> PromptExample:
    return PromptExample(
        schema_=schema_,
        query=query,
        correct=correct,
        incorrect=incorrect,
        why_wrong=why_wrong,
    )


def _make_rules() -> PromptRules:
    return PromptRules(
        output=["Rule about output format"],
        tables=["Only use tables from schema"],
        columns=["Only use columns from table"],
        filters=["Extract filters exactly"],
        source=["Copy phrase verbatim"],
        limit=["Capture integer limit"],
        aggregation=["Capture COUNT/SUM etc"],
        sort=["Capture sort direction"],
    )


def _make_spec(
    extra_examples: dict | None = None,
    example_sets: dict | None = None,
    user_template: str = "Schema summary:\n<SCHEMA_SUMMARY>\n\nUser query:\n<USER_QUERY>",
    role_description: str = "You are a schema-mapping assistant.",
    output_structure: str = "Respond with JSON only.",
) -> StrategyPromptSpec:
    examples = {
        "example_one": _make_example(),
    }
    if extra_examples:
        examples.update(extra_examples)

    sets = example_sets or {"default": ["example_one"]}

    return StrategyPromptSpec(
        role_description=role_description,
        output_structure=output_structure,
        rules=_make_rules(),
        example_sets=sets,
        examples=examples,
        user_template=user_template,
    )


# ===========================================================================
# Group A — validate() passes on valid spec
# ===========================================================================
class TestValidatePasses:

    def test_A1_valid_complete_spec_passes(self):
        """A1 — A fully valid spec with correct cross-references passes without exception."""
        spec = _make_spec()
        # Should not raise
        PromptBuilder.validate(spec)


# ===========================================================================
# Group B — validate() catches semantic problems
# ===========================================================================
class TestValidateCatchesProblems:

    def test_B1_example_set_references_missing_example(self):
        """B1 — Example set references a name that does not exist in examples."""
        spec = _make_spec(
            example_sets={"default": ["example_one", "does_not_exist"]}
        )
        with pytest.raises(ValueError, match="does_not_exist"):
            PromptBuilder.validate(spec)

    def test_B2_user_template_missing_schema_summary_placeholder(self):
        """B2 — user_template missing <SCHEMA_SUMMARY> placeholder."""
        spec = _make_spec(user_template="User query:\n<USER_QUERY>")
        with pytest.raises(ValueError, match="<SCHEMA_SUMMARY>"):
            PromptBuilder.validate(spec)

    def test_B3_user_template_missing_user_query_placeholder(self):
        """B3 — user_template missing <USER_QUERY> placeholder."""
        spec = _make_spec(user_template="Schema summary:\n<SCHEMA_SUMMARY>")
        with pytest.raises(ValueError, match="<USER_QUERY>"):
            PromptBuilder.validate(spec)

    def test_B4_incorrect_without_why_wrong_raises(self):
        """B4 — Example has incorrect but no why_wrong."""
        example_with_problem = _make_example(
            incorrect='{"tables": [], "columns": [], "filters": [], "limit": null, "aggregation": null, "sort": []}',
            why_wrong=None,
        )
        spec = _make_spec(
            extra_examples={"bad_example": example_with_problem},
            example_sets={"default": ["bad_example"]},
        )
        with pytest.raises(ValueError, match="why_wrong"):
            PromptBuilder.validate(spec)

    def test_B5_why_wrong_without_incorrect_raises(self):
        """B5 — Example has why_wrong but no incorrect."""
        example_with_problem = _make_example(
            incorrect=None,
            why_wrong="This is wrong because...",
        )
        spec = _make_spec(
            extra_examples={"bad_example": example_with_problem},
            example_sets={"default": ["bad_example"]},
        )
        with pytest.raises(ValueError, match="incorrect"):
            PromptBuilder.validate(spec)


# ===========================================================================
# Group C — build_system_prompt() output
# ===========================================================================
class TestBuildSystemPrompt:

    def test_C1_output_contains_role_description(self):
        """C1 — Built prompt contains the role_description text."""
        spec = _make_spec(role_description="You are a UNIQUE_ROLE_MARKER assistant.")
        result = PromptBuilder.build_system_prompt(spec, "default")
        assert "UNIQUE_ROLE_MARKER" in result

    def test_C2_output_contains_output_structure(self):
        """C2 — Built prompt contains the output_structure text."""
        spec = _make_spec(output_structure="UNIQUE_OUTPUT_STRUCTURE_MARKER JSON only.")
        result = PromptBuilder.build_system_prompt(spec, "default")
        assert "UNIQUE_OUTPUT_STRUCTURE_MARKER" in result

    def test_C3_rules_appear_in_correct_order(self):
        """C3 — Rules sections appear in the fixed order defined in _RULE_ORDER."""
        spec = _make_spec()
        result = PromptBuilder.build_system_prompt(spec, "default")
        # Find position of each rule group heading
        positions = []
        for group in _RULE_ORDER:
            heading = f"{group.capitalize()}:"
            pos = result.find(heading)
            assert pos != -1, f"Rule group heading '{heading}' not found in prompt"
            positions.append(pos)
        # Each position must be greater than the previous
        for i in range(1, len(positions)):
            assert positions[i] > positions[i - 1], (
                f"Rule group '{_RULE_ORDER[i]}' appears before '{_RULE_ORDER[i-1]}'"
            )

    def test_C4_output_contains_example_content(self):
        """C4 — Built prompt contains content from the active example set."""
        spec = _make_spec(
            extra_examples={},
        )
        # example_one query is "get customers"
        result = PromptBuilder.build_system_prompt(spec, "default")
        assert "get customers" in result

    def test_C5_unknown_example_set_raises(self):
        """C5 — Requesting an unknown example set name raises ValueError."""
        spec = _make_spec()
        with pytest.raises(ValueError, match="nonexistent_set"):
            PromptBuilder.build_system_prompt(spec, "nonexistent_set")


# ===========================================================================
# Group D — render_user_prompt() output
# ===========================================================================
class TestRenderUserPrompt:

    def test_D1_schema_summary_placeholder_replaced(self):
        """D1 — <SCHEMA_SUMMARY> is replaced with the provided schema summary."""
        spec = _make_spec()
        result = PromptBuilder.render_user_prompt(spec, "MY_SCHEMA_CONTENT", "some query")
        assert "MY_SCHEMA_CONTENT" in result
        assert "<SCHEMA_SUMMARY>" not in result

    def test_D2_user_query_placeholder_replaced(self):
        """D2 — <USER_QUERY> is replaced with the provided user query."""
        spec = _make_spec()
        result = PromptBuilder.render_user_prompt(spec, "some schema", "MY_UNIQUE_QUERY")
        assert "MY_UNIQUE_QUERY" in result
        assert "<USER_QUERY>" not in result

    def test_D3_both_placeholders_substituted_simultaneously(self):
        """D3 — Both placeholders substituted in one call — no leftover placeholders."""
        spec = _make_spec()
        result = PromptBuilder.render_user_prompt(
            spec, "SCHEMA_GOES_HERE", "QUERY_GOES_HERE"
        )
        assert "SCHEMA_GOES_HERE" in result
        assert "QUERY_GOES_HERE" in result
        assert "<SCHEMA_SUMMARY>" not in result
        assert "<USER_QUERY>" not in result
