# tests/validator/test_table_column_validator.py
# V0 - Initial implementation
#
# Tests for run_table_column_validator() in src/validator/table_column_validator.py
#
# What this function does:
#   Reads context.llm_output.tables and context.llm_output.columns.
#   Validates each against the real ABC_app.json schema.
#   Raises NoRelevantTablesError or NoRelevantColumnsError on any mismatch.
#   On success, populates context.resolved_tables and context.resolved_columns
#   with the full dicts (including source field) from llm_output.
#
# Test groups:
#   A — Table validation: happy path
#   B — Table validation: failure path
#   C — Column validation: happy path
#   D — Column validation: failure path
#   E — Stage ordering and logging
#
# Real ABC_app.json schema is used throughout — no mocking of schema data.
# StructuredLogger is built with real settings loaded from YAML + env vars.

import pytest

from src.core.exceptions import NoRelevantColumnsError, NoRelevantTablesError
from src.core.models import QueryContext
from src.validator.table_column_validator import run_table_column_validator


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_context(tables: list[dict], columns: list[dict], filters: list[dict] = None) -> QueryContext:
    """
    Build a QueryContext with llm_output populated for the given tables + columns.
    app_id points to the real ABC_app schema loaded in the fixture.
    """
    return QueryContext(
        nl_query_original="give me customer name for customer ASA in ABC",
        app_id="ABC_app",
        app_schema_version="1.0",
        user_id="test-user",
        llm_output={
            "tables": tables,
            "columns": columns,
            "filters": filters or [],
            "limit": None,
            "aggregation": None,
            "sort": [],
        },
    )


# ---------------------------------------------------------------------------
# Group A — Table validation: happy path
# ---------------------------------------------------------------------------

class TestTableValidationHappyPath:
    """Valid table proposals are accepted and stored in resolved_tables."""

    def test_a1_single_valid_table_passes(
        self, abc_schema_repo, test_logger
    ):
        """
        Single valid table 'Major.Customer' → passes validation.
        resolved_tables contains the full dict with table and source.
        """
        tables = [{"table": "Major.Customer", "source": "customer"}]
        context = make_context(tables=tables, columns=[])

        result = run_table_column_validator(context, abc_schema_repo, test_logger)

        assert len(result.resolved_tables) == 1
        assert result.resolved_tables[0]["table"] == "Major.Customer"
        assert result.resolved_tables[0]["source"] == "customer"

    def test_a2_multiple_valid_tables_all_stored(
        self, abc_schema_repo, test_logger
    ):
        """
        Two valid tables → both stored in resolved_tables, order preserved.
        """
        tables = [
            {"table": "Major.Customer", "source": "customer"},
            {"table": "Major.CustomerDemographics", "source": "customer name"},
        ]
        context = make_context(tables=tables, columns=[])

        result = run_table_column_validator(context, abc_schema_repo, test_logger)

        assert len(result.resolved_tables) == 2
        names = [e["table"] for e in result.resolved_tables]
        assert "Major.Customer" in names
        assert "Major.CustomerDemographics" in names

    def test_a3_duplicate_table_for_self_join_both_preserved(
        self, abc_schema_repo, test_logger
    ):
        """
        Major.Acc appears twice (top acc + sub acc self-join).
        Both entries must be preserved in resolved_tables — source differs.
        Join resolver needs both to assign hierarchy roles.
        """
        tables = [
            {"table": "Major.Acc", "source": "top acc"},
            {"table": "Major.Acc", "source": "sub acc"},
        ]
        context = make_context(tables=tables, columns=[])

        result = run_table_column_validator(context, abc_schema_repo, test_logger)

        assert len(result.resolved_tables) == 2
        sources = [e["source"] for e in result.resolved_tables]
        assert "top acc" in sources
        assert "sub acc" in sources

    def test_a4_junction_table_proposed_raises_no_relevant_tables(
        self, abc_schema_repo, test_logger
    ):
        """
        Major.PackagePlan is a junction table — LLM must never propose it.
        Validator rejects it even though it exists in the schema.
        """
        tables = [{"table": "Major.PackagePlan", "source": "package plan"}]
        context = make_context(tables=tables, columns=[])

        with pytest.raises(NoRelevantTablesError) as exc_info:
            run_table_column_validator(context, abc_schema_repo, test_logger)

        assert exc_info.value.code == "NO_RELEVANT_TABLES"
        assert "junction" in exc_info.value.message.lower()


# ---------------------------------------------------------------------------
# Group B — Table validation: failure path
# ---------------------------------------------------------------------------

class TestTableValidationFailurePath:
    """Invalid table proposals are rejected with NoRelevantTablesError."""

    def test_b1_single_invalid_table_raises(
        self, abc_schema_repo, test_logger
    ):
        """
        Table 'Major.Fake' not in schema → NoRelevantTablesError.
        Error message names the invalid table.
        """
        tables = [{"table": "Major.Fake", "source": "fake"}]
        context = make_context(tables=tables, columns=[])

        with pytest.raises(NoRelevantTablesError) as exc_info:
            run_table_column_validator(context, abc_schema_repo, test_logger)

        assert exc_info.value.code == "NO_RELEVANT_TABLES"
        assert "Major.Fake" in exc_info.value.message

    def test_b2_mix_of_valid_and_invalid_raises(
        self, abc_schema_repo, test_logger
    ):
        """
        One valid + one invalid table → raises NoRelevantTablesError.
        Any invalid table fails the whole stage.
        """
        tables = [
            {"table": "Major.Customer", "source": "customer"},
            {"table": "Major.Ghost", "source": "ghost"},
        ]
        context = make_context(tables=tables, columns=[])

        with pytest.raises(NoRelevantTablesError) as exc_info:
            run_table_column_validator(context, abc_schema_repo, test_logger)

        assert "Major.Ghost" in exc_info.value.message

    def test_b3_empty_tables_list_raises(
        self, abc_schema_repo, test_logger
    ):
        """
        Empty tables list → NoRelevantTablesError.
        Cannot build a SQL query with no tables.
        """
        context = make_context(tables=[], columns=[])

        with pytest.raises(NoRelevantTablesError) as exc_info:
            run_table_column_validator(context, abc_schema_repo, test_logger)

        assert exc_info.value.code == "NO_RELEVANT_TABLES"


# ---------------------------------------------------------------------------
# Group C — Column validation: happy path
# ---------------------------------------------------------------------------

class TestColumnValidationHappyPath:
    """Valid column proposals are accepted and stored in resolved_columns."""

    def test_c1_single_valid_column_passes(
        self, abc_schema_repo, test_logger
    ):
        """
        CustomerName on Major.CustomerDemographics → passes.
        resolved_columns contains full dict with table, column, source.
        """
        tables = [{"table": "Major.CustomerDemographics", "source": "customer name"}]
        columns = [
            {
                "table": "Major.CustomerDemographics",
                "column": "CustomerName",
                "source": "customer name",
            }
        ]
        context = make_context(tables=tables, columns=columns)

        result = run_table_column_validator(context, abc_schema_repo, test_logger)

        assert len(result.resolved_columns) == 1
        assert result.resolved_columns[0]["column"] == "CustomerName"
        assert result.resolved_columns[0]["table"] == "Major.CustomerDemographics"
        assert result.resolved_columns[0]["source"] == "customer name"

    def test_c2_multiple_columns_across_tables_all_stored(
        self, abc_schema_repo, test_logger
    ):
        """
        CustomerName (CustomerDemographics) + AccName (Acc) → both stored.
        """
        tables = [
            {"table": "Major.CustomerDemographics", "source": "customer name"},
            {"table": "Major.Acc", "source": "acc"},
        ]
        columns = [
            {
                "table": "Major.CustomerDemographics",
                "column": "CustomerName",
                "source": "customer name",
            },
            {
                "table": "Major.Acc",
                "column": "AccName",
                "source": "acc name",
            },
        ]
        context = make_context(tables=tables, columns=columns)

        result = run_table_column_validator(context, abc_schema_repo, test_logger)

        assert len(result.resolved_columns) == 2
        col_names = [e["column"] for e in result.resolved_columns]
        assert "CustomerName" in col_names
        assert "AccName" in col_names

    def test_c3_column_matched_by_exact_name_no_synonyms_needed(
        self, abc_schema_repo, test_logger
    ):
        """
        CustomerCID has synonyms but matching is by exact column name only.
        Proposing 'CustomerCID' directly must pass — no synonym lookup needed.
        """
        tables = [{"table": "Major.Customer", "source": "customer"}]
        columns = [
            {
                "table": "Major.Customer",
                "column": "CustomerCID",
                "source": "customer id",
            }
        ]
        context = make_context(tables=tables, columns=columns)

        result = run_table_column_validator(context, abc_schema_repo, test_logger)

        assert len(result.resolved_columns) == 1
        assert result.resolved_columns[0]["column"] == "CustomerCID"


# ---------------------------------------------------------------------------
# Group D — Column validation: failure path
# ---------------------------------------------------------------------------

class TestColumnValidationFailurePath:
    """Invalid column proposals are rejected with NoRelevantColumnsError."""

    def test_d1_column_not_on_table_raises(
        self, abc_schema_repo, test_logger
    ):
        """
        'FakeColumn' does not exist on Major.Customer → NoRelevantColumnsError.
        """
        tables = [{"table": "Major.Customer", "source": "customer"}]
        columns = [
            {
                "table": "Major.Customer",
                "column": "FakeColumn",
                "source": "fake",
            }
        ]
        context = make_context(tables=tables, columns=columns)

        with pytest.raises(NoRelevantColumnsError) as exc_info:
            run_table_column_validator(context, abc_schema_repo, test_logger)

        assert exc_info.value.code == "NO_RELEVANT_COLUMNS"
        assert "FakeColumn" in exc_info.value.message

    def test_d2_column_references_table_not_in_proposed_tables_raises(
        self, abc_schema_repo, test_logger
    ):
        """
        Column references Major.CustomerDemographics but only Major.Customer
        was proposed in tables → NoRelevantColumnsError.
        The column's table was never proposed.
        """
        tables = [{"table": "Major.Customer", "source": "customer"}]
        columns = [
            {
                "table": "Major.CustomerDemographics",
                "column": "CustomerName",
                "source": "customer name",
            }
        ]
        context = make_context(tables=tables, columns=columns)

        with pytest.raises(NoRelevantColumnsError) as exc_info:
            run_table_column_validator(context, abc_schema_repo, test_logger)

        assert exc_info.value.code == "NO_RELEVANT_COLUMNS"
        assert "Major.CustomerDemographics" in exc_info.value.message

    def test_d3_valid_table_wrong_column_raises(
        self, abc_schema_repo, test_logger
    ):
        """
        Major.Customer is valid but 'AccName' does not exist on it
        (AccName belongs to Major.Acc) → NoRelevantColumnsError.
        """
        tables = [{"table": "Major.Customer", "source": "customer"}]
        columns = [
            {
                "table": "Major.Customer",
                "column": "AccName",
                "source": "acc name",
            }
        ]
        context = make_context(tables=tables, columns=columns)

        with pytest.raises(NoRelevantColumnsError) as exc_info:
            run_table_column_validator(context, abc_schema_repo, test_logger)

        assert "AccName" in exc_info.value.message


# ---------------------------------------------------------------------------
# Group E — Stage ordering and logging
# ---------------------------------------------------------------------------

class TestStageOrderingAndLogging:
    """Table failure happens before column check. Log emitted on success."""

    def test_e1_table_failure_raised_before_column_check(
        self, abc_schema_repo, test_logger
    ):
        """
        Invalid table + valid column on that invalid table.
        NoRelevantTablesError raised before column validation runs.
        Error code must be NO_RELEVANT_TABLES, not NO_RELEVANT_COLUMNS.
        """
        tables = [{"table": "Major.Nonexistent", "source": "nonexistent"}]
        columns = [
            {
                "table": "Major.Nonexistent",
                "column": "SomeColumn",
                "source": "some",
            }
        ]
        context = make_context(tables=tables, columns=columns)

        with pytest.raises(NoRelevantTablesError) as exc_info:
            run_table_column_validator(context, abc_schema_repo, test_logger)

        assert exc_info.value.code == "NO_RELEVANT_TABLES"

    def test_e2_validation_result_log_emitted_on_success(
        self, abc_schema_repo, capturing_logger
    ):
        """
        On success, VALIDATION_RESULT log entry is emitted.
        Payload contains resolved_tables and resolved_columns.
        """
        tables = [{"table": "Major.Customer", "source": "customer"}]
        columns = [
            {
                "table": "Major.Customer",
                "column": "CustomerCID",
                "source": "customer id",
            }
        ]
        context = make_context(tables=tables, columns=columns)

        run_table_column_validator(context, abc_schema_repo, capturing_logger)

        assert len(capturing_logger.entries) == 1
        entry = capturing_logger.entries[0]
        assert entry.stage == "VALIDATION_RESULT"
        assert "resolved_tables" in entry.payload
        assert "resolved_columns" in entry.payload

    def test_e3_status_set_to_success_after_clean_run(
        self, abc_schema_repo, test_logger
    ):
        """
        context.status must be 'success' after a clean validation run.
        """
        tables = [{"table": "Major.Customer", "source": "customer"}]
        context = make_context(tables=tables, columns=[])

        result = run_table_column_validator(context, abc_schema_repo, test_logger)

        assert result.status == "success"


# ---------------------------------------------------------------------------
# Group F — Filter validation & pass-through  [Story 5.9, Bug #15]
# ---------------------------------------------------------------------------
# The validator must validate user filters (same rules as columns) and copy them
# into context.resolved_filters. Before V2 this never happened — filters were
# silently lost and never reached the WHERE clause.

class TestFilterValidation:

    def test_f1_valid_filter_passes_through(self, abc_schema_repo, capturing_logger):
        """F1: A valid filter (Customer.CustomerCID = ASA) lands in resolved_filters."""
        tables = [{"table": "Major.Customer", "source": "customer"}]
        columns = [{"table": "Major.Customer", "column": "CustomerCID", "source": "customer id"}]
        filters = [{
            "table": "Major.Customer", "column": "CustomerCID",
            "operator": "=", "value": "ASA", "source": "customer ASA",
        }]
        context = make_context(tables=tables, columns=columns, filters=filters)

        result = run_table_column_validator(context, abc_schema_repo, capturing_logger)

        assert len(result.resolved_filters) == 1
        f = result.resolved_filters[0]
        assert f["table"] == "Major.Customer"
        assert f["column"] == "CustomerCID"
        assert f["value"] == "ASA"

    def test_f2_filter_table_not_in_proposed_raises(self, abc_schema_repo, capturing_logger):
        """F2: Filter references a table not in proposed tables → NoRelevantColumnsError."""
        tables = [{"table": "Major.Customer", "source": "customer"}]
        columns = [{"table": "Major.Customer", "column": "CustomerCID", "source": "id"}]
        # Filter points at Major.Acc, which is NOT in proposed tables
        filters = [{
            "table": "Major.Acc", "column": "AccName",
            "operator": "=", "value": "X", "source": "acc X",
        }]
        context = make_context(tables=tables, columns=columns, filters=filters)

        with pytest.raises(NoRelevantColumnsError) as exc_info:
            run_table_column_validator(context, abc_schema_repo, capturing_logger)
        assert "Major.Acc" in exc_info.value.message

    def test_f3_filter_column_not_on_table_raises(self, abc_schema_repo, capturing_logger):
        """F3: Filter references a column that doesn't exist on its table → error."""
        tables = [{"table": "Major.Customer", "source": "customer"}]
        columns = [{"table": "Major.Customer", "column": "CustomerCID", "source": "id"}]
        filters = [{
            "table": "Major.Customer", "column": "NonExistentColumn",
            "operator": "=", "value": "X", "source": "whatever",
        }]
        context = make_context(tables=tables, columns=columns, filters=filters)

        with pytest.raises(NoRelevantColumnsError) as exc_info:
            run_table_column_validator(context, abc_schema_repo, capturing_logger)
        assert "NonExistentColumn" in exc_info.value.message

    def test_f4_no_filters_empty_list(self, abc_schema_repo, capturing_logger):
        """F4: No filters in llm_output → resolved_filters is empty, no error."""
        tables = [{"table": "Major.Customer", "source": "customer"}]
        columns = [{"table": "Major.Customer", "column": "CustomerCID", "source": "id"}]
        context = make_context(tables=tables, columns=columns)  # filters defaults to []

        result = run_table_column_validator(context, abc_schema_repo, capturing_logger)
        assert result.resolved_filters == []

    def test_f5_filter_only_table(self, abc_schema_repo, capturing_logger):
        """F5: A table present in tables + filter but with NO selected column → filter validates."""
        # Customer is the filter-only table; the selected column comes from Demographics.
        tables = [
            {"table": "Major.Customer", "source": "customer"},
            {"table": "Major.CustomerDemographics", "source": "customer name"},
        ]
        columns = [
            {"table": "Major.CustomerDemographics", "column": "CustomerName", "source": "customer name"},
        ]
        filters = [{
            "table": "Major.Customer", "column": "CustomerCID",
            "operator": "=", "value": "ASA", "source": "customer ASA",
        }]
        context = make_context(tables=tables, columns=columns, filters=filters)

        result = run_table_column_validator(context, abc_schema_repo, capturing_logger)

        assert len(result.resolved_filters) == 1
        assert result.resolved_filters[0]["table"] == "Major.Customer"

    def test_f6_log_includes_resolved_filters(self, abc_schema_repo, capturing_logger):
        """F6: VALIDATION_RESULT log payload includes resolved_filters."""
        tables = [{"table": "Major.Customer", "source": "customer"}]
        columns = [{"table": "Major.Customer", "column": "CustomerCID", "source": "id"}]
        filters = [{
            "table": "Major.Customer", "column": "CustomerCID",
            "operator": "=", "value": "ASA", "source": "customer ASA",
        }]
        context = make_context(tables=tables, columns=columns, filters=filters)

        run_table_column_validator(context, abc_schema_repo, capturing_logger)

        entry = capturing_logger.entries[0]
        assert "resolved_filters" in entry.payload
        assert len(entry.payload["resolved_filters"]) == 1
