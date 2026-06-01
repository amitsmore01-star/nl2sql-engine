# src/api/tools/app_identifier_tool.py
# V0 - Initial implementation
# V1 - Story 6.4: Removed route-level MissingContextFieldsError catch.
#      Now handled by global exception handler (middleware.py → HTTP 400).
#      Removed unused MISSING_CONTEXT_FIELDS and MissingContextFieldsError imports.
#
# Foundry tool endpoint: POST /v1/tools/app-identifier
#
# First stop on the Foundry tool belt. Accepts a raw NL query context,
# runs Intent Guard, then identifies which app schema the query belongs to.
# Returns updated QueryContext with app_id and app_schema_version populated.
#
# This is the same run_app_identifier() function called by the full pipeline
# orchestrator — exposed here as a standalone HTTP endpoint so the Foundry
# agent can call it independently before proceeding to /v1/tools/nl-to-ir.
#
# Architecture rules applied here:
#   - One function, two callers: run_app_identifier() is the same internal
#     function called by the orchestrator. Zero code duplication.
#   - ContextValidator validates required fields FIRST before any stage runs.
#   - Stage "app-identifier" requires: nl_query_original only.
#     app_id is NOT required — this stage PRODUCES it.
#   - Intent Guard runs before app identifier — non-select queries are
#     blocked before any schema matching occurs.
#   - Business errors (APP_NOT_DETERMINED, MULTIPLE_APPS_MATCHED) → HTTP 200
#     with error populated in context. Caller inspects context.status.
#   - Unexpected exceptions → HTTP 500.
#   - app.state carries schema_repo and settings — injected at startup,
#     read here via the request object.
#
# Auth pattern:
#   require_foundry_key is declared as a Depends() in the route signature.
#   FastAPI calls it automatically before the handler body runs.
#   It raises HTTPException 401 if the key is missing or wrong.
#   The handler body never executes on auth failure.

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from src.api.auth import require_foundry_key
from src.api.models.response import ErrorDetail, ToolResponse
from src.api.tools.context_validator import ContextValidator
from src.core.constants import (
    APP_NOT_DETERMINED,
    INTERNAL_ERROR,
    MULTIPLE_APPS_MATCHED,
    REQUEST_RECEIVED,
)
from src.core.exceptions import (
    AppNotDeterminedError,
    MultipleAppsMatchedError,
)
from src.core.logging.log_models import LogEntry
from src.core.logging.logger import StructuredLogger
from src.core.models import QueryContext
from src.pipeline.intent_guard import run_intent_guard
from src.validator.app_identifier import run_app_identifier

router = APIRouter()

# Single ContextValidator instance — built once, reused across all requests.
_context_validator = ContextValidator()


@router.post(
    "/app-identifier",
    summary="Run App Identifier stage",
    description=(
        "Foundry tool endpoint. Accepts a QueryContext with nl_query_original set, "
        "runs Intent Guard then identifies the app schema from the query. "
        "Returns updated QueryContext with app_id and app_schema_version populated. "
        "This must be called before /v1/tools/nl-to-ir."
    ),
    response_model=ToolResponse,
)
def tools_app_identifier(
    request: Request,
    context: QueryContext,
    _auth: None = Depends(require_foundry_key),
) -> JSONResponse:
    """
    POST /v1/tools/app-identifier

    FastAPI injects three things before this body runs:
      - request   : gives access to app.state (schema_repo, settings)
      - context   : QueryContext parsed from the HTTP request body
      - _auth     : require_foundry_key dependency — raises 401 before we get
                    here if the key is missing or wrong. We never inspect _auth.

    Returns:
        ToolResponse with updated QueryContext. HTTP 200 always (even on business
        errors — matches architecture rule: business errors are 200, not 4xx/5xx).
        HTTP 400 only for missing context fields.
        HTTP 500 only for unexpected internal errors.
    """
    # ------------------------------------------------------------------
    # Read dependencies from app.state — set during lifespan startup.
    # ------------------------------------------------------------------
    settings = request.app.state.settings
    schema_repo = request.app.state.schema_repo

    # Build a logger for this request
    logger = StructuredLogger(settings)

    # ------------------------------------------------------------------
    # Emit REQUEST_RECEIVED with caller="foundry"
    # ------------------------------------------------------------------
    logger.log(
        LogEntry(
            stage=REQUEST_RECEIVED,
            request_id=context.request_id,
            user_id=context.user_id,
            app_id=context.app_id,
            app_schema_version=context.app_schema_version,
            payload={
                "nl_query_original": context.nl_query_original,
                "caller": "foundry",
            },
        )
    )

    # ------------------------------------------------------------------
    # Step 1 — Validate required context fields for this stage.
    # Stage "app-identifier" requires: nl_query_original only.
    # Missing fields → HTTP 400 immediately.
    # ------------------------------------------------------------------
    _context_validator.validate(context, stage_name="app-identifier")
    # ------------------------------------------------------------------
    # Step 2 — Intent Guard
    # Deterministic keyword scan. Does not raise — sets context.status if
    # a blocked keyword is found. Stop and return immediately on failure.
    # App identifier never runs for non-select queries.
    # ------------------------------------------------------------------
    context = run_intent_guard(context, logger)
    if context.status == "failed":
        error = context.error or {}
        return JSONResponse(
            status_code=200,
            content=ToolResponse(
                request_id=context.request_id,
                status="failed",
                context=context,
                errors=[
                    ErrorDetail(
                        code=error.get("code", INTERNAL_ERROR),
                        message=error.get("message", "Intent guard blocked the query."),
                    )
                ],
            ).model_dump(),
        )

    # ------------------------------------------------------------------
    # Step 3 — App Identifier
    # Matches nl_query_original against app schema synonyms.
    # Populates context.app_id and context.app_schema_version on success.
    #
    # AppNotDeterminedError   → no app matched → HTTP 200, APP_NOT_DETERMINED
    # MultipleAppsMatchedError → ambiguous match → HTTP 200, MULTIPLE_APPS_MATCHED
    # Any other exception     → unexpected failure → HTTP 500
    # ------------------------------------------------------------------
    try:
        context = run_app_identifier(context, schema_repo, logger)

    except AppNotDeterminedError as exc:
        context.status = "failed"
        context.error = {
            "code": APP_NOT_DETERMINED,
            "message": str(exc),
        }
        return JSONResponse(
            status_code=200,
            content=ToolResponse(
                request_id=context.request_id,
                status="failed",
                context=context,
                errors=[
                    ErrorDetail(
                        code=APP_NOT_DETERMINED,
                        message=str(exc),
                    )
                ],
            ).model_dump(),
        )

    except MultipleAppsMatchedError as exc:
        context.status = "failed"
        context.error = {
            "code": MULTIPLE_APPS_MATCHED,
            "message": str(exc),
        }
        return JSONResponse(
            status_code=200,
            content=ToolResponse(
                request_id=context.request_id,
                status="failed",
                context=context,
                errors=[
                    ErrorDetail(
                        code=MULTIPLE_APPS_MATCHED,
                        message=str(exc),
                    )
                ],
            ).model_dump(),
        )

    except Exception as exc:
        context.status = "failed"
        context.error = {
            "code": INTERNAL_ERROR,
            "message": f"App identifier failed unexpectedly: {exc}",
        }
        return JSONResponse(
            status_code=500,
            content=ToolResponse(
                request_id=context.request_id,
                status="failed",
                context=context,
                errors=[
                    ErrorDetail(
                        code=INTERNAL_ERROR,
                        message=context.error["message"],
                    )
                ],
            ).model_dump(),
        )

    # ------------------------------------------------------------------
    # Success — set status and return updated context with app_id and
    # app_schema_version populated.
    # run_app_identifier() does not set status='success' — the endpoint
    # is responsible for marking the final outcome.
    # ------------------------------------------------------------------
    context.status = "success"
    return JSONResponse(
        status_code=200,
        content=ToolResponse(
            request_id=context.request_id,
            status=context.status,
            context=context,
            errors=[],
        ).model_dump(),
    )
