# tests/api/tools/test_validator_tool.py
# V0 - Initial implementation
# V1 - Story 4.6 fix: E1 assertion corrected from INTERNAL_ERROR to
#      SCHEMA_LOAD_ERROR — schema load failure returns its specific code,
#      not the generic INTERNAL_ERROR.
#
# Tests for POST /v1/tools/validator — Foundry validator tool endpoint.
#
# What this endpoint does:
#   1. Validates required QueryContext fields (app_id, app_schema_version,
#      llm_output) — returns 400 if any are missing.
#   2. Runs table/column validator — rejects unknown tables/columns (200 on failure).
#   3. Runs join resolver — rejects unresolvable join paths (200 on failure).
#   4. Runs rule applicator — applies business rules (always succeeds if tables valid).
#   5. Runs structured query builder — builds StructuredQuery (200 on failure).
#   6. Returns ToolResponse with updated QueryContext including structured_query.
#
# Test groups:
#   A — Auth (wrong/missing key)
#   B — Context field validation (missing required fields)
#   C — Validator chain business errors (HTTP 200)
#   D — Success path (structured_query populated)
#   E — Schema not found for app_id
#
# Fixtures used from tests/api/conftest.py (autouse):
#   set_test_env_vars — injects ENV, CLIENT_API_KEY, FOUNDRY_API_KEY, LLM_PROVIDER

import json

from fastapi.testclient import TestClient

from src.api.app import create_app

# ---------------------------------------------------------------------------
# Shared test constants
# ---------------------------------------------------------------------------

FOUNDRY_KEY = "test-foundry-key-67890"
CLIENT_KEY  = "test-client-key-12345"
WRONG_KEY   = "wrong-key"

# Minimal valid llm_output — single table, one column, no filters.
# Matches ABC_app schema — Major.Customer and Major.CustomerDemographics exist.
_GOLDEN_LLM_OUTPUT = {
    "tables": [
        {"table": "Major.Customer",             "source": "customer"},
        {"table": "Major.CustomerDemographics", "source": "customer name"},
    ],
    "columns": [
        {"table": "Major.CustomerDemographics", "column": "CustomerName", "source": "customer name"},
        {"table": "Major.Customer",             "column": "CustomerCID",  "source": "customer id"},
    ],
    "filters": [
        {"table": "Major.Customer", "column": "CustomerCID",
         "operator": "=", "value": "ASA", "source": "customer ASA"},
    ],
    "limit": None,
    "aggregation": None,
    "sort": [],
}

# A valid QueryContext body with all required fields for "validator" stage.
# llm_output is populated — NL-to-IR stage already ran.
_VALID_CONTEXT = {
    "request_id":          "test-req-validator-001",
    "user_id":             "test-agent",
    "app_id":              "ABC_app",
    "app_schema_version":  "1.0",
    "nl_query_original":   "give me customer name for customer ASA in ABC",
    "nl_query_corrected":  None,
    "llm_output":          _GOLDEN_LLM_OUTPUT,
    "resolved_tables":     [],
    "resolved_columns":    [],
    "resolved_filters":    [],
    "resolved_joins":      [],
    "applied_rules":       [],
    "structured_query":    None,
    "sql":                 None,
    "latency_ms":          {},
    "total_latency_ms":    0,
    "token_usage":         {},
    "warnings":            [],
    "status":              "success",
    "error":               None,
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_client() -> TestClient:
    """Create a TestClient using the real ABC schema directory."""
    app = create_app(schema_dir="schemas")
    return TestClient(app, raise_server_exceptions=False)


# ---------------------------------------------------------------------------
# Group A — Authentication
# Tool endpoints use FOUNDRY_API_KEY, not CLIENT_API_KEY.
# ---------------------------------------------------------------------------

class TestAuth:
    """Auth enforcement on POST /v1/tools/validator."""

    def test_A1_missing_api_key_returns_401(self):
        """No X-API-Key header → 401."""
        with make_client() as client:
            response = client.post("/v1/tools/validator", json=_VALID_CONTEXT)
        assert response.status_code == 401

    def test_A2_wrong_key_value_returns_401(self):
        """Wrong X-API-Key value → 401."""
        with make_client() as client:
            response = client.post(
                "/v1/tools/validator",
                json=_VALID_CONTEXT,
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
                "/v1/tools/validator",
                json=_VALID_CONTEXT,
                headers={"X-API-Key": CLIENT_KEY},
            )
        assert response.status_code == 401

    def test_A4_correct_foundry_key_passes_auth(self):
        """Correct FOUNDRY_API_KEY → request is not rejected by auth."""
        with make_client() as client:
            response = client.post(
                "/v1/tools/validator",
                json=_VALID_CONTEXT,
                headers={"X-API-Key": FOUNDRY_KEY},
            )
        assert response.status_code != 401


# ---------------------------------------------------------------------------
# Group B — Context field validation
# Stage "validator" requires: app_id, app_schema_version, llm_output.
# Missing or empty → HTTP 400, MISSING_CONTEXT_FIELDS, field list in response.
# ---------------------------------------------------------------------------

class TestContextValidation:
    """Missing required context fields return 400 before any stage runs."""

    def test_B1_missing_app_id_returns_400(self):
        """app_id empty → 400 MISSING_CONTEXT_FIELDS."""
        body = {**_VALID_CONTEXT, "app_id": ""}
        with make_client() as client:
            response = client.post(
                "/v1/tools/validator",
                json=body,
                headers={"X-API-Key": FOUNDRY_KEY},
            )
        assert response.status_code == 400
        data = response.json()
        assert data["errors"][0]["code"] == "MISSING_CONTEXT_FIELDS"
        assert "app_id" in data["missing_fields"]

    def test_B2_missing_app_schema_version_returns_400(self):
        """app_schema_version empty → 400 MISSING_CONTEXT_FIELDS."""
        body = {**_VALID_CONTEXT, "app_schema_version": ""}
        with make_client() as client:
            response = client.post(
                "/v1/tools/validator",
                json=body,
                headers={"X-API-Key": FOUNDRY_KEY},
            )
        assert response.status_code == 400
        data = response.json()
        assert data["errors"][0]["code"] == "MISSING_CONTEXT_FIELDS"
        assert "app_schema_version" in data["missing_fields"]

    def test_B3_llm_output_none_returns_400(self):
        """
        llm_output = None → 400 MISSING_CONTEXT_FIELDS.
        None means NL-to-IR stage never ran — validator cannot proceed.
        """
        body = {**_VALID_CONTEXT, "llm_output": None}
        with make_client() as client:
            response = client.post(
                "/v1/tools/validator",
                json=body,
                headers={"X-API-Key": FOUNDRY_KEY},
            )
        assert response.status_code == 400
        data = response.json()
        assert data["errors"][0]["code"] == "MISSING_CONTEXT_FIELDS"
        assert "llm_output" in data["missing_fields"]

    def test_B4_all_three_missing_lists_all_in_error(self):
        """All three required fields missing → 400, all three in missing_fields."""
        body = {
            **_VALID_CONTEXT,
            "app_id": "",
            "app_schema_version": "",
            "llm_output": None,
        }
        with make_client() as client:
            response = client.post(
                "/v1/tools/validator",
                json=body,
                headers={"X-API-Key": FOUNDRY_KEY},
            )
        assert response.status_code == 400
        data = response.json()
        missing = data["missing_fields"]
        assert "app_id" in missing
        assert "app_schema_version" in missing
        assert "llm_output" in missing


# ---------------------------------------------------------------------------
# Group C — Validator chain business errors (HTTP 200)
# Each error is an expected pipeline outcome — not a server failure.
# context.status = "failed", HTTP 200, error code in response.
# ---------------------------------------------------------------------------

class TestValidatorChainErrors:
    """Business errors from any stage return HTTP 200 with error code."""

    def test_C1_unknown_table_returns_no_relevant_tables(self):
        """
        LLM proposed a table not in schema → 200, NO_RELEVANT_TABLES.
        """
        body = {
            **_VALID_CONTEXT,
            "llm_output": {
                **_GOLDEN_LLM_OUTPUT,
                "tables": [{"table": "Major.NonExistentTable", "source": "bad table"}],
                "columns": [],
                "filters": [],
            },
        }
        with make_client() as client:
            response = client.post(
                "/v1/tools/validator",
                json=body,
                headers={"X-API-Key": FOUNDRY_KEY},
            )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "failed"
        assert data["errors"][0]["code"] == "NO_RELEVANT_TABLES"

    def test_C2_unknown_column_returns_no_relevant_columns(self):
        """
        LLM proposed a column not on its table → 200, NO_RELEVANT_COLUMNS.
        """
        body = {
            **_VALID_CONTEXT,
            "llm_output": {
                **_GOLDEN_LLM_OUTPUT,
                "tables": [{"table": "Major.Customer", "source": "customer"}],
                "columns": [
                    {"table": "Major.Customer", "column": "NonExistentColumn",
                     "source": "bad column"},
                ],
                "filters": [],
            },
        }
        with make_client() as client:
            response = client.post(
                "/v1/tools/validator",
                json=body,
                headers={"X-API-Key": FOUNDRY_KEY},
            )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "failed"
        assert data["errors"][0]["code"] == "NO_RELEVANT_COLUMNS"

    def test_C3_no_join_path_returns_no_join_path(self):
        """
        Two tables with no relationship → 200, NO_JOIN_PATH.
        Major.Plan and Major.CustomerDemographics have no direct relationship.
        """
        body = {
            **_VALID_CONTEXT,
            "llm_output": {
                **_GOLDEN_LLM_OUTPUT,
                "tables": [
                    {"table": "Major.Plan",                  "source": "plan"},
                    {"table": "Major.CustomerDemographics",  "source": "customer name"},
                ],
                "columns": [
                    {"table": "Major.Plan", "column": "PlanName", "source": "plan name"},
                ],
                "filters": [],
            },
        }
        with make_client() as client:
            response = client.post(
                "/v1/tools/validator",
                json=body,
                headers={"X-API-Key": FOUNDRY_KEY},
            )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "failed"
        assert data["errors"][0]["code"] == "NO_JOIN_PATH"


# ---------------------------------------------------------------------------
# Group D — Success path
# Valid context with good llm_output → structured_query populated.
# ---------------------------------------------------------------------------

class TestSuccess:
    """Valid context produces a successful ToolResponse with structured_query."""

    def test_D1_valid_context_returns_200_with_structured_query(self):
        """
        Valid context body → 200, structured_query populated,
        context.status = "success".
        """
        with make_client() as client:
            response = client.post(
                "/v1/tools/validator",
                json=_VALID_CONTEXT,
                headers={"X-API-Key": FOUNDRY_KEY},
            )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["context"]["structured_query"] is not None
        assert "tables" in data["context"]["structured_query"]
        assert "columns" in data["context"]["structured_query"]

    def test_D2_response_has_correct_tool_response_shape(self):
        """
        Response envelope matches ToolResponse shape:
          request_id, status, context, errors.
        errors is empty list on success.
        """
        with make_client() as client:
            response = client.post(
                "/v1/tools/validator",
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

    def test_D3_request_id_preserved_in_response(self):
        """request_id sent in context body must be echoed unchanged in response."""
        my_request_id = "validator-req-abc-999"
        body = {**_VALID_CONTEXT, "request_id": my_request_id}
        with make_client() as client:
            response = client.post(
                "/v1/tools/validator",
                json=body,
                headers={"X-API-Key": FOUNDRY_KEY},
            )
        data = response.json()
        assert data["request_id"] == my_request_id

    def test_D4_applied_rules_present_in_structured_query(self):
        """
        applied_rules must be present in the structured_query in the response.
        Rule applicator runs as part of the chain — rules are expected for
        Major.Customer which has active_record business rules in the schema.
        """
        with make_client() as client:
            response = client.post(
                "/v1/tools/validator",
                json=_VALID_CONTEXT,
                headers={"X-API-Key": FOUNDRY_KEY},
            )
        assert response.status_code == 200
        data = response.json()
        sq = data["context"]["structured_query"]
        assert "applied_rules" in sq
        assert len(sq["applied_rules"]) > 0


# ---------------------------------------------------------------------------
# Group E — Schema not found
# ---------------------------------------------------------------------------

class TestSchemaNotFound:
    """Unknown app_id causes schema lookup failure → 500 INTERNAL_ERROR."""

    def test_E1_unknown_app_id_returns_500(self):
        """
        app_id set to a value not in any loaded schema → 500 INTERNAL_ERROR.
        ContextValidator passes (app_id is non-empty) but schema_repo raises
        when table_column_validator tries to load the schema.
        """
        body = {
            **_VALID_CONTEXT,
            "app_id": "UNKNOWN_APP",
            "app_schema_version": "1.0",
        }
        with make_client() as client:
            response = client.post(
                "/v1/tools/validator",
                json=body,
                headers={"X-API-Key": FOUNDRY_KEY},
            )
        assert response.status_code == 500
        data = response.json()
        assert data["context"]["status"] == "failed"
        assert data["errors"][0]["code"] == "SCHEMA_LOAD_ERROR"
