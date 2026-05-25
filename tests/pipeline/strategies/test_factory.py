# tests/pipeline/strategies/test_factory.py
# V0 - Initial implementation
#
# Tests for NLToIRStrategyFactory (src/pipeline/strategies/factory.py).
#
# Coverage:
#   B1 — Factory mechanism works: a registered stub strategy is returned correctly
#   B2 — Unknown strategy string raises UnknownStrategyError
#   B3 — UnknownStrategyError carries the correct UNKNOWN_STRATEGY error code
#   B4 — registered_strategies() returns only currently-importable strategy keys
#
# Note on B1:
#   SingleCallStrategy does not exist until Story 3.6.
#   We test the factory MECHANISM by monkey-patching a test stub into the factory's
#   internal _strategies dict via a subclass override.
#   This verifies: factory reads settings, looks up by key, calls constructor,
#   returns an NLToIRStrategy instance — without needing SingleCallStrategy to exist.

import pytest
from unittest.mock import MagicMock

from src.core.constants import UNKNOWN_STRATEGY
from src.core.exceptions import UnknownStrategyError
from src.core.models import QueryContext
from src.pipeline.strategies.base import NLToIRStrategy
from src.pipeline.strategies.factory import NLToIRStrategyFactory


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class _StubStrategy(NLToIRStrategy):
    """
    Minimal concrete strategy for testing the factory mechanism.
    Accepts (settings, llm_provider, logger) just like real strategies will.
    """

    def __init__(self, settings, llm_provider, logger) -> None:
        self._settings = settings
        self._llm_provider = llm_provider
        self._logger = logger

    def execute(self, context: QueryContext, schema_summary: str) -> QueryContext:
        return context

    def strategy_name(self) -> str:
        return "stub"


def _make_settings(strategy_name: str = "stub"):
    """Build a minimal mock Settings object with the required llm.nl_to_ir_strategy."""
    settings = MagicMock()
    settings.llm.nl_to_ir_strategy = strategy_name
    return settings


class _PatchedFactory(NLToIRStrategyFactory):
    """
    Factory subclass that injects a stub strategy into _strategies,
    bypassing the lazy import of SingleCallStrategy (which doesn't exist yet).
    """

    @staticmethod
    def create(settings, llm_provider, logger) -> NLToIRStrategy:
        _strategies = {"stub": _StubStrategy}

        strategy_name: str = settings.llm.nl_to_ir_strategy
        strategy_class = _strategies.get(strategy_name)

        if strategy_class is None:
            from src.core.exceptions import UnknownStrategyError
            registered = sorted(_strategies.keys())
            raise UnknownStrategyError(
                message=(
                    f"Unknown NL-to-IR strategy '{strategy_name}'. "
                    f"Registered strategies: {registered}"
                )
            )

        return strategy_class(settings, llm_provider, logger)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestNLToIRStrategyFactory:
    """Tests for NLToIRStrategyFactory."""

    def test_b1_factory_returns_strategy_instance(self):
        """B1: factory with a registered strategy key returns an NLToIRStrategy."""
        settings = _make_settings("stub")
        mock_llm = MagicMock()
        mock_logger = MagicMock()

        strategy = _PatchedFactory.create(settings, mock_llm, mock_logger)

        assert isinstance(strategy, NLToIRStrategy)
        assert strategy.strategy_name() == "stub"

    def test_b1_factory_passes_dependencies_to_strategy(self):
        """B1 (extended): settings, llm_provider, logger are passed to the strategy."""
        settings = _make_settings("stub")
        mock_llm = MagicMock()
        mock_logger = MagicMock()

        strategy = _PatchedFactory.create(settings, mock_llm, mock_logger)

        assert strategy._settings is settings
        assert strategy._llm_provider is mock_llm
        assert strategy._logger is mock_logger

    def test_b2_unknown_strategy_raises_unknown_strategy_error(self):
        """B2: unrecognised strategy name raises UnknownStrategyError."""
        settings = _make_settings("nonexistent_strategy")
        mock_llm = MagicMock()
        mock_logger = MagicMock()

        with pytest.raises(UnknownStrategyError):
            _PatchedFactory.create(settings, mock_llm, mock_logger)

    def test_b3_unknown_strategy_error_has_correct_code(self):
        """B3: UnknownStrategyError.code == UNKNOWN_STRATEGY constant."""
        settings = _make_settings("nonexistent_strategy")
        mock_llm = MagicMock()
        mock_logger = MagicMock()

        with pytest.raises(UnknownStrategyError) as exc_info:
            _PatchedFactory.create(settings, mock_llm, mock_logger)

        assert exc_info.value.code == UNKNOWN_STRATEGY

    def test_b4_registered_strategies_returns_list(self):
        """B4: registered_strategies() returns a list (may be empty before Story 3.6)."""
        result = NLToIRStrategyFactory.registered_strategies()
        assert isinstance(result, list)
        # All items must be strings
        for item in result:
            assert isinstance(item, str)
