# src/pipeline/prompt_builder.py
# V0 - Initial implementation
#
# PromptBuilder assembles the sectioned prompts.yaml into final prompt strings.
#
# Three static methods:
#   validate()           — semantic validation (cross-references, placeholders,
#                          incorrect/why_wrong pairing). Called at strategy
#                          construction — service refuses to start on failure.
#   build_system_prompt() — assembles system prompt once at strategy construction.
#                           Same string reused for every request in that process.
#   render_user_prompt()  — substitutes <SCHEMA_SUMMARY> and <USER_QUERY>
#                           placeholders per request.
#
# Assembly order (fixed — architecture document Section 7.5):
#   role_description
#   → output_structure
#   → STRICT RULES (output → tables → columns → filters → source → limit → aggregation → sort)
#   → EXAMPLES (schema → query → correct → incorrect → why_wrong)
#
# This file never reads YAML directly — it only receives a StrategyPromptSpec
# that has already been loaded and structurally validated by Pydantic.

from __future__ import annotations

from src.config.prompts_models import StrategyPromptSpec

# Fixed rule group assembly order — must match architecture document Section 7.5
_RULE_ORDER = ["output", "tables", "columns", "filters", "source", "limit", "aggregation", "sort"]

# Placeholder tokens that must appear in user_template
_REQUIRED_PLACEHOLDERS = ["<SCHEMA_SUMMARY>", "<USER_QUERY>"]


class PromptBuilder:
    """
    Stateless utility — all methods are static.
    Strategies call these methods; they never instantiate PromptBuilder.
    """

    @staticmethod
    def validate(spec: StrategyPromptSpec) -> None:
        """
        Semantic validation of a StrategyPromptSpec.

        Checks things Pydantic cannot: broken cross-references between
        example_sets and examples, placeholder presence, and pairing rules.

        Args:
            spec: A structurally valid StrategyPromptSpec (already Pydantic-validated).

        Raises:
            ValueError: With a descriptive message for any semantic problem found.
                        Raises on the FIRST problem found — caller sees one clear error.
        """
        # 1. Every example name referenced in any example_set must exist in examples
        for set_name, example_names in spec.example_sets.items():
            for example_name in example_names:
                if example_name not in spec.examples:
                    raise ValueError(
                        f"Example set '{set_name}' references example '{example_name}' "
                        f"which does not exist in the examples section. "
                        f"Available examples: {sorted(spec.examples.keys())}"
                    )

        # 2. user_template must contain both required placeholders
        for placeholder in _REQUIRED_PLACEHOLDERS:
            if placeholder not in spec.user_template:
                raise ValueError(
                    f"user_template is missing required placeholder '{placeholder}'. "
                    f"Both <SCHEMA_SUMMARY> and <USER_QUERY> must appear in user_template."
                )

        # 3. incorrect and why_wrong must always appear together
        for example_name, example in spec.examples.items():
            has_incorrect = example.incorrect is not None
            has_why_wrong = example.why_wrong is not None
            if has_incorrect and not has_why_wrong:
                raise ValueError(
                    f"Example '{example_name}' has 'incorrect' but is missing 'why_wrong'. "
                    f"Both must be present together or both must be absent."
                )
            if has_why_wrong and not has_incorrect:
                raise ValueError(
                    f"Example '{example_name}' has 'why_wrong' but is missing 'incorrect'. "
                    f"Both must be present together or both must be absent."
                )

    @staticmethod
    def build_system_prompt(spec: StrategyPromptSpec, example_set_name: str) -> str:
        """
        Assemble the full system prompt from a StrategyPromptSpec.

        Called once at strategy construction — the result is cached on the
        strategy instance and reused for every request.

        Args:
            spec:             A validated StrategyPromptSpec.
            example_set_name: Name of the example set to include
                              (e.g. "default", "minimal").

        Returns:
            The assembled system prompt string.

        Raises:
            ValueError: If example_set_name does not exist in spec.example_sets.
        """
        if example_set_name not in spec.example_sets:
            raise ValueError(
                f"Example set '{example_set_name}' not found in prompts.yaml. "
                f"Available sets: {sorted(spec.example_sets.keys())}"
            )

        parts: list[str] = []

        # --- 1. Role description ---
        parts.append(spec.role_description.strip())

        # --- 2. Output structure ---
        parts.append(spec.output_structure.strip())

        # --- 3. Rules — fixed order ---
        rules_lines: list[str] = ["STRICT RULES", ""]
        rules_dict = spec.rules.model_dump()
        for group_name in _RULE_ORDER:
            rules = rules_dict.get(group_name, [])
            if rules:
                rules_lines.append(f"{group_name.capitalize()}:")
                for rule in rules:
                    rules_lines.append(f"- {rule}")
                rules_lines.append("")  # blank line between groups
        parts.append("\n".join(rules_lines).strip())

        # --- 4. Examples — from the named example set ---
        example_names = spec.example_sets[example_set_name]
        example_parts: list[str] = ["EXAMPLES", ""]
        for i, example_name in enumerate(example_names, start=1):
            example = spec.examples[example_name]
            ex_lines: list[str] = [f"Example {i}:"]
            ex_lines.append(f"Schema:\n{example.schema_.strip()}")
            ex_lines.append(f"Query: {example.query.strip()}")
            ex_lines.append(f"Correct output:\n{example.correct.strip()}")
            if example.incorrect is not None:
                ex_lines.append(f"Incorrect output:\n{example.incorrect.strip()}")
            if example.why_wrong is not None:
                ex_lines.append(f"Why wrong:\n{example.why_wrong.strip()}")
            example_parts.append("\n".join(ex_lines))
            example_parts.append("")  # blank line between examples

        parts.append("\n".join(example_parts).strip())

        return "\n\n".join(parts)

    @staticmethod
    def render_user_prompt(
        spec: StrategyPromptSpec,
        schema_summary: str,
        user_query: str,
    ) -> str:
        """
        Render the per-request user prompt by substituting placeholders.

        Args:
            spec:          A validated StrategyPromptSpec.
            schema_summary: Output of build_schema_summary() for the active schema.
            user_query:    The raw NL query from the user (nl_query_original).

        Returns:
            The rendered user prompt string with both placeholders substituted.
        """
        prompt = spec.user_template
        prompt = prompt.replace("<SCHEMA_SUMMARY>", schema_summary)
        prompt = prompt.replace("<USER_QUERY>", user_query)
        return prompt
