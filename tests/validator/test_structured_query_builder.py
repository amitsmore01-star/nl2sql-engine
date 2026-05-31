# tests/validator/test_structured_query_builder.py
# V0 - Initial implementation
# V1 - Story 5.9 (Bug #12): Added class E -- TestSingleInstanceFallback (SB-1 to SB-5)
#
# Test scenarios:
#
# A -- Happy path (single table)
#   A1: Single table, two columns, no joins, no filters, no rules — baseline
#
# B -- Happy path (multi-table)
#   B1: Two tables, columns from each, one join, one filter — full happy path
#   B2: applied_rules copied across to StructuredQuery.applied_rules
#   B3: llm_output["limit"] populated -> top_rows set correctly
#   B4: llm_output["limit"] is None   -> top_rows is None
#
# C -- Self-join alias resolution
#   C1: Self-join — columns mapped to correct aliases (a_top, a_sub)
#   C2: Self-join — filter mapped to correct alias
#   C3: Self-join — column role is None on self-join table -> StructuredQueryBuildError
#   C4: Self-join — filter role is None on self-join table -> StructuredQueryBuildError
#
# D -- Context and logging
#   D1: context.structured_query populated and context.status = "success" on clean run
#   D2: STRUCTURED_QUERY_BUILT log emitted with correct payload on success
#   D3: Error logged to STRUCTURED_QUERY_BUILT before raising on ambiguous self-join

import pytest

from src.core.exceptions import StructuredQueryBuildError
from src.core.models import QueryContext, StructuredQuery
from src.validator.structured_query_builder import run_structured_query_builder


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_context(
    tables: list,
    columns: list,
    joins: list = None,
    filters: list = None,
    applied_rules: list = None,
    limit=None,
    query: str = "test query",
) -> QueryContext:
    ctx = QueryContext(
        nl_query_original=query,
        app_id="ABC_app",
        app_schema_version="1.0",
    )
    ctx.resolved_tables = tables
    ctx.resolved_columns = columns
    ctx.resolved_joins = joins or []
    ctx.resolved_filters = filters or []
    ctx.applied_rules = applied_rules or []
    ctx.llm_output = {
        "tables": [],
        "columns": [],
        "filters": [],
        "limit": limit,
        "aggregation": None,
        "sort": [],
    }
    return ctx


# ---------------------------------------------------------------------------
# A -- Happy path (single table)
# ---------------------------------------------------------------------------

class TestSingleTable:

    def test_A1_single_table_two_columns(self, capturing_logger):
        """A1: Single table, two columns, no joins, no filters, no rules."""
        ctx = _make_context(
            tables=[{"table": "Major.Customer", "source": "customer", "alias": "c"}],
            columns=[
                {"table": "Major.Customer", "column": "CustomerName", "source": "customer name"},
                {"table": "Major.Customer", "column": "CustomerCID",  "source": "customer id"},
            ],
        )
        result = run_structured_query_builder(ctx, capturing_logger)

        sq: StructuredQuery = result.structured_query
        assert sq is not None
        assert sq.app_id == "ABC_app"

        assert len(sq.tables) == 1
        assert sq.tables[0].table_name == "Major.Customer"
        assert sq.tables[0].alias == "c"

        assert len(sq.columns) == 2
        assert sq.columns[0].table_alias == "c"
        assert sq.columns[0].column_name == "CustomerName"
        assert sq.columns[0].output_alias == "CustomerName"
        assert sq.columns[1].column_name == "CustomerCID"

        assert sq.joins == []
        assert sq.filters == []
        assert sq.applied_rules == []


# ---------------------------------------------------------------------------
# B -- Happy path (multi-table)
# ---------------------------------------------------------------------------

class TestMultiTable:

    def test_B1_two_tables_join_and_filter(self, capturing_logger):
        """B1: Two tables, columns from each, one join, one filter."""
        ctx = _make_context(
            tables=[
                {"table": "Major.Customer",             "source": "customer",      "alias": "c"},
                {"table": "Major.CustomerDemographics", "source": "customer name", "alias": "cd"},
            ],
            columns=[
                {"table": "Major.Customer",             "column": "CustomerCID",  "source": "customer id"},
                {"table": "Major.CustomerDemographics", "column": "CustomerName", "source": "customer name"},
            ],
            joins=[{
                "join_type": "INNER JOIN",
                "table_name": "Major.CustomerDemographics",
                "alias": "cd",
                "on_conditions": [{"left": "c.CustomerID", "right": "cd.CustomerID"}],
            }],
            filters=[{
                "table": "Major.Customer",
                "column": "CustomerCID",
                "operator": "=",
                "value": "ASA",
                "source": "customer ASA",
            }],
        )
        result = run_structured_query_builder(ctx, capturing_logger)

        sq = result.structured_query
        assert len(sq.tables) == 2
        assert len(sq.columns) == 2
        assert len(sq.joins) == 1
        assert len(sq.filters) == 1

        # Join shape
        join = sq.joins[0]
        assert join.join_type == "INNER JOIN"
        assert join.table_name == "Major.CustomerDemographics"
        assert join.alias == "cd"
        assert join.on_conditions == [{"left": "c.CustomerID", "right": "cd.CustomerID"}]

        # Filter shape
        f = sq.filters[0]
        assert f.table_alias == "c"
        assert f.column_name == "CustomerCID"
        assert f.operator == "="
        assert f.value == "ASA"

        # Column alias lookup
        col_cd = next(c for c in sq.columns if c.column_name == "CustomerName")
        assert col_cd.table_alias == "cd"

    def test_B2_applied_rules_copied(self, capturing_logger):
        """B2: applied_rules from context land in StructuredQuery.applied_rules."""
        ctx = _make_context(
            tables=[{"table": "Major.Customer", "source": "customer", "alias": "c"}],
            columns=[{"table": "Major.Customer", "column": "CustomerCID", "source": "id"}],
            applied_rules=["c.VersionTermDate IS NULL", "ISNULL(c.DeletedFlag, 0) = 0"],
        )
        result = run_structured_query_builder(ctx, capturing_logger)

        sq = result.structured_query
        assert sq.applied_rules == ["c.VersionTermDate IS NULL", "ISNULL(c.DeletedFlag, 0) = 0"]

    def test_B3_limit_set(self, capturing_logger):
        """B3: llm_output["limit"] = 10 -> StructuredQuery.top_rows = 10."""
        ctx = _make_context(
            tables=[{"table": "Major.Customer", "source": "customer", "alias": "c"}],
            columns=[{"table": "Major.Customer", "column": "CustomerCID", "source": "id"}],
            limit=10,
        )
        result = run_structured_query_builder(ctx, capturing_logger)
        assert result.structured_query.top_rows == 10

    def test_B4_limit_none(self, capturing_logger):
        """B4: llm_output["limit"] = None -> StructuredQuery.top_rows = None."""
        ctx = _make_context(
            tables=[{"table": "Major.Customer", "source": "customer", "alias": "c"}],
            columns=[{"table": "Major.Customer", "column": "CustomerCID", "source": "id"}],
            limit=None,
        )
        result = run_structured_query_builder(ctx, capturing_logger)
        assert result.structured_query.top_rows is None


# ---------------------------------------------------------------------------
# C -- Self-join alias resolution
# ---------------------------------------------------------------------------

class TestSelfJoin:

    def _self_join_context(self, capturing_logger=None) -> QueryContext:
        """
        Shared context for self-join tests.
        Customer + Acc(top) + Acc(sub).
        Columns from both Acc instances.
        Filter on top Acc.
        """
        return _make_context(
            tables=[
                {"table": "Major.Customer", "source": "customer",  "alias": "c"},
                {"table": "Major.Acc",      "source": "top acc",   "alias": "a_top", "role": "top_Acc"},
                {"table": "Major.Acc",      "source": "sub acc",   "alias": "a_sub", "role": "sub_Acc"},
            ],
            columns=[
                {"table": "Major.Customer", "column": "CustomerCID", "source": "customer"},
                {"table": "Major.Acc",      "column": "AccName",     "source": "top acc name",  "role": "top_Acc"},
                {"table": "Major.Acc",      "column": "AccName",     "source": "sub acc name",  "role": "sub_Acc"},
            ],
            joins=[
                {
                    "join_type": "INNER JOIN",
                    "table_name": "Major.Acc",
                    "alias": "a_top",
                    "on_conditions": [{"left": "c.CustomerID", "right": "a_top.CustomerID"}],
                },
                {
                    "join_type": "INNER JOIN",
                    "table_name": "Major.Acc",
                    "alias": "a_sub",
                    "on_conditions": [
                        {"left": "a_top.AccID",   "right": "a_sub.ParentAccID"},
                        {"left": "c.CustomerID",  "right": "a_sub.CustomerID"},
                    ],
                },
            ],
            filters=[{
                "table": "Major.Acc",
                "column": "AccCID",
                "operator": "=",
                "value": "TOP1",
                "source": "top acc TOP1",
                "role": "top_Acc",
            }],
            query="give me top acc and sub acc for customer ASA",
        )

    def test_C1_columns_mapped_to_correct_aliases(self, capturing_logger):
        """C1: Self-join columns mapped to a_top and a_sub correctly."""
        ctx = self._self_join_context()
        result = run_structured_query_builder(ctx, capturing_logger)

        sq = result.structured_query
        acc_cols = [c for c in sq.columns if c.column_name == "AccName"]
        assert len(acc_cols) == 2

        aliases = {c.table_alias for c in acc_cols}
        assert "a_top" in aliases
        assert "a_sub" in aliases

    def test_C2_filter_mapped_to_correct_alias(self, capturing_logger):
        """C2: Self-join filter mapped to a_top (not a_sub)."""
        ctx = self._self_join_context()
        result = run_structured_query_builder(ctx, capturing_logger)

        sq = result.structured_query
        assert len(sq.filters) == 1
        assert sq.filters[0].table_alias == "a_top"
        assert sq.filters[0].column_name == "AccCID"
        assert sq.filters[0].value == "TOP1"

    def test_C3_column_role_none_on_self_join_raises(self, capturing_logger):
        """C3: Column on self-join table with role=None -> StructuredQueryBuildError."""
        ctx = _make_context(
            tables=[
                {"table": "Major.Acc", "source": "top acc", "alias": "a_top", "role": "top_Acc"},
                {"table": "Major.Acc", "source": "sub acc", "alias": "a_sub", "role": "sub_Acc"},
            ],
            columns=[
                # role is None — source was too vague
                {"table": "Major.Acc", "column": "AccName", "source": "account name", "role": None},
            ],
        )
        with pytest.raises(StructuredQueryBuildError) as exc_info:
            run_structured_query_builder(ctx, capturing_logger)

        assert exc_info.value.code == "STRUCTURED_QUERY_BUILD_ERROR"
        assert "Major.Acc" in exc_info.value.message
        assert "AccName" in exc_info.value.message

    def test_C4_filter_role_none_on_self_join_raises(self, capturing_logger):
        """C4: Filter on self-join table with role=None -> StructuredQueryBuildError."""
        ctx = _make_context(
            tables=[
                {"table": "Major.Acc", "source": "top acc", "alias": "a_top", "role": "top_Acc"},
                {"table": "Major.Acc", "source": "sub acc", "alias": "a_sub", "role": "sub_Acc"},
            ],
            columns=[
                {"table": "Major.Acc", "column": "AccName", "source": "top acc name", "role": "top_Acc"},
            ],
            filters=[
                # role is None — vague source
                {"table": "Major.Acc", "column": "AccCID", "operator": "=", "value": "X",
                 "source": "account X", "role": None},
            ],
        )
        with pytest.raises(StructuredQueryBuildError) as exc_info:
            run_structured_query_builder(ctx, capturing_logger)

        assert exc_info.value.code == "STRUCTURED_QUERY_BUILD_ERROR"
        assert "AccCID" in exc_info.value.message


# ---------------------------------------------------------------------------
# D -- Context and logging
# ---------------------------------------------------------------------------

class TestContextAndLogging:

    def test_D1_status_and_structured_query_set(self, capturing_logger):
        """D1: context.structured_query populated and status = 'success'."""
        ctx = _make_context(
            tables=[{"table": "Major.Customer", "source": "customer", "alias": "c"}],
            columns=[{"table": "Major.Customer", "column": "CustomerCID", "source": "id"}],
        )
        result = run_structured_query_builder(ctx, capturing_logger)

        assert result.status == "success"
        assert result.structured_query is not None
        assert isinstance(result.structured_query, StructuredQuery)

    def test_D2_success_log_emitted(self, capturing_logger):
        """D2: STRUCTURED_QUERY_BUILT log emitted with correct payload on success."""
        ctx = _make_context(
            tables=[{"table": "Major.Customer", "source": "customer", "alias": "c"}],
            columns=[{"table": "Major.Customer", "column": "CustomerCID", "source": "id"}],
        )
        run_structured_query_builder(ctx, capturing_logger)

        assert len(capturing_logger.entries) == 1
        entry = capturing_logger.entries[0]
        assert entry.stage == "STRUCTURED_QUERY_BUILT"
        assert entry.payload["status"] == "success"
        assert "table_count" in entry.payload
        assert "column_count" in entry.payload

    def test_D3_error_logged_before_raising(self, capturing_logger):
        """D3: On StructuredQueryBuildError, error is logged before exception propagates."""
        ctx = _make_context(
            tables=[
                {"table": "Major.Acc", "source": "top acc", "alias": "a_top", "role": "top_Acc"},
                {"table": "Major.Acc", "source": "sub acc", "alias": "a_sub", "role": "sub_Acc"},
            ],
            columns=[
                {"table": "Major.Acc", "column": "AccName", "source": "account name", "role": None},
            ],
        )
        with pytest.raises(StructuredQueryBuildError):
            run_structured_query_builder(ctx, capturing_logger)

        # Log must have been emitted even though exception was raised
        assert len(capturing_logger.entries) == 1
        entry = capturing_logger.entries[0]
        assert entry.stage == "STRUCTURED_QUERY_BUILT"
        assert entry.payload["status"] == "failed"
        assert entry.payload["error_code"] == "STRUCTURED_QUERY_BUILD_ERROR"


# ---------------------------------------------------------------------------
# E -- Single-instance hierarchy fallback  [Story 5.9, Bug #12]
# ---------------------------------------------------------------------------
# When a hierarchy table appears ONCE, a column/filter whose role is None must
# still resolve to that table's single alias (no ambiguity). Self-join tables
# are unaffected — role=None there still raises StructuredQueryBuildError.
# Helpers return warnings (Option Y); the builder appends them to context.warnings.

class TestSingleInstanceFallback:

    def test_SB1_single_instance_column_with_role_resolves(self, capturing_logger):
        """SB-1: Single-instance Acc, column WITH role stamped -> resolves to a_top (regression)."""
        ctx = _make_context(
            tables=[
                {"table": "Major.Customer", "source": "customer", "alias": "c"},
                {"table": "Major.Acc", "source": "top acc", "alias": "a_top", "role": "top_Acc"},
            ],
            columns=[
                {"table": "Major.Acc", "column": "AccName", "source": "top acc name", "role": "top_Acc"},
            ],
            joins=[{
                "join_type": "INNER JOIN",
                "table_name": "Major.Customer",
                "alias": "c",
                "on_conditions": [{"left": "a_top.CustomerID", "right": "c.CustomerID"}],
            }],
        )
        result = run_structured_query_builder(ctx, capturing_logger)

        sq = result.structured_query
        col = next(c for c in sq.columns if c.column_name == "AccName")
        assert col.table_alias == "a_top"
        # No fallback fired -> no warnings
        assert result.warnings == []

    def test_SB2_single_instance_column_role_none_falls_back(self, capturing_logger):
        """SB-2: Single-instance Acc, column role=None -> falls back to a_top, warning logged."""
        ctx = _make_context(
            tables=[
                {"table": "Major.Customer", "source": "customer", "alias": "c"},
                {"table": "Major.Acc", "source": "top acc", "alias": "a_top", "role": "top_Acc"},
            ],
            columns=[
                {"table": "Major.Acc", "column": "AccName", "source": "top acc name", "role": "top_Acc"},
                # LLM dropped the hierarchy word -> role None
                {"table": "Major.Acc", "column": "AccID", "source": "accid", "role": None},
            ],
            joins=[{
                "join_type": "INNER JOIN",
                "table_name": "Major.Customer",
                "alias": "c",
                "on_conditions": [{"left": "a_top.CustomerID", "right": "c.CustomerID"}],
            }],
        )
        result = run_structured_query_builder(ctx, capturing_logger)

        sq = result.structured_query
        acc_id_col = next(c for c in sq.columns if c.column_name == "AccID")
        # Fallback resolved the empty alias to the one Acc instance
        assert acc_id_col.table_alias == "a_top"
        # Warning recorded for the fallback
        assert any("AccID" in w and "single instance" in w for w in result.warnings)

    def test_SB3_single_instance_filter_role_none_falls_back(self, capturing_logger):
        """SB-3: Single-instance Acc, filter role=None -> falls back to a_top, warning logged."""
        ctx = _make_context(
            tables=[
                {"table": "Major.Customer", "source": "customer", "alias": "c"},
                {"table": "Major.Acc", "source": "top acc", "alias": "a_top", "role": "top_Acc"},
            ],
            columns=[
                {"table": "Major.Acc", "column": "AccName", "source": "top acc name", "role": "top_Acc"},
            ],
            filters=[
                # vague source -> role None, but only one Acc instance exists
                {"table": "Major.Acc", "column": "AccKey", "operator": "=", "value": "K1",
                 "source": "acc K1", "role": None},
            ],
            joins=[{
                "join_type": "INNER JOIN",
                "table_name": "Major.Customer",
                "alias": "c",
                "on_conditions": [{"left": "a_top.CustomerID", "right": "c.CustomerID"}],
            }],
        )
        result = run_structured_query_builder(ctx, capturing_logger)

        sq = result.structured_query
        assert len(sq.filters) == 1
        assert sq.filters[0].table_alias == "a_top"
        assert sq.filters[0].column_name == "AccKey"
        assert any("AccKey" in w and "single instance" in w for w in result.warnings)

    def test_SB4_self_join_role_none_still_raises(self, capturing_logger):
        """SB-4: Self-join Acc, column role=None -> still raises (fallback must NOT apply)."""
        ctx = _make_context(
            tables=[
                {"table": "Major.Acc", "source": "top acc", "alias": "a_top", "role": "top_Acc"},
                {"table": "Major.Acc", "source": "sub acc", "alias": "a_sub", "role": "sub_Acc"},
            ],
            columns=[
                {"table": "Major.Acc", "column": "AccName", "source": "account name", "role": None},
            ],
        )
        with pytest.raises(StructuredQueryBuildError) as exc_info:
            run_structured_query_builder(ctx, capturing_logger)

        assert exc_info.value.code == "STRUCTURED_QUERY_BUILD_ERROR"
        assert "Major.Acc" in exc_info.value.message

    def test_SB5_non_hierarchy_single_table_resolves_normally(self, capturing_logger):
        """SB-5: Single non-hierarchy table column resolves via (table, None) — no fallback needed."""
        ctx = _make_context(
            tables=[{"table": "Major.Customer", "source": "customer", "alias": "c"}],
            columns=[{"table": "Major.Customer", "column": "CustomerCID", "source": "customer id"}],
        )
        result = run_structured_query_builder(ctx, capturing_logger)

        sq = result.structured_query
        assert sq.columns[0].table_alias == "c"
        # (Major.Customer, None) hit the composite lookup directly -> no fallback warning
        assert result.warnings == []
