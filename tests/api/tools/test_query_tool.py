# tests/api/tools/test_query_tool.py
# V0 - Initial implementation
# V1 - Fixed success tests (D1-D8): override app.state.llm_provider with a properly
#      configured MockLLMProvider(responses=[_GOLDEN_IR]) after app creation.
#      The factory creates MockLLMProvider(responses=["mock_response"]) which is not
#      valid IR JSON — success tests that reach the LLM stage need a real IR response.
#      Groups A, B, C, E are unchanged — they never reach the LLM call.
# V2 - Fixed override timing: app.state.llm_provider must be set AFTER the TestClient
#      context manager opens (lifespan runs on open and overwrites any pre-open override).
#      Each Group D test sets app.state.llm_provider inside the `with` block before
#      the request is made.
#
# Tests for POST /v1/tools/query — Foundry full pipeline tool endpoint.
#
# What this endpoint does:
#   1. Validates required QueryContext fields (nl_query_original) — returns 400 if missing.
#   2. Calls run_pipeline() — runs all 5 stages internally:
#      App Identifier → Intent Guard → NL-to-IR → Validator → SQL Builder.
#   3. Returns ToolResponse with fully populated QueryContext including context.sql.
#
# Test groups:
#   A — Auth (wrong/missing key)
#   B — Context field validation (missing/empty nl_query_original)
#   C — Intent Guard blocking (non-select query blocked inside pipeline)
#   D — Success path (full pipeline produces sql)
#   E — Business error: APP_NOT_DETERMINED (unrecognised app)
#
# Fixtures used from tests/api/conftest.py (autouse):
#   set_test_env_vars — injects ENV, CLIENT_API_KEY, FOUNDRY_API_KEY, LLM_PROVIDER

import json
from fastapi.testclient import TestClient

from src.api.app import create_app
from src.llm.mock_provider import MockLLMProvider

# ---------------------------------------------------------------------------
# Shared test constants
# ---------------------------------------------------------------------------

FOUNDRY_KEY = "test-foundry-key-67890"
CLIENT_KEY  = "test-client-key-12345"
WRONG_KEY   = "wrong-key"
ENDPOINT    = "/v1/tools/query"

# Golden NL query — matches Acme app, produces valid SQL end-to-end.
GOLDEN_QUERY = "give me customer name for customer CUST01 in Acme"

# Valid simplified IR — what the mock LLM must return for the pipeline to succeed.
# Copied from tests/pipeline/test_orchestrator.py — same IR, same schema references.
_GOLDEN_IR = json.dumps({
    "tables": [
        {"table": "Major.Customer",             "source": "customer"},
        {"table": "Major.CustomerDemographics", "source": "customer name"},
    ],
    "columns": [
        {"table": "Major.CustomerDemographics", "column": "CustomerName", "source": "customer name"},
    ],
    "filters": [
        {
            "table": "Major.Customer",
            "column": "CustomerCID",
            "operator": "=",
            "value": "CUST01",
            "source": "customer CUST01",
        }
    ],
    "limit": None,
    "aggregation": None,
    "sort": [],
})


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_app():
    """
    Create the FastAPI app using the real Acme schema directory.
    The factory wires MockLLMProvider(responses=["mock_response"]) by default —
    a placeholder that is NOT valid IR JSON.

    For tests that reach the LLM stage (Group D), override llm_provider
    INSIDE the `with TestClient(app) as client:` block — after lifespan runs.

    Why inside the with block:
        TestClient lifespan runs when the `with` block OPENS.
        Any override set before opening is overwritten by lifespan Step 5.
        Setting it on the line after `with` means lifespan is already done —
        our override sticks for the duration of that test.
    """
    return create_app(schema_dir="schemas")


def _minimal_context(nl_query: str = GOLDEN_QUERY) -> dict:
    """
    Minimal valid QueryContext payload for this endpoint.
    Only nl_query_original is required — the pipeline produces everything else.
    """
    return {
        "nl_query_original": nl_query,
        "app_id": "",
        "app_schema_version": "",
    }


# ---------------------------------------------------------------------------
# Group A — Authentication
# Tool endpoints use FOUNDRY_API_KEY, not CLIENT_API_KEY.
# These tests never reach the LLM — no llm_provider override needed.
# ---------------------------------------------------------------------------

class TestAuth:
    """Auth enforcement on POST /v1/tools/query."""

    def test_A1_missing_api_key_returns_401(self):
        """No X-API-Key header → 401."""
        with TestClient(make_app(), raise_server_exceptions=False) as client:
            response = client.post(ENDPOINT, json=_minimal_context())
        assert response.status_code == 401

    def test_A2_wrong_key_value_returns_401(self):
        """Wrong X-API-Key value → 401."""
        with TestClient(make_app(), raise_server_exceptions=False) as client:
            response = client.post(
                ENDPOINT,
                json=_minimal_context(),
                headers={"X-API-Key": WRONG_KEY},
            )
        assert response.status_code == 401

    def test_A3_client_key_on_tool_endpoint_returns_401(self):
        """
        CLIENT_API_KEY used on a Foundry tool endpoint → 401.
        Keys are not interchangeable — each key only works on its own routes.
        """
        with TestClient(make_app(), raise_server_exceptions=False) as client:
            response = client.post(
                ENDPOINT,
                json=_minimal_context(),
                headers={"X-API-Key": CLIENT_KEY},
            )
        assert response.status_code == 401

    def test_A4_correct_foundry_key_passes_auth(self):
        """Correct FOUNDRY_API_KEY → request is not rejected by auth."""
        with TestClient(make_app(), raise_server_exceptions=False) as client:
            response = client.post(
                ENDPOINT,
                json=_minimal_context(),
                headers={"X-API-Key": FOUNDRY_KEY},
            )
        assert response.status_code != 401


# ---------------------------------------------------------------------------
# Group B — Context field validation
# Stage "query" requires: nl_query_original.
# These tests never reach the LLM — no llm_provider override needed.
# ---------------------------------------------------------------------------

class TestContextValidation:
    """Missing required context fields return 400 before pipeline runs."""

    def test_B1_null_nl_query_returns_422(self):
        """
        nl_query_original = None → 422 Unprocessable Entity from Pydantic.

        QueryContext defines nl_query_original as str (required, not Optional).
        Pydantic rejects None before our handler body runs.
        422 is the correct and expected protection for this case.
        """
        body = {
            "nl_query_original": None,
            "app_id": "",
            "app_schema_version": "",
        }
        with TestClient(make_app(), raise_server_exceptions=False) as client:
            response = client.post(
                ENDPOINT,
                json=body,
                headers={"X-API-Key": FOUNDRY_KEY},
            )
        assert response.status_code == 422

    def test_B2_empty_nl_query_returns_400(self):
        """nl_query_original = '' (empty string) → 400 MISSING_CONTEXT_FIELDS."""
        with TestClient(make_app(), raise_server_exceptions=False) as client:
            response = client.post(
                ENDPOINT,
                json=_minimal_context(nl_query=""),
                headers={"X-API-Key": FOUNDRY_KEY},
            )
        assert response.status_code == 400
        data = response.json()
        assert data["errors"][0]["code"] == "MISSING_CONTEXT_FIELDS"


# ---------------------------------------------------------------------------
# Group C — Intent Guard blocking (fires inside run_pipeline)
# Blocked at Stage 2 — LLM never called.
# No llm_provider override needed.
# ---------------------------------------------------------------------------

class TestIntentGuardBlocking:
    """Non-select queries blocked by Intent Guard inside the pipeline."""

    def test_C1_delete_query_returns_200(self):
        """HTTP 200 even for blocked queries — business error, not HTTP error."""
        with TestClient(make_app(), raise_server_exceptions=False) as client:
            response = client.post(
                ENDPOINT,
                json=_minimal_context("DELETE all customers in Acme"),
                headers={"X-API-Key": FOUNDRY_KEY},
            )
        assert response.status_code == 200

    def test_C2_delete_query_status_is_failed(self):
        """status is 'failed' when Intent Guard blocks the query."""
        with TestClient(make_app(), raise_server_exceptions=False) as client:
            response = client.post(
                ENDPOINT,
                json=_minimal_context("DELETE all customers in Acme"),
                headers={"X-API-Key": FOUNDRY_KEY},
            )
        data = response.json()
        assert data["status"] == "failed"

    def test_C3_delete_query_error_code_is_unsupported_intent(self):
        """Error code is UNSUPPORTED_INTENT when Intent Guard fires."""
        with TestClient(make_app(), raise_server_exceptions=False) as client:
            response = client.post(
                ENDPOINT,
                json=_minimal_context("DELETE all customers in Acme"),
                headers={"X-API-Key": FOUNDRY_KEY},
            )
        data = response.json()
        assert data["errors"][0]["code"] == "UNSUPPORTED_INTENT"

    def test_C4_delete_query_sql_is_none(self):
        """context.sql remains None when Intent Guard blocks."""
        with TestClient(make_app(), raise_server_exceptions=False) as client:
            response = client.post(
                ENDPOINT,
                json=_minimal_context("DELETE all customers in Acme"),
                headers={"X-API-Key": FOUNDRY_KEY},
            )
        data = response.json()
        assert data["context"]["sql"] is None


# ---------------------------------------------------------------------------
# Group D — Success path
# Full pipeline runs including LLM call.
# Each test overrides app.state.llm_provider INSIDE the `with` block,
# after lifespan has run, so the override is not overwritten by startup.
# ---------------------------------------------------------------------------

class TestSuccess:
    """Happy path — golden query runs full pipeline and returns SQL."""

    def test_D1_valid_query_returns_200(self):
        """HTTP 200 returned for a valid query."""
        with TestClient(make_app(), raise_server_exceptions=False) as client:
            client.app.state.llm_provider = MockLLMProvider(responses=[_GOLDEN_IR])
            response = client.post(
                ENDPOINT,
                json=_minimal_context(),
                headers={"X-API-Key": FOUNDRY_KEY},
            )
        assert response.status_code == 200

    def test_D2_valid_query_populates_sql(self):
        """context.sql is populated on success."""
        with TestClient(make_app(), raise_server_exceptions=False) as client:
            client.app.state.llm_provider = MockLLMProvider(responses=[_GOLDEN_IR])
            response = client.post(
                ENDPOINT,
                json=_minimal_context(),
                headers={"X-API-Key": FOUNDRY_KEY},
            )
        data = response.json()
        assert data["context"]["sql"] is not None
        assert "SELECT" in data["context"]["sql"]

    def test_D3_valid_query_status_is_success(self):
        """context.status is 'success' on happy path."""
        with TestClient(make_app(), raise_server_exceptions=False) as client:
            client.app.state.llm_provider = MockLLMProvider(responses=[_GOLDEN_IR])
            response = client.post(
                ENDPOINT,
                json=_minimal_context(),
                headers={"X-API-Key": FOUNDRY_KEY},
            )
        data = response.json()
        assert data["status"] == "success"

    def test_D4_response_has_correct_tool_response_shape(self):
        """Response envelope has: request_id, status, context, errors."""
        with TestClient(make_app(), raise_server_exceptions=False) as client:
            client.app.state.llm_provider = MockLLMProvider(responses=[_GOLDEN_IR])
            response = client.post(
                ENDPOINT,
                json=_minimal_context(),
                headers={"X-API-Key": FOUNDRY_KEY},
            )
        data = response.json()
        assert "request_id" in data
        assert "status" in data
        assert "context" in data
        assert "errors" in data

    def test_D5_errors_list_is_empty_on_success(self):
        """errors list is empty on success."""
        with TestClient(make_app(), raise_server_exceptions=False) as client:
            client.app.state.llm_provider = MockLLMProvider(responses=[_GOLDEN_IR])
            response = client.post(
                ENDPOINT,
                json=_minimal_context(),
                headers={"X-API-Key": FOUNDRY_KEY},
            )
        data = response.json()
        assert data["errors"] == []

    def test_D6_request_id_preserved_in_response(self):
        """request_id sent in context body is echoed unchanged in response."""
        my_request_id = "query-tool-req-abc-999"
        body = {**_minimal_context(), "request_id": my_request_id}
        with TestClient(make_app(), raise_server_exceptions=False) as client:
            client.app.state.llm_provider = MockLLMProvider(responses=[_GOLDEN_IR])
            response = client.post(
                ENDPOINT,
                json=body,
                headers={"X-API-Key": FOUNDRY_KEY},
            )
        data = response.json()
        assert data["request_id"] == my_request_id

    def test_D7_app_id_populated_by_pipeline(self):
        """
        context.app_id is populated even though it was not sent.
        App Identifier stage (Stage 1) detects it from the query.
        """
        with TestClient(make_app(), raise_server_exceptions=False) as client:
            client.app.state.llm_provider = MockLLMProvider(responses=[_GOLDEN_IR])
            response = client.post(
                ENDPOINT,
                json=_minimal_context(),
                headers={"X-API-Key": FOUNDRY_KEY},
            )
        data = response.json()
        assert data["context"]["app_id"] == "Acme_app"

    def test_D8_pre_set_app_id_accepted_by_pipeline(self):
        """
        app_id pre-set in context → pipeline uses it directly (Path 1 in App Identifier).
        sql still produced end-to-end.
        """
        body = {**_minimal_context(), "app_id": "Acme_app"}
        with TestClient(make_app(), raise_server_exceptions=False) as client:
            client.app.state.llm_provider = MockLLMProvider(responses=[_GOLDEN_IR])
            response = client.post(
                ENDPOINT,
                json=body,
                headers={"X-API-Key": FOUNDRY_KEY},
            )
        data = response.json()
        assert data["status"] == "success"
        assert data["context"]["sql"] is not None


# ---------------------------------------------------------------------------
# Group E — Business error: APP_NOT_DETERMINED
# Blocked at Stage 1 — LLM never called.
# No llm_provider override needed.
# ---------------------------------------------------------------------------

class TestAppNotDetermined:
    """No matching app synonym → business error, HTTP 200."""

    def test_E1_unrecognised_app_returns_200(self):
        """HTTP 200 even when no app is found — business error, not HTTP error."""
        with TestClient(make_app(), raise_server_exceptions=False) as client:
            response = client.post(
                ENDPOINT,
                json=_minimal_context("show me all records in UNKNOWN_XYZ_APP"),
                headers={"X-API-Key": FOUNDRY_KEY},
            )
        assert response.status_code == 200

    def test_E2_unrecognised_app_status_is_failed(self):
        """status is 'failed' when no app is matched."""
        with TestClient(make_app(), raise_server_exceptions=False) as client:
            response = client.post(
                ENDPOINT,
                json=_minimal_context("show me all records in UNKNOWN_XYZ_APP"),
                headers={"X-API-Key": FOUNDRY_KEY},
            )
        data = response.json()
        assert data["status"] == "failed"

    def test_E3_unrecognised_app_error_code(self):
        """Error code is APP_NOT_DETERMINED when no app is matched."""
        with TestClient(make_app(), raise_server_exceptions=False) as client:
            response = client.post(
                ENDPOINT,
                json=_minimal_context("show me all records in UNKNOWN_XYZ_APP"),
                headers={"X-API-Key": FOUNDRY_KEY},
            )
        data = response.json()
        assert data["errors"][0]["code"] == "APP_NOT_DETERMINED"
