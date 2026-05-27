# src/validator/join_resolver.py
# V0 - Initial implementation
# V1 - Story 4.5: Stamp "role" on resolved_columns and resolved_filters entries
#      for self-join tables. Uses the same _match_hierarchy_role() function already
#      used for table entries — single source of truth, zero duplication.
#      This enables structured_query_builder to use (table, role) as a composite
#      key for alias lookup — exact match, no fuzzy source matching needed.
#      Only self-join tables are stamped — non-self-join tables are unaffected.
#
# Deterministic join resolver.
# Resolves join paths between all tables proposed by the LLM, using only
# the schema relationships defined in the app schema JSON.
#
# Two callers (same function, zero duplication — architecture rule):
#   - src/pipeline/orchestrator.py       (full pipeline via POST /v1/query)
#   - src/api/tools/validator_tool.py    (Foundry tool via POST /v1/tools/validator)
#
# Responsibilities:
#   1. Assign aliases to every table in resolved_tables (schema-driven, no hardcoding).
#   2. Detect self-joins (same table name appearing more than once).
#      For self-joins: match each instance's "source" against hierarchy synonyms
#      in the schema to assign a role (e.g. top_Acc, sub_Acc).
#      Role drives alias suffix (a_top, a_sub) and conditions in rule applicator.
#   3. Resolve join paths between all distinct tables using schema relationships.
#      Direct joins: found directly in table.relationships.
#      Junction bridging: when two tables have no direct relationship but share
#      a junction table (is_junction_table=True) that links them.
#   4. Populate context.resolved_joins as list[dict].
#      Each join dict uses on_conditions: list[dict] with left/right keys.
#      Consistent shape for all joins — single or multi-condition.
#   5. Enrich context.resolved_tables entries with "alias" and optional "role" keys.
#   6. [V1] Stamp "role" on resolved_columns and resolved_filters entries for
#      self-join tables. Enables exact (table, role) alias lookup in query builder.
#
# Join dict shape (consistent for ALL joins):
#   {
#       "join_type": "INNER JOIN",
#       "table_name": "Major.Acc",
#       "alias": "a_sub",
#       "on_conditions": [
#           {"left": "c.CustomerID",  "right": "a_sub.CustomerID"},
#           {"left": "a_top.AccID",   "right": "a_sub.ParentAccID"},
#       ]
#   }
#
# Single-table queries:
#   resolved_joins = [] — no join needed, no error raised.
#
# Error cases:
#   NoJoinPathError — two or more distinct tables with no resolvable join path.
#
# Alias generation algorithm (fully schema-driven):
#   1. Get display_name from schema for the table.
#   2. If display_name contains '_': split on '_', take first letter of each part.
#   3. Elif display_name starts with uppercase: CamelCase split, take initials.
#   4. Else (all lowercase, no '_'): take first 3 characters.
#   5. For hierarchy roles: append _{role_suffix} to base alias
#      e.g. role "top_Acc" on base "a" → "a_top"
#   6. Collision resolution: if alias already taken, append _2, _3 etc.

import re
import time
from typing import Optional

from src.core.constants import VALIDATION_RESULT
from src.core.exceptions import NoJoinPathError
from src.core.logging.log_models import LogEntry
from src.core.logging.logger import StructuredLogger
from src.core.models import QueryContext
from src.schema.schema_models import AppSchema, TableSchema
from src.schema.schema_repository import SchemaRepository


# ---------------------------------------------------------------------------
# Alias generation helpers
# ---------------------------------------------------------------------------

def _camel_split(name: str) -> list[str]:
    """
    Split a CamelCase string into its component words.
    Example: "CustomerDemographics" -> ["Customer", "Demographics"]
    Example: "Acc" -> ["Acc"]
    """
    parts = re.sub(r"([a-z])([A-Z])", r"\1 \2", name).split()
    return parts if parts else [name]


def _build_alias_candidate(display_name: str) -> str:
    """
    Build an alias candidate from a table's display_name.
    Rules (in priority order):
      1. Contains '_' -> split on '_', take first letter of each part, lowercase
      2. Starts with uppercase -> CamelCase split, take initials, lowercase
         Covers single-word ("Customer" -> "c") and multi-word ("CustomerDemographics" -> "cd")
      3. All lowercase, no '_' -> first 3 chars, lowercase
    """
    if not display_name:
        return "t"

    if "_" in display_name:
        parts = display_name.split("_")
        return "".join(p[0].lower() for p in parts if p)

    if display_name[0].isupper():
        parts = _camel_split(display_name)
        return "".join(p[0].lower() for p in parts if p)

    return display_name[:3].lower()


def _resolve_alias(
    display_name: str,
    role,
    assigned: set,
) -> str:
    """
    Produce a unique alias for a table instance.
    For hierarchy roles: {base}_{role_suffix}
    e.g. role="top_Acc" -> suffix="top", base="a" -> alias="a_top"
    Collisions resolved by appending _2, _3 etc.
    """
    base = _build_alias_candidate(display_name)

    if role and "_" in role:
        suffix = role.split("_")[0].lower()
        candidate = f"{base}_{suffix}"
    else:
        candidate = base

    if candidate not in assigned:
        return candidate

    counter = 2
    while f"{candidate}_{counter}" in assigned:
        counter += 1
    return f"{candidate}_{counter}"


# ---------------------------------------------------------------------------
# Hierarchy role matching
# ---------------------------------------------------------------------------

def _match_hierarchy_role(source: str, table_schema):
    """
    Match a source phrase against hierarchy synonyms defined in the schema.
    Returns the role key (e.g. "top_Acc") if matched, None otherwise.
    Matching is case-insensitive whole-word using regex boundaries.
    """
    if not table_schema.business_rules or not table_schema.business_rules.hierarchy:
        return None

    hierarchy = table_schema.business_rules.hierarchy
    source_lower = source.lower()

    for level_name in hierarchy.level_names():
        level = hierarchy.get_level(level_name)
        if level is None:
            continue
        for synonym in level.synonyms:
            pattern = r"\b" + re.escape(synonym.lower()) + r"\b"
            if re.search(pattern, source_lower):
                return level_name

    return None


# ---------------------------------------------------------------------------
# Junction table bridging
# ---------------------------------------------------------------------------

def _find_junction_bridge(table_a: str, table_b: str, app_schema):
    """
    Find a junction table that bridges table_a and table_b.
    Returns the junction TableSchema if found, None otherwise.
    """
    for table in app_schema.tables:
        if not table.is_junction_table:
            continue
        related = {rel.related_table for rel in table.relationships}
        if table_a in related and table_b in related:
            return table
    return None


# ---------------------------------------------------------------------------
# Relationship finders
# ---------------------------------------------------------------------------

def _find_direct_relationship(from_table, to_table_name: str):
    """
    Find the first direct non-self relationship from from_table to to_table_name.
    Returns (from_column, to_column) if found, None otherwise.
    """
    for rel in from_table.relationships:
        if rel.related_table == to_table_name and rel.type != "self":
            return (rel.from_, rel.to)
    return None


def _find_all_direct_relationships(from_table, to_table_name: str) -> list:
    """
    Find ALL direct non-self relationships from from_table to to_table_name.
    Returns list of (from_column, to_column) tuples.
    """
    return [
        (rel.from_, rel.to)
        for rel in from_table.relationships
        if rel.related_table == to_table_name and rel.type != "self"
    ]


# ---------------------------------------------------------------------------
# Join path resolution
# ---------------------------------------------------------------------------

def _resolve_joins_for_tables(
    table_instances: list,
    table_lookup: dict,
    app_schema,
    table_name_counts: dict,
) -> list:
    """
    Resolve all join dicts for table instances that already have aliases.
    First instance is the FROM table (anchor).

    Self-join handling:
      - First instance of a repeated table joins normally to other tables.
      - Second+ instances collect:
          1. Primary: self relationship condition (e.g. a_top.AccID = a_sub.ParentAccID)
          2. Additional: direct conditions from all other anchored tables
             (e.g. c.CustomerID = a_sub.CustomerID)
        All go into on_conditions list on a single join dict.
    """
    if len(table_instances) <= 1:
        return []

    joins = []
    anchored_instances = [table_instances[0]]

    for instance in table_instances[1:]:
        t_name = instance["table"]
        t_alias = instance["alias"]
        t_schema = table_lookup.get(t_name)

        if t_schema is None:
            # TECH DEBT: log error before raise — Phase 1 cleanup
            raise NoJoinPathError(
                message=f"Table '{t_name}' not found in schema during join resolution."
            )

        is_self_join_table = table_name_counts.get(t_name, 1) > 1
        prior_same_table = any(a["table"] == t_name for a in anchored_instances)
        joined = False

        # ------------------------------------------------------------------
        # Self-join path: second+ instance of a repeated table
        # ------------------------------------------------------------------
        if is_self_join_table and prior_same_table:
            on_conditions = []

            # Primary: self relationship (e.g. a_top.AccID = a_sub.ParentAccID)
            for anchored in anchored_instances:
                if anchored["table"] != t_name:
                    continue
                a_alias = anchored["alias"]
                for rel in t_schema.relationships:
                    if rel.type == "self" and rel.related_table == t_name:
                        on_conditions.append({
                            "left": f"{a_alias}.{rel.to}",
                            "right": f"{t_alias}.{rel.from_}",
                        })
                        break
                if on_conditions:
                    break

            # Additional: conditions from other anchored tables
            for anchored in anchored_instances:
                if anchored["table"] == t_name:
                    continue
                a_name = anchored["table"]
                a_alias = anchored["alias"]
                a_schema = table_lookup.get(a_name)
                if a_schema is None:
                    continue

                for from_col, to_col in _find_all_direct_relationships(a_schema, t_name):
                    on_conditions.append({
                        "left": f"{a_alias}.{from_col}",
                        "right": f"{t_alias}.{to_col}",
                    })

                for from_col, to_col in _find_all_direct_relationships(t_schema, a_name):
                    on_conditions.append({
                        "left": f"{a_alias}.{to_col}",
                        "right": f"{t_alias}.{from_col}",
                    })

            if on_conditions:
                joins.append({
                    "join_type": "INNER JOIN",
                    "table_name": t_name,
                    "alias": t_alias,
                    "on_conditions": on_conditions,
                })
                joined = True

        # ------------------------------------------------------------------
        # Normal join: first instance of a table or non-self-join table
        # ------------------------------------------------------------------
        if not joined:
            for anchored in anchored_instances:
                a_name = anchored["table"]
                a_alias = anchored["alias"]
                a_schema = table_lookup.get(a_name)

                if a_schema is None:
                    continue

                result = _find_direct_relationship(a_schema, t_name)
                if result:
                    from_col, to_col = result
                    joins.append({
                        "join_type": "INNER JOIN",
                        "table_name": t_name,
                        "alias": t_alias,
                        "on_conditions": [
                            {"left": f"{a_alias}.{from_col}", "right": f"{t_alias}.{to_col}"}
                        ],
                    })
                    joined = True
                    break

                result = _find_direct_relationship(t_schema, a_name)
                if result:
                    from_col, to_col = result
                    joins.append({
                        "join_type": "INNER JOIN",
                        "table_name": t_name,
                        "alias": t_alias,
                        "on_conditions": [
                            {"left": f"{a_alias}.{to_col}", "right": f"{t_alias}.{from_col}"}
                        ],
                    })
                    joined = True
                    break

        # ------------------------------------------------------------------
        # Junction bridge fallback
        # ------------------------------------------------------------------
        if not joined:
            for anchored in anchored_instances:
                a_name = anchored["table"]
                a_alias = anchored["alias"]

                if t_name == a_name:
                    continue

                junction = _find_junction_bridge(a_name, t_name, app_schema)
                if junction is None:
                    continue

                j_display = junction.display_name or junction.name.split(".")[-1]
                j_alias = _build_alias_candidate(j_display)

                j_from_anchored = _find_direct_relationship(
                    table_lookup[a_name], junction.name
                )
                j_to_new = _find_direct_relationship(junction, t_name)

                if j_from_anchored and j_to_new:
                    fa_col, fa_to_col = j_from_anchored
                    jn_col, jn_to_col = j_to_new
                    joins.append({
                        "join_type": "INNER JOIN",
                        "table_name": junction.name,
                        "alias": j_alias,
                        "on_conditions": [
                            {"left": f"{a_alias}.{fa_col}", "right": f"{j_alias}.{fa_to_col}"}
                        ],
                    })
                    joins.append({
                        "join_type": "INNER JOIN",
                        "table_name": t_name,
                        "alias": t_alias,
                        "on_conditions": [
                            {"left": f"{j_alias}.{jn_col}", "right": f"{t_alias}.{jn_to_col}"}
                        ],
                    })
                    joined = True
                    break

        if not joined:
            # TECH DEBT: log error before raise — Phase 1 cleanup
            raise NoJoinPathError(
                message=(
                    f"No join path found between '{t_name}' and any of "
                    f"{[i['table'] for i in anchored_instances]}. "
                    f"Check schema relationships."
                )
            )

        anchored_instances.append(instance)

    return joins


# ---------------------------------------------------------------------------
# Role stamping for columns and filters  [V1]
# ---------------------------------------------------------------------------

def _stamp_roles_on_columns_and_filters(
    context: QueryContext,
    self_join_tables: set[str],
    table_lookup: dict,
) -> None:
    """
    For every entry in resolved_columns and resolved_filters whose table is a
    self-join table, match its source phrase against hierarchy synonyms and
    stamp the "role" key onto the entry.

    Non-self-join table entries are left untouched — no "role" key added.

    Called once after all table aliases and roles have been assigned.

    Args:
        context:           Pipeline state. resolved_columns and resolved_filters
                           must be populated (by table_column_validator, Story 4.2).
        self_join_tables:  Set of table names that appear more than once in
                           resolved_tables (i.e. are self-join tables this request).
        table_lookup:      table_name -> TableSchema dict for role matching.
    """
    for entry in context.resolved_columns:
        t_name = entry.get("table", "")
        if t_name not in self_join_tables:
            continue
        t_schema = table_lookup.get(t_name)
        if t_schema is None:
            continue
        source = entry.get("source", "")
        role = _match_hierarchy_role(source, t_schema)
        entry["role"] = role  # May be None if source is too vague

    for entry in context.resolved_filters:
        t_name = entry.get("table", "")
        if t_name not in self_join_tables:
            continue
        t_schema = table_lookup.get(t_name)
        if t_schema is None:
            continue
        source = entry.get("source", "")
        role = _match_hierarchy_role(source, t_schema)
        entry["role"] = role  # May be None if source is too vague


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def run_join_resolver(
    context: QueryContext,
    schema_repo: SchemaRepository,
    logger: StructuredLogger,
) -> QueryContext:
    """
    Resolve join paths between all validated tables in context.resolved_tables.

    Reads:
        context.resolved_tables  -- list of {table, source} dicts (from 4.2)
        context.resolved_columns -- list of {table, column, source} dicts (from 4.2)
        context.resolved_filters -- list of {table, column, operator, value, source} (from 4.2)
        context.app_id           -- used to load the correct schema

    Writes (on success):
        context.resolved_tables  -- enriched with "alias" and optional "role" keys
        context.resolved_columns -- self-join entries stamped with "role" key [V1]
        context.resolved_filters -- self-join entries stamped with "role" key [V1]
        context.resolved_joins   -- list of join dicts with on_conditions lists
        context.status = "success"

    Raises:
        NoJoinPathError: Two or more distinct tables with no resolvable join path.

    Single table: resolved_joins = [], no error.
    """
    start_ms = int(time.time() * 1000)

    app_schema: AppSchema = schema_repo.get_schema(context.app_id)

    table_lookup = {t.name: t for t in app_schema.tables}
    table_instances = context.resolved_tables

    # ------------------------------------------------------------------
    # Single table -- no join needed
    # ------------------------------------------------------------------
    if len(table_instances) <= 1:
        if table_instances:
            t_name = table_instances[0]["table"]
            t_schema = table_lookup.get(t_name)
            display_name = (
                t_schema.display_name if t_schema and t_schema.display_name
                else t_name.split(".")[-1]
            )
            assigned: set = set()
            alias = _resolve_alias(display_name, None, assigned)
            assigned.add(alias)
            table_instances[0]["alias"] = alias

        context.resolved_joins = []
        context.status = "success"
        _emit_log(context, logger, start_ms)
        return context

    # ------------------------------------------------------------------
    # Multiple tables -- count occurrences, assign aliases, resolve joins
    # ------------------------------------------------------------------
    table_name_counts: dict = {}
    for entry in table_instances:
        t = entry["table"]
        table_name_counts[t] = table_name_counts.get(t, 0) + 1

    # Set of table names that appear more than once — used for role stamping
    self_join_tables: set[str] = {
        t for t, count in table_name_counts.items() if count > 1
    }

    assigned_aliases: set = set()

    for entry in table_instances:
        t_name = entry["table"]
        t_schema = table_lookup.get(t_name)
        display_name = (
            t_schema.display_name if t_schema and t_schema.display_name
            else t_name.split(".")[-1]
        )

        is_self_join = table_name_counts[t_name] > 1
        role = None

        if is_self_join:
            source = entry.get("source", "")
            role = _match_hierarchy_role(source, t_schema) if t_schema else None
            if role is None:
                context.warnings.append(
                    f"Table '{t_name}' appears multiple times but source "
                    f"'{source}' matched no hierarchy synonym. "
                    f"Alias will be auto-generated."
                )

        alias = _resolve_alias(display_name, role, assigned_aliases)
        assigned_aliases.add(alias)
        entry["alias"] = alias
        if role is not None:
            entry["role"] = role

    # ------------------------------------------------------------------
    # [V1] Stamp role on columns and filters for self-join tables
    # ------------------------------------------------------------------
    if self_join_tables:
        _stamp_roles_on_columns_and_filters(context, self_join_tables, table_lookup)

    resolved_joins = _resolve_joins_for_tables(
        table_instances, table_lookup, app_schema, table_name_counts
    )

    context.resolved_joins = resolved_joins
    context.status = "success"
    _emit_log(context, logger, start_ms)
    return context


# ---------------------------------------------------------------------------
# Log helper
# ---------------------------------------------------------------------------

def _emit_log(context: QueryContext, logger: StructuredLogger, start_ms: int) -> None:
    elapsed_ms = int(time.time() * 1000) - start_ms
    context.latency_ms["join_resolver"] = elapsed_ms

    logger.log(
        LogEntry(
            stage=VALIDATION_RESULT,
            request_id=context.request_id,
            user_id=context.user_id,
            app_id=context.app_id,
            app_schema_version=context.app_schema_version,
            latency_ms=elapsed_ms,
            payload={
                "resolved_joins": context.resolved_joins,
                "resolved_tables": context.resolved_tables,
            },
        )
    )
