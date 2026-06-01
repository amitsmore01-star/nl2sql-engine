# tests/api/tools/test_tools_integration.py
# V0 - Initial implementation
#
# Integration tests for the Foundry agent tool workflow.
#
# These tests prove the CHAIN works — not just each stage in isolation.
# Each test calls real HTTP endpoints in sequence, passing the context
# returned by one stage as the body to the next.
#
# What is being verified:
#   1. Context ACCUMULATES correctly stage by stage — each stage adds its
#      output fields and preserves all fields the previous stages set.
#   2. The engine does NOT enforce call order — any stage runs as long as
#      its required fields are present, regardless of how they got there.
#   3. Hand-crafted llm_output is accepted by the validator — the agent
#      can bypass the LLM stage entirely if it already knows the IR.
#   4. Intent Guard fires at EVERY entry point that accepts nl_query_original.
#
# Test groups:
#   A — Sequential full pipeline (stage by stage, real chain)
#   B — Hand-crafted llm_output (skip LLM step entirely)
#   C — Out-of-order call (skip tool endpoint calls, pre-populate fields)
#   D — Mixed: app-identifier tool then one-shot tools/query
#   E — Intent Guard at every tool entry point
#
# Infrastructure notes:
#   - tests/api/conftest.py injects ENV, CLIENT_API_KEY, FOUNDRY_API_KEY,
#     LLM_PROVIDER=mock via autouse — no explicit setup needed in tests.
#   - MockLLMProvider must be overridden INSIDE the with TestClient() block
#     (after lifespan runs) — LLMProviderFactory.create() runs at startup.
#   - MockLLMProvider(responses=[_GOLDEN_IR]) — one response consumed for
#     the nl-to-ir step. Other stages don't call the LLM.
#   - All tool endpoints use FOUNDRY_KEY (X-API-Key header).
#   - raise_server_exceptions=False — lets global exception handler respond
#     instead of crashing the test thread.

import json

from fastapi.testclient import TestClient

from src.api.app import create_app
from src.llm.mock_provider import MockLLMProvider

# ---------------------------------------------------------------------------
# Shared constants
# ---------------------------------------------------------------------------

FOUNDRY_KEY = "test-foundry-key-67890"

# Minimal valid simplified IR — Major.Customer ↔ Major.CustomerDemographics
# have a direct relationship in ABC_app.json. The validator chain resolves
# a clean StructuredQuery from this IR and the SQL builder produces valid SQL.
# Same golden IR used in test_query.py and test_response_consistency.py.
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

# Pre-built llm_output dict for hand-crafted bypass tests (Groups B and C).
# Same content as _GOLDEN_IR but as a Python dict — sent directly in the
# context body so the agent bypasses the nl-to-ir endpoint entirely.
_HAND_CRAFTED_LLM_OUTPUT = {
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

# Minimal initial context body — only nl_query_original required for the
# first stage (app-identifier). All other QueryContext fields use defaults.
_INITIAL_CONTEXT = {
    "nl_query_original": "give me customers in ABC",
    "user_id": "integration-test-user",
}

# Non-select query used to trigger Intent Guard at every entry point.
_DELETE_QUERY_CONTEXT = {
    "nl_query_original": "DELETE all customers in ABC",
    "user_id": "integration-test-user",
}


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def make_client() -> TestClient:
    """
    Create a TestClient with the real ABC schema loaded.
    raise_server_exceptions=False lets the global exception handler (Story 6.2)
    return structured responses rather than re-raising in the test thread.
    The MockLLMProvider is NOT overridden here — tests that need a specific
    LLM response do so inside the with-block after lifespan runs.
    """
    app = create_app(schema_dir="schemas")
    return TestClient(app, raise_server_exceptions=False)


# ---------------------------------------------------------------------------
# Group A — Sequential full pipeline
# ---------------------------------------------------------------------------

class TestSequentialPipeline:
    """
    The core integration scenario: the Foundry agent calls each stage
    endpoint in sequence, passing the full context from each response
    as the body of the next request.

    Verifies that context accumulates correctly at every stage boundary —
    the output fields from stage N are present and correct in stage N+1's
    context.
    """

    def test_a1_full_sequential_chain_accumulates_context_and_produces_sql(self):
        """
        A1: Complete stage-by-stage workflow.

        Step 1  POST /v1/tools/app-identifier
                Input:  nl_query_original only
                Assert: context.app_id == "ABC_app"

        Step 2  POST /v1/tools/nl-to-ir
                Input:  context from Step 1 (app_id now set)
                Assert: context.llm_output is populated

        Step 3  POST /v1/tools/validator
                Input:  context from Step 2 (llm_output now set)
                Assert: context.structured_query is populated

        Step 4  POST /v1/tools/sql-builder
                Input:  context from Step 3 (structured_query now set)
                Assert: context.sql is populated and contains SELECT
        """
        app = create_app(schema_dir="schemas")
        with TestClient(app, raise_server_exceptions=False) as client:

            # Override LLM provider — consumed at Step 2 (nl-to-ir)
            app.state.llm_provider = MockLLMProvider(responses=[_GOLDEN_IR])

            # ----------------------------------------------------------
            # Step 1 — App Identifier
            # ----------------------------------------------------------
            r1 = client.post(
                "/v1/tools/app-identifier",
                json=_INITIAL_CONTEXT,
                headers={"X-API-Key": FOUNDRY_KEY},
            )
            assert r1.status_code == 200, f"Step 1 failed: {r1.text}"
            ctx1 = r1.json()["context"]
            assert ctx1["app_id"] == "ABC_app", (
                "Step 1: app_id must be 'ABC_app' after app-identifier runs."
            )
            assert ctx1["app_schema_version"] == "1.0", (
                "Step 1: app_schema_version must be populated by app-identifier."
            )
            assert ctx1["status"] == "success"

            # ----------------------------------------------------------
            # Step 2 — NL-to-IR (LLM call happens here)
            # Context from Step 1 is sent verbatim — app_id is now set.
            # ----------------------------------------------------------
            r2 = client.post(
                "/v1/tools/nl-to-ir",
                json=ctx1,
                headers={"X-API-Key": FOUNDRY_KEY},
            )
            assert r2.status_code == 200, f"Step 2 failed: {r2.text}"
            ctx2 = r2.json()["context"]
            assert ctx2["llm_output"] is not None, (
                "Step 2: llm_output must be populated after nl-to-ir runs."
            )
            assert "tables" in ctx2["llm_output"], (
                "Step 2: llm_output must have a 'tables' key."
            )
            # app_id from Step 1 must be preserved
            assert ctx2["app_id"] == "ABC_app", (
                "Step 2: app_id set in Step 1 must still be present."
            )

            # ----------------------------------------------------------
            # Step 3 — Validator chain
            # Context from Step 2 is sent — llm_output is now set.
            # ----------------------------------------------------------
            r3 = client.post(
                "/v1/tools/validator",
                json=ctx2,
                headers={"X-API-Key": FOUNDRY_KEY},
            )
            assert r3.status_code == 200, f"Step 3 failed: {r3.text}"
            ctx3 = r3.json()["context"]
            assert ctx3["structured_query"] is not None, (
                "Step 3: structured_query must be populated after validator runs."
            )
            assert ctx3["status"] == "success", (
                "Step 3: validator must complete with status='success'."
            )

            # ----------------------------------------------------------
            # Step 4 — SQL Builder
            # Context from Step 3 is sent — structured_query is now set.
            # ----------------------------------------------------------
            r4 = client.post(
                "/v1/tools/sql-builder",
                json=ctx3,
                headers={"X-API-Key": FOUNDRY_KEY},
            )
            assert r4.status_code == 200, f"Step 4 failed: {r4.text}"
            ctx4 = r4.json()["context"]
            assert ctx4["sql"] is not None, (
                "Step 4: sql must be populated after sql-builder runs."
            )
            assert "SELECT" in ctx4["sql"], (
                "Step 4: sql must contain SELECT."
            )
            assert "CustomerName" in ctx4["sql"], (
                "Step 4: sql must contain the CustomerName column."
            )
            assert ctx4["status"] == "success"


# ---------------------------------------------------------------------------
# Group B — Hand-crafted llm_output (agent bypasses the LLM step)
# ---------------------------------------------------------------------------

class TestHandCraftedLLMOutput:
    """
    The agent constructs the simplified IR manually (or from a cache) and
    sends it directly to the validator — bypassing /v1/tools/nl-to-ir.

    This is one of the key flexibility guarantees: the validator doesn't
    care WHERE llm_output came from. It only checks that it's present and
    that the tables/columns exist in the schema.
    """

    def test_b1_hand_crafted_llm_output_accepted_by_validator(self):
        """
        B1: Pre-built llm_output sent directly to validator.
        The agent populates app_id, app_schema_version, and llm_output
        itself — no tool endpoint calls for those fields.
        structured_query is populated in the response.
        """
        context_body = {
            **_INITIAL_CONTEXT,
            "app_id": "ABC_app",
            "app_schema_version": "1.0",
            "llm_output": _HAND_CRAFTED_LLM_OUTPUT,
        }

        with make_client() as client:
            response = client.post(
                "/v1/tools/validator",
                json=context_body,
                headers={"X-API-Key": FOUNDRY_KEY},
            )

        assert response.status_code == 200, f"B1 failed: {response.text}"
        ctx = response.json()["context"]
        assert ctx["structured_query"] is not None, (
            "B1: validator must accept hand-crafted llm_output and produce structured_query."
        )
        assert ctx["status"] == "success"

    def test_b2_sql_builder_accepts_context_from_hand_crafted_validator(self):
        """
        B2: Chain the hand-crafted validator result into sql-builder.
        Proves the two-step bypass workflow produces valid SQL.
        """
        context_body = {
            **_INITIAL_CONTEXT,
            "app_id": "ABC_app",
            "app_schema_version": "1.0",
            "llm_output": _HAND_CRAFTED_LLM_OUTPUT,
        }

        with make_client() as client:

            # Step 1 — Validator with hand-crafted llm_output
            r1 = client.post(
                "/v1/tools/validator",
                json=context_body,
                headers={"X-API-Key": FOUNDRY_KEY},
            )
            assert r1.status_code == 200, f"B2 validator step failed: {r1.text}"
            ctx_after_validator = r1.json()["context"]

            # Step 2 — SQL Builder with validated context
            r2 = client.post(
                "/v1/tools/sql-builder",
                json=ctx_after_validator,
                headers={"X-API-Key": FOUNDRY_KEY},
            )

        assert r2.status_code == 200, f"B2 sql-builder step failed: {r2.text}"
        ctx = r2.json()["context"]
        assert ctx["sql"] is not None, (
            "B2: sql-builder must produce SQL from hand-crafted validator output."
        )
        assert "SELECT" in ctx["sql"]


# ---------------------------------------------------------------------------
# Group C — Out-of-order call (pre-populated context)
# ---------------------------------------------------------------------------

class TestOutOfOrderCall:
    """
    The engine does not enforce stage call order. Any stage runs as long
    as its required fields are present — regardless of how those fields
    were set (via a previous tool endpoint, loaded from a cache, or
    constructed manually by the agent).

    This test skips ALL tool endpoint calls for the earlier stages and
    sends a pre-populated context directly to the validator.
    """

    def test_c1_validator_runs_with_pre_populated_context_bypassing_all_earlier_tools(self):
        """
        C1: The agent sends a context with app_id, app_schema_version, and
        llm_output already populated — without ever calling the app-identifier
        or nl-to-ir tool endpoints. The validator runs successfully.

        This confirms the architecture guarantee: the engine is stateless and
        order-agnostic. The agent drives the workflow.
        """
        # All required fields for the validator stage are pre-populated.
        # No prior tool endpoint calls were made to set them.
        pre_populated_context = {
            "nl_query_original": "give me customers in ABC",
            "user_id": "integration-test-user",
            "app_id": "ABC_app",                    # normally set by app-identifier
            "app_schema_version": "1.0",             # normally set by app-identifier
            "llm_output": _HAND_CRAFTED_LLM_OUTPUT, # normally set by nl-to-ir
        }

        with make_client() as client:
            response = client.post(
                "/v1/tools/validator",
                json=pre_populated_context,
                headers={"X-API-Key": FOUNDRY_KEY},
            )

        assert response.status_code == 200, f"C1 failed: {response.text}"
        ctx = response.json()["context"]
        assert ctx["structured_query"] is not None, (
            "C1: validator must run successfully when required fields are "
            "pre-populated, regardless of how they were set."
        )
        assert ctx["status"] == "success"


# ---------------------------------------------------------------------------
# Group D — Mixed: tool app-identifier then one-shot tools/query
# ---------------------------------------------------------------------------

class TestMixedWorkflow:
    """
    The agent uses the app-identifier tool to identify the app first,
    then hands the enriched context (with app_id) to /v1/tools/query
    for a one-shot full pipeline run.

    This mirrors a real Foundry agent pattern: use the lightest tool
    to resolve the app, then fire the full pipeline with confidence.
    """

    def test_d1_app_identifier_then_full_pipeline_via_tools_query(self):
        """
        D1: app-identifier sets app_id → enriched context sent to tools/query
        → full pipeline runs remaining stages → SQL produced.
        """
        app = create_app(schema_dir="schemas")
        with TestClient(app, raise_server_exceptions=False) as client:

            # Override LLM provider — consumed by run_pipeline() inside tools/query
            app.state.llm_provider = MockLLMProvider(responses=[_GOLDEN_IR])

            # ----------------------------------------------------------
            # Step 1 — App Identifier (lightweight tool call)
            # ----------------------------------------------------------
            r1 = client.post(
                "/v1/tools/app-identifier",
                json=_INITIAL_CONTEXT,
                headers={"X-API-Key": FOUNDRY_KEY},
            )
            assert r1.status_code == 200, f"D1 app-identifier failed: {r1.text}"
            ctx_with_app = r1.json()["context"]
            assert ctx_with_app["app_id"] == "ABC_app"

            # ----------------------------------------------------------
            # Step 2 — Full pipeline via tools/query
            # The agent passes the enriched context (with app_id set).
            # run_pipeline() skips the app-identifier stage when app_id
            # is already populated and runs nl-to-ir → validator → SQL.
            # ----------------------------------------------------------
            r2 = client.post(
                "/v1/tools/query",
                json=ctx_with_app,
                headers={"X-API-Key": FOUNDRY_KEY},
            )

        assert r2.status_code == 200, f"D1 tools/query failed: {r2.text}"
        ctx_final = r2.json()["context"]
        assert ctx_final["sql"] is not None, (
            "D1: tools/query must produce SQL when app_id is pre-populated."
        )
        assert "SELECT" in ctx_final["sql"]
        assert ctx_final["status"] == "success"


# ---------------------------------------------------------------------------
# Group E — Intent Guard at every tool entry point
# ---------------------------------------------------------------------------

class TestIntentGuardAtEveryEntryPoint:
    """
    The Intent Guard blocks non-select queries at EVERY endpoint that
    accepts nl_query_original. This is the architecture's safety guarantee:
    DELETE/DROP/INSERT queries never reach the LLM or any downstream stage.

    Architecture rule (Section 10.1):
    "Intent Guard runs at every endpoint that accepts nl_query_original."
    """

    def test_e1_delete_query_blocked_at_app_identifier(self):
        """
        E1: Non-select query to /v1/tools/app-identifier → UNSUPPORTED_INTENT.
        Intent Guard fires before app identifier runs.
        HTTP 200 (business error — not an HTTP error code).
        """
        with make_client() as client:
            response = client.post(
                "/v1/tools/app-identifier",
                json=_DELETE_QUERY_CONTEXT,
                headers={"X-API-Key": FOUNDRY_KEY},
            )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "failed"
        assert len(data["errors"]) > 0
        assert data["errors"][0]["code"] == "UNSUPPORTED_INTENT", (
            "E1: Intent Guard must block DELETE query at app-identifier "
            "with UNSUPPORTED_INTENT."
        )

    def test_e2_delete_query_blocked_at_nl_to_ir(self):
        """
        E2: Non-select query to /v1/tools/nl-to-ir → UNSUPPORTED_INTENT.
        Intent Guard fires before any LLM call is made.
        app_id pre-populated so the ContextValidator does not block first.
        HTTP 200.
        """
        context_body = {
            **_DELETE_QUERY_CONTEXT,
            "app_id": "ABC_app",
            "app_schema_version": "1.0",
        }

        with make_client() as client:
            response = client.post(
                "/v1/tools/nl-to-ir",
                json=context_body,
                headers={"X-API-Key": FOUNDRY_KEY},
            )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "failed"
        assert data["errors"][0]["code"] == "UNSUPPORTED_INTENT", (
            "E2: Intent Guard must block DELETE query at nl-to-ir "
            "before any LLM call is made."
        )

    def test_e3_delete_query_blocked_at_tools_query(self):
        """
        E3: Non-select query to /v1/tools/query → UNSUPPORTED_INTENT.
        Intent Guard fires at Stage 2 of the full pipeline (inside
        run_pipeline()). HTTP 200.
        """
        with make_client() as client:
            response = client.post(
                "/v1/tools/query",
                json=_DELETE_QUERY_CONTEXT,
                headers={"X-API-Key": FOUNDRY_KEY},
            )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "failed"
        assert data["errors"][0]["code"] == "UNSUPPORTED_INTENT", (
            "E3: Intent Guard must block DELETE query at tools/query "
            "with UNSUPPORTED_INTENT."
        )
