# src/sql/sql_builder.py
# V0 - Initial implementation
#
# SQL Builder.
# Assembles the final SQL string from context.structured_query by calling
# the three clause builders in sequence:
#   build_select()  — SELECT TOP N ... AS ...
#   build_join()    — FROM table alias \n INNER JOIN ...
#   build_where()   — WHERE ...
#
# Then stitches the clauses together with a trailing semicolon.
#
# No LLM calls. No schema lookups. Pure assembly — reads StructuredQuery,
# writes context.sql.
#
# Two callers (same function, zero duplication — architecture rule):
#   - src/pipeline/orchestrator.py       (full pipeline via POST /v1/query)
#   - src/api/tools/sql_builder_tool.py  (Foundry tool via POST /v1/tools/sql-builder)
#
# TOP guard:
#   structured_query.top_rows takes precedence over default_top_rows from settings.
#   If both are 0 (or top_rows=0) — TOP clause is omitted.
#   If top_rows is None — fall back to settings.sql.default_top_rows.
#
# Error handling:
#   context.structured_query must be populated before calling run_sql_builder().
#   If it is None, sets context.status="failed" and returns immediately — no raise.
#   All other errors propagate up to the orchestrator.

import time

from src.core.constants import SQL_BUILT
from src.core.logging.log_models import LogEntry
from src.core.logging.logger import StructuredLogger
from src.core.models import QueryContext
from src.sql.select_builder import build_select
from src.sql.join_builder import build_join
from src.sql.where_builder import build_where


def run_sql_builder(
    context: QueryContext,
    logger: StructuredLogger,
    settings,
) -> QueryContext:
    """
    Assemble the final SQL string from context.structured_query.

    Reads:
        context.structured_query  — must be populated by StructuredQueryBuilder
        settings.sql.default_top_rows — fallback when structured_query.top_rows is None

    Writes (on success):
        context.sql               — final SQL string ending with semicolon
        context.status = "success"
        SQL_BUILT log emitted

    On missing structured_query:
        context.status = "failed"
        context.error populated with SQL_BUILD_ERROR code
        Returns immediately — does not raise

    Args:
        context:  Pipeline state. structured_query must be populated.
        logger:   StructuredLogger for emitting SQL_BUILT.
        settings: Loaded Settings object — reads settings.sql.default_top_rows.
                  Not type-hinted to avoid circular import.

    Returns:
        Updated QueryContext with sql populated (or status="failed" if pre-condition
        not met).
    """
    start_ms = int(time.time() * 1000)

    # ------------------------------------------------------------------
    # Pre-condition: structured_query must be populated
    # ------------------------------------------------------------------
    if context.structured_query is None:
        context.status = "failed"
        context.error = {
            "code": "SQL_BUILD_ERROR",
            "message": (
                "structured_query is not populated. "
                "Run the validator stage before the SQL builder."
            ),
        }
        return context

    sq = context.structured_query
    default_top_rows = getattr(settings.sql, "default_top_rows", 10000)

    # ------------------------------------------------------------------
    # Build each clause
    # SELECT TOP N ... AS ...
    # FROM table alias \n INNER JOIN ...
    # WHERE ...
    # ------------------------------------------------------------------
    select_clause = build_select(sq, default_top_rows)
    join_clause = build_join(sq)
    where_clause = build_where(sq)

    # ------------------------------------------------------------------
    # Stitch clauses together
    # Only include non-empty clauses so a minimal query (no joins, no
    # filters) still produces valid SQL without blank lines.
    # ------------------------------------------------------------------
    parts = [select_clause]
    if join_clause:
        parts.append(join_clause)
    if where_clause:
        parts.append(where_clause)

    sql = "\n".join(parts) + ";"

    context.sql = sql
    context.status = "success"

    # ------------------------------------------------------------------
    # Emit SQL_BUILT log
    # ------------------------------------------------------------------
    elapsed_ms = int(time.time() * 1000) - start_ms
    context.latency_ms["sql_builder"] = elapsed_ms

    logger.log(
        LogEntry(
            stage=SQL_BUILT,
            request_id=context.request_id,
            user_id=context.user_id,
            app_id=context.app_id,
            app_schema_version=context.app_schema_version,
            latency_ms=elapsed_ms,
            payload={"sql": sql},
        )
    )

    return context
