# src/pipeline/orchestrator.py
# V0 - Initial implementation (partial — Stories 4.x and 5.4 add validator + SQL builder)
#
# Wires the first three pipeline stages in sequence:
#   1. App Identifier     — detect which app schema the query refers to
#   2. Intent Guard       — block non-SELECT keywords before any LLM call
#   3. NL-to-IR Strategy  — single LLM call, produces simplified IR in context.llm_output
#
# Design rules:
#   - Each stage is called via its own internal function (run_app_identifier, etc.)
#   - Both /v1/query and /v1/tools/query call run_pipeline() — zero duplication
#   - If any stage sets context.status = "failed", the pipeline stops immediately
#   - Exceptions raised by stages are caught here and converted into context failures
#     so callers always receive a context object, never a raw exception from a
#     business error
#   - The orchestrator never inspects the *content* of errors — only checks status
#
# TODO (Story 5.4): Add run_validator() and run_sql_builder() stages after NL-to-IR.
#                   Replace temporary QueryContext response in query.py with final
#                   QueryResponse shape and remove this TODO marker.

from src.core.models import QueryContext
from src.core.constants import REQUEST_RECEIVED, INTERNAL_ERROR
from src.core.logging.logger import StructuredLogger
from src.core.logging.log_models import LogEntry
from src.schema.schema_repository import SchemaRepository
from src.llm.base import LLMProvider
from src.validator.app_identifier import run_app_identifier
from src.pipeline.intent_guard import run_intent_guard
from src.pipeline.strategies.factory import NLToIRStrategyFactory
from src.pipeline.schema_summary import build_schema_summary
from src.core.exceptions import AppNotDeterminedError, MultipleAppsMatchedError


def run_pipeline(
    context: QueryContext,
    schema_repo: SchemaRepository,
    llm_provider: LLMProvider,
    logger: StructuredLogger,
    settings,
) -> QueryContext:
    """
    Run the partial pipeline: App Identifier → Intent Guard → NL-to-IR Strategy.

    Each stage reads from context and writes its outputs back to context.
    If any stage fails — either by raising a known business exception or by
    setting context.status = "failed" — the pipeline stops and returns the
    context so the caller can inspect the error.

    Known business exceptions (AppNotDeterminedError, MultipleAppsMatchedError)
    are caught here and converted into context failures. Callers (query.py,
    tool endpoints) always receive a context object — never a raw business exception.

    Args:
        context:      Pipeline state object. nl_query_original must be set.
        schema_repo:  Loaded schema repository — passed to App Identifier.
        llm_provider: LLM provider instance — passed to NL-to-IR Strategy.
        logger:       StructuredLogger — passed to every stage.
        settings:     Loaded Settings object (src.config.settings.Settings).
                      Needed by NLToIRStrategyFactory to select the strategy
                      and example set. Not type-hinted here to avoid a
                      circular import — Settings imports nothing from pipeline.

    Returns:
        The context object after all stages have run (or after the first failure).
        context.status = "success" on clean run.
        context.status = "failed" + context.error populated on any failure.
    """
    # ------------------------------------------------------------------
    # Emit REQUEST_RECEIVED at pipeline entry.
    # caller="user" — this function is called from /v1/query (user-facing).
    # Foundry tool endpoints emit their own REQUEST_RECEIVED with
    # caller="foundry" when those endpoints are built in Sprint 4/5.
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
                "caller": "user",
            },
        )
    )

    # ------------------------------------------------------------------
    # Stage 1 — App Identifier
    # Detects which app schema this query belongs to.
    # Populates context.app_id and context.app_schema_version.
    #
    # run_app_identifier() raises on failure — it does not set context fields.
    # We catch the known exceptions and convert to context failures here.
    # ------------------------------------------------------------------
    try:
        context = run_app_identifier(context, schema_repo, logger)
    except (AppNotDeterminedError, MultipleAppsMatchedError) as exc:
        context.status = "failed"
        context.error = {"code": exc.code, "message": exc.message}
        return context

    # ------------------------------------------------------------------
    # Stage 2 — Intent Guard
    # Deterministic keyword scan — no LLM call.
    # Blocks DELETE / DROP / UPDATE / INSERT / TRUNCATE / ALTER / CREATE.
    # run_intent_guard() does not raise — it sets context.status = "failed"
    # and returns. We check status and stop early if needed.
    # ------------------------------------------------------------------
    context = run_intent_guard(context, logger)
    if context.status == "failed":
        return context

    # ------------------------------------------------------------------
    # Stage 3 — NL-to-IR Strategy
    # Builds a compressed schema summary for the LLM prompt, then runs
    # the configured strategy (Phase 1: SingleCallStrategy).
    # Populates context.llm_output with the simplified IR.
    #
    # schema_repo.get_schema() raises SchemaLoadError if app_id not found —
    # should not happen here since Stage 1 confirmed the app, but we guard
    # defensively and treat it as an internal error.
    # ------------------------------------------------------------------
    try:
        app_schema = schema_repo.get_schema(context.app_id)
    except Exception as exc:
        context.status = "failed"
        context.error = {
            "code": INTERNAL_ERROR,
            "message": f"Failed to load schema for app '{context.app_id}': {exc}",
        }
        return context

    schema_summary = build_schema_summary(app_schema)
    strategy = NLToIRStrategyFactory.create(settings, llm_provider, logger)
    context = strategy.execute(context, schema_summary)

    return context
