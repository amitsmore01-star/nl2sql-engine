# src/validator/structured_query_builder.py
# V0 - Initial implementation
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
#   Non-self-join tables: simple {table_name -> alias} lookup.
#   Self-join tables:     composite {(table_name, role) -> alias} lookup.
#   join_resolver V1 stamps "role" onto column and filter entries for self-join
#   tables — so this builder uses exact (table, role) matching, no fuzzy logic.
#
# Error handling:
#   StructuredQueryBuildError raised when a column or filter on a self-join table
#   has role=None (source was too vague to match a hierarchy synonym).
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
# Alias lookup builder
# ---------------------------------------------------------------------------

def _build_alias_lookup(resolved_tables: list[dict]) -> dict:
    """
    Build an alias lookup from resolved_tables entries.

    For non-self-join tables (no "role" key):
        key = (table_name, None)  -> alias

    For self-join tables ("role" key present):
        key = (table_name, role)  -> alias

    Using (table, role) as the composite key handles both cases uniformly.
    Non-self-join entries always have role=None so their key is (table, None).

    Example result:
        {
            ("Major.Customer", None):   "c",
            ("Major.Acc",      "top_Acc"): "a_top",
            ("Major.Acc",      "sub_Acc"): "a_sub",
        }
    """
    lookup: dict = {}
    for entry in resolved_tables:
        table_name = entry.get("table", "")
        role = entry.get("role")        # None for non-self-join tables
        alias = entry.get("alias", "")
        lookup[(table_name, role)] = alias
    return lookup


# ---------------------------------------------------------------------------
# Column translation
# ---------------------------------------------------------------------------

def _build_resolved_columns(
    resolved_columns: list[dict],
    alias_lookup: dict,
    self_join_tables: set[str],
) -> list[ResolvedColumn]:
    """
    Translate resolved_columns dicts into ResolvedColumn models.

    For each column entry:
      1. Determine the role: entry.get("role") — stamped by join_resolver V1
         for self-join tables; absent (None) for non-self-join tables.
      2. Look up alias via (table_name, role).
      3. If lookup fails for a self-join table (role is None but table is
         self-join) — raise StructuredQueryBuildError. Caller logs before raising.
      4. output_alias defaults to column_name (Phase 1).

    Args:
        resolved_columns:  List of column dicts from QueryContext.
        alias_lookup:      {(table_name, role) -> alias} dict.
        self_join_tables:  Set of table names that appear more than once.

    Returns:
        List of ResolvedColumn models in original order.

    Raises:
        StructuredQueryBuildError: Column on a self-join table has role=None.
    """
    columns: list[ResolvedColumn] = []

    for entry in resolved_columns:
        table_name = entry.get("table", "")
        column_name = entry.get("column", "")
        role = entry.get("role")  # None for non-self-join; role string for self-join

        # Detect ambiguous self-join: table is self-join but role could not be assigned
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

        alias = alias_lookup.get((table_name, role), "")

        columns.append(ResolvedColumn(
            table_alias=alias,
            column_name=column_name,
            output_alias=column_name,   # Phase 1: always same as column name
        ))

    return columns


# ---------------------------------------------------------------------------
# Filter translation
# ---------------------------------------------------------------------------

def _build_resolved_filters(
    resolved_filters: list[dict],
    alias_lookup: dict,
    self_join_tables: set[str],
) -> list[ResolvedFilter]:
    """
    Translate resolved_filters dicts into ResolvedFilter models.

    Same alias resolution logic as columns:
      - (table_name, role) lookup for exact match.
      - StructuredQueryBuildError if self-join table has role=None.

    Args:
        resolved_filters:  List of filter dicts from QueryContext.
        alias_lookup:      {(table_name, role) -> alias} dict.
        self_join_tables:  Set of table names that appear more than once.

    Returns:
        List of ResolvedFilter models in original order.

    Raises:
        StructuredQueryBuildError: Filter on a self-join table has role=None.
    """
    filters: list[ResolvedFilter] = []

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

        filters.append(ResolvedFilter(
            table_alias=alias,
            column_name=column_name,
            operator=entry.get("operator", "="),
            value=entry.get("value", ""),
        ))

    return filters


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
    # Build alias lookup: (table_name, role) -> alias
    # ------------------------------------------------------------------
    alias_lookup = _build_alias_lookup(context.resolved_tables)

    # ------------------------------------------------------------------
    # Translate each section — errors logged before raising
    # ------------------------------------------------------------------
    try:
        tables = _build_resolved_tables(context.resolved_tables)
        columns = _build_resolved_columns(
            context.resolved_columns, alias_lookup, self_join_tables
        )
        joins = _build_resolved_joins(context.resolved_joins)
        filters = _build_resolved_filters(
            context.resolved_filters, alias_lookup, self_join_tables
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
            },
        )
    )

    return context
