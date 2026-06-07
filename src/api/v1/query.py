# src/api/v1/query.py
# V0 - Initial implementation
# V1 - Story 3.7: Replaced direct run_app_identifier() call with run_pipeline()
#                 (orchestrator). Response is now full QueryContext dict (temporary shape).
#                 Removed explicit AppNotDeterminedError / MultipleAppsMatchedError
#                 except blocks — orchestrator now catches these and converts them
#                 to context.status="failed" + context.error internally.
#                 REQUEST_RECEIVED log now emitted inside run_pipeline() — removed
#                 duplicate emit that was in V0.
#                 Added llm_provider read from app.state.
#                 TODO (Story 5.4): Replace temporary QueryContext response with final
#                 QueryResponse shape defined in Section 10.3 of architecture document.
#                 Remove this TODO marker when done.
# V2 - Story 5.4: Replaced temporary QueryContext response with final QueryResponse
#                 shape (Section 10.3). TODO marker removed.
#                 Emits RESPONSE_SENT log with status, total_latency_ms,
#                 total_tokens_used after pipeline completes.
#                 Business errors now in errors[] list (not context.error dict).
#                 data.sql populated from context.sql on success.
#
# POST /v1/query — user-facing query endpoint.
#
# What this file does:
#   1. Accepts QueryRequest body (nl_query, optional app_id, user_id, request_id)
#   2. Enforces CLIENT_API_KEY auth via Depends(require_client_key)
#   3. Builds an initial QueryContext from the request fields
#   4. Calls run_pipeline() — full 5-stage pipeline
#   5. Returns final QueryResponse shape (Section 10.3)
#   6. Business errors → HTTP 200, status="failed", errors[] list populated
#   7. Unexpected exceptions → INTERNAL_ERROR, HTTP 500
#
# TECH DEBT (flagged here for future story):
#   StructuredLogger currently has no Strategy pattern — switching log destination
#   (e.g. file → Azure Monitor) requires a code change. Should be refactored to
#   LogWriter ABC + factory + config key (logging.writer: jsonl_file) in a
#   future story before Phase 2.

import time

from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import JSONResponse

from src.api.auth import require_client_key
from src.api.models.request import QueryRequest
from src.core.constants import INTERNAL_ERROR, RESPONSE_SENT
from src.core.logging.log_models import LogEntry
from src.core.logging.logger import StructuredLogger
from src.core.models import QueryContext
from src.pipeline.orchestrator import run_pipeline

# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------
router = APIRouter()


@router.post("/query")
def query(
    request: Request,
    body: QueryRequest,
    _auth: None = Depends(require_client_key),
) -> JSONResponse:
    """
    POST /v1/query — Submit a natural language query, receive SQL.

    Runs full 5-stage pipeline and returns the final QueryResponse shape
    defined in architecture Section 10.3.

    Args:
        request: FastAPI Request — gives access to app.state (schema_repo,
                 llm_provider, settings).
        body:    Validated QueryRequest body from the HTTP request.
        _auth:   Auth dependency result — None on success, raises 401 on failure.

    Returns:
        JSONResponse with QueryResponse envelope.
        HTTP 200 on success and on business errors.
        HTTP 500 on unexpected internal errors.
    """
    request_start_ms = int(time.time() * 1000)

    schema_repo = request.app.state.schema_repo
    llm_provider = request.app.state.llm_provider
    settings = request.app.state.settings

    logger = StructuredLogger(settings)

    context = QueryContext(
        request_id=body.request_id,
        user_id=body.user_id,
        app_id=body.app_id or "",
        nl_query_original=body.nl_query,
    )

    try:
        if schema_repo is None:
            raise RuntimeError(
                "schema_repo is not initialised — startup may have failed."
            )

        context = run_pipeline(
            context=context,
            schema_repo=schema_repo,
            llm_provider=llm_provider,
            logger=logger,
            settings=settings,
        )

    except Exception as exc:
        # ------------------------------------------------------------------
        # Unexpected error — INTERNAL_ERROR
        # Full detail goes to the log only — never exposed to caller.
        # ------------------------------------------------------------------
        logger.log(
            LogEntry(
                stage=INTERNAL_ERROR,
                request_id=context.request_id,
                user_id=context.user_id,
                payload={
                    "error_type": type(exc).__name__,
                    "error_detail": str(exc),
                },
            )
        )
        total_ms = int(time.time() * 1000) - request_start_ms
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=_build_response(
                context=context,
                override_status="failed",
                errors=[{"code": INTERNAL_ERROR, "message": "An unexpected error occurred. Please check the logs."}],
                total_ms=total_ms,
            ),
        )

    # ------------------------------------------------------------------
    # Build final QueryResponse (Section 10.3)
    # ------------------------------------------------------------------
    total_ms = int(time.time() * 1000) - request_start_ms
    context.total_latency_ms = total_ms

    # Collect errors[] from context.error (set by orchestrator on business failures)
    errors = []
    if context.error:
        errors.append(context.error)

    response_body = _build_response(
        context=context,
        override_status=None,
        errors=errors,
        total_ms=total_ms,
    )

    # ------------------------------------------------------------------
    # Emit RESPONSE_SENT log
    # ------------------------------------------------------------------
    total_tokens = context.token_usage.get("total", 0) if context.token_usage else 0
    logger.log(
        LogEntry(
            stage=RESPONSE_SENT,
            request_id=context.request_id,
            user_id=context.user_id,
            app_id=context.app_id,
            app_schema_version=context.app_schema_version,
            payload={
                "status": context.status,
                "total_latency_ms": total_ms,
                "total_tokens_used": total_tokens,
            },
        )
    )

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=response_body,
    )


# ---------------------------------------------------------------------------
# Response builder — constructs the Section 10.3 envelope
# ---------------------------------------------------------------------------

def _build_response(
    context: QueryContext,
    override_status: str | None,
    errors: list[dict],
    total_ms: int,
) -> dict:
    """
    Build the final QueryResponse dict matching architecture Section 10.3.

    {
      "request_id": "...",
      "status":     "success | failed",
      "data": {
        "sql":              "SELECT TOP 10000 ...",
        "structured_query": { ... } | null,
        "warnings":         []
      },
      "meta": {
        "app_id":             "Acme_app",
        "app_schema_version": "1.0",
        "total_latency_ms":   310,
        "total_tokens_used":  2140
      },
      "errors": [
        { "code": "...", "message": "..." }
      ]
    }

    Args:
        context:         Pipeline state after all stages have run.
        override_status: Force a specific status string (used for 500 errors).
                         If None, uses context.status.
        errors:          List of error dicts to populate errors[].
        total_ms:        Total request latency in milliseconds.

    Returns:
        Dict ready to be serialised as JSON response body.
    """
    final_status = override_status if override_status is not None else context.status
    total_tokens = context.token_usage.get("total", 0) if context.token_usage else 0

    structured_query_dict = None
    if context.structured_query is not None:
        structured_query_dict = context.structured_query.model_dump()

    return {
        "request_id": context.request_id,
        "status": final_status,
        "data": {
            "sql": context.sql,
            "structured_query": structured_query_dict,
            "warnings": list(context.warnings),
        },
        "meta": {
            "app_id": context.app_id,
            "app_schema_version": context.app_schema_version,
            "total_latency_ms": total_ms,
            "total_tokens_used": total_tokens,
        },
        "errors": errors,
    }
