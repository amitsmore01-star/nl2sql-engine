# src/pipeline/strategies/base.py
# V0 - Initial implementation
#
# Abstract base class for NL-to-IR strategies.
#
# The Strategy pattern here mirrors LLMProvider in src/llm/base.py:
#   - LLMProvider abstracts WHICH model is called (OpenAI, Azure, Anthropic, Mock)
#   - NLToIRStrategy abstracts HOW the LLM is used (single call, two calls, RAG)
#
# Both layers are independently swappable via config — zero code changes required.
#
# Phase 1: SingleCallStrategy is the only concrete implementation.
# Phase 2: TwoCallStrategy may be added if real failure data justifies it.
# Phase 3: RAGStrategy for vector-store-backed few-shot retrieval.
#
# Adding a new strategy:
#   1. Create a new class in src/pipeline/strategies/ that inherits NLToIRStrategy
#   2. Implement execute() and strategy_name()
#   3. Register it in NLToIRStrategyFactory._registry
#   Zero changes to orchestrator, validator, SQL builder, or tool endpoints.

from __future__ import annotations

from abc import ABC, abstractmethod

from src.core.models import QueryContext


class NLToIRStrategy(ABC):
    """
    Abstract base class for NL-to-IR transformation strategies.

    Implementations decide:
      - How many LLM calls to make
      - What prompts to use
      - What IR shape to produce
      - How to parse LLM output

    All implementations write the final simplified IR to context.llm_output.
    The orchestrator calls execute() and nothing else — it never knows which
    strategy is running.

    Contract:
      Input:  context with nl_query_original, app_id, app_schema_version populated
              schema_summary — the compressed schema text for the LLM prompt
      Output: context with llm_output populated (the simplified IR dict)
              context.status set to "failed" and context.error populated on failure
    """

    @abstractmethod
    def execute(self, context: QueryContext, schema_summary: str) -> QueryContext:
        """
        Run the NL-to-IR transformation.

        Args:
            context:        Pipeline state. Read nl_query_original; write llm_output.
            schema_summary: Compressed schema text built by build_schema_summary().

        Returns:
            Updated QueryContext with llm_output populated.
        """
        ...

    @abstractmethod
    def strategy_name(self) -> str:
        """
        Return the strategy identifier string.
        Must match the key registered in NLToIRStrategyFactory.
        Example: "single_call"
        """
        ...
