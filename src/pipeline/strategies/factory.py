# src/pipeline/strategies/factory.py
# V0 - Initial implementation
#
# Factory for NLToIRStrategy — mirrors LLMProviderFactory in src/llm/factory.py.
#
# Reads settings.llm.nl_to_ir_strategy and returns the matching strategy instance.
# Raises UnknownStrategyError for any unrecognised value — service refuses to start.
#
# Adding a new strategy:
#   1. Import the new class here (lazy import pattern — inside create())
#   2. Add one entry to the _strategies dict
#   Zero other changes required anywhere in the codebase.

from __future__ import annotations

from src.core.constants import UNKNOWN_STRATEGY
from src.core.exceptions import UnknownStrategyError
from src.pipeline.strategies.base import NLToIRStrategy


class NLToIRStrategyFactory:
    """
    Creates the configured NL-to-IR strategy instance.

    Usage:
        strategy = NLToIRStrategyFactory.create(settings, llm_provider, logger)

    The strategy is constructed once at startup (inside the orchestrator or
    app lifespan) and reused for every request — strategies are stateless
    across requests. They may cache the system prompt at construction time.
    """

    @staticmethod
    def create(settings, llm_provider, logger) -> NLToIRStrategy:
        """
        Instantiate and return the strategy named in settings.llm.nl_to_ir_strategy.

        Args:
            settings:     Loaded Settings object — reads settings.llm.nl_to_ir_strategy.
            llm_provider: LLMProvider instance — passed to the strategy constructor.
            logger:       StructuredLogger instance — passed to the strategy constructor.

        Returns:
            A concrete NLToIRStrategy instance ready to call execute().

        Raises:
            UnknownStrategyError: if settings.llm.nl_to_ir_strategy does not match
                                  any registered strategy key.
        """
        # Lazy imports — strategy files may not exist yet during early development.
        # This mirrors the pattern in LLMProviderFactory.
        _strategies: dict[str, type[NLToIRStrategy]] = {}

        try:
            from src.pipeline.strategies.single_call import SingleCallStrategy
            _strategies["single_call"] = SingleCallStrategy
        except ImportError:
            pass  # SingleCallStrategy not built yet (Story 3.6) — skip registration

        strategy_name: str = settings.llm.nl_to_ir_strategy
        strategy_class = _strategies.get(strategy_name)

        if strategy_class is None:
            registered = sorted(_strategies.keys())
            raise UnknownStrategyError(
                message=(
                    f"Unknown NL-to-IR strategy '{strategy_name}'. "
                    f"Registered strategies: {registered}"
                )
            )

        return strategy_class(settings, llm_provider, logger)

    @staticmethod
    def registered_strategies() -> list[str]:
        """
        Return the list of strategy keys that are currently registered.
        Useful for error messages and the /ready health check.
        Reflects only strategies whose source files exist at import time.
        """
        keys: list[str] = []
        try:
            from src.pipeline.strategies.single_call import SingleCallStrategy  # noqa: F401
            keys.append("single_call")
        except ImportError:
            pass
        return sorted(keys)
