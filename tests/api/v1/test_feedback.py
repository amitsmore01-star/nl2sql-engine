# tests/api/v1/test_feedback.py
# V0 - Initial implementation
#
# Tests for POST /v1/feedback — user-facing feedback submission endpoint.
#
# Test groups:
#   A — Auth (missing / wrong / foundry key / correct client key)
#   B — Request validation (Pydantic 422 on malformed bodies)
#   C — Success responses (200, success envelope, request_id echoed)
#   D — Logging (USER_FEEDBACK entry emitted with correct payload)
#
# Group D approach:
#   The endpoint builds StructuredLogger(settings) and calls logger.log(LogEntry(...)).
#   We patch src.api.v1.feedback.StructuredLogger so no real log file is written and
#   we can inspect the LogEntry passed to .log(). LogEntry itself is NOT patched — it
#   is constructed for real inside the endpoint, so entry.stage / entry.request_id /
#   entry.payload are real attributes we can assert on.

from unittest.mock import patch

from fastapi.testclient import TestClient

from src.api.app import create_app
from src.core.constants import USER_FEEDBACK

# ---------------------------------------------------------------------------
# Shared test constants
# ---------------------------------------------------------------------------

VALID_KEY = "test-client-key-12345"
WRONG_KEY = "wrong-key"
FOUNDRY_KEY = "test-foundry-key-67890"

# Minimal valid feedback body — request_id + status are the only required fields.
VALID_FEEDBACK_PASS = {
    "request_id": "orig-req-pass-123",
    "status": "pass",
}

# Full feedback body — includes the optional expected_output and actual_sql.
VALID_FEEDBACK_FAIL = {
    "request_id": "orig-req-fail-456",
    "status": "fail",
    "expected_output": "SELECT CustomerName FROM Major.CustomerDemographics",
    "actual_sql": "SELECT TOP 10000 * FROM Major.Customer",
}


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def make_client(schema_dir="schemas") -> TestClient:
    """
    Create a TestClient using the real ABC schema directory.
    The feedback endpoint needs only app.state.settings (for the logger and the
    auth key) — no LLM provider or schema_repo required — but startup still loads
    the full app state, so we use the real schema dir like the query tests do.
    """
    app = create_app(schema_dir=schema_dir)
    return TestClient(app, raise_server_exceptions=False)


# ---------------------------------------------------------------------------
# Group A — Auth
# ---------------------------------------------------------------------------

class TestAuth:
    """Auth enforcement on POST /v1/feedback — uses the CLIENT key (user-facing)."""

    def test_a1_missing_api_key_returns_401(self):
        """No X-API-Key header → 401 Unauthorized."""
        with make_client() as client:
            response = client.post("/v1/feedback", json=VALID_FEEDBACK_PASS)
        assert response.status_code == 401

    def test_a2_wrong_api_key_returns_401(self):
        """Wrong X-API-Key value → 401 Unauthorized."""
        with make_client() as client:
            response = client.post(
                "/v1/feedback",
                json=VALID_FEEDBACK_PASS,
                headers={"X-API-Key": WRONG_KEY},
            )
        assert response.status_code == 401

    def test_a3_foundry_key_rejected_on_user_endpoint(self):
        """
        Foundry key on a user-facing endpoint → 401.
        /v1/feedback is protected by require_client_key, so the foundry key
        must not be accepted here.
        """
        with make_client() as client:
            response = client.post(
                "/v1/feedback",
                json=VALID_FEEDBACK_PASS,
                headers={"X-API-Key": FOUNDRY_KEY},
            )
        assert response.status_code == 401

    def test_a4_correct_client_key_is_not_blocked(self):
        """Correct client X-API-Key → request is not rejected by auth."""
        with make_client() as client:
            response = client.post(
                "/v1/feedback",
                json=VALID_FEEDBACK_PASS,
                headers={"X-API-Key": VALID_KEY},
            )
        assert response.status_code != 401


# ---------------------------------------------------------------------------
# Group B — Request Validation (Pydantic 422)
# ---------------------------------------------------------------------------

class TestRequestValidation:
    """FeedbackRequest body validation — malformed bodies rejected with 422."""

    def test_b1_missing_request_id_returns_422(self):
        """request_id is required → omitting it → 422."""
        with make_client() as client:
            response = client.post(
                "/v1/feedback",
                json={"status": "pass"},
                headers={"X-API-Key": VALID_KEY},
            )
        assert response.status_code == 422

    def test_b2_missing_status_returns_422(self):
        """status is required → omitting it → 422."""
        with make_client() as client:
            response = client.post(
                "/v1/feedback",
                json={"request_id": "orig-req-123"},
                headers={"X-API-Key": VALID_KEY},
            )
        assert response.status_code == 422

    def test_b3_invalid_status_value_returns_422(self):
        """status must be 'pass' or 'fail' → any other value → 422."""
        with make_client() as client:
            response = client.post(
                "/v1/feedback",
                json={"request_id": "orig-req-123", "status": "maybe"},
                headers={"X-API-Key": VALID_KEY},
            )
        assert response.status_code == 422

    def test_b4_empty_body_returns_422(self):
        """Empty body → both required fields missing → 422."""
        with make_client() as client:
            response = client.post(
                "/v1/feedback",
                json={},
                headers={"X-API-Key": VALID_KEY},
            )
        assert response.status_code == 422


# ---------------------------------------------------------------------------
# Group C — Success
# ---------------------------------------------------------------------------

class TestSuccess:
    """Successful feedback submission via POST /v1/feedback."""

    def test_c1_pass_feedback_returns_success_envelope(self):
        """
        C1: Valid 'pass' feedback → 200, status="success", errors=[].
        """
        with make_client() as client:
            response = client.post(
                "/v1/feedback",
                json=VALID_FEEDBACK_PASS,
                headers={"X-API-Key": VALID_KEY},
            )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["errors"] == []

    def test_c2_fail_feedback_with_optional_fields_returns_200(self):
        """
        C2: Valid 'fail' feedback including expected_output + actual_sql → 200.
        Confirms the optional fields are accepted.
        """
        with make_client() as client:
            response = client.post(
                "/v1/feedback",
                json=VALID_FEEDBACK_FAIL,
                headers={"X-API-Key": VALID_KEY},
            )
        assert response.status_code == 200
        assert response.json()["status"] == "success"

    def test_c3_request_id_echoed_in_response(self):
        """
        C3: The original query's request_id is echoed back unchanged.
        """
        with make_client() as client:
            response = client.post(
                "/v1/feedback",
                json=VALID_FEEDBACK_PASS,
                headers={"X-API-Key": VALID_KEY},
            )
        assert response.json()["request_id"] == VALID_FEEDBACK_PASS["request_id"]


# ---------------------------------------------------------------------------
# Group D — Logging
# ---------------------------------------------------------------------------

class TestLogging:
    """
    Verify the endpoint logs a USER_FEEDBACK entry with the correct content.

    StructuredLogger is patched in the feedback module so no real file is written
    and the LogEntry passed to .log() can be inspected directly.
    """

    def test_d1_logs_one_user_feedback_entry(self):
        """
        D1: A valid request triggers exactly one log call, stage=USER_FEEDBACK.
        """
        with make_client() as client:
            with patch("src.api.v1.feedback.StructuredLogger") as mock_logger_cls:
                response = client.post(
                    "/v1/feedback",
                    json=VALID_FEEDBACK_PASS,
                    headers={"X-API-Key": VALID_KEY},
                )
        assert response.status_code == 200
        mock_logger_cls.return_value.log.assert_called_once()
        entry = mock_logger_cls.return_value.log.call_args.args[0]
        assert entry.stage == USER_FEEDBACK

    def test_d2_logged_payload_contains_feedback_fields(self):
        """
        D2: The logged payload carries the submitted status, expected_output, actual_sql.
        """
        with make_client() as client:
            with patch("src.api.v1.feedback.StructuredLogger") as mock_logger_cls:
                response = client.post(
                    "/v1/feedback",
                    json=VALID_FEEDBACK_FAIL,
                    headers={"X-API-Key": VALID_KEY},
                )
        assert response.status_code == 200
        entry = mock_logger_cls.return_value.log.call_args.args[0]
        assert entry.payload["status"] == VALID_FEEDBACK_FAIL["status"]
        assert entry.payload["expected_output"] == VALID_FEEDBACK_FAIL["expected_output"]
        assert entry.payload["actual_sql"] == VALID_FEEDBACK_FAIL["actual_sql"]

    def test_d3_logged_request_id_matches_body(self):
        """
        D3: The logged entry's request_id matches the request_id in the body
        (so feedback correlates with the original query's log file).
        """
        with make_client() as client:
            with patch("src.api.v1.feedback.StructuredLogger") as mock_logger_cls:
                response = client.post(
                    "/v1/feedback",
                    json=VALID_FEEDBACK_PASS,
                    headers={"X-API-Key": VALID_KEY},
                )
        assert response.status_code == 200
        entry = mock_logger_cls.return_value.log.call_args.args[0]
        assert entry.request_id == VALID_FEEDBACK_PASS["request_id"]
