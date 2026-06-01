# tests/api/test_api_integration.py
# V0 - Initial implementation
#
# Full API integration sweep — tests every endpoint at least once, verifies
# auth key separation across all route types, covers core error codes at the
# HTTP response level, and confirms pytest tests/api/ passes as a full suite.
#
# This is NOT a deep test of individual endpoint behaviour — that is covered
# by the endpoint-specific test files (test_query.py, test_feedback.py, etc.).
# This file answers one question: does the complete API hold together?
#
# Test groups:
#   A — Health endpoints (no auth, always reachable)
#   B — User-facing endpoints with CLIENT key
#   C — Tool endpoints with FOUNDRY key
#   D — Auth key separation (CLIENT key ≠ FOUNDRY key — not interchangeable)
#   E — Core error codes visible at the API response level
#
# Infrastructure:
#   tests/api/conftest.py injects ENV, CLIENT_API_KEY, FOUNDRY_API_KEY,
#   LLM_PROVIDER=mock via autouse — no explicit setup needed here.
#   Each test creates its own TestClient — no shared state between tests.
#   raise_server_exceptions=False — lets global exception handler respond
#   rather than re-raising in the test thread.

import json

from fastapi.testclient import TestClient

from src.api.app import create_app
from src.llm.mock_provider import MockLLMProvider

# ---------------------------------------------------------------------------
# Shared constants
# ---------------------------------------------------------------------------

CLIENT_KEY  = "test-client-key-12345"
FOUNDRY_KEY = "test-foundry-key-67890"
WRONG_KEY   = "wrong-key"

# Minimal valid simplified IR — used wherever a LLM response is needed.
# Major.Customer ↔ Major.CustomerDemographics have a direct relationship
# in ABC_app.json — validator chain resolves a clean StructuredQuery.
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

# Pre-built llm_output dict for validator and sql-builder tests.
# Same content as _GOLDEN_IR but as a Python dict so it can be embedded
# directly in a QueryContext body without JSON-decoding.
_LLM_OUTPUT = {
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
}

# Pre-built StructuredQuery for the sql-builder test (C4).
_STRUCTURED_QUERY = {
    "app_id": "ABC_app",
    "top_rows": None,
    "tables": [
        {"table_name": "Major.Customer", "alias": "c"},
        {"table_name": "Major.CustomerDemographics", "alias": "cd"},
    ],
    "columns": [
        {
            "table_alias": "cd",
            "column_name": "CustomerName",
            "output_alias": "CustomerName",
        }
    ],
    "joins": [
        {
            "join_type": "INNER JOIN",
            "table_name": "Major.CustomerDemographics",
            "alias": "cd",
            "on_conditions": [
                {"left": "c.CustomerID", "right": "cd.CustomerID"}
            ],
        }
    ],
    "filters": [],
    "applied_rules": [
        "c.VersionTermDate IS NULL",
        "ISNULL(c.DeletedFlag, 0) = 0",
    ],
}


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def make_client() -> TestClient:
    """Standard TestClient for this test suite."""
    app = create_app(schema_dir="schemas")
    return TestClient(app, raise_server_exceptions=False)


# ---------------------------------------------------------------------------
# Group A — Health endpoints (no auth required)
# ---------------------------------------------------------------------------

class TestHealthEndpoints:
    """Health endpoints must always respond — no auth, no body required."""

    def test_a1_health_returns_200(self):
        """GET /health → 200. Service is alive."""
        with make_client() as client:
            response = client.get("/health")
        assert response.status_code == 200

    def test_a2_ready_returns_200(self):
        """GET /ready → 200. All startup dependencies loaded successfully."""
        with make_client() as client:
            response = client.get("/ready")
        assert response.status_code == 200


# ---------------------------------------------------------------------------
# Group B — User-facing endpoints with CLIENT key
# ---------------------------------------------------------------------------

class TestUserFacingEndpoints:
    """
    All user-facing endpoints accept CLIENT_API_KEY and return the correct
    response shape. Verifies every user-facing route is reachable and wired.
    """

    def test_b1_query_success_returns_sql(self):
        """
        POST /v1/query — full pipeline success.
        CLIENT key accepted, SQL produced, response shape correct.
        """
        app = create_app(schema_dir="schemas")
        with TestClient(app, raise_server_exceptions=False) as client:
            app.state.llm_provider = MockLLMProvider(responses=[_GOLDEN_IR])
            response = client.post(
                "/v1/query",
                json={
                    "nl_query": "give me customers in ABC",
                    "user_id": "integration-test",
                },
                headers={"X-API-Key": CLIENT_KEY},
            )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["data"]["sql"] is not None
        assert "SELECT" in data["data"]["sql"]

    def test_b2_feedback_returns_success(self):
        """
        POST /v1/feedback — feedback accepted and logged.
        CLIENT key accepted, success envelope returned.
        """
        with make_client() as client:
            response = client.post(
                "/v1/feedback",
                json={
                    "request_id": "orig-request-uuid-123",
                    "status": "pass",
                },
                headers={"X-API-Key": CLIENT_KEY},
            )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["errors"] == []

    def test_b3_apps_returns_abc_app(self):
        """
        GET /v1/apps — loaded schema list returned.
        CLIENT key accepted, ABC_app present with version.
        """
        with make_client() as client:
            response = client.get(
                "/v1/apps",
                headers={"X-API-Key": CLIENT_KEY},
            )

        assert response.status_code == 200
        apps = response.json()["data"]["apps"]
        app_ids = [a["app_id"] for a in apps]
        assert "ABC_app" in app_ids, "ABC_app must appear in /v1/apps response."


# ---------------------------------------------------------------------------
# Group C — Tool endpoints with FOUNDRY key
# ---------------------------------------------------------------------------

class TestToolEndpoints:
    """
    All Foundry tool endpoints accept FOUNDRY_API_KEY and return ToolResponse
    shape. Verifies every tool route is reachable and wired correctly.
    """

    def test_c1_app_identifier_populates_app_id(self):
        """POST /v1/tools/app-identifier → 200, context.app_id = 'ABC_app'."""
        with make_client() as client:
            response = client.post(
                "/v1/tools/app-identifier",
                json={
                    "nl_query_original": "give me customers in ABC",
                    "user_id": "integration-test",
                },
                headers={"X-API-Key": FOUNDRY_KEY},
            )

        assert response.status_code == 200
        assert response.json()["context"]["app_id"] == "ABC_app"

    def test_c2_nl_to_ir_populates_llm_output(self):
        """POST /v1/tools/nl-to-ir → 200, context.llm_output populated."""
        app = create_app(schema_dir="schemas")
        with TestClient(app, raise_server_exceptions=False) as client:
            app.state.llm_provider = MockLLMProvider(responses=[_GOLDEN_IR])
            response = client.post(
                "/v1/tools/nl-to-ir",
                json={
                    "nl_query_original": "give me customers in ABC",
                    "app_id": "ABC_app",
                    "app_schema_version": "1.0",
                    "user_id": "integration-test",
                },
                headers={"X-API-Key": FOUNDRY_KEY},
            )

        assert response.status_code == 200
        ctx = response.json()["context"]
        assert ctx["llm_output"] is not None
        assert "tables" in ctx["llm_output"]

    def test_c3_validator_populates_structured_query(self):
        """POST /v1/tools/validator → 200, context.structured_query populated."""
        with make_client() as client:
            response = client.post(
                "/v1/tools/validator",
                json={
                    "nl_query_original": "give me customers in ABC",
                    "app_id": "ABC_app",
                    "app_schema_version": "1.0",
                    "user_id": "integration-test",
                    "llm_output": _LLM_OUTPUT,
                },
                headers={"X-API-Key": FOUNDRY_KEY},
            )

        assert response.status_code == 200
        assert response.json()["context"]["structured_query"] is not None

    def test_c4_sql_builder_populates_sql(self):
        """POST /v1/tools/sql-builder → 200, context.sql populated."""
        with make_client() as client:
            response = client.post(
                "/v1/tools/sql-builder",
                json={
                    "nl_query_original": "give me customers in ABC",
                    "app_id": "ABC_app",
                    "app_schema_version": "1.0",
                    "user_id": "integration-test",
                    "structured_query": _STRUCTURED_QUERY,
                },
                headers={"X-API-Key": FOUNDRY_KEY},
            )

        assert response.status_code == 200
        ctx = response.json()["context"]
        assert ctx["sql"] is not None
        assert "SELECT" in ctx["sql"]

    def test_c5_tools_query_produces_sql(self):
        """POST /v1/tools/query → 200, context.sql populated via full pipeline."""
        app = create_app(schema_dir="schemas")
        with TestClient(app, raise_server_exceptions=False) as client:
            app.state.llm_provider = MockLLMProvider(responses=[_GOLDEN_IR])
            response = client.post(
                "/v1/tools/query",
                json={
                    "nl_query_original": "give me customers in ABC",
                    "user_id": "integration-test",
                },
                headers={"X-API-Key": FOUNDRY_KEY},
            )

        assert response.status_code == 200
        ctx = response.json()["context"]
        assert ctx["sql"] is not None
        assert "SELECT" in ctx["sql"]

    def test_c6_tools_feedback_returns_501(self):
        """
        POST /v1/tools/feedback → 501 Not Implemented.
        Phase 3 placeholder — confirms route is stable and registered.
        No auth on this placeholder route.
        """
        with make_client() as client:
            response = client.post("/v1/tools/feedback")

        assert response.status_code == 501
        assert response.json()["status"] == "not_implemented"


# ---------------------------------------------------------------------------
# Group D — Auth key separation
# ---------------------------------------------------------------------------

class TestAuthKeySeparation:
    """
    CLIENT key and FOUNDRY key are not interchangeable.
    Using the wrong key on any endpoint returns 401.
    This is the cross-cutting auth guarantee that protects
    the entire API boundary.
    """

    def test_d1_client_key_rejected_on_tool_endpoint(self):
        """
        CLIENT key used on a tool endpoint → 401.
        Tool endpoints require FOUNDRY_API_KEY — using the user-facing
        key must be rejected.
        """
        with make_client() as client:
            response = client.post(
                "/v1/tools/app-identifier",
                json={
                    "nl_query_original": "give me customers in ABC",
                    "user_id": "test",
                },
                headers={"X-API-Key": CLIENT_KEY},
            )
        assert response.status_code == 401

    def test_d2_foundry_key_rejected_on_user_facing_endpoint(self):
        """
        FOUNDRY key used on a user-facing endpoint → 401.
        User-facing endpoints require CLIENT_API_KEY — using the Foundry
        key must be rejected.
        """
        with make_client() as client:
            response = client.post(
                "/v1/query",
                json={
                    "nl_query": "give me customers in ABC",
                    "user_id": "test",
                },
                headers={"X-API-Key": FOUNDRY_KEY},
            )
        assert response.status_code == 401

    def test_d3_no_key_on_protected_endpoint_returns_401(self):
        """
        Missing X-API-Key header on any protected endpoint → 401.
        Tests both user-facing and tool endpoints to confirm the rule
        applies universally.
        """
        with make_client() as client:
            # User-facing — no key
            r_user = client.post(
                "/v1/query",
                json={"nl_query": "give me customers in ABC", "user_id": "test"},
            )
            # Tool endpoint — no key
            r_tool = client.post(
                "/v1/tools/app-identifier",
                json={"nl_query_original": "give me customers in ABC", "user_id": "test"},
            )

        assert r_user.status_code == 401, "Missing key on /v1/query must return 401"
        assert r_tool.status_code == 401, "Missing key on tool endpoint must return 401"


# ---------------------------------------------------------------------------
# Group E — Core error codes at API response level
# ---------------------------------------------------------------------------

class TestErrorCodes:
    """
    Core error codes must be visible in the API response body.
    This is the HTTP-level check that error handling is end-to-end —
    the right code appears in errors[0].code, not just in internal logs.
    """

    def test_e1_app_not_determined_in_response(self):
        """
        Unrecognisable query → APP_NOT_DETERMINED in errors[0].code.
        HTTP 200 (business error), status='failed'.
        """
        with make_client() as client:
            response = client.post(
                "/v1/query",
                json={
                    "nl_query": "give me all the data please",
                    "user_id": "integration-test",
                },
                headers={"X-API-Key": CLIENT_KEY},
            )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "failed"
        assert data["errors"][0]["code"] == "APP_NOT_DETERMINED"

    def test_e2_unsupported_intent_in_response(self):
        """
        DELETE query → UNSUPPORTED_INTENT in errors[0].code.
        HTTP 200 (business error), status='failed'.
        Intent Guard fires before any LLM call.
        """
        with make_client() as client:
            response = client.post(
                "/v1/query",
                json={
                    "nl_query": "DELETE all customers in ABC",
                    "user_id": "integration-test",
                },
                headers={"X-API-Key": CLIENT_KEY},
            )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "failed"
        assert data["errors"][0]["code"] == "UNSUPPORTED_INTENT"

    def test_e3_missing_context_fields_in_response(self):
        """
        Tool endpoint called with missing required context field →
        MISSING_CONTEXT_FIELDS in errors[0].code.
        HTTP 400 (bad request — agent sent incomplete context).
        Global exception handler (middleware.py) produces the response.
        """
        with make_client() as client:
            # nl-to-ir requires app_id — sending "" (default) triggers the validator
            response = client.post(
                "/v1/tools/nl-to-ir",
                json={
                    "nl_query_original": "give me customers in ABC",
                    "user_id": "integration-test",
                    # app_id defaults to "" — ContextValidator treats as missing
                },
                headers={"X-API-Key": FOUNDRY_KEY},
            )

        assert response.status_code == 400
        data = response.json()
        assert data["status"] == "failed"
        assert data["errors"][0]["code"] == "MISSING_CONTEXT_FIELDS"

    def test_e4_internal_error_on_broken_startup(self):
        """
        schema_repo = None (simulated broken startup) on /v1/query →
        INTERNAL_ERROR in errors[0].code.
        HTTP 500. Raw exception detail must not be in the response body.
        """
        app = create_app(schema_dir="schemas")
        with TestClient(app, raise_server_exceptions=False) as client:
            app.state.schema_repo = None
            response = client.post(
                "/v1/query",
                json={
                    "nl_query": "give me customers in ABC",
                    "user_id": "integration-test",
                },
                headers={"X-API-Key": CLIENT_KEY},
            )

        assert response.status_code == 500
        data = response.json()
        assert data["status"] == "failed"
        assert data["errors"][0]["code"] == "INTERNAL_ERROR"
        # Raw Python error detail must never reach the caller
        assert "schema_repo" not in response.text
        assert "Traceback" not in response.text
