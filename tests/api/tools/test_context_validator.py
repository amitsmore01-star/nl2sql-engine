# tests/api/tools/test_context_validator.py
# V0 - Initial implementation
# V1 - Fixed test helper and A1/A5/A6/B1/B2/C2 to match actual QueryContext field types.
#      app_id and app_schema_version are str (default ""), not Optional[str].
#      StructuredQuery requires app_id — cannot instantiate with no args.

"""
Tests for ContextValidator and all StageRequirements strategies.

Coverage map:
  Group A  — Happy path: valid context, no error raised
  Group B  — Single missing field per stage
  Group C  — Multiple missing fields in one call
  Group D  — Empty string treated as missing (string fields only)
  Group E  — Unknown stage name raises ValueError
  Group F  — Error detail: code, message content, missing_fields attribute

Key constraint from models.py:
  QueryContext.app_id          → str, default=""   (NOT Optional — None rejected by Pydantic)
  QueryContext.app_schema_version → str, default="" (NOT Optional — None rejected by Pydantic)
  QueryContext.nl_query_original  → str, required   (NOT Optional)
  QueryContext.intent_output   → Optional[dict]     (None is valid)
  QueryContext.mapping_output  → Optional[dict]     (None is valid)
  QueryContext.structured_query → Optional[StructuredQuery] (None is valid)
  StructuredQuery.app_id       → str, required      (no default — must be supplied)

To simulate a "missing" string field: pass "" (empty string).
The context validator treats "" the same as None — both count as missing.
"""

import pytest

from src.api.tools.context_validator import (
    AppIdentifierRequirements,
    ContextValidator,
    FullQueryRequirements,
    IntentExtractorRequirements,
    SchemMapperRequirements,
    SqlBuilderRequirements,
    ValidatorRequirements,
)
from src.core.exceptions import MissingContextFieldsError
from src.core.models import QueryContext, StructuredQuery


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_context(**overrides) -> QueryContext:
    """
    Build a fully-populated QueryContext for testing.

    All fields that the context validator checks are given sensible defaults.
    Pass keyword arguments to override specific fields.

    IMPORTANT — string fields cannot be None:
      QueryContext.app_id and app_schema_version are typed as `str` with
      default="" . Pydantic rejects None for these.
      To simulate a missing string value: pass "" (empty string).
      The context validator treats "" the same as missing/absent.

      Only Optional fields accept None:
        intent_output, mapping_output, structured_query, nl_query_corrected.
    """
    defaults = dict(
        nl_query_original="give me customer name in ABC",
        app_id="ABC_app",
        app_schema_version="1.0",
        intent_output={"intent": "select", "entities": ["customer"]},
        mapping_output={"tables": ["Major.Customer"]},
        structured_query=None,
    )
    defaults.update(overrides)
    return QueryContext(**defaults)


# ---------------------------------------------------------------------------
# Group A — Happy path
# ---------------------------------------------------------------------------

class TestHappyPath:
    """A1-A6: valid context for each stage raises no error."""

    def test_a1_app_identifier_valid(self):
        """
        A1: app-identifier only needs nl_query_original.
        app_id and app_schema_version start as "" (model default) — that is fine
        because app-identifier does NOT check those fields; it produces them.
        """
        ctx = make_context(
            app_id="",               # empty — stage will populate this
            app_schema_version="",   # empty — stage will populate this
            intent_output=None,
            mapping_output=None,
        )
        # Should not raise — app-identifier only requires nl_query_original
        ContextValidator().validate(ctx, "app-identifier")

    def test_a2_intent_extractor_valid(self):
        """A2: intent-extractor needs nl_query_original + app_id + app_schema_version."""
        ctx = make_context(intent_output=None, mapping_output=None)
        ContextValidator().validate(ctx, "intent-extractor")

    def test_a3_schema_mapper_valid(self):
        """A3: schema-mapper needs app_id + app_schema_version + intent_output."""
        ctx = make_context(mapping_output=None)
        ContextValidator().validate(ctx, "schema-mapper")

    def test_a4_validator_valid(self):
        """A4: validator needs app_id + app_schema_version + intent_output + mapping_output."""
        ctx = make_context()
        ContextValidator().validate(ctx, "validator")

    def test_a5_sql_builder_valid(self):
        """
        A5: sql-builder needs app_id + structured_query.
        StructuredQuery requires app_id — cannot be instantiated with no arguments.
        """
        sq = StructuredQuery(app_id="ABC_app")
        ctx = make_context(structured_query=sq)
        ContextValidator().validate(ctx, "sql-builder")

    def test_a6_full_query_valid(self):
        """
        A6: query (full pipeline tool) only needs nl_query_original.
        app_id starts as "" — fine because this stage produces it.
        """
        ctx = make_context(
            app_id="",
            app_schema_version="",
            intent_output=None,
            mapping_output=None,
        )
        ContextValidator().validate(ctx, "query")


# ---------------------------------------------------------------------------
# Group B — Single missing field
# ---------------------------------------------------------------------------

class TestSingleMissingField:
    """
    B1-B5: each stage raises when its key field is absent/empty.

    For string fields (app_id, app_schema_version, nl_query_original):
      pass "" — Pydantic accepts it, validator treats it as missing.
    For Optional fields (intent_output, mapping_output, structured_query):
      pass None — Pydantic accepts it, validator treats it as missing.
    """

    def test_b1_app_identifier_missing_nl_query(self):
        """B1: app-identifier — nl_query_original is '' → treated as missing."""
        ctx = make_context(nl_query_original="")
        with pytest.raises(MissingContextFieldsError) as exc_info:
            ContextValidator().validate(ctx, "app-identifier")
        assert "nl_query_original" in exc_info.value.missing_fields

    def test_b2_intent_extractor_missing_app_id(self):
        """B2: intent-extractor — app_id is '' → treated as missing."""
        ctx = make_context(app_id="")
        with pytest.raises(MissingContextFieldsError) as exc_info:
            ContextValidator().validate(ctx, "intent-extractor")
        assert "app_id" in exc_info.value.missing_fields

    def test_b3_schema_mapper_missing_intent_output(self):
        """B3: schema-mapper — intent_output is None → missing."""
        ctx = make_context(intent_output=None)
        with pytest.raises(MissingContextFieldsError) as exc_info:
            ContextValidator().validate(ctx, "schema-mapper")
        assert "intent_output" in exc_info.value.missing_fields

    def test_b4_validator_missing_mapping_output(self):
        """B4: validator — mapping_output is None → missing."""
        ctx = make_context(mapping_output=None)
        with pytest.raises(MissingContextFieldsError) as exc_info:
            ContextValidator().validate(ctx, "validator")
        assert "mapping_output" in exc_info.value.missing_fields

    def test_b5_sql_builder_missing_structured_query(self):
        """B5: sql-builder — structured_query is None → missing."""
        ctx = make_context(structured_query=None)
        with pytest.raises(MissingContextFieldsError) as exc_info:
            ContextValidator().validate(ctx, "sql-builder")
        assert "structured_query" in exc_info.value.missing_fields


# ---------------------------------------------------------------------------
# Group C — Multiple missing fields reported in one error
# ---------------------------------------------------------------------------

class TestMultipleMissingFields:
    """C1-C2: all missing fields listed in a single error."""

    def test_c1_validator_both_llm_outputs_missing(self):
        """C1: validator — intent_output and mapping_output both None → both listed."""
        ctx = make_context(intent_output=None, mapping_output=None)
        with pytest.raises(MissingContextFieldsError) as exc_info:
            ContextValidator().validate(ctx, "validator")
        missing = exc_info.value.missing_fields
        assert "intent_output" in missing
        assert "mapping_output" in missing
        assert len(missing) == 2

    def test_c2_intent_extractor_two_fields_missing(self):
        """C2: intent-extractor — app_id='' and app_schema_version='' → both listed."""
        ctx = make_context(app_id="", app_schema_version="")
        with pytest.raises(MissingContextFieldsError) as exc_info:
            ContextValidator().validate(ctx, "intent-extractor")
        missing = exc_info.value.missing_fields
        assert "app_id" in missing
        assert "app_schema_version" in missing
        assert len(missing) == 2


# ---------------------------------------------------------------------------
# Group D — Empty string treated as missing
# ---------------------------------------------------------------------------

class TestEmptyStringAsMissing:
    """D1-D3: empty/whitespace string on a string field is treated as missing.
       D4: empty dict on a dict field is NOT treated as missing."""

    def test_d1_nl_query_empty_string(self):
        """D1: nl_query_original='' → treated as missing."""
        ctx = make_context(nl_query_original="")
        with pytest.raises(MissingContextFieldsError) as exc_info:
            ContextValidator().validate(ctx, "app-identifier")
        assert "nl_query_original" in exc_info.value.missing_fields

    def test_d2_app_id_empty_string(self):
        """D2: app_id='' → treated as missing."""
        ctx = make_context(app_id="")
        with pytest.raises(MissingContextFieldsError) as exc_info:
            ContextValidator().validate(ctx, "intent-extractor")
        assert "app_id" in exc_info.value.missing_fields

    def test_d3_whitespace_only_string(self):
        """D3: app_schema_version='   ' (whitespace only) → treated as missing."""
        ctx = make_context(app_schema_version="   ")
        with pytest.raises(MissingContextFieldsError) as exc_info:
            ContextValidator().validate(ctx, "intent-extractor")
        assert "app_schema_version" in exc_info.value.missing_fields

    def test_d4_empty_dict_is_not_missing(self):
        """D4: intent_output={} is NOT missing — empty dict is a valid value."""
        ctx = make_context(intent_output={}, mapping_output={})
        # Should not raise
        ContextValidator().validate(ctx, "validator")


# ---------------------------------------------------------------------------
# Group E — Unknown stage name
# ---------------------------------------------------------------------------

class TestUnknownStage:
    """E1-E2: unrecognised stage name is a programming error → ValueError."""

    def test_e1_unknown_stage_raises_value_error(self):
        """E1: unknown stage → ValueError, not MissingContextFieldsError."""
        ctx = make_context()
        with pytest.raises(ValueError) as exc_info:
            ContextValidator().validate(ctx, "unknown-stage")
        assert "unknown-stage" in str(exc_info.value)

    def test_e2_error_message_lists_valid_stages(self):
        """E2: ValueError message includes at least one valid stage name."""
        ctx = make_context()
        with pytest.raises(ValueError) as exc_info:
            ContextValidator().validate(ctx, "bad-stage")
        assert "app-identifier" in str(exc_info.value)


# ---------------------------------------------------------------------------
# Group F — Error detail quality
# ---------------------------------------------------------------------------

class TestErrorDetail:
    """F1-F4: MissingContextFieldsError carries correct code, message, fields."""

    def test_f1_error_code_is_missing_context_fields(self):
        """F1: error.code == MISSING_CONTEXT_FIELDS constant."""
        from src.core.constants import MISSING_CONTEXT_FIELDS
        ctx = make_context(intent_output=None)
        with pytest.raises(MissingContextFieldsError) as exc_info:
            ContextValidator().validate(ctx, "schema-mapper")
        assert exc_info.value.code == MISSING_CONTEXT_FIELDS

    def test_f2_error_message_contains_stage_name(self):
        """F2: error message mentions the stage that failed."""
        ctx = make_context(mapping_output=None)
        with pytest.raises(MissingContextFieldsError) as exc_info:
            ContextValidator().validate(ctx, "validator")
        assert "validator" in exc_info.value.message

    def test_f3_missing_fields_accessible_as_list_attribute(self):
        """F3: missing_fields is a list on the exception — not buried in a string."""
        ctx = make_context(intent_output=None, mapping_output=None)
        with pytest.raises(MissingContextFieldsError) as exc_info:
            ContextValidator().validate(ctx, "validator")
        assert isinstance(exc_info.value.missing_fields, list)
        assert len(exc_info.value.missing_fields) > 0

    def test_f4_error_is_subclass_of_base_error(self):
        """F4: MissingContextFieldsError is a proper NL2SQLBaseError subclass."""
        from src.core.exceptions import NL2SQLBaseError
        ctx = make_context(intent_output=None)
        with pytest.raises(NL2SQLBaseError):
            ContextValidator().validate(ctx, "schema-mapper")


# ---------------------------------------------------------------------------
# Unit tests for individual StageRequirements classes
# ---------------------------------------------------------------------------

class TestStageRequirementsDirectly:
    """
    Unit-test each StageRequirements class in isolation.
    Validates the Strategy pattern — each class is independently correct.
    """

    def test_app_identifier_stage_name(self):
        assert AppIdentifierRequirements().stage_name == "app-identifier"

    def test_intent_extractor_stage_name(self):
        assert IntentExtractorRequirements().stage_name == "intent-extractor"

    def test_schema_mapper_stage_name(self):
        assert SchemMapperRequirements().stage_name == "schema-mapper"

    def test_validator_stage_name(self):
        assert ValidatorRequirements().stage_name == "validator"

    def test_sql_builder_stage_name(self):
        assert SqlBuilderRequirements().stage_name == "sql-builder"

    def test_full_query_stage_name(self):
        assert FullQueryRequirements().stage_name == "query"

    def test_registry_contains_all_six_stages(self):
        """ContextValidator registry must cover all 6 defined stages."""
        validator = ContextValidator()
        expected = {
            "app-identifier",
            "intent-extractor",
            "schema-mapper",
            "validator",
            "sql-builder",
            "query",
        }
        assert set(validator.supported_stages) == expected
