# src/api/models/request.py
# V0 - Initial implementation
#
# HTTP request body models for all nl2sql-engine endpoints.
#
# Three models:
#   QueryRequest    — body for POST /v1/query (user-facing, full pipeline)
#   FeedbackRequest — body for POST /v1/feedback (user-facing, feedback submission)
#   ToolRequest     — body for POST /v1/tools/{stage} (Foundry agent, inherits QueryContext)
#
# Design note — ToolRequest inherits QueryContext:
#   Today it adds no extra fields — it is identical to QueryContext.
#   Tomorrow, if the Fabric agent needs to send extra metadata (e.g. agent_version,
#   trace_id, caller_system) we add those fields here without touching QueryContext.
#   QueryContext stays clean as the pipeline state object.
#   ToolRequest is the HTTP boundary model for Foundry endpoints.
#
# Design note — nl_query length validation:
#   Max length (from settings.sql.max_nl_query_length) is NOT enforced here.
#   Pydantic field constraints are class-level — they cannot read from YAML config.
#   Length validation is handled by the pipeline orchestrator where settings are available.

from __future__ import annotations

import uuid
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator

from src.core.models import QueryContext


# ---------------------------------------------------------------------------
# QueryRequest — user-facing POST /v1/query
# ---------------------------------------------------------------------------

class QueryRequest(BaseModel):
    """
    Request body for POST /v1/query.

    Sent by a human user or user-facing application.
    The engine runs the full pipeline and returns SQL.

    Example:
        {
            "nl_query": "give me customer name for customer CUST01 in Acme",
            "app_id": "Acme_app",
            "user_id": "user-123",
            "request_id": "optional-uuid"
        }
    """

    nl_query: str = Field(
        ...,                          # ... means required — no default value
        description="The natural language query from the user. Must not be empty."
    )

    app_id: Optional[str] = Field(
        default=None,
        description=(
            "Optional. If provided, the engine uses this app schema directly. "
            "If omitted, the engine detects the app from the NL query."
        )
    )

    user_id: str = Field(
        ...,
        description="Identifier for the user submitting the query."
    )

    request_id: str = Field(
        default_factory=lambda: str(uuid.uuid4()),
        description=(
            "Optional. Unique identifier for this request. "
            "Auto-generated UUID if not provided. "
            "Used for log correlation and tracing."
        )
    )

    @field_validator("nl_query")
    @classmethod
    def nl_query_must_not_be_empty(cls, value: str) -> str:
        """
        Rejects empty strings and whitespace-only strings.

        Why a validator instead of min_length=1:
            min_length=1 would accept a single space character " ".
            This validator strips whitespace before checking, so " " is also rejected.
        """
        if not value.strip():
            raise ValueError("nl_query must not be empty or whitespace only.")
        return value


# ---------------------------------------------------------------------------
# FeedbackRequest — user-facing POST /v1/feedback
# ---------------------------------------------------------------------------

class FeedbackRequest(BaseModel):
    """
    Request body for POST /v1/feedback.

    Allows users to report whether a generated SQL was correct or not.
    Logged for analysis — not used to change pipeline behaviour in Phase 1.

    Example:
        {
            "request_id": "uuid-of-original-query",
            "status": "fail",
            "expected_output": "SELECT CustomerName FROM ...",
            "actual_sql": "SELECT TOP 10000 ..."
        }
    """

    request_id: str = Field(
        ...,
        description="The request_id of the original query this feedback refers to."
    )

    status: Literal["pass", "fail"] = Field(
        ...,
        description=(
            "'pass' — the generated SQL was correct. "
            "'fail' — the generated SQL was wrong."
        )
    )
    # Literal["pass", "fail"] means Pydantic will reject any value other than
    # exactly "pass" or "fail". This is enforced at parse time with no extra code.

    expected_output: Optional[str] = Field(
        default=None,
        description="Optional. The SQL the user expected to receive."
    )

    actual_sql: Optional[str] = Field(
        default=None,
        description="Optional. The SQL the engine actually generated."
    )


# ---------------------------------------------------------------------------
# ToolRequest — Foundry tool endpoints POST /v1/tools/{stage}
# ---------------------------------------------------------------------------

class ToolRequest(QueryContext):
    """
    Request body for POST /v1/tools/{stage} (Foundry agent endpoints).

    Inherits all fields from QueryContext — the Fabric agent sends the full
    pipeline state as the request body. The stage reads what it needs,
    runs its logic, and returns the updated context in ToolResponse.

    Why inherit instead of wrap:
        Wrapping would force the agent to send {"context": {...all fields...}}
        which adds an unnecessary nesting layer. Inheriting means the agent
        sends the QueryContext fields directly at the top level — cleaner.

    Why inherit instead of using QueryContext directly:
        If the Fabric agent ever needs to send extra metadata alongside the
        context (e.g. agent_version, trace_id, caller_system), we add those
        fields here without changing QueryContext.

    Today: identical structure to QueryContext.
    Future: may add agent-specific fields here.
    """
    pass  # No extra fields in Phase 1 — inherits everything from QueryContext
