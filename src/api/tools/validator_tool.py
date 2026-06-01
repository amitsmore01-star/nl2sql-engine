# src/api/tools/validator_tool.py
# V0 - Initial implementation
# V1 - Story 4.6 fix: Catch SchemaLoadError separately before NL2SQLBaseError.
#      SchemaLoadError is an infrastructure error (HTTP 500), not a business
#      error (HTTP 200). Previously it was swallowed by the NL2SQLBaseError
#      handler and returned 200 incorrectly.
# V2 - Story 6.4: Removed route-level MissingContextFieldsError catch.
#      Now handled by global exception handler (middleware.py → HTTP 400).
#      Removed unused MISSING_CONTEXT_FIELDS and MissingContextFieldsError imports.
#
# Foundry tool endpoint: POST /v1/tools/validator
#
# Runs four pipeline stages in sequence:
#   1. Table/Column Validator — checks LLM-proposed tables and columns against schema
#   2. Join Resolver          — resolves join paths, assigns aliases, stamps roles
#   3. Rule Applicator        — applies business rules, versioning, hierarchy conditions
#   4. Structured Query Builder — translates enriched context into StructuredQuery model
#
# The agent must already have called /v1/tools/nl-to-ir before this endpoint
# (llm_output, app_id, and app_schema_version must be populated in the context).
#
# Architecture rules applied here:
#   - One function, two callers: all four stage functions are the same internal
#     functions called by the orchestrator. Zero code duplication.
#   - ContextValidator validates required fields FIRST before any stage runs.
#   - All validator business errors (NoRelevantTablesError, NoJoinPathError,
#     StructuredQueryBuildError, etc.) are caught as NL2SQLBaseError — single
#     handler, HTTP 200. All carry code + message via base class.
#     TECH DEBT: split into per-exception handlers if HTTP codes diverge — Phase 1 cleanup.
#   - app.state carries schema_repo, settings — injected at startup, read via request.
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
from src.core.exceptions import NL2SQLBaseError, SchemaLoadError
from src.core.logging.log_models import LogEntry
from src.core.logging.logger import StructuredLogger
from src.core.models import QueryContext
from src.validator.join_resolver import run_join_resolver
from src.validator.rule_applicator import run_rule_applicator
from src.validator.structured_query_builder import run_structured_query_builder
from src.validator.table_column_validator import run_table_column_validator

router = APIRouter()

# Single ContextValidator instance — built once, reused across all requests.
_context_validator = ContextValidator()


@router.post(
    "/validator",
    summary="Run full validator chain",
    description=(
        "Foundry tool endpoint. Accepts a QueryContext with llm_output already "
        "populated, runs the full validator chain (table/column validator → join "
        "resolver → rule applicator → structured query builder), returns the updated "
        "QueryContext with structured_query populated. Requires app_id, "
        "app_schema_version, and llm_output to already be set in the context "
        "(call /v1/tools/nl-to-ir first)."
    ),
    response_model=ToolResponse,
)
def tools_validator(
    request: Request,
    context: QueryContext,
    _auth: None = Depends(require_foundry_key),
) -> JSONResponse:
    """
    POST /v1/tools/validator

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
    # Read all dependencies from app.state — set during lifespan startup.
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

    
    _context_validator.validate(context, stage_name="validator")
        # ------------------------------------------------------------------
    # Step 2 — Run the full validator chain.
    # All four stages share the same schema_repo and logger.
    # All business errors are caught as NL2SQLBaseError — single handler.
    # TECH DEBT: split into per-exception handlers if HTTP codes diverge
    #            — Phase 1 cleanup.
    # ------------------------------------------------------------------
    try:
        context = run_table_column_validator(context, schema_repo, logger)
        context = run_join_resolver(context, schema_repo, logger)
        context = run_rule_applicator(context, schema_repo, logger)
        context = run_structured_query_builder(context, logger)

    except SchemaLoadError as exc:
        # Infrastructure error — schema could not be loaded for this app_id.
        # This is not a business error — return 500.
        context.status = "failed"
        context.error = {"code": exc.code, "message": exc.message}
        return JSONResponse(
            status_code=500,
            content=ToolResponse(
                request_id=context.request_id,
                status="failed",
                context=context,
                errors=[
                    ErrorDetail(
                        code=exc.code,
                        message=exc.message,
                    )
                ],
            ).model_dump(),
        )

    except NL2SQLBaseError as exc:
        context.status = "failed"
        context.error = {"code": exc.code, "message": exc.message}
        return JSONResponse(
            status_code=200,
            content=ToolResponse(
                request_id=context.request_id,
                status="failed",
                context=context,
                errors=[
                    ErrorDetail(
                        code=exc.code,
                        message=exc.message,
                    )
                ],
            ).model_dump(),
        )

    except Exception as exc:
        context.status = "failed"
        context.error = {
            "code": INTERNAL_ERROR,
            "message": f"Validator chain failed unexpectedly: {exc}",
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
    # Success — return updated context with structured_query populated.
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
