# src/pipeline/strategies/single_call.py
# V0 - Initial implementation
#
# SingleCallStrategy — Phase 1 default NL-to-IR strategy.
#
# Makes one LLM call per request. Assembles the system prompt once at
# construction time (reused across all requests). Renders the user prompt
# per request by substituting the schema summary and user query.
#
# Output: simplified IR written to context.llm_output
# Shape:  { tables, columns, filters, limit, aggregation, sort }
#         Each table/column/filter carries a "source" field tracing back
#         to the exact word or phrase in the user query.
#
# Phase 1 note:
#   aggregation and sort are captured in the IR but NOT executed by the
#   SQL builder in Phase 1. They are recorded for Phase 2.

from __future__ import annotations

import json
import time

from src.config.settings import Settings
from src.core.constants import LLM_OUTPUT, UNKNOWN_STRATEGY
from src.core.exceptions import LLMOutputParseError
from src.core.models import QueryContext
from src.core.logging.logger import StructuredLogger
from src.core.logging.log_models import LogEntry
from src.llm.base import LLMProvider
from src.pipeline.prompt_builder import PromptBuilder
from src.pipeline.schema_summary import build_schema_summary
from src.pipeline.strategies.base import NLToIRStrategy

# Required top-level keys in the LLM's JSON response
_REQUIRED_IR_KEYS = {"tables", "columns", "filters", "limit", "aggregation", "sort"}


class SingleCallStrategy(NLToIRStrategy):
    """
    Single-call NL-to-IR strategy.

    Sends one prompt to the LLM and parses the simplified IR from the response.
    The system prompt is built once at construction — it is identical for every
    request and contains the role description, output structure, rules, and examples.
    The user prompt is rendered per request with the schema summary and user query.
    """

    def __init__(
        self,
        settings: Settings,
        llm_provider: LLMProvider,
        logger: StructuredLogger,
    ) -> None:
        """
        Construct the strategy and build the system prompt.

        Raises:
            ValueError: If PromptBuilder.validate() finds a semantic problem
                        in prompts.yaml. Service refuses to start.
        """
        self._settings = settings
        self._llm_provider = llm_provider
        self._logger = logger

        # Retrieve the prompt spec from settings
        spec = settings.prompts  # StrategyPromptSpec — already Pydantic-validated

        # Semantic validation — raises ValueError on any problem
        PromptBuilder.validate(spec)

        # Build system prompt once — reused for every request
        self._system_prompt: str = PromptBuilder.build_system_prompt(
            spec=spec,
            example_set_name=settings.llm.prompt_example_set,
        )

        # Keep spec for render_user_prompt calls
        self._spec = spec

    def strategy_name(self) -> str:
        return "single_call"

    def execute(self, context: QueryContext, schema_summary: str) -> QueryContext:
        """
        Run one LLM call and populate context.llm_output with the simplified IR.

        Args:
            context:        Current pipeline state. Must have nl_query_original set.
            schema_summary: Compressed schema text from build_schema_summary().

        Returns:
            Updated QueryContext with llm_output populated.

        Raises:
            LLMOutputParseError: If the LLM response is not valid JSON or is
                                 missing required top-level keys.
        """
        start_ms = int(time.time() * 1000)

        # Render per-request user prompt
        user_prompt = PromptBuilder.render_user_prompt(
            spec=self._spec,
            schema_summary=schema_summary,
            user_query=context.nl_query_original,
        )

        # Call LLM — synchronous, blocking
        raw_response = self._llm_provider.complete(
            system_prompt=self._system_prompt,
            user_prompt=user_prompt,
        )

        # Parse JSON response
        ir = _parse_ir(raw_response)

        # Record latency
        elapsed_ms = int(time.time() * 1000) - start_ms
        context.latency_ms["nl_to_ir"] = elapsed_ms

        # Record token usage if provider exposes it (mock does not)
        token_usage = getattr(self._llm_provider, "_last_token_usage", None)
        if token_usage:
            context.token_usage.update(token_usage)

        # Populate context
        context.llm_output = ir
        context.status = "success"

        # Emit LLM_OUTPUT log stage
        self._logger.log(
            LogEntry(
                stage=LLM_OUTPUT,
                request_id=context.request_id,
                user_id=context.user_id,
                app_id=context.app_id,
                app_schema_version=context.app_schema_version,
                latency_ms=elapsed_ms,
                payload={
                    "strategy_name": self.strategy_name(),
                    "token_usage": context.token_usage,
                    "llm_output": ir,
                },
            )
        )

        return context


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _parse_ir(raw: str) -> dict:
    """
    Parse and validate the LLM's JSON response into the simplified IR dict.

    Args:
        raw: Raw string returned by LLMProvider.complete().

    Returns:
        Parsed IR dict with all required top-level keys present.

    Raises:
        LLMOutputParseError: If parsing fails or required keys are missing.
    """
    # Strip markdown code fences if the LLM wrapped its response
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        lines = cleaned.splitlines()
        # Drop first line (```json or ```) and last line (```)
        cleaned = "\n".join(lines[1:-1]).strip()

    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise LLMOutputParseError(
            message=(
                f"LLM response is not valid JSON. "
                f"Parse error: {exc}. "
                f"Raw response (first 200 chars): {raw[:200]!r}"
            )
        ) from exc

    if not isinstance(parsed, dict):
        raise LLMOutputParseError(
            message=(
                f"LLM response parsed to {type(parsed).__name__}, expected a JSON object. "
                f"Raw response (first 200 chars): {raw[:200]!r}"
            )
        )

    missing_keys = _REQUIRED_IR_KEYS - set(parsed.keys())
    if missing_keys:
        raise LLMOutputParseError(
            message=(
                f"LLM response JSON is missing required keys: {sorted(missing_keys)}. "
                f"All of these must be present: {sorted(_REQUIRED_IR_KEYS)}. "
                f"Received keys: {sorted(parsed.keys())}"
            )
        )

    return parsed
