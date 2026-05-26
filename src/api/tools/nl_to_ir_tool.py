# src/api/tools/nl_to_ir_tool.py
# V0 - Initial implementation
#
# Foundry tool endpoint: POST /v1/tools/nl-to-ir
#
# Runs two pipeline stages in sequence:
#   1. Intent Guard  — deterministic keyword check, no LLM call
#   2. NL-to-IR Strategy — single LLM call, produces simplified IR
#
# The agent must already have called /v1/tools/app-identifier before this
# endpoint (app_id and app_schema_version must be populated in the context).
#
# Architecture rules applied here:
#   - One function, two callers: run_intent_guard() and strategy.execute()
#     are the same internal functions called by the orchestrator.
#     Zero code duplication.
#   - Tool endpoint validates required context fields FIRST via ContextValidator
#     before running any stage logic.
#   - Intent Guard runs before any LLM call — non-select queries never reach
#     the LLM.
#   - app.state carries schema_repo, llm_provider, settings — injected at
#     startup, read here via the request object.
#
# Auth pattern:
#   require_foundry_key is declared as a Depends() in the route signature.
#   FastAPI calls it automatically before the handler body runs.
#   It extracts X-API-Key via its own Depends(_api_key_header) and raises
#   HTTPException 401 if the key is missing or wrong.
#   The handler body never executes on auth failure.

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from src.api.auth import require_foundry_key
from src.api.models.response import ErrorDetail, ToolResponse
from src.api.tools.context_validator import ContextValidator
from src.core.constants import INTERNAL_ERROR, MISSING_CONTEXT_FIELDS, REQUEST_RECEIVED
from src.core.exceptions import MissingContextFieldsError
from src.core.logging.log_models import LogEntry
from src.core.logging.logger import StructuredLogger
from src.core.models import QueryContext
from src.pipeline.intent_guard import run_intent_guard
from src.pipeline.schema_summary import build_schema_summary
from src.pipeline.strategies.factory import NLToIRStrategyFactory

router = APIRouter()

# Single ContextValidator instance — built once, reused across all requests.
_context_validator = ContextValidator()


@router.post(
    "/nl-to-ir",
    summary="Run NL-to-IR Strategy stage",
    description=(
        "Foundry tool endpoint. Accepts a QueryContext, runs Intent Guard then "
        "the NL-to-IR Strategy (single LLM call), returns the updated QueryContext "
        "with llm_output populated. Requires app_id and app_schema_version to already "
        "be set in the context (call /v1/tools/app-identifier first)."
    ),
    response_model=ToolResponse,
)
def tools_nl_to_ir(
    request: Request,
    context: QueryContext,
    _auth: None = Depends(require_foundry_key),
) -> JSONResponse:
    """
    POST /v1/tools/nl-to-ir

    FastAPI injects three things before this body runs:
      - request   : gives access to app.state (schema_repo, llm_provider, settings)
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
    # Read all dependencies from app.state — set during lifespan startup.
    # ------------------------------------------------------------------
    settings = request.app.state.settings
    schema_repo = request.app.state.schema_repo
    llm_provider = request.app.state.llm_provider

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
    # Stage "nl-to-ir" requires: nl_query_original, app_id, app_schema_version.
    # Missing fields → HTTP 400 immediately.
    # ------------------------------------------------------------------
    try:
        _context_validator.validate(context, stage_name="nl-to-ir")
    except MissingContextFieldsError as exc:
        return JSONResponse(
            status_code=400,
            content={
                "status": "failed",
                "errors": [
                    {"code": MISSING_CONTEXT_FIELDS, "message": exc.message}
                ],
                "missing_fields": exc.missing_fields or [],
            },
        )

    # ------------------------------------------------------------------
    # Step 2 — Intent Guard
    # Deterministic keyword scan. Does not raise — sets context.status if
    # a blocked keyword is found. We stop and return immediately on failure.
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
    # Step 3 — NL-to-IR Strategy
    # Load the app schema, build summary, run the configured strategy.
    # Populates context.llm_output with the simplified IR.
    # ------------------------------------------------------------------
    try:
        app_schema = schema_repo.get_schema(context.app_id)
    except Exception as exc:
        context.status = "failed"
        context.error = {
            "code": INTERNAL_ERROR,
            "message": f"Failed to load schema for app '{context.app_id}': {exc}",
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

    schema_summary = build_schema_summary(app_schema)

    try:
        strategy = NLToIRStrategyFactory.create(settings, llm_provider, logger)
        context = strategy.execute(context, schema_summary)
    except Exception as exc:
        context.status = "failed"
        context.error = {
            "code": INTERNAL_ERROR,
            "message": f"NL-to-IR strategy failed: {exc}",
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
    # Success — return updated context with llm_output populated.
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
