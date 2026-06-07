# tests/api/tools/test_app_identifier_tool.py
# V0 - Initial implementation
#
# Tests for POST /v1/tools/app-identifier — Foundry App Identifier tool endpoint.
#
# What this endpoint does:
#   1. Validates required QueryContext fields (nl_query_original) — returns 400 if missing.
#   2. Runs Intent Guard — blocks non-SELECT queries (UNSUPPORTED_INTENT).
#   3. Calls run_app_identifier() — matches query to app schema.
#   4. Returns ToolResponse with updated QueryContext including app_id + app_schema_version.
#
# Test groups:
#   A — Auth (wrong/missing key)
#   B — Context field validation (missing/empty nl_query_original)
#   C — Intent Guard blocking (non-select query)
#   D — Success path (app_id populated)
#   E — Business error (APP_NOT_DETERMINED)
#   F — Explicit app_id pre-set (Path 1 in run_app_identifier)
#
# Fixtures used from tests/api/conftest.py (autouse):
#   set_test_env_vars — injects ENV, CLIENT_API_KEY, FOUNDRY_API_KEY, LLM_PROVIDER

from fastapi.testclient import TestClient

from src.api.app import create_app

# ---------------------------------------------------------------------------
# Shared test constants
# ---------------------------------------------------------------------------

FOUNDRY_KEY = "test-foundry-key-67890"
CLIENT_KEY  = "test-client-key-12345"
WRONG_KEY   = "wrong-key"
ENDPOINT    = "/v1/tools/app-identifier"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_client() -> TestClient:
    """Create a TestClient using the real Acme schema directory."""
    app = create_app(schema_dir="schemas")
    return TestClient(app, raise_server_exceptions=False)


def _valid_context() -> dict:
    """
    Minimal valid QueryContext payload for this endpoint.
    Only nl_query_original is required — app_id is intentionally left empty
    because this stage PRODUCES app_id, it does not require it.
    """
    return {
        "nl_query_original": "show me all customers in Acme",
        "app_id": "",
        "app_schema_version": "",
    }


# ---------------------------------------------------------------------------
# Group A — Authentication
# Tool endpoints use FOUNDRY_API_KEY, not CLIENT_API_KEY.
# ---------------------------------------------------------------------------

class TestAuth:
    """Auth enforcement on POST /v1/tools/app-identifier."""

    def test_A1_missing_api_key_returns_401(self):
        """No X-API-Key header → 401."""
        with make_client() as client:
            response = client.post(ENDPOINT, json=_valid_context())
        assert response.status_code == 401

    def test_A2_wrong_key_value_returns_401(self):
        """Wrong X-API-Key value → 401."""
        with make_client() as client:
            response = client.post(
                ENDPOINT,
                json=_valid_context(),
                headers={"X-API-Key": WRONG_KEY},
            )
        assert response.status_code == 401

    def test_A3_client_key_on_tool_endpoint_returns_401(self):
        """
        CLIENT_API_KEY used on a Foundry tool endpoint → 401.
        Keys are not interchangeable — each key only works on its own routes.
        """
        with make_client() as client:
            response = client.post(
                ENDPOINT,
                json=_valid_context(),
                headers={"X-API-Key": CLIENT_KEY},
            )
        assert response.status_code == 401

    def test_A4_correct_foundry_key_passes_auth(self):
        """Correct FOUNDRY_API_KEY → request is not rejected by auth."""
        with make_client() as client:
            response = client.post(
                ENDPOINT,
                json=_valid_context(),
                headers={"X-API-Key": FOUNDRY_KEY},
            )
        assert response.status_code != 401


# ---------------------------------------------------------------------------
# Group B — Context field validation
# Stage "app-identifier" requires: nl_query_original.
# Missing or empty → HTTP 400, MISSING_CONTEXT_FIELDS.
# ---------------------------------------------------------------------------

class TestContextValidation:
    """Missing required context fields return 400 before any stage runs."""

    def test_B1_null_nl_query_returns_422(self):
        """
        nl_query_original = None → 422 Unprocessable Entity from Pydantic.

        QueryContext defines nl_query_original as str (required, no default,
        not Optional). Pydantic rejects None before our handler body runs —
        there is no way for None to reach the ContextValidator.
        422 is the correct and expected protection for this case.
        """
        body = {
            "nl_query_original": None,
            "app_id": "",
            "app_schema_version": "",
        }
        with make_client() as client:
            response = client.post(
                ENDPOINT,
                json=body,
                headers={"X-API-Key": FOUNDRY_KEY},
            )
        assert response.status_code == 422

    def test_B2_empty_nl_query_returns_400(self):
        """nl_query_original = '' (empty string) → 400 MISSING_CONTEXT_FIELDS."""
        body = _valid_context()
        body["nl_query_original"] = ""
        with make_client() as client:
            response = client.post(
                ENDPOINT,
                json=body,
                headers={"X-API-Key": FOUNDRY_KEY},
            )
        assert response.status_code == 400
        data = response.json()
        assert data["errors"][0]["code"] == "MISSING_CONTEXT_FIELDS"


# ---------------------------------------------------------------------------
# Group C — Intent Guard blocking
# Non-SELECT keywords must be blocked before app identifier runs.
# ---------------------------------------------------------------------------

class TestIntentGuardBlocking:
    """Intent Guard fires before app identifier for non-select queries."""

    def test_C1_delete_query_returns_200(self):
        """HTTP 200 even for blocked queries — business error, not HTTP error."""
        body = _valid_context()
        body["nl_query_original"] = "DELETE all customers in Acme"
        with make_client() as client:
            response = client.post(
                ENDPOINT,
                json=body,
                headers={"X-API-Key": FOUNDRY_KEY},
            )
        assert response.status_code == 200

    def test_C2_delete_query_status_is_failed(self):
        """status is 'failed' when Intent Guard blocks the query."""
        body = _valid_context()
        body["nl_query_original"] = "DELETE all customers in Acme"
        with make_client() as client:
            response = client.post(
                ENDPOINT,
                json=body,
                headers={"X-API-Key": FOUNDRY_KEY},
            )
        data = response.json()
        assert data["status"] == "failed"

    def test_C3_delete_query_error_code_is_unsupported_intent(self):
        """Error code is UNSUPPORTED_INTENT when Intent Guard fires."""
        body = _valid_context()
        body["nl_query_original"] = "DELETE all customers in Acme"
        with make_client() as client:
            response = client.post(
                ENDPOINT,
                json=body,
                headers={"X-API-Key": FOUNDRY_KEY},
            )
        data = response.json()
        assert data["errors"][0]["code"] == "UNSUPPORTED_INTENT"

    def test_C4_delete_query_app_id_not_populated(self):
        """app_id remains empty when Intent Guard blocks — identifier never ran."""
        body = _valid_context()
        body["nl_query_original"] = "DELETE all customers in Acme"
        with make_client() as client:
            response = client.post(
                ENDPOINT,
                json=body,
                headers={"X-API-Key": FOUNDRY_KEY},
            )
        data = response.json()
        assert data["context"]["app_id"] == ""


# ---------------------------------------------------------------------------
# Group D — Success path
# Valid query with Acme synonym → app_id and app_schema_version populated.
# ---------------------------------------------------------------------------

class TestSuccess:
    """Happy path — query matches Acme app via synonym."""

    def test_D1_valid_query_returns_200(self):
        """HTTP 200 returned for a valid query that matches a known app."""
        with make_client() as client:
            response = client.post(
                ENDPOINT,
                json=_valid_context(),
                headers={"X-API-Key": FOUNDRY_KEY},
            )
        assert response.status_code == 200

    def test_D2_valid_query_populates_app_id(self):
        """context.app_id is populated with the matched app ID."""
        with make_client() as client:
            response = client.post(
                ENDPOINT,
                json=_valid_context(),
                headers={"X-API-Key": FOUNDRY_KEY},
            )
        data = response.json()
        assert data["context"]["app_id"] == "Acme_app"

    def test_D3_valid_query_populates_app_schema_version(self):
        """context.app_schema_version is populated on success."""
        with make_client() as client:
            response = client.post(
                ENDPOINT,
                json=_valid_context(),
                headers={"X-API-Key": FOUNDRY_KEY},
            )
        data = response.json()
        assert data["context"]["app_schema_version"] not in ("", None)

    def test_D4_valid_query_status_is_success(self):
        """context.status is 'success' on happy path."""
        with make_client() as client:
            response = client.post(
                ENDPOINT,
                json=_valid_context(),
                headers={"X-API-Key": FOUNDRY_KEY},
            )
        data = response.json()
        assert data["status"] == "success"

    def test_D5_valid_query_errors_list_is_empty(self):
        """errors list is empty on success."""
        with make_client() as client:
            response = client.post(
                ENDPOINT,
                json=_valid_context(),
                headers={"X-API-Key": FOUNDRY_KEY},
            )
        data = response.json()
        assert data["errors"] == []

    def test_D6_response_has_correct_tool_response_shape(self):
        """Response envelope has: request_id, status, context, errors."""
        with make_client() as client:
            response = client.post(
                ENDPOINT,
                json=_valid_context(),
                headers={"X-API-Key": FOUNDRY_KEY},
            )
        data = response.json()
        assert "request_id" in data
        assert "status" in data
        assert "context" in data
        assert "errors" in data


# ---------------------------------------------------------------------------
# Group E — Business error: APP_NOT_DETERMINED
# Query that matches no known app synonym → HTTP 200 with error in context.
# ---------------------------------------------------------------------------

class TestAppNotDetermined:
    """No matching app synonym → business error, HTTP 200."""

    def test_E1_unrecognised_app_returns_200(self):
        """HTTP 200 even when no app is found — business error, not HTTP error."""
        body = _valid_context()
        body["nl_query_original"] = "show me all records in UNKNOWN_XYZ_APP"
        with make_client() as client:
            response = client.post(
                ENDPOINT,
                json=body,
                headers={"X-API-Key": FOUNDRY_KEY},
            )
        assert response.status_code == 200

    def test_E2_unrecognised_app_status_is_failed(self):
        """status is 'failed' when no app is matched."""
        body = _valid_context()
        body["nl_query_original"] = "show me all records in UNKNOWN_XYZ_APP"
        with make_client() as client:
            response = client.post(
                ENDPOINT,
                json=body,
                headers={"X-API-Key": FOUNDRY_KEY},
            )
        data = response.json()
        assert data["status"] == "failed"

    def test_E3_unrecognised_app_error_code(self):
        """Error code is APP_NOT_DETERMINED when no app is matched."""
        body = _valid_context()
        body["nl_query_original"] = "show me all records in UNKNOWN_XYZ_APP"
        with make_client() as client:
            response = client.post(
                ENDPOINT,
                json=body,
                headers={"X-API-Key": FOUNDRY_KEY},
            )
        data = response.json()
        assert data["errors"][0]["code"] == "APP_NOT_DETERMINED"


# ---------------------------------------------------------------------------
# Group F — Explicit app_id pre-set (Path 1 in run_app_identifier)
# When app_id is already set, synonym matching is skipped — just validates
# the ID exists in loaded schemas and populates app_schema_version.
# ---------------------------------------------------------------------------

class TestExplicitAppId:
    """Explicit app_id pre-set → Path 1 — skip synonym matching."""

    def test_F1_explicit_app_id_returns_200(self):
        """HTTP 200 when app_id is pre-set to a valid known app."""
        body = _valid_context()
        body["app_id"] = "Acme_app"
        with make_client() as client:
            response = client.post(
                ENDPOINT,
                json=body,
                headers={"X-API-Key": FOUNDRY_KEY},
            )
        assert response.status_code == 200

    def test_F2_explicit_app_id_unchanged_in_response(self):
        """app_id is unchanged when pre-set to a valid value."""
        body = _valid_context()
        body["app_id"] = "Acme_app"
        with make_client() as client:
            response = client.post(
                ENDPOINT,
                json=body,
                headers={"X-API-Key": FOUNDRY_KEY},
            )
        data = response.json()
        assert data["context"]["app_id"] == "Acme_app"

    def test_F3_explicit_app_id_populates_version(self):
        """app_schema_version is populated even when app_id was pre-set."""
        body = _valid_context()
        body["app_id"] = "Acme_app"
        with make_client() as client:
            response = client.post(
                ENDPOINT,
                json=body,
                headers={"X-API-Key": FOUNDRY_KEY},
            )
        data = response.json()
        assert data["context"]["app_schema_version"] not in ("", None)
