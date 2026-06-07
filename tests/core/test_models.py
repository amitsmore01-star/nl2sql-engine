# tests/core/test_models.py
# V0 - Initial implementation
# V1 - Story 3.5: Updated for llm_output field replacing intent_output + mapping_output.
#      Added C1-C5 tests for the llm_output refactor.
#      Removed any references to intent_output and mapping_output.
#
# Tests for QueryContext and StructuredQuery Pydantic models.
# Also covers sub-models: ResolvedTable, ResolvedColumn, ResolvedJoin, ResolvedFilter.

import uuid
import pytest

from src.core.models import (
    QueryContext,
    StructuredQuery,
    ResolvedTable,
    ResolvedColumn,
    ResolvedJoin,
    ResolvedFilter,
)


# ---------------------------------------------------------------------------
# QueryContext — core behaviour
# ---------------------------------------------------------------------------

class TestQueryContextDefaults:
    """Basic field defaults and required fields."""

    def test_request_id_auto_generated(self):
        """request_id is a UUID string auto-generated when not supplied."""
        ctx = QueryContext(nl_query_original="test")
        assert isinstance(ctx.request_id, str)
        # Verify it's a valid UUID — uuid.UUID() raises ValueError if not
        uuid.UUID(ctx.request_id)

    def test_request_id_explicit(self):
        """Explicit request_id is preserved."""
        ctx = QueryContext(nl_query_original="test", request_id="my-id-123")
        assert ctx.request_id == "my-id-123"

    def test_user_id_default(self):
        """user_id defaults to Phase1_user."""
        ctx = QueryContext(nl_query_original="test")
        assert ctx.user_id == "Phase1_user"

    def test_app_id_default_empty_string(self):
        """app_id defaults to empty string — not None."""
        ctx = QueryContext(nl_query_original="test")
        assert ctx.app_id == ""

    def test_app_schema_version_default_empty_string(self):
        """app_schema_version defaults to empty string — not None."""
        ctx = QueryContext(nl_query_original="test")
        assert ctx.app_schema_version == ""

    def test_nl_query_original_required(self):
        """nl_query_original is required — omitting it raises ValidationError."""
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            QueryContext()  # type: ignore[call-arg]

    def test_status_defaults_to_pending(self):
        """status defaults to 'pending'."""
        ctx = QueryContext(nl_query_original="test")
        assert ctx.status == "pending"

    def test_list_fields_default_to_empty(self):
        """All list fields default to empty lists."""
        ctx = QueryContext(nl_query_original="test")
        assert ctx.resolved_tables == []
        assert ctx.resolved_columns == []
        assert ctx.resolved_filters == []
        assert ctx.resolved_joins == []
        assert ctx.applied_rules == []
        assert ctx.warnings == []

    def test_dict_fields_default_to_empty(self):
        """latency_ms and token_usage default to empty dicts."""
        ctx = QueryContext(nl_query_original="test")
        assert ctx.latency_ms == {}
        assert ctx.token_usage == {}

    def test_optional_fields_default_to_none(self):
        """Optional fields default to None."""
        ctx = QueryContext(nl_query_original="test")
        assert ctx.nl_query_corrected is None
        assert ctx.structured_query is None
        assert ctx.sql is None
        assert ctx.error is None


# ---------------------------------------------------------------------------
# llm_output field — Story 3.5 refactor (replaces intent_output + mapping_output)
# ---------------------------------------------------------------------------

class TestLLMOutputField:
    """C1-C5: llm_output field behaviour."""

    def test_c1_llm_output_defaults_to_none(self):
        """C1: llm_output defaults to None when not supplied."""
        ctx = QueryContext(nl_query_original="test")
        assert ctx.llm_output is None

    def test_c2_llm_output_accepts_populated_dict(self):
        """C2: llm_output accepts a populated simplified IR dict."""
        ir = {
            "tables": [{"table": "Major.Customer", "source": "customer"}],
            "columns": [{"table": "Major.CustomerDemographics", "column": "CustomerName", "source": "customer name"}],
            "filters": [{"table": "Major.Customer", "column": "CustomerCID", "operator": "=", "value": "CUST01", "source": "customer CUST01"}],
            "limit": None,
            "aggregation": None,
            "sort": [],
        }
        ctx = QueryContext(nl_query_original="test", llm_output=ir)
        assert ctx.llm_output == ir
        assert ctx.llm_output["tables"][0]["table"] == "Major.Customer"

    def test_c3_intent_output_field_does_not_exist(self):
        """C3: intent_output no longer exists — accessing it raises AttributeError."""
        ctx = QueryContext(nl_query_original="test")
        with pytest.raises(AttributeError):
            _ = ctx.intent_output  # type: ignore[attr-defined]

    def test_c4_mapping_output_field_does_not_exist(self):
        """C4: mapping_output no longer exists — accessing it raises AttributeError."""
        ctx = QueryContext(nl_query_original="test")
        with pytest.raises(AttributeError):
            _ = ctx.mapping_output  # type: ignore[attr-defined]

    def test_c5_llm_output_can_be_updated_after_creation(self):
        """C5: llm_output is mutable — strategy can write to it after context is created."""
        ctx = QueryContext(nl_query_original="test")
        assert ctx.llm_output is None
        ctx.llm_output = {"tables": [], "columns": [], "filters": [], "limit": None}
        assert ctx.llm_output is not None
        assert ctx.llm_output["tables"] == []


# ---------------------------------------------------------------------------
# nl_query_original immutability
# ---------------------------------------------------------------------------

class TestNLQueryImmutability:
    """nl_query_original must not be reassignable after creation."""

    def test_nl_query_original_stored_correctly(self):
        """The value is accessible after creation."""
        ctx = QueryContext(nl_query_original="give me customers in Acme")
        assert ctx.nl_query_original == "give me customers in Acme"

    def test_nl_query_original_cannot_be_reassigned(self):
        """Reassigning nl_query_original after creation raises AttributeError."""
        ctx = QueryContext(nl_query_original="original query")
        with pytest.raises(AttributeError):
            ctx.nl_query_original = "modified query"

    def test_other_fields_remain_mutable(self):
        """Other fields (e.g. app_id) can be freely updated after creation."""
        ctx = QueryContext(nl_query_original="test")
        ctx.app_id = "Acme_app"
        assert ctx.app_id == "Acme_app"


# ---------------------------------------------------------------------------
# StructuredQuery
# ---------------------------------------------------------------------------

class TestStructuredQuery:
    """StructuredQuery model — defaults and field behaviour."""

    def test_app_id_required(self):
        """app_id is required — omitting raises ValidationError."""
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            StructuredQuery()  # type: ignore[call-arg]

    def test_defaults_are_empty(self):
        """All list fields default to empty, top_rows defaults to None."""
        sq = StructuredQuery(app_id="Acme_app")
        assert sq.top_rows is None
        assert sq.tables == []
        assert sq.columns == []
        assert sq.joins == []
        assert sq.filters == []
        assert sq.applied_rules == []

    def test_full_construction(self):
        """StructuredQuery accepts all fields."""
        sq = StructuredQuery(
            app_id="Acme_app",
            top_rows=10000,
            tables=[ResolvedTable(table_name="Major.Customer", alias="c")],
            columns=[ResolvedColumn(table_alias="c", column_name="CustomerName", output_alias="CustomerName")],
            joins=[ResolvedJoin(table_name="Major.CustomerDemographics", alias="cd", on_left="c.CustomerID", on_right="cd.CustomerID")],
            filters=[ResolvedFilter(table_alias="c", column_name="CustomerCID", operator="=", value="CUST01")],
            applied_rules=["c.VersionTermDate IS NULL"],
        )
        assert sq.app_id == "Acme_app"
        assert sq.top_rows == 10000
        assert len(sq.tables) == 1
        assert sq.tables[0].alias == "c"
        assert sq.applied_rules == ["c.VersionTermDate IS NULL"]


# ---------------------------------------------------------------------------
# Sub-models
# ---------------------------------------------------------------------------

class TestResolvedTable:
    def test_fields(self):
        t = ResolvedTable(table_name="Major.Customer", alias="c")
        assert t.table_name == "Major.Customer"
        assert t.alias == "c"


class TestResolvedColumn:
    def test_fields(self):
        col = ResolvedColumn(table_alias="cd", column_name="CustomerName", output_alias="CustomerName")
        assert col.table_alias == "cd"
        assert col.column_name == "CustomerName"
        assert col.output_alias == "CustomerName"


class TestResolvedJoin:
    def test_default_join_type(self):
        """join_type defaults to INNER JOIN."""
        j = ResolvedJoin(table_name="Major.CustomerDemographics", alias="cd", on_left="c.CustomerID", on_right="cd.CustomerID")
        assert j.join_type == "INNER JOIN"

    def test_explicit_join_type(self):
        j = ResolvedJoin(join_type="LEFT JOIN", table_name="Major.Acc", alias="a", on_left="c.CustomerID", on_right="a.CustomerID")
        assert j.join_type == "LEFT JOIN"


class TestResolvedFilter:
    def test_fields(self):
        f = ResolvedFilter(table_alias="c", column_name="CustomerCID", operator="=", value="CUST01")
        assert f.table_alias == "c"
        assert f.operator == "="
        assert f.value == "CUST01"
