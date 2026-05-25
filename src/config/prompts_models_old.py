# src/config/prompts_models.py
# V0 - Initial implementation
#
# Pydantic models that describe the structure of config/prompts.yaml.
# Loaded at startup by src/config/settings.py via load_settings().
# If prompts.yaml does not match these models, the service refuses to start.
#
# Structural validation:  Pydantic (this file) — wrong types, missing keys
# Semantic validation:    PromptBuilder.validate() — broken references,
#                         missing placeholders, incorrect/why_wrong pairing

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, ConfigDict


# ---------------------------------------------------------------------------
# Individual example — one few-shot example in prompts.yaml
# ---------------------------------------------------------------------------

class PromptExample(BaseModel):
    """
    One few-shot example.

    schema:    compressed table/column summary shown to the LLM in the example
    query:     the natural language query for this example
    correct:   the correct JSON IR output
    incorrect: an incorrect output (optional — must be paired with why_wrong)
    why_wrong: explanation of why the incorrect output is wrong (optional —
               must be paired with incorrect)
    """
    model_config = ConfigDict(extra="forbid")

    schema_: str  # 'schema' is a reserved word in Pydantic — aliased below
    query: str
    correct: str
    incorrect: Optional[str] = None
    why_wrong: Optional[str] = None

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    # Pydantic alias so YAML key 'schema' maps to field 'schema_'
    @classmethod
    def model_fields_set(cls):  # noqa: D102
        return super().model_fields_set()

    class Config:
        # Allow the YAML key 'schema' to populate field 'schema_'
        populate_by_name = True


# ---------------------------------------------------------------------------
# Rules — grouped by topic
# ---------------------------------------------------------------------------

class PromptRules(BaseModel):
    """
    Rules grouped by topic. Each value is a list of rule strings.
    Assembly order is enforced by PromptBuilder — not by dict key order.
    """
    model_config = ConfigDict(extra="forbid")

    output: list[str]
    tables: list[str]
    columns: list[str]
    filters: list[str]
    source: list[str]
    limit: list[str]
    aggregation: list[str]
    sort: list[str]


# ---------------------------------------------------------------------------
# One strategy's full prompt spec
# ---------------------------------------------------------------------------

class StrategyPromptSpec(BaseModel):
    """
    All prompt sections for one NL-to-IR strategy.

    role_description:  what the assistant is and what it does
    output_structure:  exact JSON shape the LLM must produce
    rules:             grouped rules by topic
    example_sets:      named groupings — keys are set names, values are
                       lists of example names (must exist in 'examples')
    examples:          each example defined once, referenced by name from sets
    user_template:     per-request template — must contain <SCHEMA_SUMMARY>
                       and <USER_QUERY> placeholders
    """
    model_config = ConfigDict(extra="forbid")

    role_description: str
    output_structure: str
    rules: PromptRules
    example_sets: dict[str, list[str]]
    examples: dict[str, PromptExample]
    user_template: str


# ---------------------------------------------------------------------------
# Root model — top-level keys are strategy names
# ---------------------------------------------------------------------------

class PromptsConfig(BaseModel):
    """
    Root model for config/prompts.yaml.

    Each top-level key is a strategy name (e.g. nl_to_structured_query).
    Future strategies add their own top-level key here.
    """
    model_config = ConfigDict(extra="allow")  # allow future strategy keys

    nl_to_structured_query: StrategyPromptSpec
