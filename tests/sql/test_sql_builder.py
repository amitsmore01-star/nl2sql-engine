# tests/sql/test_sql_builder.py
# V0 - Initial implementation
#
# Tests for run_sql_builder() in src/sql/sql_builder.py
#
# run_sql_builder() assembles SELECT + FROM/JOIN + WHERE into a final SQL string.
# It reads context.structured_query and writes context.sql.
#
# These tests build StructuredQuery objects directly — no LLM, no schema lookups.
# Uses a real StructuredLogger backed by a temp directory.

import pytest
from pathlib import Path
from unittest.mock import MagicMock

from src.core.models import (
    QueryContext,
    StructuredQuery,
    ResolvedTable,
    ResolvedColumn,
    ResolvedJoin,
    ResolvedFilter,
)
from src.sql.sql_builder import run_sql_builder
from src.config.settings import load_settings
from src.core.logging.logger import StructuredLogger


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_context(structured_query=None) -> QueryContext:
    """Build a minimal QueryContext with optional structured_query."""
    ctx = QueryContext(
        user_id="test_user",
        app_id="ABC_app",
        app_schema_version="1.0",
        nl_query_original="give me customers in ABC",
    )
    ctx.structured_query = structured_query
    return ctx


def _minimal_structured_query() -> StructuredQuery:
    """
    A minimal StructuredQuery with one table, one column, one filter.
    Matches a simple 'give me customer CID for customer ASA in ABC' query.
    """
    return StructuredQuery(
        app_id="ABC_app",
        top_rows=None,   # None → SQL builder uses settings default (10000)
        tables=[
            ResolvedTable(table_name="Major.Customer", alias="c"),
        ],
        columns=[
            ResolvedColumn(
                table_alias="c",
                column_name="CustomerCID",
                output_alias="CustomerCID",
            ),
        ],
        joins=[],
        filters=[
            ResolvedFilter(
                table_alias="c",
                column_name="CustomerCID",
                operator="=",
                value="ASA",
            ),
        ],
        applied_rules=[],
    )


def _full_structured_query() -> StructuredQuery:
    """
    StructuredQuery with table + join + filter + applied_rule.
    Used for clause presence checks (SELECT, FROM, JOIN, WHERE).
    """
    return StructuredQuery(
        app_id="ABC_app",
        top_rows=None,
        tables=[
            ResolvedTable(table_name="Major.Customer", alias="c"),
            ResolvedTable(table_name="Major.CustomerDemographics", alias="cd"),
        ],
        columns=[
            ResolvedColumn(
                table_alias="cd",
                column_name="CustomerName",
                output_alias="CustomerName",
            ),
        ],
        joins=[
            ResolvedJoin(
                join_type="INNER JOIN",
                table_name="Major.CustomerDemographics",
                alias="cd",
                on_conditions=[
                    {"left": "c.CustomerID", "right": "cd.CustomerID"}
                ],
            ),
        ],
        filters=[
            ResolvedFilter(
                table_alias="c",
                column_name="CustomerCID",
                operator="=",
                value="ASA",
            ),
        ],
        applied_rules=["c.VersionTermDate IS NULL"],
    )


@pytest.fixture
def settings():
    return load_settings()


@pytest.fixture
def logger(settings, tmp_path) -> StructuredLogger:
    """StructuredLogger writing to a temp directory."""
    settings.logging.log_dir = str(tmp_path)
    settings.logging.log_archive_dir = str(tmp_path / "archive")
    return StructuredLogger(settings)


# ---------------------------------------------------------------------------
# S — SQL Builder tests
# ---------------------------------------------------------------------------

class TestSqlBuilder:

    def test_s1_sql_is_populated_after_run(self, settings, logger):
        """
        S1: context.sql is None before run, populated after run_sql_builder().
        """
        ctx = _make_context(_minimal_structured_query())
        assert ctx.sql is None   # pre-condition

        result = run_sql_builder(ctx, logger, settings)

        assert result.sql is not None
        assert len(result.sql) > 0

    def test_s2_output_contains_select_top(self, settings, logger):
        """
        S2: SQL output contains SELECT TOP when default_top_rows > 0.
        We set it explicitly here — test must not depend on config value.
        """
        settings.sql.default_top_rows = 10000
        ctx = _make_context(_minimal_structured_query())
        result = run_sql_builder(ctx, logger, settings)

        assert "SELECT TOP" in result.sql

    def test_s3_output_contains_from(self, settings, logger):
        """
        S3: SQL output contains FROM clause.
        """
        ctx = _make_context(_full_structured_query())
        result = run_sql_builder(ctx, logger, settings)

        assert "FROM" in result.sql

    def test_s4_output_contains_inner_join(self, settings, logger):
        """
        S4: SQL output contains INNER JOIN when joins are present.
        """
        ctx = _make_context(_full_structured_query())
        result = run_sql_builder(ctx, logger, settings)

        assert "INNER JOIN" in result.sql

    def test_s5_output_contains_where(self, settings, logger):
        """
        S5: SQL output contains WHERE clause when filters or rules are present.
        """
        ctx = _make_context(_full_structured_query())
        result = run_sql_builder(ctx, logger, settings)

        assert "WHERE" in result.sql

    def test_s6_status_is_success_after_clean_run(self, settings, logger):
        """
        S6: context.status = "success" after a clean run.
        """
        ctx = _make_context(_minimal_structured_query())
        result = run_sql_builder(ctx, logger, settings)

        assert result.status == "success"

    def test_s7_missing_structured_query_sets_failed_status(self, settings, logger):
        """
        S7: structured_query=None → status="failed", error code SQL_BUILD_ERROR.
        run_sql_builder() does not raise — it sets context.status="failed".
        """
        ctx = _make_context(structured_query=None)
        result = run_sql_builder(ctx, logger, settings)

        assert result.status == "failed"
        assert result.error is not None
        assert result.error["code"] == "SQL_BUILD_ERROR"
        assert result.sql is None
