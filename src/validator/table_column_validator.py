# src/validator/table_column_validator.py
# V0 - Initial implementation
# V1 - Story 5.9 (Bug #13): Drop phantom DUPLICATE table entries.
#      When the LLM emits the same table more than once, each duplicate's source
#      must match a table synonym/display name OR a hierarchy synonym (via the
#      shared synonym_matching module). Duplicates matching neither are phantoms
#      (e.g. a column name like 'accKey' emitted as a second table) and are dropped
#      with a warning. If ALL duplicates of a table are phantom, the FIRST is kept
#      so a needed table is never fully removed. Single-instance tables are NEVER
#      scrutinised — their source is left untouched (protects legitimate column-ish
#      sources like 'customer name'). Cleanup runs after junction/invalid-name checks,
#      before resolved_tables is stored.
#      KNOWN LIMITATION (Bug #14, Phase 2): a fused-word duplicate (e.g. 'subaccount')
#      matches no synonym and would be dropped even if legitimate — deferred.
# V2 - Story 5.9 (Bug #15): Validate and pass through user FILTERS.
#      Previously the validator handled only tables and columns; llm_output['filters']
#      was never copied into context.resolved_filters, so every user filter (e.g.
#      CustomerCID = 'ASA') was silently lost and never reached the WHERE clause.
#      New Stage 3 validates each filter the same way columns are validated (table
#      must be in proposed tables; column must exist on that table) and stores the
#      full dicts in context.resolved_filters. Filter failures raise
#      NoRelevantColumnsError (same hard-fail as columns). resolved_filters added to
#      the VALIDATION_RESULT log payload.
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
from src.validator.synonym_matching import (
    match_table_reference,
    match_hierarchy_role,
)



# ---------------------------------------------------------------------------
# Phantom duplicate cleanup  [Bug #13]
# ---------------------------------------------------------------------------

def _drop_phantom_duplicates(
    proposed_tables: list[dict],
    table_lookup: dict,
    context: QueryContext,
) -> list[dict]:
    """
    Remove phantom duplicate table entries from proposed_tables.

    Rules:
      - A table appearing exactly once is kept as-is (never scrutinised).
      - For a table appearing 2+ times, each occurrence's source must match a
        table synonym / display name OR a hierarchy synonym. Occurrences matching
        neither are phantoms and are dropped, with a warning appended to
        context.warnings.
      - If EVERY occurrence of a duplicated table is a phantom, the FIRST
        occurrence is kept (so a needed table is never fully removed).

    Order of surviving entries is preserved.

    Args:
        proposed_tables: The LLM's table list (already passed junction/name checks).
        table_lookup:    table_name -> TableSchema.
        context:         Pipeline state; warnings are appended here.

    Returns:
        The cleaned list of table entry dicts.
    """
    # Count occurrences per table name
    counts: dict[str, int] = {}
    for entry in proposed_tables:
        t = entry.get("table", "")
        counts[t] = counts.get(t, 0) + 1

    # Track, per duplicated table, whether we have kept at least one occurrence
    kept_any: dict[str, bool] = {}
    # Pre-scan: does each duplicated table have at least one matching occurrence?
    has_match: dict[str, bool] = {}
    for entry in proposed_tables:
        t_name = entry.get("table", "")
        if counts[t_name] <= 1:
            continue
        if has_match.get(t_name):
            continue
        t_schema = table_lookup.get(t_name)
        source = entry.get("source", "")
        if t_schema is not None and (
            match_table_reference(source, t_schema)
            or match_hierarchy_role(source, t_schema) is not None
        ):
            has_match[t_name] = True

    cleaned: list[dict] = []
    for entry in proposed_tables:
        t_name = entry.get("table", "")

        # Single-instance tables: never scrutinised
        if counts[t_name] <= 1:
            cleaned.append(entry)
            continue

        # Duplicated table — scrutinise this occurrence's source
        t_schema = table_lookup.get(t_name)
        source = entry.get("source", "")
        matches = t_schema is not None and (
            match_table_reference(source, t_schema)
            or match_hierarchy_role(source, t_schema) is not None
        )

        if matches:
            cleaned.append(entry)
            kept_any[t_name] = True
            continue

        # Phantom occurrence (source matches nothing)
        if not has_match.get(t_name) and not kept_any.get(t_name):
            # No occurrence of this table matches anything — keep the FIRST one
            # so the table is not fully removed, then treat the rest as phantom.
            cleaned.append(entry)
            kept_any[t_name] = True
            context.warnings.append(
                f"Table '{t_name}' appeared multiple times but no occurrence "
                f"matched a table or hierarchy synonym. Kept the first occurrence "
                f"(source '{source}') and dropped the rest."
            )
            continue

        # Drop this phantom occurrence
        context.warnings.append(
            f"Dropped phantom duplicate table entry '{t_name}' (source "
            f"'{source}') — source matched no table or hierarchy synonym. "
            f"Likely a column reference emitted as a table."
        )

    return cleaned


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
        context.resolved_filters — validated filter dicts (full, with source) [V2]
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
    proposed_filters: list[dict] = context.llm_output.get("filters", [])

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

    # ------------------------------------------------------------------
    # Bug #13 — drop phantom DUPLICATE table entries
    # A table appearing more than once is only a real (self-join) instance if
    # each occurrence's source matches a table synonym/display name OR a
    # hierarchy synonym. Occurrences matching neither are phantoms (e.g. the
    # LLM emitting column phrase 'accKey' as a second Major.Acc table entry).
    # Single-instance tables are never scrutinised.
    # ------------------------------------------------------------------
    cleaned_tables = _drop_phantom_duplicates(
        proposed_tables, table_lookup, context
    )

    # Store full dicts (preserves source for join resolver)
    context.resolved_tables = cleaned_tables

    # Build set of proposed table names for column validation below
    # (use the cleaned list so a column can still attach to a surviving instance)
    proposed_table_name_set: set[str] = {
        entry["table"] for entry in cleaned_tables
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
    # Stage 3 — Validate filters  [Bug #15]
    # Mirrors column validation: each filter's table must be among the proposed
    # tables, and its column must exist on that table. Filter-only tables are
    # fine — they are validated against the same proposed_table_name_set, which
    # is built from the tables list (the LLM includes filter-only tables there).
    # ------------------------------------------------------------------
    invalid_filters: list[str] = []

    for entry in proposed_filters:
        filt_table = entry.get("table", "")
        filt_column = entry.get("column", "")

        # Filter's table must have been proposed
        if filt_table not in proposed_table_name_set:
            invalid_filters.append(
                f"{filt_table}.{filt_column} "
                f"(table '{filt_table}' was not in proposed tables)"
            )
            continue

        # Filter's column must exist on its table in the schema
        table_schema = table_lookup.get(filt_table)
        if table_schema is None:
            invalid_filters.append(
                f"{filt_table}.{filt_column} (table '{filt_table}' not in schema)"
            )
            continue

        column_names = {col.name for col in table_schema.columns}
        if filt_column not in column_names:
            invalid_filters.append(
                f"{filt_table}.{filt_column} "
                f"(column '{filt_column}' not found on '{filt_table}')"
            )

    if invalid_filters:
        raise NoRelevantColumnsError(
            message=(
                f"LLM proposed filter(s) referencing invalid table/column in schema "
                f"'{context.app_id}': {invalid_filters}."
            )
        )

    # All filters passed — store full dicts (preserves source, operator, value)
    context.resolved_filters = list(proposed_filters)

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
                "resolved_filters": context.resolved_filters,
            },
        )
    )

    return context
