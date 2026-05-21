# src/core/logging/log_models.py
# V0 - Initial implementation
#
# Pydantic models for structured log entries.
# Every log entry written by StructuredLogger is validated against LogEntry.
# The payload field is flexible — each stage puts its own keys inside it.

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field


class LogEntry(BaseModel):
    """
    One structured log entry — written as a single JSON line (JSONL).

    Required fields:
        request_id  — unique ID for the request this entry belongs to
        stage       — which pipeline stage emitted this entry
                      (use constants from src/core/constants.py)

    Optional fields:
        user_id            — who made the request (Phase 1: "Phase1_user")
        app_id             — which app schema was used
        app_schema_version — version field from the app schema JSON
        latency_ms         — how long this stage took (None if not measured)
        payload            — arbitrary stage-specific data (tables, columns, SQL, etc.)
        timestamp_utc      — when this entry was created (auto-set to now if omitted)
    """

    # Required
    request_id: str
    stage: str

    # Optional — populated as pipeline progresses
    user_id: str | None = None
    app_id: str | None = None
    app_schema_version: str | None = None
    latency_ms: int | None = None
    payload: dict[str, Any] = Field(default_factory=dict)

    # Auto-populated — set to UTC now if caller does not provide it
    timestamp_utc: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
