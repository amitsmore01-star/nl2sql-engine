# tests/api/v1/test_query.py
# V0 - Initial implementation
#
# Tests for POST /v1/query — user-facing query endpoint skeleton.
#
# Story 2.6 scope:
#   - Auth enforcement (CLIENT_API_KEY)
#   - Request body validation (Pydantic)
#   - App identifier success (synonym match + explicit app_id)
#   - Business errors returned as HTTP 200 with error envelope
#   - Internal error (broken schema_repo) returned as HTTP 500
#
# Test groups:
#   A — Auth (missing/wrong key)
#   B — Request validation (Pydantic errors)
#   C — Success responses
#   D — Business errors (HTTP 200)
#   E — Internal errors (HTTP 500)
#
# Fixtures used from tests/api/conftest.py (autouse):
#   set_test_env_vars — injects ENV, CLIENT_API_KEY, FOUNDRY_API_KEY, LLM_PROVIDER
#
# HOW TestClient WORKS:
#   FastAPI's TestClient wraps the app in a fake HTTP server.
#   We use it as a context manager (with TestClient(app) as client:) so the
#   lifespan startup runs — this loads schemas and sets app.state.
#   Without the context manager, app.state fields would be None.

import pytest
from fastapi.testclient import TestClient

from src.api.app import create_app

# ---------------------------------------------------------------------------
# Shared test constants
# ---------------------------------------------------------------------------

# Must match CLIENT_API_KEY set in tests/api/conftest.py
VALID_KEY = "test-client-key-12345"
WRONG_KEY = "wrong-key"

# Valid request body used as base in most tests
VALID_BODY = {
    "nl_query": "give me customers in ABC",
    "user_id": "test-user",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_client(schema_dir="schemas") -> TestClient:
    """
    Create a TestClient using the real ABC schema directory.

    Why pass schema_dir:
        create_app(schema_dir=...) lets tests point at the real schemas/
        folder without relying on the YAML config reading from disk.
        Tests stay self-contained.
    """
    app = create_app(schema_dir=schema_dir)
    return TestClient(app, raise_server_exceptions=False)
    # raise_server_exceptions=False means HTTP 500 responses are returned
    # as normal responses rather than re-raising the exception in the test.


# ---------------------------------------------------------------------------
# Group A — Auth
# The auth dependency runs BEFORE the route handler.
# A wrong or missing key never reaches run_app_identifier().
# ---------------------------------------------------------------------------

class TestAuth:
    """Auth enforcement on POST /v1/query."""

    def test_a1_missing_api_key_returns_401(self):
        """No X-API-Key header → 401 Unauthorized."""
        with make_client() as client:
            response = client.post("/v1/query", json=VALID_BODY)
        assert response.status_code == 401

    def test_a2_wrong_api_key_returns_401(self):
        """Wrong X-API-Key value → 401 Unauthorized."""
        with make_client() as client:
            response = client.post(
                "/v1/query",
                json=VALID_BODY,
                headers={"X-API-Key": WRONG_KEY},
            )
        assert response.status_code == 401

    def test_a3_correct_api_key_is_not_blocked(self):
        """Correct X-API-Key → request is not rejected by auth (may fail for other reasons)."""
        with make_client() as client:
            response = client.post(
                "/v1/query",
                json=VALID_BODY,
                headers={"X-API-Key": VALID_KEY},
            )
        # Auth passed — we get something other than 401
        assert response.status_code != 401


# ---------------------------------------------------------------------------
# Group B — Request Validation (Pydantic)
# FastAPI validates the request body before calling the route handler.
# Invalid bodies return HTTP 422 Unprocessable Entity automatically.
# ---------------------------------------------------------------------------

class TestRequestValidation:
    """Pydantic request body validation on POST /v1/query."""

    def test_b1_missing_nl_query_returns_422(self):
        """Body without nl_query field → 422."""
        with make_client() as client:
            response = client.post(
                "/v1/query",
                json={"user_id": "test-user"},  # nl_query missing
                headers={"X-API-Key": VALID_KEY},
            )
        assert response.status_code == 422

    def test_b2_empty_nl_query_returns_422(self):
        """nl_query as empty string → 422 (validator rejects empty)."""
        with make_client() as client:
            response = client.post(
                "/v1/query",
                json={"nl_query": "", "user_id": "test-user"},
                headers={"X-API-Key": VALID_KEY},
            )
        assert response.status_code == 422

    def test_b3_whitespace_only_nl_query_returns_422(self):
        """nl_query as whitespace only → 422 (validator strips then checks)."""
        with make_client() as client:
            response = client.post(
                "/v1/query",
                json={"nl_query": "   ", "user_id": "test-user"},
                headers={"X-API-Key": VALID_KEY},
            )
        assert response.status_code == 422

    def test_b4_missing_user_id_returns_422(self):
        """Body without user_id field → 422."""
        with make_client() as client:
            response = client.post(
                "/v1/query",
                json={"nl_query": "give me customers in ABC"},  # user_id missing
                headers={"X-API-Key": VALID_KEY},
            )
        assert response.status_code == 422

    def test_b5_omitted_request_id_is_auto_generated(self):
        """
        request_id not provided in body → auto-generated UUID in response.

        QueryRequest.request_id has default_factory=uuid.uuid4, so Pydantic
        generates one automatically. The response must echo it back.
        """
        with make_client() as client:
            response = client.post(
                "/v1/query",
                json=VALID_BODY,  # no request_id in VALID_BODY
                headers={"X-API-Key": VALID_KEY},
            )
        data = response.json()
        assert "request_id" in data
        assert data["request_id"]  # must be non-empty
        assert len(data["request_id"]) > 0


# ---------------------------------------------------------------------------
# Group C — Success
# Valid request, app schema identified, skeleton response returned.
# ---------------------------------------------------------------------------

class TestSuccess:
    """Successful app identification via POST /v1/query."""

    def test_c1_synonym_match_returns_correct_app(self):
        """
        Query containing 'ABC' matches ABC_app via appSynonyms.
        Response: status=success, meta.app_id=ABC_app, meta.app_schema_version=1.0.
        """
        with make_client() as client:
            response = client.post(
                "/v1/query",
                json={"nl_query": "give me customers in ABC office", "user_id": "test-user"},
                headers={"X-API-Key": VALID_KEY},
            )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["meta"]["app_id"] == "ABC_app"
        assert data["meta"]["app_schema_version"] == "1.0"

    def test_c2_explicit_app_id_bypasses_synonym_matching(self):
        """
        Explicit app_id='ABC_app' in body → same result as synonym match.
        App identifier takes Path 1 (explicit) instead of Path 2 (synonym).
        """
        with make_client() as client:
            response = client.post(
                "/v1/query",
                json={
                    "nl_query": "give me all customers",  # no app name in query
                    "user_id": "test-user",
                    "app_id": "ABC_app",
                },
                headers={"X-API-Key": VALID_KEY},
            )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["meta"]["app_id"] == "ABC_app"

    def test_c3_sql_is_none_in_skeleton_response(self):
        """
        data.sql is None — SQL builder not wired yet (Story 5.4).
        This test confirms the skeleton correctly leaves sql empty.
        """
        with make_client() as client:
            response = client.post(
                "/v1/query",
                json=VALID_BODY,
                headers={"X-API-Key": VALID_KEY},
            )
        assert response.status_code == 200
        data = response.json()
        assert data["data"]["sql"] is None

    def test_c4_request_id_echoed_in_response(self):
        """
        request_id sent in request body must appear unchanged in response.
        This allows the caller to correlate responses back to their requests.
        """
        my_request_id = "test-req-id-abc123"
        with make_client() as client:
            response = client.post(
                "/v1/query",
                json={**VALID_BODY, "request_id": my_request_id},
                headers={"X-API-Key": VALID_KEY},
            )
        data = response.json()
        assert data["request_id"] == my_request_id


# ---------------------------------------------------------------------------
# Group D — Business Errors (HTTP 200)
# The pipeline handled the error — it is a known, structured outcome.
# Per architecture: business errors always return HTTP 200, not 4xx.
# The caller inspects status and errors[] to detect failure.
# ---------------------------------------------------------------------------

class TestBusinessErrors:
    """Business errors from app identifier — all return HTTP 200."""

    def test_d1_unrecognised_app_returns_app_not_determined(self):
        """
        Query with no recognisable app name → APP_NOT_DETERMINED.
        HTTP 200, status=failed, errors[0].code=APP_NOT_DETERMINED.
        """
        with make_client() as client:
            response = client.post(
                "/v1/query",
                json={
                    "nl_query": "give me all the data please",  # no app name
                    "user_id": "test-user",
                },
                headers={"X-API-Key": VALID_KEY},
            )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "failed"
        assert len(data["errors"]) > 0
        assert data["errors"][0]["code"] == "APP_NOT_DETERMINED"

    def test_d2_unknown_explicit_app_id_returns_app_not_determined(self):
        """
        Explicit app_id='UNKNOWN_APP' does not match any loaded schema.
        HTTP 200, status=failed, errors[0].code=APP_NOT_DETERMINED.
        """
        with make_client() as client:
            response = client.post(
                "/v1/query",
                json={
                    "nl_query": "give me all customers",
                    "user_id": "test-user",
                    "app_id": "UNKNOWN_APP",
                },
                headers={"X-API-Key": VALID_KEY},
            )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "failed"
        assert data["errors"][0]["code"] == "APP_NOT_DETERMINED"


# ---------------------------------------------------------------------------
# Group E — Internal Error (HTTP 500)
# Simulates a broken startup where schema_repo was not loaded.
# The endpoint must catch this and return a structured 500 response —
# never a raw Python traceback.
# ---------------------------------------------------------------------------

class TestInternalError:
    """Internal server errors return HTTP 500 with structured error body."""

    def test_e1_none_schema_repo_returns_500(self):
        """
        Simulate broken startup: set app.state.schema_repo = None after startup.
        Endpoint catches RuntimeError and returns INTERNAL_ERROR with HTTP 500.

        Why we patch app.state after startup:
            The TestClient lifespan runs startup normally (schemas load fine).
            We then forcibly break schema_repo to simulate a partial startup failure.
            This is the safest way to test the internal error path without
            creating a completely broken test schema directory.
        """
        app = create_app(schema_dir="schemas")
        with TestClient(app, raise_server_exceptions=False) as client:
            # Forcibly break schema_repo after startup succeeded
            app.state.schema_repo = None

            response = client.post(
                "/v1/query",
                json=VALID_BODY,
                headers={"X-API-Key": VALID_KEY},
            )

        assert response.status_code == 500
        data = response.json()
        assert data["status"] == "failed"
        assert len(data["errors"]) > 0
        assert data["errors"][0]["code"] == "INTERNAL_ERROR"
