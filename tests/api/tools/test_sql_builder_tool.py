# tests/api/tools/test_sql_builder_tool.py
# V0 - Initial implementation
#
# Tests for POST /v1/tools/sql-builder — Foundry SQL builder tool endpoint.
#
# What this endpoint does:
#   1. Validates required QueryContext fields (structured_query) — returns 400
#      if missing.
#   2. Calls run_sql_builder() — assembles SQL from structured_query.
#   3. Returns ToolResponse with updated QueryContext including context.sql.
#
# Test groups:
#   A — Auth (wrong/missing key)
#   B — Context field validation (missing structured_query)
#   D — Success path (sql populated)
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

# Minimal valid StructuredQuery — field names match models.py exactly.
# ResolvedTable  : table_name, alias
# ResolvedColumn : table_alias, column_name, output_alias
# ResolvedJoin   : join_type, table_name, alias, on_conditions (list of {left, right})
# ResolvedFilter : table_alias, column_name, operator, value, connector
_GOLDEN_STRUCTURED_QUERY = {
    "app_id": "ABC_app",
    "tables": [
        {"table_name": "Major.Customer",             "alias": "c"},
        {"table_name": "Major.CustomerDemographics", "alias": "cd"},
    ],
    "columns": [
        {"table_alias": "cd", "column_name": "CustomerName", "output_alias": "CustomerName"},
        {"table_alias": "c",  "column_name": "CustomerCID",  "output_alias": "CustomerCID"},
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
    "filters": [
        {
            "table_alias": "c",
            "column_name": "CustomerCID",
            "operator": "=",
            "value": "ASA",
            "connector": "AND",
        }
    ],
    "applied_rules": [],
    "top_rows": None,
    "aggregation": None,
    "sort": [],
}

# A valid QueryContext body with structured_query populated.
# sql_builder stage requires: structured_query.
_VALID_CONTEXT = {
    "request_id":         "test-req-sqlbuilder-001",
    "user_id":            "test-agent",
    "app_id":             "ABC_app",
    "app_schema_version": "1.0",
    "nl_query_original":  "give me customer name for customer ASA in ABC",
    "nl_query_corrected": None,
    "llm_output":         None,
    "resolved_tables":    [],
    "resolved_columns":   [],
    "resolved_filters":   [],
    "resolved_joins":     [],
    "applied_rules":      [],
    "structured_query":   _GOLDEN_STRUCTURED_QUERY,
    "sql":                None,
    "latency_ms":         {},
    "total_latency_ms":   0,
    "token_usage":        {},
    "warnings":           [],
    "status":             "success",
    "error":              None,
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
    """Auth enforcement on POST /v1/tools/sql-builder."""

    def test_A1_missing_api_key_returns_401(self):
        """No X-API-Key header → 401."""
        with make_client() as client:
            response = client.post("/v1/tools/sql-builder", json=_VALID_CONTEXT)
        assert response.status_code == 401

    def test_A2_wrong_key_value_returns_401(self):
        """Wrong X-API-Key value → 401."""
        with make_client() as client:
            response = client.post(
                "/v1/tools/sql-builder",
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
                "/v1/tools/sql-builder",
                json=_VALID_CONTEXT,
                headers={"X-API-Key": CLIENT_KEY},
            )
        assert response.status_code == 401

    def test_A4_correct_foundry_key_passes_auth(self):
        """Correct FOUNDRY_API_KEY → request is not rejected by auth."""
        with make_client() as client:
            response = client.post(
                "/v1/tools/sql-builder",
                json=_VALID_CONTEXT,
                headers={"X-API-Key": FOUNDRY_KEY},
            )
        assert response.status_code != 401


# ---------------------------------------------------------------------------
# Group B — Context field validation
# Stage "sql_builder" requires: structured_query.
# None → HTTP 400, MISSING_CONTEXT_FIELDS, field name in missing_fields.
# ---------------------------------------------------------------------------

class TestContextValidation:
    """Missing required context fields return 400 before any stage runs."""

    def test_B1_missing_structured_query_returns_400(self):
        """
        structured_query = None → 400 MISSING_CONTEXT_FIELDS.
        None means the validator stage never ran — SQL builder cannot proceed.
        """
        body = {**_VALID_CONTEXT, "structured_query": None}
        with make_client() as client:
            response = client.post(
                "/v1/tools/sql-builder",
                json=body,
                headers={"X-API-Key": FOUNDRY_KEY},
            )
        assert response.status_code == 400
        data = response.json()
        assert data["errors"][0]["code"] == "MISSING_CONTEXT_FIELDS"
        assert "structured_query" in data["missing_fields"]


# ---------------------------------------------------------------------------
# Group D — Success path
# Valid context with structured_query populated → sql assembled and returned.
# ---------------------------------------------------------------------------

class TestSuccess:
    """Valid context produces a successful ToolResponse with sql populated."""

    def test_D1_valid_context_returns_200_with_sql(self):
        """
        Valid context body → 200, context.sql populated, contains SELECT.
        """
        with make_client() as client:
            response = client.post(
                "/v1/tools/sql-builder",
                json=_VALID_CONTEXT,
                headers={"X-API-Key": FOUNDRY_KEY},
            )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["context"]["sql"] is not None
        assert "SELECT" in data["context"]["sql"]

    def test_D2_response_has_correct_tool_response_shape(self):
        """
        Response envelope matches ToolResponse shape:
          request_id, status, context, errors.
        errors is empty list on success.
        """
        with make_client() as client:
            response = client.post(
                "/v1/tools/sql-builder",
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
        my_request_id = "sqlbuilder-req-abc-999"
        body = {**_VALID_CONTEXT, "request_id": my_request_id}
        with make_client() as client:
            response = client.post(
                "/v1/tools/sql-builder",
                json=body,
                headers={"X-API-Key": FOUNDRY_KEY},
            )
        data = response.json()
        assert data["request_id"] == my_request_id

    def test_D4_context_status_is_success(self):
        """context.status = 'success' in response on clean run."""
        with make_client() as client:
            response = client.post(
                "/v1/tools/sql-builder",
                json=_VALID_CONTEXT,
                headers={"X-API-Key": FOUNDRY_KEY},
            )
        assert response.status_code == 200
        data = response.json()
        assert data["context"]["status"] == "success"
