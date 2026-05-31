# tests/pipeline/strategies/test_single_call.py
# V0 - Initial implementation
#
# Tests for src/pipeline/strategies/single_call.py
# All tests use MockLLMProvider — zero real API calls.
# Uses the real prompts.yaml and settings loaded from the config/ directory.

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.config.settings import load_settings
from src.core.constants import LLM_OUTPUT
from src.core.exceptions import LLMOutputParseError
from src.core.models import QueryContext
from src.llm.mock_provider import MockLLMProvider
from src.pipeline.strategies.single_call import SingleCallStrategy

# ---------------------------------------------------------------------------
# Path to real config/ directory
# ---------------------------------------------------------------------------
REAL_CONFIG_DIR = Path(__file__).parent.parent.parent.parent / "config"

# ---------------------------------------------------------------------------
# Canned valid IR response — what MockLLMProvider returns
# ---------------------------------------------------------------------------
VALID_IR = {
    "tables": [
        {"table": "Major.Customer", "source": "customer"},
        {"table": "Major.CustomerDemographics", "source": "customer name"},
    ],
    "columns": [
        {
            "table": "Major.CustomerDemographics",
            "column": "CustomerName",
            "source": "customer name",
        }
    ],
    "filters": [
        {
            "table": "Major.Customer",
            "column": "CustomerCID",
            "operator": "=",
            "value": "ASA",
            "source": "customer ASA",
        }
    ],
    "limit": None,
    "aggregation": None,
    "sort": [],
}

VALID_IR_JSON = json.dumps(VALID_IR)


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

def _make_settings(monkeypatch):
    """Load real settings with mock LLM provider."""
    monkeypatch.setenv("ENV", "dev")
    monkeypatch.setenv("CLIENT_API_KEY", "test-key")
    monkeypatch.setenv("FOUNDRY_API_KEY", "test-foundry-key")
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    return load_settings(REAL_CONFIG_DIR)


def _make_logger() -> MagicMock:
    """Return a mock logger that accepts .log() calls."""
    logger = MagicMock()
    logger.log = MagicMock()
    return logger


def _make_context() -> QueryContext:
    """Minimal QueryContext for strategy tests."""
    return QueryContext(
        user_id="test-user",
        app_id="ABC_app",
        app_schema_version="1.0",
        nl_query_original="give me customer name for customer ASA in ABC",
    )


# ===========================================================================
# Group A — Construction
# ===========================================================================
class TestSingleCallStrategyConstruction:

    def test_A1_constructs_without_error(self, monkeypatch):
        """A1 — Strategy constructs without error given valid settings, provider, logger."""
        settings = _make_settings(monkeypatch)
        provider = MockLLMProvider(responses=[VALID_IR_JSON])
        logger = _make_logger()
        strategy = SingleCallStrategy(settings, provider, logger)
        assert strategy is not None

    def test_A2_strategy_name_returns_single_call(self, monkeypatch):
        """A2 — strategy_name() returns 'single_call'."""
        settings = _make_settings(monkeypatch)
        provider = MockLLMProvider(responses=[VALID_IR_JSON])
        logger = _make_logger()
        strategy = SingleCallStrategy(settings, provider, logger)
        assert strategy.strategy_name() == "single_call"

    def test_A3_system_prompt_built_once_at_construction(self, monkeypatch):
        """A3 — System prompt is built once at construction, stored on the instance."""
        settings = _make_settings(monkeypatch)
        provider = MockLLMProvider(responses=[VALID_IR_JSON, VALID_IR_JSON])
        logger = _make_logger()
        strategy = SingleCallStrategy(settings, provider, logger)

        # System prompt is stored at construction
        assert hasattr(strategy, "_system_prompt")
        system_prompt_at_construction = strategy._system_prompt

        # Run execute() — system prompt should not change
        context = _make_context()
        strategy.execute(context, schema_summary="table: Major.Customer [customer]")

        assert strategy._system_prompt == system_prompt_at_construction


# ===========================================================================
# Group B — execute() happy path
# ===========================================================================
class TestSingleCallStrategyExecute:

    def test_B1_valid_response_populates_llm_output(self, monkeypatch):
        """B1 — Valid mock IR response populates context.llm_output correctly."""
        settings = _make_settings(monkeypatch)
        provider = MockLLMProvider(responses=[VALID_IR_JSON])
        logger = _make_logger()
        strategy = SingleCallStrategy(settings, provider, logger)

        context = _make_context()
        result = strategy.execute(context, schema_summary="table: Major.Customer [customer]")

        assert result.llm_output is not None
        assert "tables" in result.llm_output
        assert "columns" in result.llm_output
        assert "filters" in result.llm_output
        assert "limit" in result.llm_output
        assert "aggregation" in result.llm_output
        assert "sort" in result.llm_output

    def test_B2_source_field_present_on_tables(self, monkeypatch):
        """B2 — source field is present on each table entry in llm_output.tables."""
        settings = _make_settings(monkeypatch)
        provider = MockLLMProvider(responses=[VALID_IR_JSON])
        logger = _make_logger()
        strategy = SingleCallStrategy(settings, provider, logger)

        context = _make_context()
        result = strategy.execute(context, schema_summary="table: Major.Customer [customer]")

        for table_entry in result.llm_output["tables"]:
            assert "source" in table_entry, (
                f"Table entry missing 'source' field: {table_entry}"
            )

    def test_B3_source_field_present_on_columns(self, monkeypatch):
        """B3 — source field is present on each column entry in llm_output.columns."""
        settings = _make_settings(monkeypatch)
        provider = MockLLMProvider(responses=[VALID_IR_JSON])
        logger = _make_logger()
        strategy = SingleCallStrategy(settings, provider, logger)

        context = _make_context()
        result = strategy.execute(context, schema_summary="table: Major.Customer [customer]")

        for col_entry in result.llm_output["columns"]:
            assert "source" in col_entry, (
                f"Column entry missing 'source' field: {col_entry}"
            )

    def test_B4_source_field_present_on_filters(self, monkeypatch):
        """B4 — source field is present on each filter entry in llm_output.filters."""
        settings = _make_settings(monkeypatch)
        provider = MockLLMProvider(responses=[VALID_IR_JSON])
        logger = _make_logger()
        strategy = SingleCallStrategy(settings, provider, logger)

        context = _make_context()
        result = strategy.execute(context, schema_summary="table: Major.Customer [customer]")

        for filter_entry in result.llm_output["filters"]:
            assert "source" in filter_entry, (
                f"Filter entry missing 'source' field: {filter_entry}"
            )

    def test_B5_context_status_is_success(self, monkeypatch):
        """B5 — context.status is 'success' after a successful execute call."""
        settings = _make_settings(monkeypatch)
        provider = MockLLMProvider(responses=[VALID_IR_JSON])
        logger = _make_logger()
        strategy = SingleCallStrategy(settings, provider, logger)

        context = _make_context()
        result = strategy.execute(context, schema_summary="table: Major.Customer [customer]")

        assert result.status == "success"

    def test_B6_llm_output_log_stage_emitted(self, monkeypatch):
        """B6 — LLM_OUTPUT log stage is emitted with correct stage name."""
        settings = _make_settings(monkeypatch)
        provider = MockLLMProvider(responses=[VALID_IR_JSON])
        logger = _make_logger()
        strategy = SingleCallStrategy(settings, provider, logger)

        context = _make_context()
        strategy.execute(context, schema_summary="table: Major.Customer [customer]")

        # logger.log() must have been called at least once
        #logger.log.assert_called_once()
        assert logger.log.call_count == 2
        log_entry = logger.log.call_args[0][0]
        assert log_entry.stage == LLM_OUTPUT

    def test_B7_token_usage_key_present_in_context(self, monkeypatch):
        """B7 — context.token_usage is a dict (may be empty for mock provider)."""
        settings = _make_settings(monkeypatch)
        provider = MockLLMProvider(responses=[VALID_IR_JSON])
        logger = _make_logger()
        strategy = SingleCallStrategy(settings, provider, logger)

        context = _make_context()
        result = strategy.execute(context, schema_summary="table: Major.Customer [customer]")

        assert isinstance(result.token_usage, dict)


# ===========================================================================
# Group C — error handling
# ===========================================================================
class TestSingleCallStrategyErrors:

    def test_C1_malformed_json_raises_llm_output_parse_error(self, monkeypatch):
        """C1 — LLM returns non-JSON string → LLMOutputParseError raised."""
        settings = _make_settings(monkeypatch)
        provider = MockLLMProvider(responses=["this is not json at all"])
        logger = _make_logger()
        strategy = SingleCallStrategy(settings, provider, logger)

        context = _make_context()
        with pytest.raises(LLMOutputParseError):
            strategy.execute(context, schema_summary="table: Major.Customer [customer]")

    def test_C2_missing_required_key_raises_llm_output_parse_error(self, monkeypatch):
        """C2 — LLM returns valid JSON but missing 'tables' key → LLMOutputParseError."""
        incomplete_ir = json.dumps({
            "columns": [],
            "filters": [],
            "limit": None,
            "aggregation": None,
            "sort": [],
            # 'tables' key is intentionally missing
        })
        settings = _make_settings(monkeypatch)
        provider = MockLLMProvider(responses=[incomplete_ir])
        logger = _make_logger()
        strategy = SingleCallStrategy(settings, provider, logger)

        context = _make_context()
        with pytest.raises(LLMOutputParseError, match="tables"):
            strategy.execute(context, schema_summary="table: Major.Customer [customer]")

    def test_C3_mock_provider_called_exactly_once_per_execute(self, monkeypatch):
        """C3 — MockLLMProvider.complete() is called exactly once per execute() call."""
        settings = _make_settings(monkeypatch)
        provider = MockLLMProvider(responses=[VALID_IR_JSON])
        logger = _make_logger()

        # Wrap complete() with a spy
        original_complete = provider.complete
        call_count = []

        def spy_complete(system_prompt, user_prompt):
            call_count.append(1)
            return original_complete(system_prompt, user_prompt)

        provider.complete = spy_complete

        strategy = SingleCallStrategy(settings, provider, logger)
        context = _make_context()
        strategy.execute(context, schema_summary="table: Major.Customer [customer]")

        assert len(call_count) == 1, (
            f"Expected exactly 1 LLM call per execute(), got {len(call_count)}"
        )
