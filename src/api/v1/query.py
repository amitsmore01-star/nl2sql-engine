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
#
# POST /v1/query — user-facing query endpoint.
#
# Story 3.7 scope — what this file does NOW:
#   1. Accepts QueryRequest body (nl_query, optional app_id, user_id, request_id)
#   2. Enforces CLIENT_API_KEY auth via Depends(require_client_key)
#   3. Builds an initial QueryContext from the request fields
#   4. Calls run_pipeline() — App Identifier → Intent Guard → NL-to-IR Strategy
#   5. Returns full QueryContext as response body (temporary — Story 5.4 finalises shape)
#   6. Business errors (APP_NOT_DETERMINED, UNSUPPORTED_INTENT etc.) → HTTP 200 with
#      context.status="failed" and context.error populated (set inside orchestrator)
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
from src.core.constants import INTERNAL_ERROR
from src.core.logging.log_models import LogEntry
from src.core.logging.logger import StructuredLogger
from src.core.models import QueryContext
from src.pipeline.orchestrator import run_pipeline

# ---------------------------------------------------------------------------
# Router
# APIRouter groups related endpoints. Registered in app.py with prefix="/v1".
# Result: this router handles POST /v1/query.
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

    Story 3.7: Calls run_pipeline() (orchestrator). Returns full QueryContext
    as temporary response body. SQL is None until Story 5.4.

    Args:
        request: FastAPI Request — gives access to app.state (schema_repo,
                 llm_provider, settings).
        body:    Validated QueryRequest body from the HTTP request.
        _auth:   Auth dependency result — None on success, raises 401 on failure.
                 Prefixed with _ to signal the return value is intentionally unused.

    Returns:
        JSONResponse with QueryContext body (temporary shape — Story 5.4 finalises).
        HTTP 200 on success and on business errors (APP_NOT_DETERMINED etc.).
        HTTP 500 on unexpected internal errors.
    """
    # ------------------------------------------------------------------
    # Pull shared state off app.state.
    # These are set during lifespan startup in app.py.
    # If startup failed, schema_repo may be None — handled in the
    # try/except below as an INTERNAL_ERROR.
    # ------------------------------------------------------------------
    schema_repo = request.app.state.schema_repo
    llm_provider = request.app.state.llm_provider
    settings = request.app.state.settings

    # ------------------------------------------------------------------
    # Build StructuredLogger.
    # One logger per request — writes to logs/{request_id}.log.
    # ------------------------------------------------------------------
    logger = StructuredLogger(settings)

    # ------------------------------------------------------------------
    # Build initial QueryContext from the request.
    #
    # QueryContext is the pipeline state object that travels through
    # every stage. We populate what we know from the request now.
    # Each subsequent stage will add its own outputs.
    #
    # app_id: use body.app_id if provided, else "" (app_identifier fills it in).
    # nl_query_original: the raw query — immutable after construction.
    # request_id: from body (auto-generated UUID if not provided by caller).
    # ------------------------------------------------------------------
    context = QueryContext(
        request_id=body.request_id,
        user_id=body.user_id,
        app_id=body.app_id or "",
        nl_query_original=body.nl_query,
    )

    # ------------------------------------------------------------------
    # Main pipeline try/except block.
    # Business errors (APP_NOT_DETERMINED, UNSUPPORTED_INTENT etc.) are
    # caught inside run_pipeline() and converted to context failures —
    # they never raise out to here.
    # Only truly unexpected exceptions (RuntimeError, AttributeError etc.)
    # reach this except block.
    # ------------------------------------------------------------------
    try:
        # Defensive check — schema_repo must be loaded.
        # This catches the case where app startup failed silently.
        if schema_repo is None:
            raise RuntimeError(
                "schema_repo is not initialised — startup may have failed."
            )

        # --------------------------------------------------------------
        # Run pipeline: App Identifier → Intent Guard → NL-to-IR Strategy
        # REQUEST_RECEIVED log is emitted inside run_pipeline().
        # Each stage reads from context and writes its outputs back.
        # Business errors set context.status="failed" — pipeline stops.
        # --------------------------------------------------------------
        context = run_pipeline(
            context=context,
            schema_repo=schema_repo,
            llm_provider=llm_provider,
            logger=logger,
            settings=settings,
        )

    # ------------------------------------------------------------------
    # Unexpected error — INTERNAL_ERROR
    # Full detail goes to the log only — never exposed to the caller.
    # HTTP 500.
    # ------------------------------------------------------------------
    except Exception as exc:
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
        context.status = "failed"
        context.error = {
            "code": INTERNAL_ERROR,
            "message": "An unexpected error occurred. Please check the logs.",
        }
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=context.model_dump(),
        )

    # ------------------------------------------------------------------
    # Return the full QueryContext as the response body.
    # Business errors: context.status="failed", context.error populated.
    # Success: context.status="success", context.llm_output populated.
    # Both return HTTP 200 — per architecture rule.
    # TODO (Story 5.4): Replace with final QueryResponse shape (Section 10.3).
    # Remove this TODO marker when done.
    # ------------------------------------------------------------------
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=context.model_dump(),
    )
