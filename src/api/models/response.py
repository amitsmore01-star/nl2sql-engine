# src/api/models/response.py
# V0 - Initial implementation
#
# HTTP response envelope models for all nl2sql-engine endpoints.
#
# Models:
#   ErrorDetail        — shared error block: {"code": "...", "message": "..."}
#   QueryResponseData  — the "data" block inside QueryResponse
#   QueryResponseMeta  — the "meta" block inside QueryResponse
#   QueryResponse      — full envelope for POST /v1/query (user-facing)
#   ToolResponse       — full envelope for POST /v1/tools/{stage} (Foundry)
#
# Both response types share ErrorDetail.
# QueryResponse wraps data + meta blocks (user-friendly, SQL-focused).
# ToolResponse wraps the full updated QueryContext (agent-friendly, context-focused).

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field

from src.core.models import QueryContext, StructuredQuery


# ---------------------------------------------------------------------------
# ErrorDetail — shared error block used in all response types
# ---------------------------------------------------------------------------

class ErrorDetail(BaseModel):
    """
    A single structured error.
    Used in the errors[] list of both QueryResponse and ToolResponse.

    Example:
        {"code": "NO_JOIN_PATH", "message": "No join path found between ..."}
    """
    code: str = Field(
        ...,
        description="Machine-readable error code. Matches a constant in src/core/constants.py."
    )
    message: str = Field(
        ...,
        description="Human-readable explanation of what went wrong."
    )


# ---------------------------------------------------------------------------
# QueryResponseData — the "data" block inside QueryResponse
# ---------------------------------------------------------------------------

class QueryResponseData(BaseModel):
    """
    The data payload inside a QueryResponse.
    Contains the SQL and supporting information the user cares about.

    sql and structured_query are None when status = "failed".
    warnings is always present — empty list when no warnings.

    Example:
        {
            "sql": "SELECT TOP 10000 ...",
            "structured_query": { ... full StructuredQuery ... },
            "warnings": []
        }
    """
    sql: Optional[str] = Field(
        default=None,
        description="The generated SQL string. None if pipeline failed."
    )

    structured_query: Optional[StructuredQuery] = Field(
        default=None,
        description=(
            "The full validated SQL blueprint produced by the deterministic validator. "
            "Contains all resolved tables, columns, joins, filters, and applied rules. "
            "None if pipeline failed before the validator completed."
        )
    )

    warnings: list[str] = Field(
        default_factory=list,
        description="Non-fatal issues encountered during processing. Empty list if none."
    )


# ---------------------------------------------------------------------------
# QueryResponseMeta — the "meta" block inside QueryResponse
# ---------------------------------------------------------------------------

class QueryResponseMeta(BaseModel):
    """
    Observability metadata inside a QueryResponse.
    Contains timing, token usage, and schema version information.

    Example:
        {
            "app_id": "Acme_app",
            "app_schema_version": "1.0",
            "total_latency_ms": 310,
            "total_tokens_used": 2140
        }
    """
    app_id: str = Field(
        ...,
        description="The app schema that was used to process this query."
    )

    app_schema_version: str = Field(
        ...,
        description="Version of the app schema used. Matches the version field in the schema JSON."
    )

    total_latency_ms: int = Field(
        ...,
        description="Total end-to-end processing time in milliseconds."
    )

    total_tokens_used: int = Field(
        ...,
        description="Total LLM tokens consumed across all steps (step1 + step2)."
    )


# ---------------------------------------------------------------------------
# QueryResponse — full envelope for POST /v1/query (user-facing)
# ---------------------------------------------------------------------------

class QueryResponse(BaseModel):
    """
    Full HTTP response envelope for POST /v1/query.

    Returned to the user-facing application after the full pipeline runs.
    Structured for human/app consumption — SQL-focused, not context-focused.

    Structure:
        {
            "request_id": "uuid",
            "status": "success | failed | cancelled",
            "data": {
                "sql": "SELECT TOP 10000 ...",
                "structured_query": { ... },
                "warnings": []
            },
            "meta": {
                "app_id": "Acme_app",
                "app_schema_version": "1.0",
                "total_latency_ms": 310,
                "total_tokens_used": 2140
            },
            "errors": []
        }
    """

    request_id: str = Field(
        ...,
        description="Unique identifier for this request. Matches the request_id in the original request."
    )

    status: str = Field(
        ...,
        description="Pipeline outcome: 'success' | 'failed' | 'cancelled'"
    )

    data: QueryResponseData = Field(
        default_factory=QueryResponseData,
        description="The SQL and supporting data. Fields are None on failure."
    )

    meta: Optional[QueryResponseMeta] = Field(
        default=None,
        description=(
            "Observability metadata — app, version, timing, tokens. "
            "May be None if pipeline failed before app identification."
        )
    )

    errors: list[ErrorDetail] = Field(
        default_factory=list,
        description="Structured errors. Empty on success. One or more entries on failure."
    )


# ---------------------------------------------------------------------------
# ToolResponse — full envelope for POST /v1/tools/{stage} (Foundry)
# ---------------------------------------------------------------------------

class ToolResponse(BaseModel):
    """
    Full HTTP response envelope for POST /v1/tools/{stage}.

    Returned to the Fabric agent after a single pipeline stage runs.
    Structured for agent consumption — context-focused, not SQL-focused.

    The agent sends a QueryContext, the stage runs, the updated QueryContext
    is returned under the "context" key. The agent reads whatever fields it
    needs and passes the context to the next stage.

    Structure:
        {
            "request_id": "uuid",
            "status": "success | failed",
            "context": {
                ... all QueryContext fields ...
                "intent_output": { ... },   ← populated by intent-extractor stage
            },
            "errors": []
        }
    """

    request_id: str = Field(
        ...,
        description="Unique identifier for this request. Matches QueryContext.request_id."
    )

    status: str = Field(
        ...,
        description="Stage outcome: 'success' | 'failed'"
    )

    context: Optional[QueryContext] = Field(
        default=None,
        description=(
            "The updated QueryContext after the stage ran. "
            "Contains all fields the agent sent, plus the stage's output fields now populated. "
            "None only if the request was so malformed the context could not be parsed."
        )
    )

    errors: list[ErrorDetail] = Field(
        default_factory=list,
        description="Structured errors. Empty on success. One or more entries on failure."
    )
