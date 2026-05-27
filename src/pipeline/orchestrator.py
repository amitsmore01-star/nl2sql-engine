# src/pipeline/orchestrator.py
# V0 - Initial implementation (partial — Stories 4.x and 5.4 add validator + SQL builder)
# V1 - Story 5.4: Added validator chain and run_sql_builder() stages after NL-to-IR.
#                 Removed TODO marker. Pipeline is now complete end-to-end.
#                 NL2SQLBaseError caught from validator chain and converted to context failure.
#
# Wires all five pipeline stages in sequence:
#   1. App Identifier       — detect which app schema the query refers to
#   2. Intent Guard         — block non-SELECT keywords before any LLM call
#   3. NL-to-IR Strategy    — single LLM call, produces simplified IR in context.llm_output
#   4. Validator            — four sub-stages: table/column validator → join resolver
#                             → rule applicator → structured query builder
#   5. SQL Builder          — assembles final SQL from StructuredQuery
#
# Design rules:
#   - Each stage is called via its own internal function
#   - Both /v1/query and /v1/tools/query call run_pipeline() — zero duplication
#   - If any stage sets context.status = "failed", the pipeline stops immediately
#   - Exceptions raised by stages are caught here and converted into context failures
#     so callers always receive a context object, never a raw business exception

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
from src.core.exceptions import (
    AppNotDeterminedError,
    MultipleAppsMatchedError,
    NL2SQLBaseError,
)
from src.validator.table_column_validator import run_table_column_validator
from src.validator.join_resolver import run_join_resolver
from src.validator.rule_applicator import run_rule_applicator
from src.validator.structured_query_builder import run_structured_query_builder
from src.sql.sql_builder import run_sql_builder


def run_pipeline(
    context: QueryContext,
    schema_repo: SchemaRepository,
    llm_provider: LLMProvider,
    logger: StructuredLogger,
    settings,
) -> QueryContext:
    """
    Run the full pipeline: App Identifier → Intent Guard → NL-to-IR Strategy
                           → Validator chain → SQL Builder.

    Each stage reads from context and writes its outputs back to context.
    If any stage fails — either by raising a known business exception or by
    setting context.status = "failed" — the pipeline stops and returns the
    context so the caller can inspect the error.

    Known business exceptions are caught here and converted into context
    failures. Callers always receive a context object — never a raw exception.

    Args:
        context:      Pipeline state object. nl_query_original must be set.
        schema_repo:  Loaded schema repository — passed to App Identifier.
        llm_provider: LLM provider instance — passed to NL-to-IR Strategy.
        logger:       StructuredLogger — passed to every stage.
        settings:     Loaded Settings object (src.config.settings.Settings).
                      Needed by NLToIRStrategyFactory and run_sql_builder.
                      Not type-hinted here to avoid a circular import.

    Returns:
        The context object after all stages have run (or after the first failure).
        context.status = "success" on clean run.
        context.status = "failed" + context.error populated on any failure.
    """
    # ------------------------------------------------------------------
    # Emit REQUEST_RECEIVED at pipeline entry.
    # caller="user" — this function is called from /v1/query (user-facing).
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
    # ------------------------------------------------------------------
    try:
        context = run_app_identifier(context, schema_repo, logger)
    except (AppNotDeterminedError, MultipleAppsMatchedError) as exc:
        context.status = "failed"
        context.error = {"code": exc.code, "message": exc.message}
        return context

    # ------------------------------------------------------------------
    # Stage 2 — Intent Guard
    # ------------------------------------------------------------------
    context = run_intent_guard(context, logger)
    if context.status == "failed":
        return context

    # ------------------------------------------------------------------
    # Stage 3 — NL-to-IR Strategy
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
    if context.status == "failed":
        return context

    # ------------------------------------------------------------------
    # Stage 4 — Validator chain
    # Four sub-stages run in sequence — same pattern as validator_tool.py.
    # All business errors are caught as NL2SQLBaseError (base class of
    # NoRelevantTablesError, NoJoinPathError, StructuredQueryBuildError etc.)
    # and converted to context failures.
    # ------------------------------------------------------------------
    try:
        context = run_table_column_validator(context, schema_repo, logger)
        context = run_join_resolver(context, schema_repo, logger)
        context = run_rule_applicator(context, schema_repo, logger)
        context = run_structured_query_builder(context, logger)
    except NL2SQLBaseError as exc:
        context.status = "failed"
        context.error = {"code": exc.code, "message": exc.message}
        return context

    if context.status == "failed":
        return context

    # ------------------------------------------------------------------
    # Stage 5 — SQL Builder
    # ------------------------------------------------------------------
    context = run_sql_builder(context, logger, settings)

    return context
