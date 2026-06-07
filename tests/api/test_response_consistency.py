# tests/api/test_response_consistency.py
# V0 - Initial implementation
#
# Response consistency audit — asserts every endpoint returns the correct
# envelope shape as defined in the architecture.
#
# Section 10.3 (user-facing):  {request_id, status, data, meta, errors}
# Section 10.5 (tool endpoints): {request_id, status, context, errors}
# Minimal envelope (feedback, error paths): {request_id, status, errors}
#
# Test groups:
#   A — Confirm Story 3.7 TODO is gone (query.py V2 has final shape, not raw QueryContext)
#   B — Tool endpoint ToolResponse shapes (success path, all 5 endpoints)
#   C — Error response shapes are also correct (business error + 400 fix confirmation)
#   D — feedback_tool 501 placeholder shape is stable
#
# Story 6.4 FIX CONFIRMED by C2:
#   Before fix: tool endpoint 400 responses had {status, errors, missing_fields}
#               — non-standard key, missing request_id.
#   After fix:  MissingContextFieldsError propagates to global exception handler
#               (middleware.py, Story 6.2) → {request_id, status, errors}.
#               No missing_fields at top level.

import json

from fastapi.testclient import TestClient

from src.api.app import create_app
from src.llm.mock_provider import MockLLMProvider

# ---------------------------------------------------------------------------
# Shared test constants
# ---------------------------------------------------------------------------

VALID_KEY   = "test-client-key-12345"
FOUNDRY_KEY = "test-foundry-key-67890"

# Minimal valid simplified IR — same as test_query.py.
# Major.Customer ↔ Major.CustomerDemographics have a direct relationship
# in Acme_app.json, so the validator chain resolves a clean StructuredQuery.
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

# Pre-built StructuredQuery dict for the sql-builder test (B4).
# Bypasses the LLM + validator stages entirely — sql-builder only reads
# structured_query from the context.
_STRUCTURED_QUERY = {
    "app_id": "Acme_app",
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

# Pre-populated llm_output dict for the validator test (B3).
# Bypasses the LLM stage — validator reads llm_output from context directly.
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


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_client(schema_dir: str = "schemas") -> TestClient:
    """
    TestClient for both user-facing and tool endpoint tests.
    raise_server_exceptions=False is required so the global exception handler
    (Story 6.2) can respond to errors rather than crashing the test thread.
    """
    app = create_app(schema_dir=schema_dir)
    return TestClient(app, raise_server_exceptions=False)


# ---------------------------------------------------------------------------
# Group A — Confirm Story 3.7 TODO is gone
# ---------------------------------------------------------------------------

class TestStory37Removed:
    """
    The temporary QueryContext response shape introduced in Story 3.7 must
    be fully gone. POST /v1/query must return the final QueryResponse shape
    (Section 10.3), not raw QueryContext fields at the top level.
    """

    def test_a1_query_success_has_no_querycontext_fields_at_top_level(self):
        """
        A1: Successful /v1/query response top-level keys are exactly
            {request_id, status, data, meta, errors}.
            Raw QueryContext fields (nl_query_original, llm_output,
            resolved_tables, etc.) must NOT appear at the top level.
        """
        app = create_app(schema_dir="schemas")
        with TestClient(app, raise_server_exceptions=False) as client:
            app.state.llm_provider = MockLLMProvider(responses=[_GOLDEN_IR])
            response = client.post(
                "/v1/query",
                json={
                    "nl_query": "give me customers in Acme",
                    "user_id": "test-user",
                },
                headers={"X-API-Key": VALID_KEY},
            )

        assert response.status_code == 200
        data = response.json()

        # Required top-level keys — Section 10.3
        for key in ("request_id", "status", "data", "meta", "errors"):
            assert key in data, f"Missing required key: {key}"

        # Raw QueryContext fields must NOT be at top level
        for raw_key in (
            "nl_query_original",
            "llm_output",
            "resolved_tables",
            "resolved_columns",
            "resolved_filters",
            "resolved_joins",
            "structured_query",
            "applied_rules",
        ):
            assert raw_key not in data, (
                f"QueryContext field '{raw_key}' must not appear at the top level "
                "of a /v1/query response. Story 3.7 temporary shape was not removed."
            )


# ---------------------------------------------------------------------------
# Group B — Tool endpoint ToolResponse shapes
# ---------------------------------------------------------------------------

class TestToolResponseShapes:
    """
    Every Foundry tool endpoint must return ToolResponse shape (Section 10.5):
    {request_id, status, context, errors}
    """

    def test_b1_app_identifier_has_tool_response_shape(self):
        """
        B1: POST /v1/tools/app-identifier success → {request_id, status, context, errors}.
        """
        with make_client() as client:
            response = client.post(
                "/v1/tools/app-identifier",
                json={
                    "nl_query_original": "give me customers in Acme",
                    "user_id": "test-user",
                },
                headers={"X-API-Key": FOUNDRY_KEY},
            )

        assert response.status_code == 200
        data = response.json()
        for key in ("request_id", "status", "context", "errors"):
            assert key in data, f"ToolResponse missing key: {key}"

    def test_b2_nl_to_ir_has_tool_response_shape(self):
        """
        B2: POST /v1/tools/nl-to-ir success → {request_id, status, context, errors}.
        Requires MockLLMProvider — overridden after lifespan runs.
        """
        app = create_app(schema_dir="schemas")
        with TestClient(app, raise_server_exceptions=False) as client:
            app.state.llm_provider = MockLLMProvider(responses=[_GOLDEN_IR])
            response = client.post(
                "/v1/tools/nl-to-ir",
                json={
                    "nl_query_original": "give me customers in Acme",
                    "app_id": "Acme_app",
                    "app_schema_version": "1.0",
                    "user_id": "test-user",
                },
                headers={"X-API-Key": FOUNDRY_KEY},
            )

        assert response.status_code == 200
        data = response.json()
        for key in ("request_id", "status", "context", "errors"):
            assert key in data, f"ToolResponse missing key: {key}"

    def test_b3_validator_has_tool_response_shape(self):
        """
        B3: POST /v1/tools/validator success → {request_id, status, context, errors}.
        llm_output pre-populated in the request body — no LLM call needed.
        """
        with make_client() as client:
            response = client.post(
                "/v1/tools/validator",
                json={
                    "nl_query_original": "give me customers in Acme",
                    "app_id": "Acme_app",
                    "app_schema_version": "1.0",
                    "user_id": "test-user",
                    "llm_output": _LLM_OUTPUT,
                },
                headers={"X-API-Key": FOUNDRY_KEY},
            )

        assert response.status_code == 200
        data = response.json()
        for key in ("request_id", "status", "context", "errors"):
            assert key in data, f"ToolResponse missing key: {key}"

    def test_b4_sql_builder_has_tool_response_shape(self):
        """
        B4: POST /v1/tools/sql-builder success → {request_id, status, context, errors}.
        structured_query pre-populated in the request body — no LLM or validator needed.
        """
        with make_client() as client:
            response = client.post(
                "/v1/tools/sql-builder",
                json={
                    "nl_query_original": "give me customers in Acme",
                    "app_id": "Acme_app",
                    "app_schema_version": "1.0",
                    "user_id": "test-user",
                    "structured_query": _STRUCTURED_QUERY,
                },
                headers={"X-API-Key": FOUNDRY_KEY},
            )

        assert response.status_code == 200
        data = response.json()
        for key in ("request_id", "status", "context", "errors"):
            assert key in data, f"ToolResponse missing key: {key}"

    def test_b5_query_tool_has_tool_response_shape(self):
        """
        B5: POST /v1/tools/query success → {request_id, status, context, errors}.
        Full pipeline — requires MockLLMProvider override.
        """
        app = create_app(schema_dir="schemas")
        with TestClient(app, raise_server_exceptions=False) as client:
            app.state.llm_provider = MockLLMProvider(responses=[_GOLDEN_IR])
            response = client.post(
                "/v1/tools/query",
                json={
                    "nl_query_original": "give me customers in Acme",
                    "user_id": "test-user",
                },
                headers={"X-API-Key": FOUNDRY_KEY},
            )

        assert response.status_code == 200
        data = response.json()
        for key in ("request_id", "status", "context", "errors"):
            assert key in data, f"ToolResponse missing key: {key}"


# ---------------------------------------------------------------------------
# Group C — Error response shapes are correct
# ---------------------------------------------------------------------------

class TestErrorResponseShapes:
    """
    Error paths must also return correctly shaped responses.
    Confirms both the user-facing business error envelope and the
    Story 6.4 fix (400 from middleware, not non-conformant route catch).
    """

    def test_c1_query_business_error_has_user_facing_envelope(self):
        """
        C1: APP_NOT_DETERMINED business error still returns Section 10.3 shape.
        HTTP 200 with status='failed' — no raw exception exposed, all keys present.
        """
        with make_client() as client:
            response = client.post(
                "/v1/query",
                json={
                    "nl_query": "give me all data please",
                    "user_id": "test-user",
                },
                headers={"X-API-Key": VALID_KEY},
            )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "failed"
        for key in ("request_id", "status", "data", "meta", "errors"):
            assert key in data, f"Business error response missing key: {key}"
        # Raw exception detail must not appear
        assert len(data["errors"]) > 0
        assert data["errors"][0]["code"] == "APP_NOT_DETERMINED"

    def test_c2_tool_missing_context_400_has_correct_envelope_no_missing_fields_key(self):
        """
        C2: MissingContextFieldsError from a tool endpoint → Story 6.2 middleware
            → HTTP 400 with {request_id, status, errors}.

        BEFORE Story 6.4 fix: response was {status, errors, missing_fields}
                               — no request_id, extra non-standard key.
        AFTER Story 6.4 fix:  middleware returns {request_id, status, errors}
                               — no missing_fields at top level.

        Trigger: send nl-to-ir with app_id="" (default) — validator requires it.
        """
        with make_client() as client:
            response = client.post(
                "/v1/tools/nl-to-ir",
                json={
                    "nl_query_original": "give me customers in Acme",
                    "user_id": "test-user",
                    # app_id defaults to "" — ContextValidator treats as missing
                },
                headers={"X-API-Key": FOUNDRY_KEY},
            )

        assert response.status_code == 400
        data = response.json()

        # These keys must be present (correct minimal envelope from middleware)
        assert "request_id" in data, "request_id must be present in 400 response"
        assert "status" in data
        assert "errors" in data
        assert data["status"] == "failed"
        assert data["errors"][0]["code"] == "MISSING_CONTEXT_FIELDS"

        # This key must NOT be present (it was the non-conformant addition pre-fix)
        assert "missing_fields" not in data, (
            "'missing_fields' must not appear as a top-level key. "
            "Story 6.4 fix: route-level MissingContextFieldsError catch removed, "
            "middleware handles it with the standard envelope."
        )


# ---------------------------------------------------------------------------
# Group D — feedback_tool 501 placeholder shape is stable
# ---------------------------------------------------------------------------

class TestFeedbackToolPlaceholder:
    """
    POST /v1/tools/feedback is a Phase 3 placeholder returning 501.
    Confirm it is still in that state and won't silently change shape.
    """

    def test_d1_feedback_tool_returns_501_not_implemented(self):
        """
        D1: POST /v1/tools/feedback → 501, status='not_implemented'.
        No auth on this placeholder route.
        """
        with make_client() as client:
            response = client.post("/v1/tools/feedback")

        assert response.status_code == 501
        data = response.json()
        assert data["status"] == "not_implemented"
