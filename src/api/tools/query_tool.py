# src/api/tools/query_tool.py
# V0 - Initial implementation
#
# Foundry tool endpoint: POST /v1/tools/query
#
# One-shot full pipeline endpoint for the Foundry agent.
# Accepts a QueryContext with only nl_query_original required,
# runs the complete pipeline via run_pipeline() (same orchestrator
# used by /v1/query), returns a ToolResponse with the fully
# populated QueryContext including context.sql.
#
# Why this endpoint exists alongside /v1/query:
#   - /v1/query        : user-facing, CLIENT_API_KEY, returns QueryResponse
#                        (clean SQL-focused shape for human/app consumption)
#   - /v1/tools/query  : Foundry-facing, FOUNDRY_API_KEY, returns ToolResponse
#                        (full QueryContext shape so agent can inspect every field:
#                         llm_output, resolved_tables, structured_query, sql, etc.)
#
# Both call the exact same run_pipeline() — zero code duplication.
#
# Architecture rules applied here:
#   - ContextValidator validates required fields FIRST.
#     Stage "query" requires: nl_query_original only.
#   - Intent Guard runs INSIDE run_pipeline() as Stage 2 —
#     this endpoint does NOT call it separately.
#   - Business errors (UNSUPPORTED_INTENT, APP_NOT_DETERMINED, etc.)
#     → HTTP 200 with error in context. Caller inspects context.status.
#   - Unexpected exceptions → HTTP 500.
#   - app.state carries schema_repo, llm_provider, settings —
#     injected at startup, read here via the request object.
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
from src.core.constants import INTERNAL_ERROR, MISSING_CONTEXT_FIELDS, REQUEST_RECEIVED
from src.core.exceptions import MissingContextFieldsError
from src.core.logging.log_models import LogEntry
from src.core.logging.logger import StructuredLogger
from src.core.models import QueryContext
from src.pipeline.orchestrator import run_pipeline

router = APIRouter()

# Single ContextValidator instance — built once, reused across all requests.
_context_validator = ContextValidator()


@router.post(
    "/query",
    summary="Run full pipeline",
    description=(
        "Foundry tool endpoint. Accepts a QueryContext with nl_query_original set, "
        "runs the complete pipeline (App Identifier → Intent Guard → NL-to-IR → "
        "Validator → SQL Builder), returns fully populated QueryContext including sql. "
        "Use this when the Foundry agent wants a one-shot full pipeline call instead "
        "of calling each stage endpoint individually."
    ),
    response_model=ToolResponse,
)
def tools_query(
    request: Request,
    context: QueryContext,
    _auth: None = Depends(require_foundry_key),
) -> JSONResponse:
    """
    POST /v1/tools/query

    FastAPI injects three things before this body runs:
      - request   : gives access to app.state (schema_repo, llm_provider, settings)
      - context   : QueryContext parsed from the HTTP request body
      - _auth     : require_foundry_key dependency — raises 401 before we get
                    here if the key is missing or wrong. We never inspect _auth.

    Returns:
        ToolResponse with fully updated QueryContext.
        HTTP 200 always (even on business errors — matches architecture rule).
        HTTP 400 only for missing context fields.
        HTTP 500 only for unexpected internal errors.
    """
    # ------------------------------------------------------------------
    # Read dependencies from app.state — set during lifespan startup.
    # ------------------------------------------------------------------
    settings = request.app.state.settings
    schema_repo = request.app.state.schema_repo
    llm_provider = request.app.state.llm_provider

    # Build a logger for this request
    logger = StructuredLogger(settings)

    # ------------------------------------------------------------------
    # Emit REQUEST_RECEIVED with caller="foundry"
    # Note: run_pipeline() also emits REQUEST_RECEIVED with caller="user".
    # We override that here by emitting BEFORE calling run_pipeline(),
    # so the log correctly reflects caller="foundry".
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
    # Stage "query" requires: nl_query_original only.
    # Missing fields → HTTP 400 immediately.
    # ------------------------------------------------------------------
    try:
        _context_validator.validate(context, stage_name="query")
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
    # Step 2 — Run full pipeline.
    # run_pipeline() handles all 5 stages internally:
    #   Stage 1: App Identifier
    #   Stage 2: Intent Guard  ← blocks non-select queries here
    #   Stage 3: NL-to-IR Strategy
    #   Stage 4: Validator chain
    #   Stage 5: SQL Builder
    #
    # run_pipeline() never raises business exceptions — it catches them
    # internally and converts them to context failures. Any exception
    # that escapes here is a genuine unexpected error → HTTP 500.
    # ------------------------------------------------------------------
    try:
        context = run_pipeline(
            context=context,
            schema_repo=schema_repo,
            llm_provider=llm_provider,
            logger=logger,
            settings=settings,
        )

    except Exception as exc:
        context.status = "failed"
        context.error = {
            "code": INTERNAL_ERROR,
            "message": f"Pipeline failed unexpectedly: {exc}",
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
    # Return updated context — status and error already set by pipeline.
    # On success: context.status = "success", context.sql populated.
    # On business error: context.status = "failed", context.error set.
    # ------------------------------------------------------------------
    error = context.error or {}
    errors = (
        [ErrorDetail(code=error["code"], message=error["message"])]
        if context.status == "failed" and error
        else []
    )

    return JSONResponse(
        status_code=200,
        content=ToolResponse(
            request_id=context.request_id,
            status=context.status,
            context=context,
            errors=errors,
        ).model_dump(),
    )
