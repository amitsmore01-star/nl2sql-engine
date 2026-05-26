# src/validator/table_column_validator.py
# V0 - Initial implementation
#
# Deterministic table and column validator.
# Validates every table and column proposed by the LLM against the loaded schema.
# Rejects anything that does not exist in the schema — no exceptions.
#
# Two callers (same function, zero duplication — architecture rule):
#   - src/pipeline/orchestrator.py       (full pipeline via POST /v1/query)
#   - src/api/tools/validator_tool.py    (Foundry tool via POST /v1/tools/validator)
#
# Validation order:
#   1. Tables first — every entry in llm_output.tables must match a real table name.
#      Junction tables are rejected even if they exist in the schema.
#      If any table fails → NoRelevantTablesError raised immediately.
#      Empty tables list → NoRelevantTablesError.
#   2. Columns second — only runs if all tables passed.
#      Every entry in llm_output.columns must name a column that exists on its table.
#      The column's table must also have been proposed in llm_output.tables.
#      If any column fails → NoRelevantColumnsError raised immediately.
#
# On success:
#   context.resolved_tables — full dicts from llm_output.tables that passed
#   context.resolved_columns — full dicts from llm_output.columns that passed
#   context.status = "success"
#   VALIDATION_RESULT log emitted

import time

from src.core.constants import VALIDATION_RESULT
from src.core.exceptions import NoRelevantColumnsError, NoRelevantTablesError
from src.core.logging.log_models import LogEntry
from src.core.logging.logger import StructuredLogger
from src.core.models import QueryContext
from src.schema.schema_repository import SchemaRepository
from src.schema.schema_models import AppSchema, TableSchema


def run_table_column_validator(
    context: QueryContext,
    schema_repo: SchemaRepository,
    logger: StructuredLogger,
) -> QueryContext:
    """
    Validate tables and columns from context.llm_output against the app schema.

    Reads:
        context.llm_output["tables"]  — list of {table, source}
        context.llm_output["columns"] — list of {table, column, source}
        context.app_id                — used to load the correct schema

    Writes (on success):
        context.resolved_tables  — validated table dicts (full, with source)
        context.resolved_columns — validated column dicts (full, with source)
        context.status = "success"

    Raises:
        NoRelevantTablesError:  Any proposed table not found in schema, or
                                is a junction table, or tables list is empty.
        NoRelevantColumnsError: Any proposed column not found on its table, or
                                column's table was not in proposed tables.

    Args:
        context:     Pipeline state. llm_output must be populated.
        schema_repo: Loaded schema repository.
        logger:      StructuredLogger for emitting VALIDATION_RESULT.

    Returns:
        Updated QueryContext with resolved_tables and resolved_columns populated.
    """
    start_ms = int(time.time() * 1000)

    app_schema: AppSchema = schema_repo.get_schema(context.app_id)

    # Build lookup: table_name → TableSchema for fast access
    # Only non-junction tables are valid targets for LLM proposals
    table_lookup: dict[str, TableSchema] = {
        t.name: t for t in app_schema.tables
    }
    valid_table_names: set[str] = {
        t.name for t in app_schema.tables if not t.is_junction_table
    }
    junction_table_names: set[str] = {
        t.name for t in app_schema.tables if t.is_junction_table
    }

    proposed_tables: list[dict] = context.llm_output.get("tables", [])
    proposed_columns: list[dict] = context.llm_output.get("columns", [])

    # ------------------------------------------------------------------
    # Stage 1 — Validate tables
    # ------------------------------------------------------------------
    if not proposed_tables:
        raise NoRelevantTablesError(
            message=(
                "LLM proposed no tables. At least one table is required to "
                "generate a SQL query."
            )
        )

    invalid_tables: list[str] = []
    junction_proposals: list[str] = []

    for entry in proposed_tables:
        table_name = entry.get("table", "")

        if table_name in junction_table_names:
            # Junction tables must never be proposed by the LLM —
            # they are auto-bridged by the join resolver.
            junction_proposals.append(table_name)
        elif table_name not in valid_table_names:
            invalid_tables.append(table_name)

    if junction_proposals:
        raise NoRelevantTablesError(
            message=(
                f"LLM proposed junction table(s) which are not user-facing: "
                f"{junction_proposals}. Junction tables are auto-resolved by "
                f"the join resolver — they must never appear in LLM output."
            )
        )

    if invalid_tables:
        raise NoRelevantTablesError(
            message=(
                f"LLM proposed table(s) not found in schema '{context.app_id}': "
                f"{invalid_tables}. "
                f"Valid tables: {sorted(valid_table_names)}"
            )
        )

    # All tables passed — store full dicts (preserves source for join resolver)
    context.resolved_tables = list(proposed_tables)

    # Build set of proposed table names for column validation below
    proposed_table_name_set: set[str] = {
        entry["table"] for entry in proposed_tables
    }

    # ------------------------------------------------------------------
    # Stage 2 — Validate columns
    # ------------------------------------------------------------------
    invalid_columns: list[str] = []

    for entry in proposed_columns:
        col_table = entry.get("table", "")
        col_name = entry.get("column", "")

        # Column's table must have been proposed
        if col_table not in proposed_table_name_set:
            invalid_columns.append(
                f"{col_table}.{col_name} "
                f"(table '{col_table}' was not in proposed tables)"
            )
            continue

        # Column must exist on its table in the schema
        table_schema = table_lookup.get(col_table)
        if table_schema is None:
            invalid_columns.append(
                f"{col_table}.{col_name} (table '{col_table}' not in schema)"
            )
            continue

        column_names = {col.name for col in table_schema.columns}
        if col_name not in column_names:
            invalid_columns.append(
                f"{col_table}.{col_name} "
                f"(column '{col_name}' not found on '{col_table}')"
            )

    if invalid_columns:
        raise NoRelevantColumnsError(
            message=(
                f"LLM proposed column(s) not found in schema '{context.app_id}': "
                f"{invalid_columns}."
            )
        )

    # All columns passed — store full dicts (preserves source and table info)
    context.resolved_columns = list(proposed_columns)

    # ------------------------------------------------------------------
    # Success — emit log and return
    # ------------------------------------------------------------------
    elapsed_ms = int(time.time() * 1000) - start_ms
    context.latency_ms["table_column_validator"] = elapsed_ms
    context.status = "success"

    logger.log(
        LogEntry(
            stage=VALIDATION_RESULT,
            request_id=context.request_id,
            user_id=context.user_id,
            app_id=context.app_id,
            app_schema_version=context.app_schema_version,
            latency_ms=elapsed_ms,
            payload={
                "resolved_tables": context.resolved_tables,
                "resolved_columns": context.resolved_columns,
            },
        )
    )

    return context
