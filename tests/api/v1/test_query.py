# tests/api/v1/test_query.py
# V0 - Initial implementation
# V1 - Story 3.7: Updated for orchestrator-based pipeline and temporary QueryContext
#                 response shape.
# V2 - Story 5.4: Groups C, D, E rewritten for final QueryResponse shape (Section 10.3).
#                 Groups A and B unchanged — auth and validation behaviour identical.
#                 Final shape has top-level keys: request_id, status, data, meta, errors.
#                 data.sql now populated on success (full pipeline runs).
#                 errors[] list replaces context.error dict for business errors.
#                 C3 (sql is None) removed — replaced with C2 (sql is populated).
#
# Tests for POST /v1/query — user-facing query endpoint.
#
# Test groups:
#   A — Auth (missing/wrong key)                   [unchanged from V1]
#   B — Request validation (Pydantic errors)        [unchanged from V1]
#   C — Success responses                           [rewritten for final QueryResponse shape]
#   D — Business errors (HTTP 200)                  [rewritten for final QueryResponse shape]
#   E — Internal errors (HTTP 500)                  [rewritten for final QueryResponse shape]

import json

from fastapi.testclient import TestClient

from src.api.app import create_app
from src.llm.mock_provider import MockLLMProvider

# ---------------------------------------------------------------------------
# Shared test constants
# ---------------------------------------------------------------------------

VALID_KEY = "test-client-key-12345"
WRONG_KEY = "wrong-key"

VALID_BODY = {
    "nl_query": "give me customers in Acme",
    "user_id": "test-user",
}

# Minimal valid simplified IR — two tables so validator can resolve a join.
# Major.Customer and Major.CustomerDemographics have a direct relationship
# in Acme_app.json — join resolver will produce a valid StructuredQuery.
_GOLDEN_IR = json.dumps({
    "tables": [
        {"table": "Major.Customer", "source": "customer"},
        {"table": "Major.CustomerDemographics", "source": "customer name"},
    ],
    "columns": [
        {
            "table": "Major.CustomerDemographics",
            "column": "CustomerName",
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
    Create a TestClient using the real Acme schema directory.
    Used for tests that do not need the NL-to-IR stage to run
    (auth tests, validation tests, business errors caught before LLM).
    """
    app = create_app(schema_dir=schema_dir)
    return TestClient(app, raise_server_exceptions=False)


# ---------------------------------------------------------------------------
# Group A — Auth  [unchanged from V1]
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
        """Correct X-API-Key → request is not rejected by auth."""
        with make_client() as client:
            response = client.post(
                "/v1/query",
                json=VALID_BODY,
                headers={"X-API-Key": VALID_KEY},
            )
        assert response.status_code != 401


# ---------------------------------------------------------------------------
# Group B — Request Validation  [unchanged from V1]
# ---------------------------------------------------------------------------

class TestRequestValidation:
    """Pydantic request body validation on POST /v1/query."""

    def test_b1_missing_nl_query_returns_422(self):
        with make_client() as client:
            response = client.post(
                "/v1/query",
                json={"user_id": "test-user"},
                headers={"X-API-Key": VALID_KEY},
            )
        assert response.status_code == 422

    def test_b2_empty_nl_query_returns_422(self):
        with make_client() as client:
            response = client.post(
                "/v1/query",
                json={"nl_query": "", "user_id": "test-user"},
                headers={"X-API-Key": VALID_KEY},
            )
        assert response.status_code == 422

    def test_b3_whitespace_only_nl_query_returns_422(self):
        with make_client() as client:
            response = client.post(
                "/v1/query",
                json={"nl_query": "   ", "user_id": "test-user"},
                headers={"X-API-Key": VALID_KEY},
            )
        assert response.status_code == 422

    def test_b4_missing_user_id_returns_422(self):
        with make_client() as client:
            response = client.post(
                "/v1/query",
                json={"nl_query": "give me customers in Acme"},
                headers={"X-API-Key": VALID_KEY},
            )
        assert response.status_code == 422

    def test_b5_request_id_auto_generated_when_omitted(self):
        """
        No request_id in body → auto-generated UUID appears in response.
        Confirms QueryContext generates it via default_factory.
        """
        app = create_app(schema_dir="schemas")
        with TestClient(app, raise_server_exceptions=False) as client:
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
# Group C — Success (final QueryResponse shape)
# ---------------------------------------------------------------------------

class TestSuccess:
    """Successful pipeline run via POST /v1/query — final QueryResponse shape."""

    def test_c1_response_has_correct_top_level_keys(self):
        """
        C1: Response envelope has all required top-level keys:
            request_id, status, data, meta, errors.
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
        assert "request_id" in data
        assert "status" in data
        assert "data" in data
        assert "meta" in data
        assert "errors" in data

    def test_c2_data_sql_is_populated_on_success(self):
        """
        C2: Full pipeline ran — data.sql is a non-empty string.
        This confirms the SQL Builder stage completed end-to-end via the API.
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
        assert data["data"]["sql"] is not None
        assert len(data["data"]["sql"]) > 0
        assert "SELECT" in data["data"]["sql"]

    def test_c3_meta_contains_app_id(self):
        """
        C3: meta.app_id = "Acme_app" after successful pipeline run.
        """
        app = create_app(schema_dir="schemas")
        with TestClient(app, raise_server_exceptions=False) as client:
            app.state.llm_provider = MockLLMProvider(responses=[_GOLDEN_IR])
            response = client.post(
                "/v1/query",
                json={"nl_query": "give me customer name in Acme office", "user_id": "test-user"},
                headers={"X-API-Key": VALID_KEY},
            )
        assert response.status_code == 200
        data = response.json()
        assert data["meta"]["app_id"] == "Acme_app"

    def test_c4_request_id_echoed_in_response(self):
        """
        C4: request_id sent in request body appears unchanged at top level of response.
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

    def test_c5_status_is_success(self):
        """
        C5: status = "success" on a clean pipeline run.
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
        assert data["status"] == "success"


# ---------------------------------------------------------------------------
# Group D — Business Errors (HTTP 200, errors[] list)
# ---------------------------------------------------------------------------

class TestBusinessErrors:
    """Business errors from pipeline stages — HTTP 200, errors[] list populated."""

    def test_d1_unrecognised_app_returns_app_not_determined(self):
        """
        D1: Query with no recognisable app → APP_NOT_DETERMINED.
        HTTP 200, status=failed, errors[0].code=APP_NOT_DETERMINED.
        """
        with make_client() as client:
            response = client.post(
                "/v1/query",
                json={"nl_query": "give me all the data please", "user_id": "test-user"},
                headers={"X-API-Key": VALID_KEY},
            )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "failed"
        assert len(data["errors"]) > 0
        assert data["errors"][0]["code"] == "APP_NOT_DETERMINED"

    def test_d2_unknown_explicit_app_id_returns_app_not_determined(self):
        """
        D2: Explicit app_id='UNKNOWN_APP' does not match any loaded schema.
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

    def test_d3_non_select_query_returns_unsupported_intent(self):
        """
        D3: Non-SELECT keyword in query → UNSUPPORTED_INTENT from Intent Guard.
        HTTP 200, status=failed, errors[0].code=UNSUPPORTED_INTENT.
        """
        with make_client() as client:
            response = client.post(
                "/v1/query",
                json={"nl_query": "DELETE all customers in Acme", "user_id": "test-user"},
                headers={"X-API-Key": VALID_KEY},
            )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "failed"
        assert data["errors"][0]["code"] == "UNSUPPORTED_INTENT"


# ---------------------------------------------------------------------------
# Group E — Internal Error (HTTP 500)
# ---------------------------------------------------------------------------

class TestInternalError:
    """Internal server errors return HTTP 500 with structured error body."""

    def test_e1_none_schema_repo_returns_500(self):
        """
        E1: Simulate broken startup: set app.state.schema_repo = None.
        HTTP 500, errors[0].code=INTERNAL_ERROR.
        Response uses final QueryResponse shape — errors[] list, not context.error dict.
        """
        app = create_app(schema_dir="schemas")
        with TestClient(app, raise_server_exceptions=False) as client:
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
