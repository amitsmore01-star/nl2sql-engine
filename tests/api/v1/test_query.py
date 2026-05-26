# tests/api/v1/test_query.py
# V0 - Initial implementation
# V1 - Story 3.7: Updated for orchestrator-based pipeline and temporary QueryContext
#                 response shape.
#                 - Groups C and E rewritten — response is now a flat QueryContext dict,
#                   not QueryResponse. Top-level fields: status, app_id, llm_output,
#                   error, request_id, sql etc.
#                 - Group D rewritten — business errors now in context.error (dict with
#                   code + message), not in errors[] list.
#                 - Groups A and B unchanged — auth and validation behaviour identical.
#                 - MockLLMProvider injected into app.state after lifespan startup so
#                   NL-to-IR stage has something to call on success paths.
#                 - make_client_with_mock_llm() helper added for success-path tests.
#                 TODO (Story 5.4): Rewrite Groups C, D, E again when final QueryResponse
#                 shape replaces the temporary QueryContext response.
#
# Tests for POST /v1/query — user-facing query endpoint.
#
# Test groups:
#   A — Auth (missing/wrong key)                   [unchanged from V0]
#   B — Request validation (Pydantic errors)        [unchanged from V0]
#   C — Success responses                           [rewritten for QueryContext shape]
#   D — Business errors (HTTP 200)                  [rewritten for QueryContext shape]
#   E — Internal errors (HTTP 500)                  [rewritten for QueryContext shape]
#
# Fixtures used from tests/api/conftest.py (autouse):
#   set_test_env_vars — injects ENV, CLIENT_API_KEY, FOUNDRY_API_KEY, LLM_PROVIDER
#
# HOW TestClient WORKS:
#   FastAPI's TestClient wraps the app in a fake HTTP server.
#   We use it as a context manager (with TestClient(app) as client:) so the
#   lifespan startup runs — this loads schemas and sets app.state.
#   Without the context manager, app.state fields would be None.

import json

from fastapi.testclient import TestClient

from src.api.app import create_app
from src.llm.mock_provider import MockLLMProvider

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

# Minimal valid simplified IR — what MockLLMProvider returns for success paths.
# SingleCallStrategy parses this and writes it to context.llm_output.
_GOLDEN_IR = json.dumps({
    "tables": [
        {"table": "Major.Customer", "source": "customer"},
    ],
    "columns": [
        {
            "table": "Major.Customer",
            "column": "CustomerCID",
            "source": "customers",
        }
    ],
    "filters": [],
    "limit": None,
    "aggregation": None,
    "sort": [],
})


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_client(schema_dir="schemas") -> TestClient:
    """
    Create a TestClient using the real ABC schema directory.
    Used for tests that do not need the NL-to-IR stage to run
    (auth tests, validation tests, business errors caught before LLM).
    """
    app = create_app(schema_dir=schema_dir)
    return TestClient(app, raise_server_exceptions=False)


def make_client_with_mock_llm(schema_dir="schemas") -> TestClient:
    """
    Create a TestClient with MockLLMProvider injected into app.state.

    Used for success-path tests where the NL-to-IR stage must run.
    The mock LLM returns _GOLDEN_IR so the stage completes without a real API call.

    IMPORTANT: We return the TestClient object directly (not as a context manager).
    The caller uses it as a context manager (with make_client_with_mock_llm() as client:)
    which triggers __enter__ → lifespan startup → then we override app.state.llm_provider.

    Why override after construction not before:
        app.state is only set during the lifespan startup (inside the context manager).
        Before __enter__ runs, app.state does not exist yet.
        We inject the mock inside the with block, after startup has run.
    """
    app = create_app(schema_dir=schema_dir)
    client = TestClient(app, raise_server_exceptions=False)
    # Inject mock AFTER entering context (lifespan has run, app.state exists).
    # Callers must use: with make_client_with_mock_llm() as client: ...
    # The injection happens inside the with block before any request is made.
    return client


# ---------------------------------------------------------------------------
# Group A — Auth
# The auth dependency runs BEFORE the route handler.
# A wrong or missing key never reaches run_pipeline().
# Unchanged from V0 — auth behaviour is identical.
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
        assert response.status_code != 401


# ---------------------------------------------------------------------------
# Group B — Request Validation (Pydantic)
# FastAPI validates the request body before calling the route handler.
# Invalid bodies return HTTP 422 Unprocessable Entity automatically.
# Unchanged from V0 — validation behaviour is identical.
# ---------------------------------------------------------------------------

class TestRequestValidation:
    """Pydantic request body validation on POST /v1/query."""

    def test_b1_missing_nl_query_returns_422(self):
        """Body without nl_query field → 422."""
        with make_client() as client:
            response = client.post(
                "/v1/query",
                json={"user_id": "test-user"},
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
                json={"nl_query": "give me customers in ABC"},
                headers={"X-API-Key": VALID_KEY},
            )
        assert response.status_code == 422

    def test_b5_omitted_request_id_is_auto_generated(self):
        """
        request_id not provided in body → auto-generated UUID in response.
        QueryRequest.request_id has default_factory=uuid.uuid4.
        The response (QueryContext dict) must contain a non-empty request_id.
        """
        app = create_app(schema_dir="schemas")
        with TestClient(app, raise_server_exceptions=False) as client:
            # Inject mock after lifespan startup
            app.state.llm_provider = MockLLMProvider(responses=[_GOLDEN_IR])
            response = client.post(
                "/v1/query",
                json=VALID_BODY,
                headers={"X-API-Key": VALID_KEY},
            )
        data = response.json()
        assert "request_id" in data
        assert data["request_id"]
        assert len(data["request_id"]) > 0


# ---------------------------------------------------------------------------
# Group C — Success
# Response is now a flat QueryContext dict (temporary — Story 5.4 finalises).
# Top-level fields: status, app_id, app_schema_version, llm_output, sql, request_id.
# ---------------------------------------------------------------------------

class TestSuccess:
    """Successful pipeline run via POST /v1/query."""

    def test_c1_synonym_match_returns_correct_app(self):
        """
        Query containing 'ABC' matches ABC_app via appSynonyms.
        Response: status=success, app_id=ABC_app, app_schema_version=1.0.
        """
        app = create_app(schema_dir="schemas")
        with TestClient(app, raise_server_exceptions=False) as client:
            app.state.llm_provider = MockLLMProvider(responses=[_GOLDEN_IR])
            response = client.post(
                "/v1/query",
                json={"nl_query": "give me customers in ABC office", "user_id": "test-user"},
                headers={"X-API-Key": VALID_KEY},
            )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["app_id"] == "ABC_app"
        assert data["app_schema_version"] == "1.0"

    def test_c2_llm_output_populated_after_full_pipeline(self):
        """
        All three stages ran — llm_output is populated in the response.
        Confirms Intent Guard passed and NL-to-IR Strategy completed.
        """
        app = create_app(schema_dir="schemas")
        with TestClient(app, raise_server_exceptions=False) as client:
            app.state.llm_provider = MockLLMProvider(responses=[_GOLDEN_IR])
            response = client.post(
                "/v1/query",
                json=VALID_BODY,
                headers={"X-API-Key": VALID_KEY},
            )
        assert response.status_code == 200
        data = response.json()
        assert data["llm_output"] is not None
        assert "tables" in data["llm_output"]

    def test_c3_sql_is_none_until_story_5_4(self):
        """
        sql is None — SQL builder not wired yet (Story 5.4).
        Confirms the temporary response shape correctly leaves sql empty.
        """
        app = create_app(schema_dir="schemas")
        with TestClient(app, raise_server_exceptions=False) as client:
            app.state.llm_provider = MockLLMProvider(responses=[_GOLDEN_IR])
            response = client.post(
                "/v1/query",
                json=VALID_BODY,
                headers={"X-API-Key": VALID_KEY},
            )
        assert response.status_code == 200
        data = response.json()
        assert data["sql"] is None

    def test_c4_request_id_echoed_in_response(self):
        """
        request_id sent in request body must appear unchanged in response.
        """
        my_request_id = "test-req-id-abc123"
        app = create_app(schema_dir="schemas")
        with TestClient(app, raise_server_exceptions=False) as client:
            app.state.llm_provider = MockLLMProvider(responses=[_GOLDEN_IR])
            response = client.post(
                "/v1/query",
                json={**VALID_BODY, "request_id": my_request_id},
                headers={"X-API-Key": VALID_KEY},
            )
        data = response.json()
        assert data["request_id"] == my_request_id


# ---------------------------------------------------------------------------
# Group D — Business Errors (HTTP 200)
# Business errors are now in context.error (dict: code + message).
# context.status = "failed". HTTP 200 per architecture rule.
# ---------------------------------------------------------------------------

class TestBusinessErrors:
    """Business errors from pipeline stages — all return HTTP 200."""

    def test_d1_unrecognised_app_returns_app_not_determined(self):
        """
        Query with no recognisable app name → APP_NOT_DETERMINED.
        HTTP 200, status=failed, error.code=APP_NOT_DETERMINED.
        """
        with make_client() as client:
            response = client.post(
                "/v1/query",
                json={
                    "nl_query": "give me all the data please",
                    "user_id": "test-user",
                },
                headers={"X-API-Key": VALID_KEY},
            )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "failed"
        assert data["error"]["code"] == "APP_NOT_DETERMINED"

    def test_d2_unknown_explicit_app_id_returns_app_not_determined(self):
        """
        Explicit app_id='UNKNOWN_APP' does not match any loaded schema.
        HTTP 200, status=failed, error.code=APP_NOT_DETERMINED.
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
        assert data["error"]["code"] == "APP_NOT_DETERMINED"

    def test_d3_non_select_query_returns_unsupported_intent(self):
        """
        Non-SELECT keyword in query → UNSUPPORTED_INTENT from Intent Guard.
        HTTP 200, status=failed, error.code=UNSUPPORTED_INTENT.
        App must be recognised first — Intent Guard runs after App Identifier.
        """
        with make_client() as client:
            response = client.post(
                "/v1/query",
                json={
                    "nl_query": "DELETE all customers in ABC",
                    "user_id": "test-user",
                },
                headers={"X-API-Key": VALID_KEY},
            )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "failed"
        assert data["error"]["code"] == "UNSUPPORTED_INTENT"


# ---------------------------------------------------------------------------
# Group E — Internal Error (HTTP 500)
# Simulates a broken startup where schema_repo was not loaded.
# Response is now a QueryContext dict (not QueryResponse with errors[]).
# ---------------------------------------------------------------------------

class TestInternalError:
    """Internal server errors return HTTP 500 with structured error body."""

    def test_e1_none_schema_repo_returns_500(self):
        """
        Simulate broken startup: set app.state.schema_repo = None after startup.
        Endpoint catches RuntimeError and returns INTERNAL_ERROR with HTTP 500.
        Response body is a QueryContext dict:
          status=failed, error.code=INTERNAL_ERROR.
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
        assert data["error"]["code"] == "INTERNAL_ERROR"
