# tests/api/tools/test_context_validator.py
# V0 - Initial implementation
# V1 - Story 3.5: Architecture v1.6 redesign.
#      - Removed tests for intent-extractor and schema-mapper stages (no longer exist)
#      - Replaced with nl-to-ir stage tests
#      - Updated validator stage tests: requires llm_output instead of
#        intent_output + mapping_output
#      - Updated make_context() helper: removed intent_output/mapping_output,
#        added llm_output
#      - Updated registry count: 6 stages → 5 stages
#      - Added D6: empty dict for llm_output is NOT missing
#      - Added D7/D8: intent-extractor and schema-mapper no longer in registry
#      - Added D9: supported_stages sanity check

"""
Tests for ContextValidator and all StageRequirements strategies.

Coverage map:
  Group A  — Happy path: valid context, no error raised
  Group B  — Single missing field per stage
  Group C  — Multiple missing fields in one call
  Group D  — Field presence rules (empty string, empty dict, removed stages)
  Group E  — Unknown stage name raises ValueError
  Group F  — Error detail: code, message content, missing_fields attribute

Key constraint from models.py (V1):
  QueryContext.app_id              → str, default=""    (NOT Optional)
  QueryContext.app_schema_version  → str, default=""    (NOT Optional)
  QueryContext.nl_query_original   → str, required
  QueryContext.llm_output          → Optional[dict]     (None is valid / missing)
  QueryContext.structured_query    → Optional[StructuredQuery] (None is valid / missing)
  StructuredQuery.app_id           → str, required      (no default)

To simulate a missing string field: pass "" (empty string).
The context validator treats "" the same as None — both count as missing.
"""

import pytest

from src.api.tools.context_validator import (
    AppIdentifierRequirements,
    ContextValidator,
    FullQueryRequirements,
    NLToIRRequirements,
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
      QueryContext.app_id and app_schema_version are typed as str with default="".
      Pydantic rejects None for these.
      To simulate a missing string value: pass "" (empty string).
      The context validator treats "" the same as missing/absent.

      Only Optional fields accept None:
        llm_output, structured_query, nl_query_corrected.
    """
    defaults = dict(
        nl_query_original="give me customer name in Acme",
        app_id="Acme_app",
        app_schema_version="1.0",
        llm_output={"tables": [], "columns": [], "filters": [], "limit": None},
        structured_query=None,
    )
    defaults.update(overrides)
    return QueryContext(**defaults)


# ---------------------------------------------------------------------------
# Group A — Happy path
# ---------------------------------------------------------------------------

class TestHappyPath:
    """A1-A5: valid context for each stage raises no error."""

    def test_a1_app_identifier_valid(self):
        """
        A1: app-identifier only needs nl_query_original.
        app_id and app_schema_version start as "" — fine because
        app-identifier does NOT check those fields; it produces them.
        """
        ctx = make_context(
            app_id="",
            app_schema_version="",
            llm_output=None,
        )
        ContextValidator().validate(ctx, "app-identifier")

    def test_a2_nl_to_ir_valid(self):
        """A2: nl-to-ir needs nl_query_original + app_id + app_schema_version."""
        ctx = make_context(llm_output=None)
        ContextValidator().validate(ctx, "nl-to-ir")

    def test_a3_validator_valid(self):
        """A3: validator needs app_id + app_schema_version + llm_output."""
        ctx = make_context()
        ContextValidator().validate(ctx, "validator")

    def test_a4_sql_builder_valid(self):
        """
        A4: sql-builder needs app_id + structured_query.
        StructuredQuery requires app_id — cannot be instantiated with no arguments.
        """
        sq = StructuredQuery(app_id="Acme_app")
        ctx = make_context(structured_query=sq)
        ContextValidator().validate(ctx, "sql-builder")

    def test_a5_full_query_valid(self):
        """
        A5: query (full pipeline tool) only needs nl_query_original.
        app_id starts as "" — fine because this stage produces it.
        """
        ctx = make_context(
            app_id="",
            app_schema_version="",
            llm_output=None,
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
    For Optional fields (llm_output, structured_query):
      pass None — Pydantic accepts it, validator treats it as missing.
    """

    def test_b1_app_identifier_missing_nl_query(self):
        """B1: app-identifier — nl_query_original is '' → treated as missing."""
        ctx = make_context(nl_query_original="")
        with pytest.raises(MissingContextFieldsError) as exc_info:
            ContextValidator().validate(ctx, "app-identifier")
        assert "nl_query_original" in exc_info.value.missing_fields

    def test_b2_nl_to_ir_missing_app_id(self):
        """B2: nl-to-ir — app_id is '' → treated as missing."""
        ctx = make_context(app_id="")
        with pytest.raises(MissingContextFieldsError) as exc_info:
            ContextValidator().validate(ctx, "nl-to-ir")
        assert "app_id" in exc_info.value.missing_fields

    def test_b3_validator_missing_llm_output(self):
        """B3: validator — llm_output is None → missing."""
        ctx = make_context(llm_output=None)
        with pytest.raises(MissingContextFieldsError) as exc_info:
            ContextValidator().validate(ctx, "validator")
        assert "llm_output" in exc_info.value.missing_fields

    def test_b4_sql_builder_missing_structured_query(self):
        """B4: sql-builder — structured_query is None → missing."""
        ctx = make_context(structured_query=None)
        with pytest.raises(MissingContextFieldsError) as exc_info:
            ContextValidator().validate(ctx, "sql-builder")
        assert "structured_query" in exc_info.value.missing_fields

    def test_b5_nl_to_ir_missing_app_schema_version(self):
        """B5: nl-to-ir — app_schema_version is '' → treated as missing."""
        ctx = make_context(app_schema_version="")
        with pytest.raises(MissingContextFieldsError) as exc_info:
            ContextValidator().validate(ctx, "nl-to-ir")
        assert "app_schema_version" in exc_info.value.missing_fields


# ---------------------------------------------------------------------------
# Group C — Multiple missing fields reported in one error
# ---------------------------------------------------------------------------

class TestMultipleMissingFields:
    """C1-C2: all missing fields listed in a single error."""

    def test_c1_nl_to_ir_two_fields_missing(self):
        """C1: nl-to-ir — app_id='' and app_schema_version='' → both listed."""
        ctx = make_context(app_id="", app_schema_version="")
        with pytest.raises(MissingContextFieldsError) as exc_info:
            ContextValidator().validate(ctx, "nl-to-ir")
        missing = exc_info.value.missing_fields
        assert "app_id" in missing
        assert "app_schema_version" in missing
        assert len(missing) == 2

    def test_c2_validator_all_fields_missing(self):
        """C2: validator — app_id='' and llm_output=None → both listed."""
        ctx = make_context(app_id="", llm_output=None)
        with pytest.raises(MissingContextFieldsError) as exc_info:
            ContextValidator().validate(ctx, "validator")
        missing = exc_info.value.missing_fields
        assert "app_id" in missing
        assert "llm_output" in missing
        assert len(missing) == 2


# ---------------------------------------------------------------------------
# Group D — Field presence rules
# ---------------------------------------------------------------------------

class TestFieldPresenceRules:
    """D1-D9: empty string, empty dict, whitespace, and removed stage rules."""

    def test_d1_nl_query_empty_string_is_missing(self):
        """D1: nl_query_original='' → treated as missing."""
        ctx = make_context(nl_query_original="")
        with pytest.raises(MissingContextFieldsError) as exc_info:
            ContextValidator().validate(ctx, "app-identifier")
        assert "nl_query_original" in exc_info.value.missing_fields

    def test_d2_app_id_empty_string_is_missing(self):
        """D2: app_id='' → treated as missing."""
        ctx = make_context(app_id="")
        with pytest.raises(MissingContextFieldsError) as exc_info:
            ContextValidator().validate(ctx, "nl-to-ir")
        assert "app_id" in exc_info.value.missing_fields

    def test_d3_whitespace_only_string_is_missing(self):
        """D3: app_schema_version='   ' (whitespace only) → treated as missing."""
        ctx = make_context(app_schema_version="   ")
        with pytest.raises(MissingContextFieldsError) as exc_info:
            ContextValidator().validate(ctx, "nl-to-ir")
        assert "app_schema_version" in exc_info.value.missing_fields

    def test_d4_empty_string_nl_query_for_full_query(self):
        """D4: query stage — nl_query_original='' → missing."""
        ctx = make_context(nl_query_original="")
        with pytest.raises(MissingContextFieldsError) as exc_info:
            ContextValidator().validate(ctx, "query")
        assert "nl_query_original" in exc_info.value.missing_fields

    def test_d5_empty_dict_llm_output_is_not_missing(self):
        """D5: llm_output={} is NOT missing — empty dict is a valid value."""
        ctx = make_context(llm_output={})
        # Should not raise — empty dict is present/valid
        ContextValidator().validate(ctx, "validator")

    def test_d6_populated_llm_output_passes(self):
        """D6: llm_output with real IR data passes validator stage check."""
        ctx = make_context(llm_output={
            "tables": [{"table": "Major.Customer", "source": "customer"}],
            "columns": [],
            "filters": [],
            "limit": None,
        })
        ContextValidator().validate(ctx, "validator")

    def test_d7_intent_extractor_stage_no_longer_exists(self):
        """D7: intent-extractor stage removed in arch v1.6 → ValueError."""
        ctx = make_context()
        with pytest.raises(ValueError) as exc_info:
            ContextValidator().validate(ctx, "intent-extractor")
        assert "intent-extractor" in str(exc_info.value)

    def test_d8_schema_mapper_stage_no_longer_exists(self):
        """D8: schema-mapper stage removed in arch v1.6 → ValueError."""
        ctx = make_context()
        with pytest.raises(ValueError) as exc_info:
            ContextValidator().validate(ctx, "schema-mapper")
        assert "schema-mapper" in str(exc_info.value)

    def test_d9_supported_stages_correct(self):
        """D9: supported_stages contains nl-to-ir and not the old stage names."""
        validator = ContextValidator()
        stages = validator.supported_stages
        assert "nl-to-ir" in stages
        assert "intent-extractor" not in stages
        assert "schema-mapper" not in stages


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
        ctx = make_context(llm_output=None)
        with pytest.raises(MissingContextFieldsError) as exc_info:
            ContextValidator().validate(ctx, "validator")
        assert exc_info.value.code == MISSING_CONTEXT_FIELDS

    def test_f2_error_message_contains_stage_name(self):
        """F2: error message mentions the stage that failed."""
        ctx = make_context(llm_output=None)
        with pytest.raises(MissingContextFieldsError) as exc_info:
            ContextValidator().validate(ctx, "validator")
        assert "validator" in exc_info.value.message

    def test_f3_missing_fields_accessible_as_list_attribute(self):
        """F3: missing_fields is a list on the exception — not buried in a string."""
        ctx = make_context(app_id="", llm_output=None)
        with pytest.raises(MissingContextFieldsError) as exc_info:
            ContextValidator().validate(ctx, "validator")
        assert isinstance(exc_info.value.missing_fields, list)
        assert len(exc_info.value.missing_fields) > 0

    def test_f4_error_is_subclass_of_base_error(self):
        """F4: MissingContextFieldsError is a proper NL2SQLBaseError subclass."""
        from src.core.exceptions import NL2SQLBaseError
        ctx = make_context(llm_output=None)
        with pytest.raises(NL2SQLBaseError):
            ContextValidator().validate(ctx, "validator")


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

    def test_nl_to_ir_stage_name(self):
        assert NLToIRRequirements().stage_name == "nl-to-ir"

    def test_validator_stage_name(self):
        assert ValidatorRequirements().stage_name == "validator"

    def test_sql_builder_stage_name(self):
        assert SqlBuilderRequirements().stage_name == "sql-builder"

    def test_full_query_stage_name(self):
        assert FullQueryRequirements().stage_name == "query"

    def test_registry_contains_exactly_five_stages(self):
        """ContextValidator registry must cover exactly the 5 defined stages (arch v1.6)."""
        validator = ContextValidator()
        expected = {
            "app-identifier",
            "nl-to-ir",
            "validator",
            "sql-builder",
            "query",
        }
        assert set(validator.supported_stages) == expected
