# tests/api/test_middleware.py
# V0 - Initial implementation
#
# Tests for the global exception handlers in src/api/middleware.py.
#
# Test groups:
#   A — MissingContextFieldsError → HTTP 400
#   B — Unhandled generic exception → HTTP 500
#   C — Safe response (raw error details never exposed to caller)
#   D — Logging (error detail written to log, not to response)
#
# TEST APPROACH — test-only throw routes:
#   The global handlers fire when an exception ESCAPES a route handler.
#   We add lightweight routes to the app that deliberately raise specific
#   exceptions. These routes have no auth and no body — they exist only
#   to trigger the exception handlers under test.
#   No production code is modified.
#
#   Routes added per test (via app.add_api_route):
#       GET /test/throw-missing  → raises MissingContextFieldsError
#       GET /test/throw-runtime  → raises RuntimeError
#
# WHY raise_server_exceptions=False:
#   By default TestClient re-raises exceptions from route handlers on the
#   test thread. Setting raise_server_exceptions=False tells TestClient to
#   let the exception propagate to the ASGI exception middleware instead,
#   so our registered handlers can run and return a structured response.

from unittest.mock import patch

from fastapi.testclient import TestClient

from src.api.app import create_app
from src.core.constants import INTERNAL_ERROR, MISSING_CONTEXT_FIELDS
from src.core.exceptions import MissingContextFieldsError

# ---------------------------------------------------------------------------
# Module-level exception-raising functions
# These are added as routes inside each test. Defined at module level so
# FastAPI can inspect their signatures cleanly (no closure issues).
# ---------------------------------------------------------------------------

def _raise_missing_context():
    """Route body — raises MissingContextFieldsError unconditionally."""
    raise MissingContextFieldsError(
        message="Stage 'nl-to-ir' requires: app_id",
        missing_fields=["app_id"],
    )


def _raise_runtime_error():
    """Route body — raises RuntimeError unconditionally."""
    raise RuntimeError("simulated internal failure — should never reach caller")


# ---------------------------------------------------------------------------
# Helper — build app with throw routes pre-registered
# ---------------------------------------------------------------------------

def make_throw_client() -> TestClient:
    """
    Create a TestClient with both throw routes added.
    raise_server_exceptions=False is required for exception handlers to run.
    """
    app = create_app(schema_dir="schemas")
    app.add_api_route("/test/throw-missing", _raise_missing_context, methods=["GET"])
    app.add_api_route("/test/throw-runtime", _raise_runtime_error, methods=["GET"])
    return TestClient(app, raise_server_exceptions=False)


# ---------------------------------------------------------------------------
# Group A — MissingContextFieldsError → HTTP 400
# ---------------------------------------------------------------------------

class TestMissingContextHandler:
    """MissingContextFieldsError is caught by the global handler and returns 400."""

    def test_a1_missing_context_returns_400(self):
        """MissingContextFieldsError raised in a route → 400 Bad Request."""
        with make_throw_client() as client:
            response = client.get("/test/throw-missing")
        assert response.status_code == 400

    def test_a2_error_code_is_missing_context_fields(self):
        """errors[0].code == MISSING_CONTEXT_FIELDS."""
        with make_throw_client() as client:
            response = client.get("/test/throw-missing")
        data = response.json()
        assert len(data["errors"]) > 0
        assert data["errors"][0]["code"] == MISSING_CONTEXT_FIELDS

    def test_a3_response_has_correct_envelope_shape(self):
        """400 response has the standard top-level keys: request_id, status, errors."""
        with make_throw_client() as client:
            response = client.get("/test/throw-missing")
        data = response.json()
        assert "request_id" in data
        assert "status" in data
        assert "errors" in data

    def test_a4_status_is_failed(self):
        """status == 'failed' on a 400 response."""
        with make_throw_client() as client:
            response = client.get("/test/throw-missing")
        assert response.json()["status"] == "failed"


# ---------------------------------------------------------------------------
# Group B — Unhandled generic exception → HTTP 500
# ---------------------------------------------------------------------------

class TestUnhandledExceptionHandler:
    """Any unhandled exception that escapes a route is caught and returns 500."""

    def test_b1_runtime_error_returns_500(self):
        """RuntimeError raised in a route → 500 Internal Server Error."""
        with make_throw_client() as client:
            response = client.get("/test/throw-runtime")
        assert response.status_code == 500

    def test_b2_error_code_is_internal_error(self):
        """errors[0].code == INTERNAL_ERROR."""
        with make_throw_client() as client:
            response = client.get("/test/throw-runtime")
        data = response.json()
        assert len(data["errors"]) > 0
        assert data["errors"][0]["code"] == INTERNAL_ERROR

    def test_b3_response_has_correct_envelope_shape(self):
        """500 response has the standard top-level keys: request_id, status, errors."""
        with make_throw_client() as client:
            response = client.get("/test/throw-runtime")
        data = response.json()
        assert "request_id" in data
        assert "status" in data
        assert "errors" in data

    def test_b4_status_is_failed(self):
        """status == 'failed' on a 500 response."""
        with make_throw_client() as client:
            response = client.get("/test/throw-runtime")
        assert response.json()["status"] == "failed"


# ---------------------------------------------------------------------------
# Group C — Safe response (raw details never exposed to caller)
# ---------------------------------------------------------------------------

class TestSafeResponse:
    """
    The caller must never see raw Python error detail in the response body.
    This is the key security property of the global exception handler.
    """

    def test_c1_runtime_error_message_not_in_500_response(self):
        """
        The RuntimeError's message must NOT appear in the 500 response body.
        The caller receives only the safe generic message.
        """
        with make_throw_client() as client:
            response = client.get("/test/throw-runtime")
        response_text = response.text
        # The raw exception message should not be visible to the caller
        assert "simulated internal failure" not in response_text
        # The safe generic message should be there instead
        assert "unexpected error" in response_text.lower()

    def test_c2_missing_context_error_message_is_curated(self):
        """
        The 400 response uses the curated exc.message (which tells the agent
        which fields to fix) — not a raw Python exception repr or traceback.
        """
        with make_throw_client() as client:
            response = client.get("/test/throw-missing")
        data = response.json()
        error_message = data["errors"][0]["message"]
        # The curated message from the exception is present
        assert "app_id" in error_message
        # No raw Python exception repr (e.g. "MissingContextFieldsError(...")
        assert "MissingContextFieldsError" not in error_message
        assert "Traceback" not in error_message

    def test_c3_request_id_present_and_non_empty_in_both_responses(self):
        """
        Both 400 and 500 responses carry a non-empty request_id for log correlation.
        (May be generated fresh if the route raised before setting one on request.state.)
        """
        with make_throw_client() as client:
            r400 = client.get("/test/throw-missing")
            r500 = client.get("/test/throw-runtime")

        assert r400.json()["request_id"]  # truthy — non-empty string
        assert r500.json()["request_id"]  # truthy — non-empty string


# ---------------------------------------------------------------------------
# Group D — Logging
# ---------------------------------------------------------------------------

class TestLogging:
    """
    The global handler must log full error detail via StructuredLogger.
    StructuredLogger is patched so no real file is written; the LogEntry
    passed to .log() is inspected directly.
    """

    def test_d1_unhandled_exception_logs_with_internal_error_stage(self):
        """
        RuntimeError → _try_log called with stage=INTERNAL_ERROR.
        Confirms full error detail is logged (not just returned to caller).
        """
        app = create_app(schema_dir="schemas")
        app.add_api_route("/test/throw-runtime", _raise_runtime_error, methods=["GET"])
        with TestClient(app, raise_server_exceptions=False) as client:
            with patch("src.api.middleware.StructuredLogger") as mock_cls:
                response = client.get("/test/throw-runtime")

        assert response.status_code == 500
        mock_cls.return_value.log.assert_called_once()
        entry = mock_cls.return_value.log.call_args.args[0]
        assert entry.stage == INTERNAL_ERROR

    def test_d2_logged_payload_contains_error_type_and_detail(self):
        """
        The logged payload carries error_type and error_detail so engineers
        can diagnose the failure from the log without the caller ever seeing it.
        """
        app = create_app(schema_dir="schemas")
        app.add_api_route("/test/throw-runtime", _raise_runtime_error, methods=["GET"])
        with TestClient(app, raise_server_exceptions=False) as client:
            with patch("src.api.middleware.StructuredLogger") as mock_cls:
                response = client.get("/test/throw-runtime")

        assert response.status_code == 500
        entry = mock_cls.return_value.log.call_args.args[0]
        assert "error_type" in entry.payload
        assert "error_detail" in entry.payload
        assert entry.payload["error_type"] == "RuntimeError"
        assert "simulated internal failure" in entry.payload["error_detail"]
