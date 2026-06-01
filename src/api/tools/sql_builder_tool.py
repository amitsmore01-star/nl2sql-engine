# src/api/tools/sql_builder_tool.py
# V0 - Initial implementation
# V1 - Story 6.4: Removed route-level MissingContextFieldsError catch.
#      Now handled by global exception handler (middleware.py → HTTP 400).
#      Removed unused MISSING_CONTEXT_FIELDS and MissingContextFieldsError imports.
#
# Foundry tool endpoint: POST /v1/tools/sql-builder
#
# Accepts a QueryContext with structured_query already populated (validator
# stage must have run first), calls run_sql_builder(), returns updated
# QueryContext with context.sql populated.
#
# Architecture rules applied here:
#   - One function, two callers: run_sql_builder() is the same internal
#     function called by the orchestrator. Zero code duplication.
#   - ContextValidator validates required fields FIRST before any stage runs.
#   - Stage "sql_builder" requires: structured_query.
#   - Business errors from run_sql_builder() (status="failed" on return)
#     are surfaced via ToolResponse — HTTP 200.
#   - Unexpected exceptions → HTTP 500.
#   - app.state carries settings — injected at startup, read via request.
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
from src.core.constants import INTERNAL_ERROR, REQUEST_RECEIVED
from src.core.logging.log_models import LogEntry
from src.core.logging.logger import StructuredLogger
from src.core.models import QueryContext
from src.sql.sql_builder import run_sql_builder

router = APIRouter()

# Single ContextValidator instance — built once, reused across all requests.
_context_validator = ContextValidator()


@router.post(
    "/sql-builder",
    summary="Run SQL builder",
    description=(
        "Foundry tool endpoint. Accepts a QueryContext with structured_query "
        "already populated, runs the SQL builder, returns the updated QueryContext "
        "with context.sql populated. Requires structured_query to already be set "
        "(call /v1/tools/validator first)."
    ),
    response_model=ToolResponse,
)
def tools_sql_builder(
    request: Request,
    context: QueryContext,
    _auth: None = Depends(require_foundry_key),
) -> JSONResponse:
    """
    POST /v1/tools/sql-builder

    FastAPI injects three things before this body runs:
      - request   : gives access to app.state (settings)
      - context   : QueryContext parsed from the HTTP request body
      - _auth     : require_foundry_key dependency — raises 401 before we get
                    here if the key is missing or wrong. We never inspect _auth.

    Returns:
        ToolResponse with updated QueryContext. HTTP 200 on success or business
        error. HTTP 400 for missing context fields. HTTP 500 for unexpected errors.
    """
    # ------------------------------------------------------------------
    # Read dependencies from app.state — set during lifespan startup.
    # ------------------------------------------------------------------
    settings = request.app.state.settings

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
    # Stage "sql_builder" requires: structured_query.
    # Missing fields → HTTP 400 immediately.
    # ------------------------------------------------------------------
    _context_validator.validate(context, stage_name="sql-builder")
        # ------------------------------------------------------------------
    # Step 2 — Run SQL builder.
    # run_sql_builder() never raises on missing structured_query — it sets
    # context.status="failed" and returns. That case is already blocked above
    # by the context validator, but all other unexpected errors propagate
    # to the except block below.
    # ------------------------------------------------------------------
    try:
        context = run_sql_builder(context, logger, settings)

    except Exception as exc:
        context.status = "failed"
        context.error = {
            "code": INTERNAL_ERROR,
            "message": f"SQL builder failed unexpectedly: {exc}",
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
    # Success — return updated context with sql populated.
    # ------------------------------------------------------------------
    return JSONResponse(
        status_code=200,
        content=ToolResponse(
            request_id=context.request_id,
            status=context.status,
            context=context,
            errors=[],
        ).model_dump(),
    )
