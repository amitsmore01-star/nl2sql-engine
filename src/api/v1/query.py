# src/api/v1/query.py
# V0 - Initial implementation
#
# POST /v1/query — user-facing query endpoint (skeleton).
#
# Story 2.6 scope — what this file does NOW:
#   1. Accepts QueryRequest body (nl_query, optional app_id, user_id, request_id)
#   2. Enforces CLIENT_API_KEY auth via require_client_key dependency
#   3. Emits REQUEST_RECEIVED log entry
#   4. Builds an initial QueryContext from the request fields
#   5. Calls run_app_identifier() to identify the app schema
#   6. Returns QueryResponse with identified app in meta — sql is None (pipeline not wired yet)
#   7. Business errors (APP_NOT_DETERMINED etc.) → QueryResponse with errors[], HTTP 200
#   8. Unexpected exceptions → INTERNAL_ERROR, HTTP 500
#
# Future stories will wire in the full pipeline (intent extractor, schema mapper,
# validator, SQL builder) after each stage is built.
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
from src.api.models.response import ErrorDetail, QueryResponse, QueryResponseMeta
from src.core.constants import (
    APP_NOT_DETERMINED,
    INTERNAL_ERROR,
    MULTIPLE_APPS_MATCHED,
    REQUEST_RECEIVED,
)
from src.core.exceptions import AppNotDeterminedError, MultipleAppsMatchedError
from src.core.logging.log_models import LogEntry
from src.core.models import QueryContext
from src.validator.app_identifier import run_app_identifier

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

    Story 2.6: Returns identified app in meta. sql is None until pipeline wired.

    Args:
        request: FastAPI Request — gives access to app.state (schema_repo, settings).
        body:    Validated QueryRequest body from the HTTP request.
        _auth:   Auth dependency result — None on success, raises 401 on failure.
                 Prefixed with _ to signal the return value is intentionally unused.

    Returns:
        JSONResponse with QueryResponse body.
        HTTP 200 on success and on business errors (APP_NOT_DETERMINED etc.).
        HTTP 500 on unexpected internal errors.
    """
    start_time = time.monotonic()

    # ------------------------------------------------------------------
    # Pull shared state off app.state.
    # These are set during lifespan startup in app.py.
    # If startup failed, schema_repo may be None — handled in the
    # try/except below as an INTERNAL_ERROR.
    # ------------------------------------------------------------------
    schema_repo = request.app.state.schema_repo
    settings = request.app.state.settings

    # ------------------------------------------------------------------
    # Build StructuredLogger.
    # One logger per request — writes to logs/{request_id}.log.
    # Uses request_id from the body (auto-generated UUID if not provided).
    # ------------------------------------------------------------------
    from src.core.logging.logger import StructuredLogger
    logger = StructuredLogger(settings)

    # ------------------------------------------------------------------
    # Emit REQUEST_RECEIVED log — first thing, before any processing.
    # "caller": "user" distinguishes this from Foundry tool calls in logs.
    # ------------------------------------------------------------------
    logger.log(
        LogEntry(
            stage=REQUEST_RECEIVED,
            request_id=body.request_id,
            user_id=body.user_id,
            app_id=body.app_id or "",
            payload={
                "nl_query_original": body.nl_query,
                "caller": "user",
            },
        )
    )

    # ------------------------------------------------------------------
    # Main pipeline try/except block.
    # Catches specific business errors (known, structured responses)
    # and any unexpected exception (INTERNAL_ERROR, HTTP 500).
    # ------------------------------------------------------------------
    try:
        # Defensive check — schema_repo must be loaded.
        # This catches the case where app startup failed silently.
        if schema_repo is None:
            raise RuntimeError("schema_repo is not initialised — startup may have failed.")

        # --------------------------------------------------------------
        # Build initial QueryContext from the request.
        #
        # QueryContext is the pipeline state object that travels through
        # every stage. We populate what we know from the request now.
        # Each subsequent stage will add its own outputs.
        #
        # app_id: use body.app_id if provided, else "" (app_identifier fills it in).
        # nl_query_original: the raw query — immutable after construction.
        # --------------------------------------------------------------
        context = QueryContext(
            request_id=body.request_id,
            user_id=body.user_id,
            app_id=body.app_id or "",
            nl_query_original=body.nl_query,
        )

        # --------------------------------------------------------------
        # Stage 1 — App Identifier
        # Matches the NL query to an app schema.
        # Populates context.app_id and context.app_schema_version.
        # Raises AppNotDeterminedError or MultipleAppsMatchedError on failure.
        # --------------------------------------------------------------
        context = run_app_identifier(context, schema_repo, logger)

        # --------------------------------------------------------------
        # Future stages go here (Sprint 3+):
        #   context = run_intent_extractor(context, llm_provider, logger)
        #   context = run_schema_mapper(context, llm_provider, logger)
        #   context = run_validator(context, schema_repo, logger)
        #   context = run_sql_builder(context, settings, logger)
        # --------------------------------------------------------------

        # --------------------------------------------------------------
        # Calculate total latency so far.
        # int() truncates — milliseconds are whole numbers.
        # --------------------------------------------------------------
        total_latency = int((time.monotonic() - start_time) * 1000)

        # --------------------------------------------------------------
        # Build and return success response.
        # sql is None — SQL builder not wired yet (Story 5.4).
        # total_tokens_used is 0 — LLM not wired yet (Story 3.5).
        # --------------------------------------------------------------
        response_body = QueryResponse(
            request_id=body.request_id,
            status="success",
            meta=QueryResponseMeta(
                app_id=context.app_id,
                app_schema_version=context.app_schema_version,
                total_latency_ms=total_latency,
                total_tokens_used=0,
            ),
        )
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content=response_body.model_dump(),
        )

    # ------------------------------------------------------------------
    # Business error — APP_NOT_DETERMINED
    # No app schema matched the NL query.
    # HTTP 200 — the pipeline handled this gracefully (architecture rule).
    # ------------------------------------------------------------------
    except AppNotDeterminedError as exc:
        response_body = QueryResponse(
            request_id=body.request_id,
            status="failed",
            errors=[ErrorDetail(code=exc.code, message=exc.message)],
        )
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content=response_body.model_dump(),
        )

    # ------------------------------------------------------------------
    # Business error — MULTIPLE_APPS_MATCHED
    # NL query matched 2+ app schemas — ambiguous.
    # HTTP 200 — same rule as above.
    # ------------------------------------------------------------------
    except MultipleAppsMatchedError as exc:
        response_body = QueryResponse(
            request_id=body.request_id,
            status="failed",
            errors=[ErrorDetail(code=exc.code, message=exc.message)],
        )
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content=response_body.model_dump(),
        )

    # ------------------------------------------------------------------
    # Unexpected error — INTERNAL_ERROR
    # Anything not caught above: RuntimeError, AttributeError, etc.
    # HTTP 500 — the service failed unexpectedly.
    # Full detail goes to the log only — never exposed to the caller.
    # ------------------------------------------------------------------
    except Exception as exc:
        # Log the raw error detail for debugging — never sent to client
        logger.log(
            LogEntry(
                stage=INTERNAL_ERROR,
                request_id=body.request_id,
                user_id=body.user_id,
                payload={
                    "error_type": type(exc).__name__,
                    "error_detail": str(exc),
                },
            )
        )
        response_body = QueryResponse(
            request_id=body.request_id,
            status="failed",
            errors=[
                ErrorDetail(
                    code=INTERNAL_ERROR,
                    message="An unexpected error occurred. Please check the logs.",
                )
            ],
        )
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=response_body.model_dump(),
        )
