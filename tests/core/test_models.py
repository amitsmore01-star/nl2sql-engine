# tests/core/test_models.py
# V0 - Initial implementation
#
# Tests for src/core/models.py
# Scenarios: M1-M8 (sub-models), S1-S7 (StructuredQuery), Q1-Q9 (QueryContext)
#
# What these tests verify:
#   M1-M8  — Sub-models accept valid data and reject missing required fields
#   S1-S7  — StructuredQuery builds correctly, defaults are right, golden example works
#   Q1-Q9  — QueryContext defaults, auto UUID, immutability of nl_query_original

import uuid

import pytest
from pydantic import ValidationError

from src.core.models import (
    QueryContext,
    ResolvedColumn,
    ResolvedFilter,
    ResolvedJoin,
    ResolvedTable,
    StructuredQuery,
)


# ---------------------------------------------------------------------------
# M1-M2 — ResolvedTable
# ---------------------------------------------------------------------------

class TestResolvedTable:

    def test_accepts_valid_data(self):
        """M1 — ResolvedTable builds with valid table_name and alias."""
        table = ResolvedTable(table_name="Major.Customer", alias="c")
        assert table.table_name == "Major.Customer"
        assert table.alias == "c"

    def test_rejects_missing_table_name(self):
        """M2 — ResolvedTable raises ValidationError when table_name is missing."""
        with pytest.raises(ValidationError):
            ResolvedTable(alias="c")

    def test_rejects_missing_alias(self):
        """M2 — ResolvedTable raises ValidationError when alias is missing."""
        with pytest.raises(ValidationError):
            ResolvedTable(table_name="Major.Customer")


# ---------------------------------------------------------------------------
# M3-M4 — ResolvedColumn
# ---------------------------------------------------------------------------

class TestResolvedColumn:

    def test_accepts_valid_data(self):
        """M3 — ResolvedColumn builds with all required fields."""
        col = ResolvedColumn(
            table_alias="cd",
            column_name="CustomerName",
            output_alias="CustomerName"
        )
        assert col.table_alias == "cd"
        assert col.column_name == "CustomerName"
        assert col.output_alias == "CustomerName"

    def test_accepts_different_output_alias(self):
        """M3 — ResolvedColumn output_alias can differ from column_name."""
        col = ResolvedColumn(
            table_alias="a_top",
            column_name="AccName",
            output_alias="TopAccName"
        )
        assert col.output_alias == "TopAccName"

    def test_rejects_missing_table_alias(self):
        """M4 — ResolvedColumn raises ValidationError when table_alias is missing."""
        with pytest.raises(ValidationError):
            ResolvedColumn(column_name="CustomerName", output_alias="CustomerName")

    def test_rejects_missing_column_name(self):
        """M4 — ResolvedColumn raises ValidationError when column_name is missing."""
        with pytest.raises(ValidationError):
            ResolvedColumn(table_alias="cd", output_alias="CustomerName")

    def test_rejects_missing_output_alias(self):
        """M4 — ResolvedColumn raises ValidationError when output_alias is missing."""
        with pytest.raises(ValidationError):
            ResolvedColumn(table_alias="cd", column_name="CustomerName")


# ---------------------------------------------------------------------------
# M5-M6 — ResolvedJoin
# ---------------------------------------------------------------------------

class TestResolvedJoin:

    def test_accepts_valid_data(self):
        """M5 — ResolvedJoin builds with all fields provided."""
        join = ResolvedJoin(
            join_type="INNER JOIN",
            table_name="Major.CustomerDemographics",
            alias="cd",
            on_left="c.CustomerID",
            on_right="cd.CustomerID"
        )
        assert join.table_name == "Major.CustomerDemographics"
        assert join.alias == "cd"
        assert join.on_left == "c.CustomerID"
        assert join.on_right == "cd.CustomerID"
        assert join.join_type == "INNER JOIN"

    def test_defaults_join_type_to_inner_join(self):
        """M6 — ResolvedJoin defaults join_type to 'INNER JOIN' when omitted."""
        join = ResolvedJoin(
            table_name="Major.CustomerDemographics",
            alias="cd",
            on_left="c.CustomerID",
            on_right="cd.CustomerID"
        )
        assert join.join_type == "INNER JOIN"

    def test_rejects_missing_table_name(self):
        """M5 — ResolvedJoin raises ValidationError when table_name is missing."""
        with pytest.raises(ValidationError):
            ResolvedJoin(alias="cd", on_left="c.CustomerID", on_right="cd.CustomerID")

    def test_rejects_missing_alias(self):
        """M5 — ResolvedJoin raises ValidationError when alias is missing."""
        with pytest.raises(ValidationError):
            ResolvedJoin(
                table_name="Major.CustomerDemographics",
                on_left="c.CustomerID",
                on_right="cd.CustomerID"
            )

    def test_rejects_missing_on_left(self):
        """M5 — ResolvedJoin raises ValidationError when on_left is missing."""
        with pytest.raises(ValidationError):
            ResolvedJoin(
                table_name="Major.CustomerDemographics",
                alias="cd",
                on_right="cd.CustomerID"
            )

    def test_rejects_missing_on_right(self):
        """M5 — ResolvedJoin raises ValidationError when on_right is missing."""
        with pytest.raises(ValidationError):
            ResolvedJoin(
                table_name="Major.CustomerDemographics",
                alias="cd",
                on_left="c.CustomerID"
            )

    def test_accepts_self_join(self):
        """M5 — ResolvedJoin handles self-join (Acc to Acc) correctly."""
        join = ResolvedJoin(
            table_name="Major.Acc",
            alias="a_sub",
            on_left="a_top.AccID",
            on_right="a_sub.ParentAccID"
        )
        assert join.table_name == "Major.Acc"
        assert join.alias == "a_sub"


# ---------------------------------------------------------------------------
# M7-M8 — ResolvedFilter
# ---------------------------------------------------------------------------

class TestResolvedFilter:

    def test_accepts_valid_data(self):
        """M7 — ResolvedFilter builds with all required fields."""
        filt = ResolvedFilter(
            table_alias="c",
            column_name="CustomerCID",
            operator="=",
            value="ASA"
        )
        assert filt.table_alias == "c"
        assert filt.column_name == "CustomerCID"
        assert filt.operator == "="
        assert filt.value == "ASA"

    def test_rejects_missing_table_alias(self):
        """M8 — ResolvedFilter raises ValidationError when table_alias is missing."""
        with pytest.raises(ValidationError):
            ResolvedFilter(column_name="CustomerCID", operator="=", value="ASA")

    def test_rejects_missing_column_name(self):
        """M8 — ResolvedFilter raises ValidationError when column_name is missing."""
        with pytest.raises(ValidationError):
            ResolvedFilter(table_alias="c", operator="=", value="ASA")

    def test_rejects_missing_operator(self):
        """M8 — ResolvedFilter raises ValidationError when operator is missing."""
        with pytest.raises(ValidationError):
            ResolvedFilter(table_alias="c", column_name="CustomerCID", value="ASA")

    def test_rejects_missing_value(self):
        """M8 — ResolvedFilter raises ValidationError when value is missing."""
        with pytest.raises(ValidationError):
            ResolvedFilter(table_alias="c", column_name="CustomerCID", operator="=")


# ---------------------------------------------------------------------------
# S1-S7 — StructuredQuery
# ---------------------------------------------------------------------------

class TestStructuredQuery:

    def test_builds_from_valid_data(self):
        """S1 — StructuredQuery builds correctly with all sub-models."""
        sq = StructuredQuery(
            app_id="ABC_app",
            tables=[ResolvedTable(table_name="Major.Customer", alias="c")],
            columns=[ResolvedColumn(table_alias="c", column_name="CustomerCID", output_alias="CustomerCID")],
            joins=[],
            filters=[ResolvedFilter(table_alias="c", column_name="CustomerCID", operator="=", value="ASA")],
            applied_rules=["c.VersionTermDate IS NULL"]
        )
        assert sq.app_id == "ABC_app"
        assert len(sq.tables) == 1
        assert len(sq.columns) == 1
        assert len(sq.filters) == 1
        assert len(sq.applied_rules) == 1

    def test_top_rows_defaults_to_none(self):
        """S2 — StructuredQuery.top_rows defaults to None when not specified by user."""
        sq = StructuredQuery(app_id="ABC_app")
        assert sq.top_rows is None

    def test_top_rows_accepts_user_value(self):
        """S2 — StructuredQuery.top_rows stores a user-specified value."""
        sq = StructuredQuery(app_id="ABC_app", top_rows=500)
        assert sq.top_rows == 500

    def test_accepts_empty_applied_rules(self):
        """S3 — StructuredQuery accepts applied_rules as empty list."""
        sq = StructuredQuery(app_id="ABC_app", applied_rules=[])
        assert sq.applied_rules == []

    def test_accepts_multiple_joins(self):
        """S4 — StructuredQuery stores a list of multiple ResolvedJoin objects."""
        joins = [
            ResolvedJoin(
                table_name="Major.CustomerDemographics",
                alias="cd",
                on_left="c.CustomerID",
                on_right="cd.CustomerID"
            ),
            ResolvedJoin(
                table_name="Major.Acc",
                alias="a_top",
                on_left="c.CustomerID",
                on_right="a_top.CustomerID"
            ),
        ]
        sq = StructuredQuery(app_id="ABC_app", joins=joins)
        assert len(sq.joins) == 2
        assert sq.joins[0].alias == "cd"
        assert sq.joins[1].alias == "a_top"

    def test_rejects_missing_app_id(self):
        """S5 — StructuredQuery raises ValidationError when app_id is missing."""
        with pytest.raises(ValidationError):
            StructuredQuery()

    def test_applied_rules_are_plain_strings(self):
        """S6 — applied_rules stores raw SQL strings exactly as provided."""
        rules = [
            "c.VersionTermDate IS NULL",
            "ISNULL(c.DeletedFlag, 0) = 0",
            "c.VoidedDate IS NULL"
        ]
        sq = StructuredQuery(app_id="ABC_app", applied_rules=rules)
        assert sq.applied_rules == rules
        for rule in sq.applied_rules:
            assert isinstance(rule, str)

    def test_golden_example_builds_correctly(self):
        """S7 — Full StructuredQuery for Section 9.3 golden query builds correctly."""
        sq = StructuredQuery(
            app_id="ABC_app",
            top_rows=None,   # not specified by user — SQL Builder will apply config
            tables=[
                ResolvedTable(table_name="Major.Customer", alias="c"),
                ResolvedTable(table_name="Major.CustomerDemographics", alias="cd"),
                ResolvedTable(table_name="Major.Acc", alias="a_top"),
                ResolvedTable(table_name="Major.Acc", alias="a_sub"),
            ],
            columns=[
                ResolvedColumn(table_alias="cd",    column_name="CustomerName", output_alias="CustomerName"),
                ResolvedColumn(table_alias="a_top", column_name="AccName",      output_alias="TopAccName"),
                ResolvedColumn(table_alias="a_sub", column_name="AccName",      output_alias="SubAccName"),
            ],
            joins=[
                ResolvedJoin(
                    table_name="Major.CustomerDemographics", alias="cd",
                    on_left="c.CustomerID", on_right="cd.CustomerID"
                ),
                ResolvedJoin(
                    table_name="Major.Acc", alias="a_top",
                    on_left="c.CustomerID", on_right="a_top.CustomerID"
                ),
                ResolvedJoin(
                    table_name="Major.Acc", alias="a_sub",
                    on_left="a_top.AccID", on_right="a_sub.ParentAccID"
                ),
            ],
            filters=[
                ResolvedFilter(
                    table_alias="c", column_name="CustomerCID", operator="=", value="ASA"
                ),
            ],
            applied_rules=[
                "c.VersionTermDate IS NULL",
                "ISNULL(c.DeletedFlag, 0) = 0",
                "c.VoidedDate IS NULL",
                "a_top.AccLevelConfig = 0",
                "a_top.ParentAccID IS NULL",
                "a_sub.AccLevelConfig = 1",
                "a_sub.ParentAccID IS NOT NULL",
            ]
        )
        # Verify structure matches Section 9.3 golden example
        assert sq.app_id == "ABC_app"
        assert sq.top_rows is None
        assert len(sq.tables) == 4
        assert len(sq.columns) == 3
        assert len(sq.joins) == 3
        assert len(sq.filters) == 1
        assert len(sq.applied_rules) == 7
        assert sq.columns[1].output_alias == "TopAccName"
        assert sq.columns[2].output_alias == "SubAccName"
        assert sq.filters[0].value == "ASA"


# ---------------------------------------------------------------------------
# Q1-Q9 — QueryContext
# ---------------------------------------------------------------------------

class TestQueryContext:

    def test_builds_with_required_fields_only(self):
        """Q1 — QueryContext builds with only nl_query_original provided."""
        ctx = QueryContext(nl_query_original="give me customers in ABC")
        assert ctx.nl_query_original == "give me customers in ABC"

    def test_auto_generates_request_id(self):
        """Q2 — QueryContext auto-generates a request_id when not provided."""
        ctx = QueryContext(nl_query_original="give me customers in ABC")
        assert ctx.request_id is not None
        assert isinstance(ctx.request_id, str)
        assert len(ctx.request_id) > 0

    def test_accepts_explicit_request_id(self):
        """Q2 — QueryContext accepts an explicitly provided request_id."""
        ctx = QueryContext(
            request_id="my-custom-id",
            nl_query_original="give me customers in ABC"
        )
        assert ctx.request_id == "my-custom-id"

    def test_optional_fields_default_to_none(self):
        """Q3 — Optional fields default to None."""
        ctx = QueryContext(nl_query_original="give me customers in ABC")
        assert ctx.intent_output is None
        assert ctx.mapping_output is None
        assert ctx.structured_query is None
        assert ctx.sql is None
        assert ctx.nl_query_corrected is None
        assert ctx.error is None

    def test_list_fields_default_to_empty_lists(self):
        """Q4 — List fields default to empty lists, not None."""
        ctx = QueryContext(nl_query_original="give me customers in ABC")
        assert ctx.resolved_tables == []
        assert ctx.resolved_columns == []
        assert ctx.resolved_filters == []
        assert ctx.resolved_joins == []
        assert ctx.applied_rules == []
        assert ctx.warnings == []

    def test_status_defaults_to_pending(self):
        """Q5 — QueryContext.status defaults to 'pending'."""
        ctx = QueryContext(nl_query_original="give me customers in ABC")
        assert ctx.status == "pending"

    def test_dict_fields_default_to_empty_dicts(self):
        """Q6 — latency_ms and token_usage default to empty dicts."""
        ctx = QueryContext(nl_query_original="give me customers in ABC")
        assert ctx.latency_ms == {}
        assert ctx.token_usage == {}

    def test_accepts_structured_query(self):
        """Q7 — QueryContext accepts a StructuredQuery on structured_query field."""
        sq = StructuredQuery(app_id="ABC_app")
        ctx = QueryContext(nl_query_original="give me customers in ABC")
        ctx.structured_query = sq
        assert ctx.structured_query is not None
        assert ctx.structured_query.app_id == "ABC_app"

    def test_nl_query_original_raises_on_reassignment(self):
        """Q8 — Reassigning nl_query_original after creation raises AttributeError."""
        ctx = QueryContext(nl_query_original="give me customers in ABC")
        with pytest.raises(AttributeError):
            ctx.nl_query_original = "something else"

    def test_nl_query_original_error_message_is_clear(self):
        """Q8 — AttributeError message explains why the field is immutable."""
        ctx = QueryContext(nl_query_original="give me customers in ABC")
        with pytest.raises(AttributeError, match="immutable"):
            ctx.nl_query_original = "something else"

    def test_other_fields_are_still_mutable(self):
        """Q8 — Only nl_query_original is protected; other fields can be updated."""
        ctx = QueryContext(nl_query_original="give me customers in ABC")
        ctx.status = "success"
        ctx.app_id = "ABC_app"
        ctx.sql = "SELECT TOP 10000 ..."
        assert ctx.status == "success"
        assert ctx.app_id == "ABC_app"
        assert ctx.sql == "SELECT TOP 10000 ..."

    def test_request_id_is_valid_uuid_format(self):
        """Q9 — Auto-generated request_id is a valid UUID string."""
        ctx = QueryContext(nl_query_original="give me customers in ABC")
        # uuid.UUID() raises ValueError if the string is not a valid UUID
        parsed = uuid.UUID(ctx.request_id)
        assert str(parsed) == ctx.request_id

    def test_two_contexts_get_different_request_ids(self):
        """Q9 — Each QueryContext gets a unique auto-generated request_id."""
        ctx1 = QueryContext(nl_query_original="query one")
        ctx2 = QueryContext(nl_query_original="query two")
        assert ctx1.request_id != ctx2.request_id
