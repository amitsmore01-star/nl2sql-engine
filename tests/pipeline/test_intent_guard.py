# tests/pipeline/test_intent_guard.py
# V0 - Initial implementation
#
# Tests for run_intent_guard() in src/pipeline/intent_guard.py
#
# What we are testing:
#   - Clean SELECT queries pass through unchanged
#   - Each blocked keyword is detected correctly
#   - Partial-word matches (e.g. "deleted", "updates") are NOT blocked
#   - INTENT_GUARD_RESULT log is emitted for both pass and block outcomes
#   - context.status and context.error are set correctly on block

import pytest
from unittest.mock import MagicMock, call

from src.core.models import QueryContext
from src.core.constants import UNSUPPORTED_INTENT, INTENT_GUARD_RESULT
from src.pipeline.intent_guard import run_intent_guard


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_context(query: str) -> QueryContext:
    """Build a minimal QueryContext with the given NL query."""
    return QueryContext(
        user_id="test_user",
        app_id="Acme_app",
        app_schema_version="1.0",
        nl_query_original=query,
    )


def _make_logger() -> MagicMock:
    """Return a mock logger — we inspect .log() calls in tests."""
    return MagicMock()


# ---------------------------------------------------------------------------
# A — Pass-through (clean SELECT queries)
# ---------------------------------------------------------------------------

class TestIntentGuardPass:
    """Queries that should pass through the guard unchanged."""

    def test_A1_clean_select_query_passes(self):
        """A normal SELECT query is not blocked."""
        ctx = _make_context("give me customer name for customer CUST01 in Acme")
        logger = _make_logger()

        result = run_intent_guard(ctx, logger)

        assert result.status != "failed"
        assert result.error is None

    def test_A9_deleted_partial_word_passes(self):
        """'deleted' contains 'delete' but is a different word — must not be blocked."""
        ctx = _make_context("show me customers who were not deleted")
        logger = _make_logger()

        result = run_intent_guard(ctx, logger)

        assert result.status != "failed"
        assert result.error is None

    def test_A10_updates_partial_word_passes(self):
        """'updates' contains 'update' but is a different word — must not be blocked."""
        ctx = _make_context("show updates to customer CUST01 in Acme")
        logger = _make_logger()

        result = run_intent_guard(ctx, logger)

        assert result.status != "failed"
        assert result.error is None

    def test_created_partial_word_passes(self):
        """'created' contains 'create' but is a different word — must not be blocked."""
        ctx = _make_context("show records created this month in Acme")
        logger = _make_logger()

        result = run_intent_guard(ctx, logger)

        assert result.status != "failed"
        assert result.error is None

    def test_insertion_partial_word_passes(self):
        """'insertion' contains 'insert' but is a different word — must not be blocked."""
        ctx = _make_context("show insertion records in Acme")
        logger = _make_logger()

        result = run_intent_guard(ctx, logger)

        assert result.status != "failed"
        assert result.error is None


# ---------------------------------------------------------------------------
# A — Block (non-SELECT keywords)
# ---------------------------------------------------------------------------

class TestIntentGuardBlock:
    """Each blocked keyword should set status=failed and populate error."""

    def _assert_blocked(self, query: str, expected_keyword: str):
        ctx = _make_context(query)
        logger = _make_logger()

        result = run_intent_guard(ctx, logger)

        assert result.status == "failed"
        assert result.error is not None
        assert result.error["code"] == UNSUPPORTED_INTENT
        assert expected_keyword in result.error["message"]

    def test_A2_delete_keyword_blocked(self):
        """DELETE is a blocked keyword."""
        self._assert_blocked("DELETE FROM customers WHERE id = 1", "DELETE")

    def test_A2_delete_case_insensitive(self):
        """DELETE is matched case-insensitively."""
        self._assert_blocked("delete all records in Acme", "DELETE")

    def test_A3_drop_keyword_blocked(self):
        """DROP is a blocked keyword."""
        self._assert_blocked("DROP TABLE customers", "DROP")

    def test_A4_update_keyword_blocked(self):
        """UPDATE is a blocked keyword."""
        self._assert_blocked("UPDATE customer SET name = 'X'", "UPDATE")

    def test_A5_insert_keyword_blocked(self):
        """INSERT is a blocked keyword."""
        self._assert_blocked("INSERT INTO customers VALUES (1, 'X')", "INSERT")

    def test_A6_truncate_keyword_blocked(self):
        """TRUNCATE is a blocked keyword."""
        self._assert_blocked("TRUNCATE TABLE customers", "TRUNCATE")

    def test_A7_alter_keyword_blocked(self):
        """ALTER is a blocked keyword."""
        self._assert_blocked("ALTER TABLE customers ADD COLUMN x INT", "ALTER")

    def test_A8_create_keyword_blocked(self):
        """CREATE is a blocked keyword."""
        self._assert_blocked("CREATE TABLE new_customers AS SELECT * FROM customers", "CREATE")


# ---------------------------------------------------------------------------
# A11 — Logging
# ---------------------------------------------------------------------------

class TestIntentGuardLogging:
    """INTENT_GUARD_RESULT log is always emitted — for both pass and block."""

    def test_A11_log_emitted_on_pass(self):
        """Log is emitted with passed=True when query passes."""
        ctx = _make_context("give me customer name in Acme")
        logger = _make_logger()

        run_intent_guard(ctx, logger)

        logger.log.assert_called_once()
        log_entry = logger.log.call_args[0][0]
        assert log_entry.stage == INTENT_GUARD_RESULT
        assert log_entry.payload["passed"] is True
        assert log_entry.payload["keywords_detected"] == []

    def test_A11_log_emitted_on_block(self):
        """Log is emitted with passed=False and keyword list when query is blocked."""
        ctx = _make_context("DELETE all customers in Acme")
        logger = _make_logger()

        run_intent_guard(ctx, logger)

        logger.log.assert_called_once()
        log_entry = logger.log.call_args[0][0]
        assert log_entry.stage == INTENT_GUARD_RESULT
        assert log_entry.payload["passed"] is False
        assert "DELETE" in log_entry.payload["keywords_detected"]

    def test_log_carries_request_id(self):
        """Log entry carries the request_id from context."""
        ctx = _make_context("give me customers in Acme")
        logger = _make_logger()

        run_intent_guard(ctx, logger)

        log_entry = logger.log.call_args[0][0]
        assert log_entry.request_id == ctx.request_id
