# src/validator/rule_applicator.py
# V0 - Initial implementation
#
# Deterministic rule applicator.
# Reads context.resolved_tables (enriched by join resolver with alias + role)
# and auto-applies all relevant SQL conditions for each table:
#   - active_record business rules (e.g. VersionTermDate IS NULL, DeletedFlag = 0)
#   - versioning conditions (e.g. VersionTermDate IS NULL for versioned tables)
#   - hierarchy conditions (e.g. AccLevelConfig = 0, ParentAccID IS NULL)
#   - suppress token logic: if nl_query_original contains a suppress token
#     for a table's filter_control, active_record rules are skipped for that table
#
# Two callers (same function, zero duplication — architecture rule):
#   - src/pipeline/orchestrator.py       (full pipeline via POST /v1/query)
#   - src/api/tools/validator_tool.py    (Foundry tool via POST /v1/tools/validator)
#
# Output:
#   context.applied_rules — list[str] of fully-qualified SQL condition strings
#   e.g. ["c.VersionTermDate IS NULL", "ISNULL(c.DeletedFlag, 0) = 0", ...]
#
# Rules are alias-prefixed using the alias set by join_resolver on each
# resolved_tables entry. The SQL builder drops these directly into WHERE.
#
# Deduplication: a seen set prevents the same string appearing twice.
# Suppress tokens: checked per-table against nl_query_original (case-insensitive).
#   Only active_record rules are suppressed — versioning and hierarchy still apply.

import re
import time

from src.core.constants import VALIDATION_RESULT
from src.core.logging.log_models import LogEntry
from src.core.logging.logger import StructuredLogger
from src.core.models import QueryContext
from src.schema.schema_models import AppSchema, TableSchema
from src.schema.schema_repository import SchemaRepository


# ---------------------------------------------------------------------------
# Suppress token check
# ---------------------------------------------------------------------------

def _is_suppressed(
    table_schema: TableSchema,
    nl_query_original: str,
) -> bool:
    """
    Return True if nl_query_original contains any suppress token defined
    in the table's filter_control.suppress_tokens list.

    Matching is case-insensitive substring match (tokens can be phrases).
    Only tables with filter_control defined are ever suppressed.
    Tables without filter_control always return False.
    """
    if not table_schema.filter_control:
        return False

    suppress_tokens = table_schema.filter_control.suppress_tokens
    if not suppress_tokens:
        return False

    query_lower = nl_query_original.lower()
    return any(token.lower() in query_lower for token in suppress_tokens)


# ---------------------------------------------------------------------------
# Rule builders
# ---------------------------------------------------------------------------

def _apply_active_record_rules(
    alias: str,
    table_schema: TableSchema,
    seen: set[str],
    rules: list[str],
) -> None:
    """
    Apply active_record conditions from table's business_rules.
    Each condition is prefixed with the table alias.
    Conditions that reference a column name get alias prefix injected.
    Conditions that are already full expressions (ISNULL, etc.) get alias
    injected at the column reference position.

    Skip if already seen (deduplication).
    """
    if not table_schema.business_rules:
        return

    for condition in table_schema.business_rules.active_record:
        qualified = _qualify_condition(condition, alias)
        if qualified not in seen:
            seen.add(qualified)
            rules.append(qualified)


def _apply_versioning_rules(
    alias: str,
    table_schema: TableSchema,
    seen: set[str],
    rules: list[str],
) -> None:
    """
    Apply versioning active_condition if the table is versioned.
    Condition is prefixed with the table alias.
    """
    if not table_schema.versioning:
        return
    if not table_schema.versioning.is_versioned:
        return

    condition = table_schema.versioning.active_condition
    qualified = _qualify_condition(condition, alias)
    if qualified not in seen:
        seen.add(qualified)
        rules.append(qualified)


def _apply_hierarchy_rules(
    alias: str,
    role: str,
    table_schema: TableSchema,
    seen: set[str],
    rules: list[str],
) -> None:
    """
    Apply hierarchy conditions for the given role.
    Both condition and parent_condition are applied.
    Each is prefixed with the table alias.
    """
    if not table_schema.business_rules or not table_schema.business_rules.hierarchy:
        return

    level = table_schema.business_rules.hierarchy.get_level(role)
    if level is None:
        return

    for condition in [level.condition, level.parent_condition]:
        qualified = _qualify_condition(condition, alias)
        if qualified not in seen:
            seen.add(qualified)
            rules.append(qualified)


# ---------------------------------------------------------------------------
# Condition qualifier
# ---------------------------------------------------------------------------

def _qualify_condition(condition: str, alias: str) -> str:
    """
    Prefix bare column references in a SQL condition with the table alias.

    Handles these patterns:
      "VersionTermDate IS NULL"          -> "alias.VersionTermDate IS NULL"
      "ISNULL(DeletedFlag, 0) = 0"       -> "ISNULL(alias.DeletedFlag, 0) = 0"
      "VoidedDate IS NOT NULL"           -> "alias.VoidedDate IS NOT NULL"
      "AccLevelConfig = 0"               -> "alias.AccLevelConfig = 0"
      "ParentAccID IS NULL"              -> "alias.ParentAccID IS NULL"
      "alias.VersionTermDate IS NULL"    -> unchanged (already qualified)

    Strategy:
      Scan all uppercase-starting word tokens in the condition.
      Skip known SQL keywords and function names.
      Prefix the first remaining token (the column name) with alias + ".".

    SQL keywords/functions skipped:
      IS, NULL, NOT, AND, OR, IN, LIKE, ISNULL, ISNUMERIC, COALESCE, NULLIF,
      CAST, CONVERT, LEN, TRIM, UPPER, LOWER, CASE, WHEN, THEN, ELSE, END.
      This list covers all Phase 1 schema conditions — extend as needed.
    """
    # Already qualified — do not double-prefix
    if f"{alias}." in condition:
        return condition

    # SQL keywords and function names that must never be treated as column names
    _SQL_KEYWORDS = {
        "IS", "NULL", "NOT", "AND", "OR", "IN", "LIKE",
        "ISNULL", "ISNUMERIC", "COALESCE", "NULLIF",
        "CAST", "CONVERT", "LEN", "TRIM", "UPPER", "LOWER",
        "CASE", "WHEN", "THEN", "ELSE", "END",
    }

    # Find all uppercase-starting word tokens not already preceded by a dot
    # Replace only the first non-keyword match
    def _try_prefix(match: re.Match) -> str:
        word = match.group(0)
        if word.upper() in _SQL_KEYWORDS:
            return word  # leave keywords untouched — case-insensitive check
        # This is the column — prefix it and signal done via a flag
        _try_prefix.done = True
        return f"{alias}.{word}"

    _try_prefix.done = False

    def _replacer(match: re.Match) -> str:
        if _try_prefix.done:
            return match.group(0)  # already prefixed one column — leave rest alone
        return _try_prefix(match)

    qualified = re.sub(
        r"(?<!\.)(?<!\w)\b([A-Z][A-Za-z0-9_]*)\b",
        _replacer,
        condition,
    )
    return qualified


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def run_rule_applicator(
    context: QueryContext,
    schema_repo: SchemaRepository,
    logger: StructuredLogger,
) -> QueryContext:
    """
    Apply all relevant business rules, versioning conditions, and hierarchy
    conditions to every table in context.resolved_tables.

    Reads:
        context.resolved_tables    — list of dicts enriched by join resolver
                                     Each entry has: table, source, alias, (role)
        context.nl_query_original  — checked against suppress tokens
        context.app_id             — used to load the correct schema

    Writes (on success):
        context.applied_rules      — list[str] of fully-qualified SQL conditions
        context.status = "success"

    Args:
        context:     Pipeline state. resolved_tables must be enriched with aliases.
        schema_repo: Loaded schema repository.
        logger:      StructuredLogger for emitting VALIDATION_RESULT.

    Returns:
        Updated QueryContext with applied_rules populated.
    """
    start_ms = int(time.time() * 1000)

    app_schema: AppSchema = schema_repo.get_schema(context.app_id)

    # Build lookup: table_name → TableSchema
    table_lookup: dict[str, TableSchema] = {
        t.name: t for t in app_schema.tables
    }

    rules: list[str] = []
    seen: set[str] = set()

    for entry in context.resolved_tables:
        t_name = entry.get("table", "")
        alias = entry.get("alias", "")
        role = entry.get("role")  # May be None for non-hierarchy tables

        table_schema = table_lookup.get(t_name)
        if table_schema is None:
            # Defensive — should not happen after table_column_validator ran
            continue

        suppressed = _is_suppressed(table_schema, context.nl_query_original)

        # 1. Active record rules — skipped if suppressed
        if not suppressed:
            _apply_active_record_rules(alias, table_schema, seen, rules)

        # 2. Versioning rules — always applied (suppress does not affect versioning)
        _apply_versioning_rules(alias, table_schema, seen, rules)

        # 3. Hierarchy conditions — only if role is assigned
        if role:
            _apply_hierarchy_rules(alias, role, table_schema, seen, rules)

    context.applied_rules = rules
    context.status = "success"

    _emit_log(context, logger, start_ms)
    return context


# ---------------------------------------------------------------------------
# Log helper
# ---------------------------------------------------------------------------

def _emit_log(
    context: QueryContext,
    logger: StructuredLogger,
    start_ms: int,
) -> None:
    elapsed_ms = int(time.time() * 1000) - start_ms
    context.latency_ms["rule_applicator"] = elapsed_ms

    logger.log(
        LogEntry(
            stage=VALIDATION_RESULT,
            request_id=context.request_id,
            user_id=context.user_id,
            app_id=context.app_id,
            app_schema_version=context.app_schema_version,
            latency_ms=elapsed_ms,
            payload={
                "applied_rules": context.applied_rules,
            },
        )
    )
