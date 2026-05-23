# src/core/models.py
# V0 - Initial implementation
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
#   ResolvedJoin    — a join between two tables, with the ON condition
#   ResolvedFilter  — a user-driven filter condition (from the NL query)

from __future__ import annotations

import uuid
from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator, model_validator


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
    output_alias: str   # Label in the SELECT clause e.g. "CustomerName", "TopAccName"


class ResolvedJoin(BaseModel):
    """
    A JOIN between two tables, fully resolved from the schema relationships.

    Example:
        ResolvedJoin(
            join_type="INNER JOIN",
            table_name="Major.CustomerDemographics",
            alias="cd",
            on_left="c.CustomerID",
            on_right="cd.CustomerID"
        )
    """
    join_type: str  = "INNER JOIN"  # Defaults to INNER JOIN — only type used in Phase 1
    table_name: str                 # Full schema-qualified name of the joined table
    alias: str                      # Alias for the joined table in SQL
    on_left: str                    # Left side of ON condition e.g. "c.CustomerID"
    on_right: str                   # Right side of ON condition e.g. "cd.CustomerID"


class ResolvedFilter(BaseModel):
    """
    A user-driven filter condition extracted from the NL query.
    These come from what the user asked for — not from business rules.

    Example:
        ResolvedFilter(
            table_alias="c",
            column_name="CustomerCID",
            operator="=",
            value="ASA"
        )
    """
    table_alias: str    # Alias of the table e.g. "c"
    column_name: str    # Column to filter on e.g. "CustomerCID"
    operator: str       # SQL operator e.g. "=", ">", "LIKE"
    value: str          # Filter value e.g. "ASA"


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

    app_schema_version: str = ""
    # Populated by AppIdentifier from the schema's version field.

    # --- Input ---
    nl_query_original: str
    # The raw NL query exactly as the user typed it. NEVER modify this field.

    nl_query_corrected: Optional[str] = None
    # Phase 2 — spell-corrected version. None in Phase 1.

    # --- LLM outputs ---
    intent_output: Optional[dict[str, Any]] = None
    # Step 1 LLM result — populated by IntentExtractor.

    mapping_output: Optional[dict[str, Any]] = None
    # Step 2 LLM result — populated by SchemaMapper.

    # --- Validator outputs ---
    resolved_tables: list[str] = Field(default_factory=list)
    # Confirmed table names after validation.

    resolved_columns: list[str] = Field(default_factory=list)
    # Confirmed column names after validation.

    resolved_filters: list[str] = Field(default_factory=list)
    # Confirmed filter conditions after validation.

    resolved_joins: list[str] = Field(default_factory=list)
    # Join graph result after join resolution.

    applied_rules: list[str] = Field(default_factory=list)
    # Business rules injected by the rule applicator.

    # --- Final outputs ---
    structured_query: Optional[StructuredQuery] = None
    # Built by StructuredQueryBuilder. SQL Builder reads this.

    sql: Optional[str] = None
    # Final SQL string. Populated by SQLBuilder.

    # --- Observability ---
    latency_ms: dict[str, Any] = Field(default_factory=dict)
    # Per-stage timing. Key = stage name, value = milliseconds.

    token_usage: dict[str, Any] = Field(default_factory=dict)
    # LLM token usage. Keys: step1, step2, total.

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
        # Use object.__setattr__ to bypass our own override and set the flag directly.
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
