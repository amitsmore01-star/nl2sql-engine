# src/core/models.py
# V0 - Initial implementation
# V1 - Story 3.5: Replaced intent_output + mapping_output with single llm_output field.
#      llm_output holds the full simplified IR from the NL-to-IR Strategy (arch v1.6).
# V2 - Story 4.2: Changed resolved_tables, resolved_columns, resolved_filters from
#      list[str] to list[dict]. Each entry preserves the full dict from llm_output
#      (including source field) so join resolver and rule applicator have full context.
#      resolved_joins remains list[str] — join resolver populates it in Story 4.3.
# V3 - Story 4.3: Changed resolved_joins from list[str] to list[dict].
#      Each entry is a join dict: {join_type, table_name, alias, on_conditions}.
#      Join resolver also enriches resolved_tables entries with alias and role keys.
# V4 - Story 4.5: Updated ResolvedJoin — replaced on_left/on_right (single condition)
#      with on_conditions: list[dict] to match join resolver output exactly.
#      Each condition dict has "left" and "right" keys.
#      Supports multi-condition joins (e.g. self-joins with 2+ ON conditions).
# V5 - Story 5.3: Added connector: str = "AND" to ResolvedFilter.
#      Defaults to "AND" so all existing callers are unaffected.
#      Allows OR conditions in WHERE clause (e.g. CustomerCID = 'ASA' OR CustomerCID = 'XYZ').
#      build_where() reads this field to emit AND or OR between filter conditions.
#
# Shared Pydantic models used across the entire nl2sql-engine pipeline.
#
# Two top-level models:
#   StructuredQuery — the SQL blueprint. Built by the validator, consumed by the SQL builder.
#   QueryContext    — the pipeline state object. Travels through every stage.
#                     Each stage reads from it and writes its outputs into it.
#
# Sub-models (building blocks for StructuredQuery):
#   ResolvedTable   — a table confirmed to exist in the schema, with its alias
#   ResolvedColumn  — a column confirmed to belong to its table, with output alias
#   ResolvedJoin    — a join between two tables, with one or more ON conditions
#   ResolvedFilter  — a user-driven filter condition (from the NL query)

from __future__ import annotations

import uuid
from typing import Any, Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Sub-models — building blocks for StructuredQuery
# ---------------------------------------------------------------------------

class ResolvedTable(BaseModel):
    """
    A table that has been confirmed to exist in the app schema.

    Example:
        ResolvedTable(table_name="Major.Customer", alias="c")
    """
    table_name: str   # Full schema-qualified name e.g. "Major.Customer"
    alias: str        # Short alias used in SQL e.g. "c", "cd", "a_top"


class ResolvedColumn(BaseModel):
    """
    A column confirmed to belong to its table in the app schema.

    Example:
        ResolvedColumn(
            table_alias="cd",
            column_name="CustomerName",
            output_alias="CustomerName"
        )
    """
    table_alias: str    # Alias of the table this column belongs to e.g. "cd"
    column_name: str    # Actual column name in the schema e.g. "CustomerName"
    output_alias: str   # Label in the SELECT clause e.g. "CustomerName"
                        # Defaults to column_name in Phase 1.
                        # Phase 3: extend for user-specified aliases ("name as Name").


class ResolvedJoin(BaseModel):
    """
    A JOIN between two tables, fully resolved from the schema relationships.
    Supports single and multi-condition ON clauses (e.g. self-joins).

    on_conditions is a list of {"left": "...", "right": "..."} dicts.
    Single-condition join:  one entry in on_conditions.
    Multi-condition join:   two or more entries (e.g. self-join).

    Example (single condition):
        ResolvedJoin(
            join_type="INNER JOIN",
            table_name="Major.CustomerDemographics",
            alias="cd",
            on_conditions=[{"left": "c.CustomerID", "right": "cd.CustomerID"}]
        )

    Example (multi-condition self-join):
        ResolvedJoin(
            join_type="INNER JOIN",
            table_name="Major.Acc",
            alias="a_sub",
            on_conditions=[
                {"left": "a_top.AccID",    "right": "a_sub.ParentAccID"},
                {"left": "c.CustomerID",   "right": "a_sub.CustomerID"},
            ]
        )
    """
    join_type: str = "INNER JOIN"              # Only type used in Phase 1
    table_name: str                            # Full schema-qualified name of joined table
    alias: str                                 # Alias for the joined table in SQL
    on_conditions: list[dict] = Field(default_factory=list)
    # Each entry: {"left": "alias.Column", "right": "alias.Column"}
    # SQL builder renders as: ON left = right [AND left = right ...]


class ResolvedFilter(BaseModel):
    """
    A user-driven filter condition extracted from the NL query.
    These come from what the user asked for — not from business rules.

    connector controls how this condition joins to the PREVIOUS condition
    in the WHERE clause. The first condition never emits a connector.

    connector values:
        "AND"  — default; condition is ANDed with the previous one
        "OR"   — condition is ORed with the previous one

    IS NULL / IS NOT NULL operators:
        When operator is "IS NULL" or "IS NOT NULL", the value field is
        ignored entirely. build_where() renders: alias.Column IS NULL

    Example (equality filter):
        ResolvedFilter(
            table_alias="c",
            column_name="CustomerCID",
            operator="=",
            value="ASA",
            connector="AND"
        )

    Example (OR filter):
        ResolvedFilter(
            table_alias="c",
            column_name="CustomerCID",
            operator="=",
            value="XYZ",
            connector="OR"
        )

    Example (IS NULL filter):
        ResolvedFilter(
            table_alias="c",
            column_name="VersionTermDate",
            operator="IS NULL",
            value="",
            connector="AND"
        )
    """
    table_alias: str          # Alias of the table e.g. "c"
    column_name: str          # Column to filter on e.g. "CustomerCID"
    operator: str             # SQL operator e.g. "=", ">", "LIKE", "IS NULL", "IS NOT NULL"
    value: str = ""           # Filter value e.g. "ASA". Ignored for IS NULL / IS NOT NULL.
    connector: str = "AND"    # How this condition joins to the previous one: "AND" | "OR"
                              # The first filter in the list never emits a connector.


# ---------------------------------------------------------------------------
# StructuredQuery — the SQL blueprint
# ---------------------------------------------------------------------------

class StructuredQuery(BaseModel):
    """
    The validated SQL blueprint produced by the deterministic validator.
    The SQL builder reads this object and assembles the final SQL string.
    The SQL builder never calls the LLM — it only reads this model.

    top_rows behaviour (set by SQL Builder, not here):
        None          → SQL Builder reads settings.sql.default_top_rows
        0 in settings → omit TOP clause entirely
        n in settings → SELECT TOP n
        User specified a number → SELECT TOP {that number}
    """
    app_id: str                              # Which app schema this query is for

    top_rows: Optional[int] = None           # None = not specified by user
                                             # SQL Builder applies config default

    tables: list[ResolvedTable] = Field(default_factory=list)
    # All tables involved in the query, in join order. First entry is the FROM table.

    columns: list[ResolvedColumn] = Field(default_factory=list)
    # All columns to SELECT, in order they should appear in the output.

    joins: list[ResolvedJoin] = Field(default_factory=list)
    # All JOIN clauses in the order they must be applied.

    filters: list[ResolvedFilter] = Field(default_factory=list)
    # User-driven WHERE conditions (from NL query).

    applied_rules: list[str] = Field(default_factory=list)
    # Auto-applied business rule conditions — raw SQL strings injected by the validator.
    # Example: ["c.VersionTermDate IS NULL", "ISNULL(c.DeletedFlag, 0) = 0"]


# ---------------------------------------------------------------------------
# QueryContext — the pipeline state object
# ---------------------------------------------------------------------------

class QueryContext(BaseModel):
    """
    The pipeline state object. Created at request entry and passed through every stage.
    Each stage reads from it and writes its outputs into it.

    nl_query_original is protected — it stores the raw user input and must never be
    modified after creation. Any attempt to reassign it raises AttributeError.
    All other fields are writable so pipeline stages can add their outputs.
    """

    model_config = {"arbitrary_types_allowed": True}

    # --- Identity ---
    request_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    # Auto-generated UUID if not provided. Unique per request.

    user_id: str = "Phase1_user"
    # Phase 1: single user. Phase 2+: real user identity.

    app_id: str = ""
    # Populated by AppIdentifier stage.
    # NOT Optional — Pydantic rejects None. Use "" for "not yet populated".

    app_schema_version: str = ""
    # Populated by AppIdentifier from the schema's version field.
    # NOT Optional — Pydantic rejects None. Use "" for "not yet populated".

    # --- Input ---
    nl_query_original: str
    # The raw NL query exactly as the user typed it. NEVER modify this field.

    nl_query_corrected: Optional[str] = None
    # Phase 2 — spell-corrected version. None in Phase 1.

    # --- LLM output (single field — architecture v1.6) ---
    llm_output: Optional[dict[str, Any]] = None
    # Populated by the NL-to-IR Strategy (SingleCallStrategy in Phase 1).
    # Holds the full simplified IR:
    #   tables:      list of {table, source}
    #   columns:     list of {table, column, source}
    #   filters:     list of {table, column, operator, value, source}
    #   limit:       int | null
    #   aggregation: dict | null   (captured in Phase 1, executed in Phase 2)
    #   sort:        list          (captured in Phase 1, executed in Phase 2)
    # Each entry carries a "source" field — the exact query phrase that produced it.
    # Replaced intent_output + mapping_output from architecture v1.5 and earlier.

    # --- Validator outputs ---
    resolved_tables: list[dict[str, Any]] = Field(default_factory=list)
    # Validated table entries from llm_output.tables.
    # Each entry starts as: {"table": "Major.Customer", "source": "customer"}
    # Join resolver enriches each entry with "alias" and optionally "role":
    #   {"table": "Major.Customer", "source": "customer", "alias": "c"}
    #   {"table": "Major.Acc", "source": "top acc", "alias": "a_top", "role": "top_Acc"}
    # Preserves duplicates (e.g. Major.Acc twice for self-join) so join resolver
    # can use the source field to assign hierarchy roles (top_acc, sub_acc).
    # Changed from list[str] in V2 — list[str] lost source, breaking hierarchy.

    resolved_columns: list[dict[str, Any]] = Field(default_factory=list)
    # Validated column entries from llm_output.columns.
    # Each entry starts as: {"table": "Major.CustomerDemographics",
    #                         "column": "CustomerName", "source": "customer name"}
    # Join resolver V1 stamps "role" on entries for self-join tables:
    #   {"table": "Major.Acc", "column": "AccName", "source": "top acc name",
    #    "role": "top_Acc"}
    # Changed from list[str] in V2 — same reason as resolved_tables.

    resolved_filters: list[dict[str, Any]] = Field(default_factory=list)
    # Validated filter entries from llm_output.filters.
    # Each entry starts as: {"table": "Major.Customer", "column": "CustomerCID",
    #                         "operator": "=", "value": "ASA", "source": "..."}
    # Join resolver V1 stamps "role" on entries for self-join tables.
    # Changed from list[str] in V2 — rule applicator needs full dict in Story 4.4.

    resolved_joins: list[dict[str, Any]] = Field(default_factory=list)
    # Join graph result — populated by join resolver in Story 4.3.
    # Each entry is a join dict:
    #   {"join_type": "INNER JOIN", "table_name": "Major.CustomerDemographics",
    #    "alias": "cd", "on_conditions": [{"left": "c.CustomerID", "right": "cd.CustomerID"}]}
    # on_conditions is a list — supports multi-condition self-joins.
    # Changed from list[str] in V3. on_left/on_right replaced with on_conditions in V4.

    applied_rules: list[str] = Field(default_factory=list)
    # Business rules injected by the rule applicator.
    # Each entry is a fully-qualified SQL condition string:
    #   "c.VersionTermDate IS NULL"
    #   "ISNULL(c.DeletedFlag, 0) = 0"
    #   "a_top.AccLevelConfig = 0"

    # --- Final outputs ---
    structured_query: Optional[StructuredQuery] = None
    # Built by StructuredQueryBuilder in Story 4.5. SQL Builder reads this.

    sql: Optional[str] = None
    # Final SQL string. Populated by SQLBuilder.

    # --- Observability ---
    latency_ms: dict[str, Any] = Field(default_factory=dict)
    # Per-stage timing. Key = stage name, value = milliseconds.

    total_latency_ms: int = 0
    # End-to-end total latency in milliseconds.

    token_usage: dict[str, Any] = Field(default_factory=dict)
    # LLM token usage. Keys: prompt, completion, total.

    warnings: list[str] = Field(default_factory=list)
    # Non-fatal issues encountered during processing.

    # --- Outcome ---
    status: str = "pending"
    # Pipeline outcome: "pending" | "success" | "failed" | "cancelled"

    error: Optional[dict[str, Any]] = None
    # Populated on failure: {"code": "...", "message": "..."}

    # -------------------------------------------------------------------
    # Protection for nl_query_original
    # Overrides __setattr__ to block reassignment of nl_query_original
    # after the model has been fully initialised.
    # _initialised is a plain Python attribute (not a Pydantic field)
    # so it does not appear in the model schema.
    # -------------------------------------------------------------------

    def model_post_init(self, __context: Any) -> None:
        """Called by Pydantic after __init__ completes. Marks model as initialised."""
        object.__setattr__(self, "_initialised", True)

    def __setattr__(self, name: str, value: Any) -> None:
        """
        Block reassignment of nl_query_original after initialisation.
        All other fields pass through to Pydantic's normal setter.
        """
        if name == "nl_query_original" and getattr(self, "_initialised", False):
            raise AttributeError(
                "nl_query_original is immutable after creation. "
                "It stores the original user input and must never be modified."
            )
        super().__setattr__(name, value)
