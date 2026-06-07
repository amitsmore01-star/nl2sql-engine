# tests/pipeline/test_orchestrator.py
# V0 - Initial implementation
# V1 - Story 5.4: Added B6-B9 covering full 5-stage pipeline with SQL output.
#                 B1-B5 unchanged.
#
# Tests for run_pipeline() in src/pipeline/orchestrator.py
#
# Covers the full pipeline: App Identifier → Intent Guard → NL-to-IR Strategy
#                           → Validator → SQL Builder.
# Uses MockLLMProvider — zero real API calls.
# Uses a real SchemaRepository loaded from schemas/Acme_app.json.

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

# Minimal valid simplified IR — what the mock LLM returns.
# References Major.Customer and Major.CustomerDemographics from Acme_app.json.
# The validator will resolve these tables and columns successfully.
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
            "value": "CUST01",
            "source": "customer CUST01"
        }
    ],
    "limit": None,
    "aggregation": None,
    "sort": []
})


@pytest.fixture
def schema_repo() -> SchemaRepository:
    """Real SchemaRepository loaded from schemas/Acme_app.json."""
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
def logger(settings, tmp_path) -> StructuredLogger:
    """StructuredLogger writing to a temp directory."""
    settings.logging.log_dir = str(tmp_path)
    settings.logging.log_archive_dir = str(tmp_path / "archive")
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
        ctx = _make_context("give me customer name for customer CUST01 in Acme")

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
        NL-to-IR stage is never called.
        """
        llm_that_must_not_be_called = MockLLMProvider(responses=["unused"])

        ctx = _make_context("DELETE all customers in Acme")

        result = run_pipeline(
            context=ctx,
            schema_repo=schema_repo,
            llm_provider=llm_that_must_not_be_called,
            logger=logger,
            settings=settings,
        )

        assert result.status == "failed"
        assert result.error["code"] == UNSUPPORTED_INTENT
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
        B4: context.status = "success" after all stages complete cleanly.
        """
        ctx = _make_context("give me customer name for customer CUST01 in Acme")

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
        ctx = _make_context("give me customer name for customer CUST01 in Acme")
        assert ctx.app_id == ""

        result = run_pipeline(
            context=ctx,
            schema_repo=schema_repo,
            llm_provider=mock_llm,
            logger=logger,
            settings=settings,
        )

        assert result.app_id == "Acme_app"

    def test_B6_full_pipeline_produces_sql(
        self, schema_repo, settings, mock_llm, logger
    ):
        """
        B6: Full 5-stage pipeline runs — context.sql is populated with a non-empty string.
        This is the first test that confirms SQL comes out of the end-to-end pipeline.
        """
        ctx = _make_context("give me customer name for customer CUST01 in Acme")

        result = run_pipeline(
            context=ctx,
            schema_repo=schema_repo,
            llm_provider=mock_llm,
            logger=logger,
            settings=settings,
        )

        assert result.sql is not None
        assert len(result.sql) > 0
        assert "SELECT" in result.sql

    def test_B7_full_pipeline_status_success(
        self, schema_repo, settings, mock_llm, logger
    ):
        """
        B7: context.status = "success" after all 5 stages complete (including SQL builder).
        """
        ctx = _make_context("give me customer name for customer CUST01 in Acme")

        result = run_pipeline(
            context=ctx,
            schema_repo=schema_repo,
            llm_provider=mock_llm,
            logger=logger,
            settings=settings,
        )

        assert result.status == "success"
        assert result.sql is not None

    def test_B8_non_select_query_sql_is_none(
        self, schema_repo, settings, logger
    ):
        """
        B8: Non-select query blocked at Intent Guard — context.sql stays None.
        Pipeline never reaches SQL Builder.
        """
        ctx = _make_context("DELETE all customers in Acme")

        result = run_pipeline(
            context=ctx,
            schema_repo=schema_repo,
            llm_provider=MockLLMProvider(responses=["unused"]),
            logger=logger,
            settings=settings,
        )

        assert result.status == "failed"
        assert result.sql is None

    def test_B9_unknown_app_sql_is_none(
        self, schema_repo, settings, logger
    ):
        """
        B9: Unknown app blocked at App Identifier — context.sql stays None.
        Pipeline never reaches SQL Builder.
        """
        ctx = _make_context("give me data from UNKNOWN_APP_XYZ")

        result = run_pipeline(
            context=ctx,
            schema_repo=schema_repo,
            llm_provider=MockLLMProvider(responses=["unused"]),
            logger=logger,
            settings=settings,
        )

        assert result.status == "failed"
        assert result.sql is None
