# tests/pipeline/test_orchestrator.py
# V0 - Initial implementation
#
# Tests for run_pipeline() in src/pipeline/orchestrator.py
#
# Covers the partial pipeline: App Identifier → Intent Guard → NL-to-IR Strategy.
# Uses MockLLMProvider — zero real API calls.
# Uses a real SchemaRepository loaded from schemas/ABC_app.json.

import json
import pytest
from pathlib import Path

from src.core.models import QueryContext
from src.core.constants import APP_NOT_DETERMINED, UNSUPPORTED_INTENT
from src.llm.mock_provider import MockLLMProvider
from src.schema.schema_repository import SchemaRepository
from src.pipeline.orchestrator import run_pipeline
from src.config.settings import load_settings
from src.core.logging.logger import StructuredLogger
from unittest.mock import MagicMock


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

# Minimal valid simplified IR — what the mock LLM returns
_GOLDEN_IR = json.dumps({
    "tables": [
        {"table": "Major.Customer", "source": "customer"},
        {"table": "Major.CustomerDemographics", "source": "customer name"}
    ],
    "columns": [
        {"table": "Major.CustomerDemographics", "column": "CustomerName", "source": "customer name"}
    ],
    "filters": [
        {
            "table": "Major.Customer",
            "column": "CustomerCID",
            "operator": "=",
            "value": "ASA",
            "source": "customer ASA"
        }
    ],
    "limit": None,
    "aggregation": None,
    "sort": []
})


@pytest.fixture
def schema_repo() -> SchemaRepository:
    """Real SchemaRepository loaded from schemas/ABC_app.json."""
    repo = SchemaRepository()
    repo.load(Path("schemas"))
    return repo


@pytest.fixture
def settings():
    """Real settings — uses mock LLM provider in dev environment."""
    return load_settings()


@pytest.fixture
def mock_llm() -> MockLLMProvider:
    """MockLLMProvider pre-loaded with one golden IR response."""
    return MockLLMProvider(responses=[_GOLDEN_IR])


@pytest.fixture
def logger(settings) -> StructuredLogger:
    """Real StructuredLogger for the pipeline."""
    return StructuredLogger(settings)


def _make_context(query: str, app_id: str = "") -> QueryContext:
    """Build a minimal QueryContext."""
    return QueryContext(
        user_id="test_user",
        app_id=app_id,
        nl_query_original=query,
    )


# ---------------------------------------------------------------------------
# B — Orchestrator tests
# ---------------------------------------------------------------------------

class TestOrchestrator:

    def test_B1_valid_query_runs_all_three_stages(
        self, schema_repo, settings, mock_llm, logger
    ):
        """
        B1: Valid query runs App Identifier → Intent Guard → NL-to-IR Strategy.
        All three stages complete — llm_output is populated.
        """
        ctx = _make_context("give me customer name for customer ASA in ABC")

        result = run_pipeline(
            context=ctx,
            schema_repo=schema_repo,
            llm_provider=mock_llm,
            logger=logger,
            settings=settings,
        )

        assert result.llm_output is not None
        assert "tables" in result.llm_output
        assert "columns" in result.llm_output

    def test_B2_non_select_query_stops_at_intent_guard(
        self, schema_repo, settings, logger
    ):
        """
        B2: Non-SELECT query stops at Intent Guard.
        NL-to-IR stage is never called (mock LLM has no responses — would
        raise ValueError if called).
        """
        # MockLLMProvider with empty responses — any call raises ValueError.
        # If NL-to-IR runs it will fail, proving Intent Guard did NOT stop it.
        # We give it a response so the test is about the guard, not the mock.
        # Actually: give it NO valid responses so that if called it explodes.
        llm_that_must_not_be_called = MockLLMProvider(responses=["unused"])

        ctx = _make_context("DELETE all customers in ABC")

        result = run_pipeline(
            context=ctx,
            schema_repo=schema_repo,
            llm_provider=llm_that_must_not_be_called,
            logger=logger,
            settings=settings,
        )

        assert result.status == "failed"
        assert result.error["code"] == UNSUPPORTED_INTENT
        # llm_output must still be None — NL-to-IR never ran
        assert result.llm_output is None

    def test_B3_unknown_app_stops_at_app_identifier(
        self, schema_repo, settings, logger
    ):
        """
        B3: Query with no recognisable app stops at App Identifier.
        Intent Guard and NL-to-IR are never called.
        """
        llm_that_must_not_be_called = MockLLMProvider(responses=["unused"])

        ctx = _make_context("give me data from UNKNOWN_APP_XYZ")

        result = run_pipeline(
            context=ctx,
            schema_repo=schema_repo,
            llm_provider=llm_that_must_not_be_called,
            logger=logger,
            settings=settings,
        )

        assert result.status == "failed"
        assert result.error["code"] == APP_NOT_DETERMINED
        assert result.llm_output is None

    def test_B4_status_is_success_on_clean_run(
        self, schema_repo, settings, mock_llm, logger
    ):
        """
        B4: context.status = "success" after all three stages complete cleanly.
        """
        ctx = _make_context("give me customer name for customer ASA in ABC")

        result = run_pipeline(
            context=ctx,
            schema_repo=schema_repo,
            llm_provider=mock_llm,
            logger=logger,
            settings=settings,
        )

        assert result.status == "success"

    def test_B5_app_id_populated_after_valid_run(
        self, schema_repo, settings, mock_llm, logger
    ):
        """
        B5: context.app_id is populated by App Identifier during the pipeline.
        """
        ctx = _make_context("give me customer name for customer ASA in ABC")
        # app_id starts empty — App Identifier fills it in
        assert ctx.app_id == ""

        result = run_pipeline(
            context=ctx,
            schema_repo=schema_repo,
            llm_provider=mock_llm,
            logger=logger,
            settings=settings,
        )

        assert result.app_id == "ABC_app"
