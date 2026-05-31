# src/validator/structured_query_builder.py
# V0 - Initial implementation
# V1 - Story 5.9 (Bug #12): Single-instance hierarchy alias-resolution fallback.
#      Problem: a hierarchy table (e.g. Major.Acc) appearing ONCE got its role
#      stamped on the table entry (alias a_top, role top_Acc) but the LLM
#      sometimes dropped the hierarchy word from a column's source (e.g. "accid"
#      instead of "top acc id"), leaving that column with role=None. The old
#      (table, role) lookup then missed -> empty alias -> broken SQL ".AccID".
#      Fix: build a second lookup {table_name -> alias} for SINGLE-INSTANCE tables
#      only. When a column/filter (table, role) lookup misses AND the table is
#      single-instance, fall back to the one alias for that table (no ambiguity
#      possible — only one instance exists). A warning is recorded for each
#      fallback. Self-join tables are UNAFFECTED: role=None on a self-join table
#      still raises StructuredQueryBuildError (genuine ambiguity).
#      Helpers stay pure (Option Y): they return (models, warnings); the main
#      function appends warnings to context.warnings.
#
# Structured query builder.
# Translates the enriched QueryContext dicts (resolved_tables, resolved_columns,
# resolved_joins, resolved_filters, applied_rules, llm_output["limit"]) into a
# typed StructuredQuery Pydantic model.
#
# No LLM calls. No schema lookups. Pure translation — reads context, writes
# context.structured_query.
#
# Two callers (same function, zero duplication — architecture rule):
#   - src/pipeline/orchestrator.py       (full pipeline via POST /v1/query)
#   - src/api/tools/validator_tool.py    (Foundry tool via POST /v1/tools/validator)
#
# Alias resolution strategy:
#   Non-self-join tables: composite {(table_name, None) -> alias} lookup.
#   Self-join tables:     composite {(table_name, role) -> alias} lookup.
#   Single-instance fallback [V1]: {table_name -> alias} for tables appearing
#     exactly once. Used only when the composite lookup misses on a
#     single-instance table — there is exactly one alias, so it is unambiguous.
#   join_resolver stamps "role" onto column and filter entries for hierarchy
#   tables — so this builder uses exact (table, role) matching first, then the
#   single-instance fallback, then (for self-join misses) raises.
#
# Error handling:
#   StructuredQueryBuildError raised when a column or filter on a SELF-JOIN table
#   has role=None (source was too vague to match a hierarchy synonym).
#   Single-instance tables never raise — they use the fallback.
#   Error is logged to the log file before raising — log stage: STRUCTURED_QUERY_BUILT.
#   Orchestrator catches this and sets context.status = "failed".
#
# Output alias:
#   ResolvedColumn.output_alias defaults to the column name itself (Phase 1).
#   Phase 3: extend for user-specified aliases ("customer name as Name").

import time

from src.core.constants import STRUCTURED_QUERY_BUILT
from src.core.exceptions import StructuredQueryBuildError
from src.core.logging.log_models import LogEntry
from src.core.logging.logger import StructuredLogger
from src.core.models import (
    QueryContext,
    ResolvedColumn,
    ResolvedFilter,
    ResolvedJoin,
    ResolvedTable,
    StructuredQuery,
)


# ---------------------------------------------------------------------------
# Alias lookup builders
# ---------------------------------------------------------------------------

def _build_alias_lookup(resolved_tables: list[dict]) -> dict:
    """
    Build the composite alias lookup from resolved_tables entries.

    For non-self-join tables (no "role" key):
        key = (table_name, None)  -> alias

    For hierarchy tables ("role" key present):
        key = (table_name, role)  -> alias

    Using (table, role) as the composite key handles both cases uniformly.
    Entries without a role always key as (table, None).

    Example result:
        {
            ("Major.Customer", None):      "c",
            ("Major.Acc",      "top_Acc"): "a_top",
            ("Major.Acc",      "sub_Acc"): "a_sub",
        }
    """
    lookup: dict = {}
    for entry in resolved_tables:
        table_name = entry.get("table", "")
        role = entry.get("role")        # None when not stamped
        alias = entry.get("alias", "")
        lookup[(table_name, role)] = alias
    return lookup


def _build_single_instance_lookup(resolved_tables: list[dict]) -> dict:
    """
    Build a {table_name -> alias} lookup for SINGLE-INSTANCE tables only [V1].

    A single-instance table appears exactly once in resolved_tables, so there
    is only one possible alias for it. This lookup is the fallback used when the
    composite (table, role) lookup misses for such a table — typically because
    the LLM dropped the hierarchy word from a column/filter source, leaving its
    role=None while the table entry carries a role.

    Tables appearing more than once (self-joins) are deliberately EXCLUDED — for
    them the alias is genuinely ambiguous and must be resolved by role, never by
    a name-only fallback.

    Example result (Acc appears once with role top_Acc):
        { "Major.Acc": "a_top", "Major.Customer": "c" }
    """
    counts: dict[str, int] = {}
    for entry in resolved_tables:
        t = entry.get("table", "")
        counts[t] = counts.get(t, 0) + 1

    lookup: dict[str, str] = {}
    for entry in resolved_tables:
        table_name = entry.get("table", "")
        if counts.get(table_name, 0) == 1:
            lookup[table_name] = entry.get("alias", "")
    return lookup


# ---------------------------------------------------------------------------
# Column translation
# ---------------------------------------------------------------------------

def _build_resolved_columns(
    resolved_columns: list[dict],
    alias_lookup: dict,
    single_instance_lookup: dict,
    self_join_tables: set[str],
) -> tuple[list[ResolvedColumn], list[str]]:
    """
    Translate resolved_columns dicts into ResolvedColumn models.

    Resolution order for each column:
      1. If the table is a self-join table AND role is None — raise
         StructuredQueryBuildError (genuine ambiguity, cannot guess instance).
      2. Try the composite (table_name, role) lookup.
      3. [V1] If that misses AND the table is single-instance, fall back to the
         single-instance lookup (the one alias for that table) and record a
         warning string.
      4. output_alias defaults to column_name (Phase 1).

    Pure function (Option Y): returns (columns, warnings). The caller appends the
    warnings to context.warnings — this function never touches context.

    Args:
        resolved_columns:        List of column dicts from QueryContext.
        alias_lookup:            {(table_name, role) -> alias} composite lookup.
        single_instance_lookup:  {table_name -> alias} for single-instance tables.
        self_join_tables:        Set of table names appearing more than once.

    Returns:
        (list of ResolvedColumn in original order, list of warning strings)

    Raises:
        StructuredQueryBuildError: Column on a self-join table has role=None.
    """
    columns: list[ResolvedColumn] = []
    warnings: list[str] = []

    for entry in resolved_columns:
        table_name = entry.get("table", "")
        column_name = entry.get("column", "")
        role = entry.get("role")  # None for non-hierarchy / unmatched source

        # 1. Ambiguous self-join — cannot guess which instance
        if table_name in self_join_tables and role is None:
            raise StructuredQueryBuildError(
                message=(
                    f"Column '{table_name}.{column_name}' source "
                    f"'{entry.get('source', '')}' could not be matched to a "
                    f"hierarchy instance. Use a specific term (e.g. 'top acc' or "
                    f"'sub acc') in your query so the engine knows which "
                    f"{table_name} instance this column belongs to."
                )
            )

        # 2. Exact composite lookup
        alias = alias_lookup.get((table_name, role), "")

        # 3. Single-instance fallback [V1]
        if not alias and table_name in single_instance_lookup:
            alias = single_instance_lookup[table_name]
            warnings.append(
                f"Column '{table_name}.{column_name}' (source "
                f"'{entry.get('source', '')}') had no hierarchy role; resolved "
                f"to the single instance of '{table_name}' (alias '{alias}')."
            )

        columns.append(ResolvedColumn(
            table_alias=alias,
            column_name=column_name,
            output_alias=column_name,   # Phase 1: always same as column name
        ))

    return columns, warnings


# ---------------------------------------------------------------------------
# Filter translation
# ---------------------------------------------------------------------------

def _build_resolved_filters(
    resolved_filters: list[dict],
    alias_lookup: dict,
    single_instance_lookup: dict,
    self_join_tables: set[str],
) -> tuple[list[ResolvedFilter], list[str]]:
    """
    Translate resolved_filters dicts into ResolvedFilter models.

    Same alias resolution order as columns:
      1. Self-join table + role None -> StructuredQueryBuildError.
      2. Composite (table_name, role) lookup.
      3. [V1] Single-instance fallback + warning.

    Pure function (Option Y): returns (filters, warnings).

    Args:
        resolved_filters:        List of filter dicts from QueryContext.
        alias_lookup:            {(table_name, role) -> alias} composite lookup.
        single_instance_lookup:  {table_name -> alias} for single-instance tables.
        self_join_tables:        Set of table names appearing more than once.

    Returns:
        (list of ResolvedFilter in original order, list of warning strings)

    Raises:
        StructuredQueryBuildError: Filter on a self-join table has role=None.
    """
    filters: list[ResolvedFilter] = []
    warnings: list[str] = []

    for entry in resolved_filters:
        table_name = entry.get("table", "")
        column_name = entry.get("column", "")
        role = entry.get("role")

        if table_name in self_join_tables and role is None:
            raise StructuredQueryBuildError(
                message=(
                    f"Filter '{table_name}.{column_name}' source "
                    f"'{entry.get('source', '')}' could not be matched to a "
                    f"hierarchy instance. Use a specific term (e.g. 'top acc' or "
                    f"'sub acc') in your query so the engine knows which "
                    f"{table_name} instance this filter applies to."
                )
            )

        alias = alias_lookup.get((table_name, role), "")

        if not alias and table_name in single_instance_lookup:
            alias = single_instance_lookup[table_name]
            warnings.append(
                f"Filter '{table_name}.{column_name}' (source "
                f"'{entry.get('source', '')}') had no hierarchy role; resolved "
                f"to the single instance of '{table_name}' (alias '{alias}')."
            )

        filters.append(ResolvedFilter(
            table_alias=alias,
            column_name=column_name,
            operator=entry.get("operator", "="),
            value=entry.get("value", ""),
        ))

    return filters, warnings


# ---------------------------------------------------------------------------
# Join translation
# ---------------------------------------------------------------------------

def _build_resolved_joins(resolved_joins: list[dict]) -> list[ResolvedJoin]:
    """
    Translate resolved_joins dicts into ResolvedJoin models.
    on_conditions is carried through as-is — list of {left, right} dicts.

    Args:
        resolved_joins: List of join dicts from QueryContext (join_resolver output).

    Returns:
        List of ResolvedJoin models in original order.
    """
    joins: list[ResolvedJoin] = []

    for entry in resolved_joins:
        joins.append(ResolvedJoin(
            join_type=entry.get("join_type", "INNER JOIN"),
            table_name=entry.get("table_name", ""),
            alias=entry.get("alias", ""),
            on_conditions=entry.get("on_conditions", []),
        ))

    return joins


# ---------------------------------------------------------------------------
# Table translation
# ---------------------------------------------------------------------------

def _build_resolved_tables(resolved_tables: list[dict]) -> list[ResolvedTable]:
    """
    Translate resolved_tables dicts into ResolvedTable models.
    First entry is the FROM table — order is preserved.

    Args:
        resolved_tables: List of table dicts from QueryContext (join_resolver output).

    Returns:
        List of ResolvedTable models in original order.
    """
    tables: list[ResolvedTable] = []

    for entry in resolved_tables:
        tables.append(ResolvedTable(
            table_name=entry.get("table", ""),
            alias=entry.get("alias", ""),
        ))

    return tables


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def run_structured_query_builder(
    context: QueryContext,
    logger: StructuredLogger,
) -> QueryContext:
    """
    Build a StructuredQuery from the enriched QueryContext.

    Reads:
        context.resolved_tables   -- list of dicts with table, alias, optional role
        context.resolved_columns  -- list of dicts with table, column, source, optional role
        context.resolved_joins    -- list of join dicts with on_conditions
        context.resolved_filters  -- list of dicts with table, column, operator, value, optional role
        context.applied_rules     -- list of raw SQL condition strings
        context.llm_output        -- reads ["limit"] for top_rows
        context.app_id            -- written to StructuredQuery.app_id

    Writes (on success):
        context.structured_query  -- populated StructuredQuery model
        context.warnings          -- appended with any single-instance fallback notes [V1]
        context.status = "success"
        STRUCTURED_QUERY_BUILT log emitted

    On error (StructuredQueryBuildError):
        Logs error to STRUCTURED_QUERY_BUILT stage before raising.
        Orchestrator catches the exception and sets context.status = "failed".

    Args:
        context: Pipeline state. All validator stages must have run before this.
        logger:  StructuredLogger for emitting STRUCTURED_QUERY_BUILT.

    Returns:
        Updated QueryContext with structured_query populated.

    Raises:
        StructuredQueryBuildError: Column or filter on a self-join table has
                                   unresolvable role (source too vague).
    """
    start_ms = int(time.time() * 1000)

    # ------------------------------------------------------------------
    # Determine which tables are self-join tables in this request
    # ------------------------------------------------------------------
    table_name_counts: dict[str, int] = {}
    for entry in context.resolved_tables:
        t = entry.get("table", "")
        table_name_counts[t] = table_name_counts.get(t, 0) + 1

    self_join_tables: set[str] = {
        t for t, count in table_name_counts.items() if count > 1
    }

    # ------------------------------------------------------------------
    # Build alias lookups
    #   composite:        (table_name, role) -> alias  (all tables)
    #   single_instance:  table_name -> alias          (count == 1 only) [V1]
    # ------------------------------------------------------------------
    alias_lookup = _build_alias_lookup(context.resolved_tables)
    single_instance_lookup = _build_single_instance_lookup(context.resolved_tables)

    # ------------------------------------------------------------------
    # Translate each section — errors logged before raising.
    # Helpers are pure (Option Y): they return (models, warnings).
    # ------------------------------------------------------------------
    try:
        tables = _build_resolved_tables(context.resolved_tables)
        columns, column_warnings = _build_resolved_columns(
            context.resolved_columns, alias_lookup, single_instance_lookup, self_join_tables
        )
        joins = _build_resolved_joins(context.resolved_joins)
        filters, filter_warnings = _build_resolved_filters(
            context.resolved_filters, alias_lookup, single_instance_lookup, self_join_tables
        )
    except StructuredQueryBuildError as exc:
        # Log the error to the file before re-raising
        elapsed_ms = int(time.time() * 1000) - start_ms
        context.latency_ms["structured_query_builder"] = elapsed_ms
        logger.log(
            LogEntry(
                stage=STRUCTURED_QUERY_BUILT,
                request_id=context.request_id,
                user_id=context.user_id,
                app_id=context.app_id,
                app_schema_version=context.app_schema_version,
                latency_ms=elapsed_ms,
                payload={
                    "status": "failed",
                    "error_code": exc.code,
                    "error_message": exc.message,
                },
            )
        )
        raise

    # ------------------------------------------------------------------
    # Append any single-instance fallback warnings to context [V1]
    # ------------------------------------------------------------------
    context.warnings.extend(column_warnings)
    context.warnings.extend(filter_warnings)

    # ------------------------------------------------------------------
    # Read top_rows from llm_output["limit"]
    # ------------------------------------------------------------------
    top_rows: int | None = None
    if context.llm_output:
        limit_val = context.llm_output.get("limit")
        if isinstance(limit_val, int):
            top_rows = limit_val

    # ------------------------------------------------------------------
    # Assemble StructuredQuery
    # ------------------------------------------------------------------
    structured_query = StructuredQuery(
        app_id=context.app_id,
        top_rows=top_rows,
        tables=tables,
        columns=columns,
        joins=joins,
        filters=filters,
        applied_rules=list(context.applied_rules),
    )

    context.structured_query = structured_query
    context.status = "success"

    # ------------------------------------------------------------------
    # Emit success log
    # ------------------------------------------------------------------
    elapsed_ms = int(time.time() * 1000) - start_ms
    context.latency_ms["structured_query_builder"] = elapsed_ms

    logger.log(
        LogEntry(
            stage=STRUCTURED_QUERY_BUILT,
            request_id=context.request_id,
            user_id=context.user_id,
            app_id=context.app_id,
            app_schema_version=context.app_schema_version,
            latency_ms=elapsed_ms,
            payload={
                "status": "success",
                "top_rows": top_rows,
                "table_count": len(tables),
                "column_count": len(columns),
                "join_count": len(joins),
                "filter_count": len(filters),
                "rule_count": len(structured_query.applied_rules),
                "fallback_warnings": len(column_warnings) + len(filter_warnings),
            },
        )
    )

    return context
