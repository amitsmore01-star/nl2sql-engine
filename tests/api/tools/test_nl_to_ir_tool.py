# tests/api/tools/test_nl_to_ir_tool.py
# V0 - Initial implementation
#
# Tests for POST /v1/tools/nl-to-ir — Foundry NL-to-IR tool endpoint.
#
# What this endpoint does:
#   1. Validates required QueryContext fields (nl_query_original, app_id,
#      app_schema_version) — returns 400 if any are missing.
#   2. Runs Intent Guard — blocks non-SELECT queries, returns 200 with
#      UNSUPPORTED_INTENT error (no LLM call made).
#   3. Runs NL-to-IR Strategy — one LLM call, populates context.llm_output.
#   4. Returns ToolResponse with updated QueryContext.
#
# Test groups:
#   A — Auth (wrong/missing key)
#   B — Context field validation (missing required fields)
#   C — Intent Guard blocks non-select queries
#   D — Success path (llm_output populated)
#   E — Schema not found for app_id
#
# Fixtures used from tests/api/conftest.py (autouse):
#   set_test_env_vars — injects ENV, CLIENT_API_KEY, FOUNDRY_API_KEY, LLM_PROVIDER
#
# How MockLLMProvider is injected:
#   Same pattern as test_query.py — create_app() starts with the real mock
#   provider (LLM_PROVIDER=mock in conftest). For success-path tests we
#   override app.state.llm_provider with a MockLLMProvider loaded with the
#   exact IR JSON we want returned, after the lifespan has run.

import json

from fastapi.testclient import TestClient

from src.api.app import create_app
from src.llm.mock_provider import MockLLMProvider

# ---------------------------------------------------------------------------
# Shared test constants
# ---------------------------------------------------------------------------

# Must match FOUNDRY_API_KEY set in tests/api/conftest.py
FOUNDRY_KEY = "test-foundry-key-67890"
CLIENT_KEY = "test-client-key-12345"
WRONG_KEY = "wrong-key"

# Minimal valid simplified IR — what MockLLMProvider returns on success paths.
_GOLDEN_IR = json.dumps({
    "tables": [
        {"table": "Major.Customer", "source": "customer"},
    ],
    "columns": [
        {
            "table": "Major.CustomerDemographics",
            "column": "CustomerName",
            "source": "customer name",
        }
    ],
    "filters": [],
    "limit": None,
    "aggregation": None,
    "sort": [],
})

# A valid QueryContext body with all required fields for "nl-to-ir" stage.
# Used as the base dict — tests modify copies of this.
_VALID_CONTEXT = {
    "request_id": "test-req-001",
    "user_id": "test-agent",
    "app_id": "Acme_app",
    "app_schema_version": "1.0",
    "nl_query_original": "give me customer name for customer CUST01 in Acme",
    "nl_query_corrected": None,
    "llm_output": None,
    "resolved_tables": [],
    "resolved_columns": [],
    "resolved_filters": [],
    "resolved_joins": [],
    "applied_rules": [],
    "structured_query": None,
    "sql": None,
    "latency_ms": {},
    "total_latency_ms": 0,
    "token_usage": {},
    "warnings": [],
    "status": "success",
    "error": None,
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_client() -> TestClient:
    """
    Create a TestClient using the real Acme schema directory.
    Used for auth, validation, and intent guard tests — no real LLM call needed.
    The default MockLLMProvider (from conftest LLM_PROVIDER=mock) is sufficient.
    """
    app = create_app(schema_dir="schemas")
    return TestClient(app, raise_server_exceptions=False)


# ---------------------------------------------------------------------------
# Group A — Authentication
# Tool endpoints use FOUNDRY_API_KEY, not CLIENT_API_KEY.
# Keys are not interchangeable — using the wrong key returns 401.
# ---------------------------------------------------------------------------

class TestAuth:
    """Auth enforcement on POST /v1/tools/nl-to-ir."""

    def test_a1_missing_api_key_returns_401(self):
        """No X-API-Key header → 401."""
        with make_client() as client:
            response = client.post("/v1/tools/nl-to-ir", json=_VALID_CONTEXT)
        assert response.status_code == 401

    def test_a2_wrong_key_value_returns_401(self):
        """Wrong X-API-Key value → 401."""
        with make_client() as client:
            response = client.post(
                "/v1/tools/nl-to-ir",
                json=_VALID_CONTEXT,
                headers={"X-API-Key": WRONG_KEY},
            )
        assert response.status_code == 401

    def test_a3_client_key_on_tool_endpoint_returns_401(self):
        """
        CLIENT_API_KEY used on a Foundry tool endpoint → 401.
        Keys are not interchangeable — each key only works on its own routes.
        """
        with make_client() as client:
            response = client.post(
                "/v1/tools/nl-to-ir",
                json=_VALID_CONTEXT,
                headers={"X-API-Key": CLIENT_KEY},
            )
        assert response.status_code == 401

    def test_a4_correct_foundry_key_passes_auth(self):
        """
        Correct FOUNDRY_API_KEY → request is not rejected by auth.
        May still fail for other reasons (schema, LLM) but not 401.
        """
        with make_client() as client:
            response = client.post(
                "/v1/tools/nl-to-ir",
                json=_VALID_CONTEXT,
                headers={"X-API-Key": FOUNDRY_KEY},
            )
        assert response.status_code != 401


# ---------------------------------------------------------------------------
# Group B — Context Field Validation (missing required fields)
# Stage "nl-to-ir" requires: nl_query_original, app_id, app_schema_version.
# Missing or empty → HTTP 400, MISSING_CONTEXT_FIELDS, field list in response.
# ---------------------------------------------------------------------------

class TestContextValidation:
    """Missing required context fields return 400 before any stage runs."""

    def test_b1_missing_nl_query_original_returns_400(self):
        """
        nl_query_original absent (empty string) → 400 MISSING_CONTEXT_FIELDS.
        ContextValidator treats empty string the same as None for string fields.
        """
        body = {**_VALID_CONTEXT, "nl_query_original": ""}
        with make_client() as client:
            response = client.post(
                "/v1/tools/nl-to-ir",
                json=body,
                headers={"X-API-Key": FOUNDRY_KEY},
            )
        assert response.status_code == 400
        data = response.json()
        assert data["errors"][0]["code"] == "MISSING_CONTEXT_FIELDS"
        assert "nl_query_original" in data["errors"][0]["missing_fields"]

    def test_b2_missing_app_id_returns_400(self):
        """app_id empty string → 400 MISSING_CONTEXT_FIELDS."""
        body = {**_VALID_CONTEXT, "app_id": ""}
        with make_client() as client:
            response = client.post(
                "/v1/tools/nl-to-ir",
                json=body,
                headers={"X-API-Key": FOUNDRY_KEY},
            )
        assert response.status_code == 400
        data = response.json()
        assert data["errors"][0]["code"] == "MISSING_CONTEXT_FIELDS"
        assert "app_id" in data ["errors"][0]["missing_fields"]

    def test_b3_missing_app_schema_version_returns_400(self):
        """app_schema_version empty string → 400 MISSING_CONTEXT_FIELDS."""
        body = {**_VALID_CONTEXT, "app_schema_version": ""}
        with make_client() as client:
            response = client.post(
                "/v1/tools/nl-to-ir",
                json=body,
                headers={"X-API-Key": FOUNDRY_KEY},
            )
        assert response.status_code == 400
        data = response.json()
        assert data["errors"][0]["code"] == "MISSING_CONTEXT_FIELDS"
        assert "app_schema_version" in data["errors"][0]["missing_fields"]

    def test_b4_all_three_fields_missing_lists_all_in_error(self):
        """
        All three required fields empty → 400, all three names in missing_fields.
        """
        body = {
            **_VALID_CONTEXT,
            "nl_query_original": "",
            "app_id": "",
            "app_schema_version": "",
        }
        with make_client() as client:
            response = client.post(
                "/v1/tools/nl-to-ir",
                json=body,
                headers={"X-API-Key": FOUNDRY_KEY},
            )
        assert response.status_code == 400
        data = response.json()
        missing = data ["errors"][0]["missing_fields"]
        assert "nl_query_original" in missing
        assert "app_id" in missing
        assert "app_schema_version" in missing


# ---------------------------------------------------------------------------
# Group C — Intent Guard blocks non-SELECT queries
# Intent Guard runs after context validation but before any LLM call.
# Result: HTTP 200, context.status="failed", UNSUPPORTED_INTENT error code.
# No LLM call is made — we verify by NOT injecting a mock with a response.
# ---------------------------------------------------------------------------

class TestIntentGuard:
    """Non-SELECT keywords are blocked by Intent Guard before any LLM call."""

    def test_c1_delete_keyword_blocked(self):
        """
        Query containing DELETE → UNSUPPORTED_INTENT.
        HTTP 200 (business error), context.status=failed.
        """
        body = {**_VALID_CONTEXT, "nl_query_original": "DELETE all customers in Acme"}
        with make_client() as client:
            response = client.post(
                "/v1/tools/nl-to-ir",
                json=body,
                headers={"X-API-Key": FOUNDRY_KEY},
            )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "failed"
        assert data["errors"][0]["code"] == "UNSUPPORTED_INTENT"

    def test_c2_drop_keyword_blocked(self):
        """
        Query containing DROP → UNSUPPORTED_INTENT.
        HTTP 200 (business error), context.status=failed.
        No LLM call is attempted — verified by using the default factory mock
        which would raise ValueError if complete() were called unexpectedly.
        """
        body = {**_VALID_CONTEXT, "nl_query_original": "DROP TABLE customers in Acme"}
        with make_client() as client:
            response = client.post(
                "/v1/tools/nl-to-ir",
                json=body,
                headers={"X-API-Key": FOUNDRY_KEY},
            )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "failed"
        assert data["errors"][0]["code"] == "UNSUPPORTED_INTENT"


# ---------------------------------------------------------------------------
# Group D — Success path
# Valid context → Intent Guard passes → NL-to-IR Strategy runs → llm_output set.
# We inject MockLLMProvider with _GOLDEN_IR after lifespan startup.
# ---------------------------------------------------------------------------

class TestSuccess:
    """Valid context produces a successful ToolResponse with llm_output populated."""

    def test_d1_valid_context_returns_200_with_llm_output(self):
        """
        Valid context body → 200, context.llm_output populated,
        context.status = "success".
        """
        app = create_app(schema_dir="schemas")
        with TestClient(app, raise_server_exceptions=False) as client:
            app.state.llm_provider = MockLLMProvider(responses=[_GOLDEN_IR])
            response = client.post(
                "/v1/tools/nl-to-ir",
                json=_VALID_CONTEXT,
                headers={"X-API-Key": FOUNDRY_KEY},
            )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["context"]["llm_output"] is not None
        assert "tables" in data["context"]["llm_output"]

    def test_d2_response_has_correct_tool_response_shape(self):
        """
        Response envelope matches ToolResponse shape:
          request_id, status, context, errors.
        errors is empty list on success.
        """
        app = create_app(schema_dir="schemas")
        with TestClient(app, raise_server_exceptions=False) as client:
            app.state.llm_provider = MockLLMProvider(responses=[_GOLDEN_IR])
            response = client.post(
                "/v1/tools/nl-to-ir",
                json=_VALID_CONTEXT,
                headers={"X-API-Key": FOUNDRY_KEY},
            )
        assert response.status_code == 200
        data = response.json()
        assert "request_id" in data
        assert "status" in data
        assert "context" in data
        assert "errors" in data
        assert data["errors"] == []

    def test_d3_request_id_preserved_in_response(self):
        """
        request_id sent in context body must be echoed unchanged in the response.
        """
        my_request_id = "tool-req-abc-999"
        body = {**_VALID_CONTEXT, "request_id": my_request_id}
        app = create_app(schema_dir="schemas")
        with TestClient(app, raise_server_exceptions=False) as client:
            app.state.llm_provider = MockLLMProvider(responses=[_GOLDEN_IR])
            response = client.post(
                "/v1/tools/nl-to-ir",
                json=body,
                headers={"X-API-Key": FOUNDRY_KEY},
            )
        data = response.json()
        assert data["request_id"] == my_request_id


# ---------------------------------------------------------------------------
# Group E — Schema not found for app_id
# If app_id does not match any loaded schema, schema_repo.get_schema() raises.
# Result: HTTP 500, INTERNAL_ERROR.
# ---------------------------------------------------------------------------

class TestSchemaNotFound:
    """Unknown app_id causes schema lookup failure → 500 INTERNAL_ERROR."""

    def test_e1_unknown_app_id_returns_500(self):
        """
        app_id set to a value not in any loaded schema → 500 INTERNAL_ERROR.
        Note: ContextValidator passes (app_id is non-empty) but schema_repo
        raises when we try to load the schema for the unknown app.
        """
        body = {
            **_VALID_CONTEXT,
            "app_id": "UNKNOWN_APP",
            "app_schema_version": "1.0",
        }
        with make_client() as client:
            response = client.post(
                "/v1/tools/nl-to-ir",
                json=body,
                headers={"X-API-Key": FOUNDRY_KEY},
            )
        assert response.status_code == 500
        data = response.json()
        assert data["context"]["status"] == "failed"
        assert data["errors"][0]["code"] == "INTERNAL_ERROR"
