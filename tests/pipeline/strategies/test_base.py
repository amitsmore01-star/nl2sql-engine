# tests/pipeline/strategies/test_base.py
# V0 - Initial implementation
#
# Tests for NLToIRStrategy ABC (src/pipeline/strategies/base.py).
#
# Coverage:
#   A1 — ABC cannot be instantiated directly
#   A2 — Concrete subclass implementing both methods can be instantiated
#   A3 — Subclass missing execute() raises TypeError on instantiation
#   A4 — Subclass missing strategy_name() raises TypeError on instantiation

import pytest

from src.core.models import QueryContext
from src.pipeline.strategies.base import NLToIRStrategy


# ---------------------------------------------------------------------------
# Helpers — minimal concrete implementations for testing the ABC contract
# ---------------------------------------------------------------------------

class _FullStrategy(NLToIRStrategy):
    """Valid concrete strategy — implements both required methods."""

    def execute(self, context: QueryContext, schema_summary: str) -> QueryContext:
        return context

    def strategy_name(self) -> str:
        return "test_full"


class _MissingExecute(NLToIRStrategy):
    """Invalid — only implements strategy_name, not execute."""

    def strategy_name(self) -> str:
        return "test_missing_execute"

    # execute() intentionally not implemented


class _MissingStrategyName(NLToIRStrategy):
    """Invalid — only implements execute, not strategy_name."""

    def execute(self, context: QueryContext, schema_summary: str) -> QueryContext:
        return context

    # strategy_name() intentionally not implemented


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestNLToIRStrategyABC:
    """Tests for the NLToIRStrategy abstract base class."""

    def test_a1_cannot_instantiate_abc_directly(self):
        """A1: NLToIRStrategy is abstract — direct instantiation raises TypeError."""
        with pytest.raises(TypeError):
            NLToIRStrategy()  # type: ignore[abstract]

    def test_a2_concrete_subclass_with_both_methods_instantiates(self):
        """A2: A class implementing execute() and strategy_name() can be instantiated."""
        strategy = _FullStrategy()
        assert strategy.strategy_name() == "test_full"

    def test_a2_execute_returns_context(self):
        """A2 (extended): execute() returns a QueryContext."""
        strategy = _FullStrategy()
        ctx = QueryContext(nl_query_original="test query")
        result = strategy.execute(ctx, schema_summary="table: Major.Customer")
        assert isinstance(result, QueryContext)

    def test_a3_missing_execute_raises_type_error(self):
        """A3: Subclass without execute() raises TypeError on instantiation."""
        with pytest.raises(TypeError):
            _MissingExecute()  # type: ignore[abstract]

    def test_a4_missing_strategy_name_raises_type_error(self):
        """A4: Subclass without strategy_name() raises TypeError on instantiation."""
        with pytest.raises(TypeError):
            _MissingStrategyName()  # type: ignore[abstract]
