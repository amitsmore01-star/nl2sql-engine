# src/api/middleware.py
# V0 - Initial implementation
#
# Global exception handlers for the nl2sql-engine FastAPI application.
#
# WHY THIS EXISTS:
#   Every route handler has its own try/except block — but that is not a guarantee.
#   If any exception escapes a route handler (a future story written without a guard,
#   a bug in third-party code, or MissingContextFieldsError propagating uncaught),
#   FastAPI's default behaviour is a raw HTTP 500 with a Python traceback visible in
#   the response. That leaks internal implementation details and is a security risk.
#
#   This module registers two exception handlers that act as the final safety net:
#
#       MissingContextFieldsError → HTTP 400 (MISSING_CONTEXT_FIELDS)
#           The Foundry agent sent a QueryContext that is missing a required field
#           for this pipeline stage. That is a bad request — not a server error.
#           The response includes the curated exc.message so the agent knows what
#           to fix. Architecture Section 13.1: "The response body lists exactly which
#           fields are missing so the agent can fix its call."
#
#       Exception (catch-all) → HTTP 500 (INTERNAL_ERROR)
#           Any other unhandled exception. Full error detail goes to the log only.
#           The caller receives only a safe generic message — no stack traces,
#           no internal paths, no library versions.
#
# IMPORTANT — HTTPException and RequestValidationError guard:
#   Registering an Exception handler in FastAPI intercepts ALL exceptions including
#   FastAPI's own HTTPException (used for 401 auth failures) and RequestValidationError
#   (used for 422 Pydantic validation errors). We must delegate those back to
#   FastAPI's built-in handlers so auth and body validation continue to work normally.
#   The isinstance checks at the top of _handle_unhandled_exception do exactly that.
#
# HOW TO REGISTER:
#   Call register_exception_handlers(app) from create_app() in src/api/app.py,
#   immediately after the FastAPI instance is created and before any routers.
#   This ensures the handlers are in place before any route can raise.

import uuid

from fastapi import HTTPException, Request
from fastapi import status as http_status
from fastapi.exception_handlers import (
    http_exception_handler,
    request_validation_exception_handler,
)
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from src.core.constants import INTERNAL_ERROR, MISSING_CONTEXT_FIELDS
from src.core.exceptions import MissingContextFieldsError
from src.core.logging.log_models import LogEntry
from src.core.logging.logger import StructuredLogger


# ---------------------------------------------------------------------------
# Exception handlers
# ---------------------------------------------------------------------------

async def _handle_missing_context_fields(
    request: Request,
    exc: MissingContextFieldsError,
) -> JSONResponse:
    """
    Handle MissingContextFieldsError — HTTP 400.

    The Foundry agent sent a QueryContext missing a required field.
    The curated exc.message (set by the tool endpoint's ContextValidator)
    is safe to return — it tells the agent exactly which fields to fix.
    Full detail also written to the log for server-side visibility.
    """
    request_id = _get_or_generate_request_id(request)

    _try_log(
        request=request,
        request_id=request_id,
        stage=MISSING_CONTEXT_FIELDS,
        exc=exc,
    )

    return JSONResponse(
        status_code=http_status.HTTP_400_BAD_REQUEST,
        content={
            "request_id": request_id,
            "status": "failed",
            "errors": [
                {
                    "code": MISSING_CONTEXT_FIELDS,
                    "message": exc.message,
                }
            ],
        },
    )


async def _handle_unhandled_exception(
    request: Request,
    exc: Exception,
) -> JSONResponse:
    """
    Catch-all handler for any exception that escapes all route handlers — HTTP 500.

    GUARD: HTTPException and RequestValidationError are delegated back to
    FastAPI's built-in handlers so auth (401) and body validation (422)
    continue to work normally. Without this guard, registering an Exception
    handler would intercept all FastAPI-internal exceptions too.

    For all other exceptions:
        - Full error type + message → log only (never to caller)
        - Safe generic message → response
    """
    # Delegate FastAPI-internal exceptions to their own handlers
    if isinstance(exc, HTTPException):
        return await http_exception_handler(request, exc)
    if isinstance(exc, RequestValidationError):
        return await request_validation_exception_handler(request, exc)

    # Truly unhandled exception — log it and return a safe generic response
    request_id = _get_or_generate_request_id(request)

    _try_log(
        request=request,
        request_id=request_id,
        stage=INTERNAL_ERROR,
        exc=exc,
    )

    return JSONResponse(
        status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "request_id": request_id,
            "status": "failed",
            "errors": [
                {
                    "code": INTERNAL_ERROR,
                    "message": "An unexpected error occurred. Please check the logs.",
                }
            ],
        },
    )


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

def register_exception_handlers(app) -> None:
    """
    Register all global exception handlers on a FastAPI app instance.

    Called once from create_app() in src/api/app.py immediately after the
    FastAPI instance is created, before any routers are registered.

    Handlers are resolved by Starlette via the exception class MRO.
    Registering MissingContextFieldsError explicitly ensures it is matched
    before the generic Exception handler.

    Args:
        app: The FastAPI application instance.
    """
    app.add_exception_handler(
        MissingContextFieldsError,
        _handle_missing_context_fields,
    )
    app.add_exception_handler(
        Exception,
        _handle_unhandled_exception,
    )


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _get_or_generate_request_id(request: Request) -> str:
    """
    Return the request_id if a route handler already set it on request.state,
    otherwise generate a new UUID.

    Route handlers set request.state.request_id when they build the QueryContext.
    For exceptions raised before or outside route handlers, we generate a fresh
    UUID so the log entry and response always have a traceable ID.
    """
    return getattr(request.state, "request_id", None) or str(uuid.uuid4())


def _try_log(
    request: Request,
    request_id: str,
    stage: str,
    exc: Exception,
) -> None:
    """
    Write an error log entry via StructuredLogger.

    Silently skips logging if app.state.settings is not available (e.g. the
    exception was raised during startup before settings loaded).

    Never raises — a logging failure must never prevent the structured error
    response from being returned to the caller.

    Args:
        request:    FastAPI Request — used to access app.state.settings and
                    the request URL path for the log payload.
        request_id: Correlation ID for this request (real or generated).
        stage:      Log stage constant (INTERNAL_ERROR or MISSING_CONTEXT_FIELDS).
        exc:        The exception that was raised.
    """
    try:
        settings = getattr(request.app.state, "settings", None)
        if settings is None:
            return

        logger = StructuredLogger(settings)
        logger.log(
            LogEntry(
                stage=stage,
                request_id=request_id,
                payload={
                    "error_type": type(exc).__name__,
                    "error_detail": str(exc),
                    "path": request.url.path,
                },
            )
        )
    except Exception:
        # Never let a logging failure block the error response
        pass
