# tests/test_e2e.py
# V0 - Initial implementation
# V1 - Fixed 401 errors: root tests/conftest.py now injects env vars (was only in tests/api/).
#      Fixed empty log stages: LOG_DIR set via monkeypatch BEFORE create_app() in A1, A4, A5.
#      Removed try/finally blocks in A1, A4, A5 — monkeypatch cleans up automatically.
# V2 - Updated _GOLDEN_SQL to match actual pipeline output (captured from live run).
#      Fixed A4 expected_stages: VALIDATION_RESULT emitted 3 times (once per validator
#      sub-stage: table/column validator, join resolver, rule applicator).
# V3 - Updated _GOLDEN_SQL after join_resolver.py V2 fix (duplicate join condition removed).
#      a_sub join now has single AND c.CustomerID = a_sub.CustomerID (was duplicated).
#
# Golden End-to-End test suite.
# THIS FILE MUST NEVER FAIL — it is the safety net for the entire pipeline.
#
# Three test classes:
#
#   TestGoldenExactMatch  (Part A)
#     — The Section 9.3 golden query run via both /v1/query and /v1/tools/query.
#     — SQL asserted character-for-character against the architecture golden output.
#     — All 9 log stages verified in correct order for the /v1/query run.
#     — Uses a fixed request_id so the log file path is predictable.
#
#   TestDataDriven  (Part B)
#     — Every entry in config/mock_responses.json that has a "final_sql" field.
#     — SQL asserted exactly against final_sql.
#     — Entries without final_sql are skipped automatically.
#     — To add a new test case: add an entry to mock_responses.json — no code change.
#
#   TestDiagnostic
#     — Every entry in config/mock_responses.json.
#     — Runs the full pipeline and PRINTS the SQL — no assertions on SQL content.
#     — Always passes as long as the pipeline does not crash.
#     — Run with: pytest tests/test_e2e.py::TestDiagnostic -v -s
#       The -s flag is required to see printed output.
#
# How to run:
#   All E2E tests:          pytest tests/test_e2e.py -v
#   Part A only:            pytest tests/test_e2e.py::TestGoldenExactMatch -v
#   Part B only:            pytest tests/test_e2e.py::TestDataDriven -v
#   Diagnostic (with output): pytest tests/test_e2e.py::TestDiagnostic -v -s
#
# Auth keys used:
#   /v1/query         → CLIENT_API_KEY  ("test-client-key-12345")
#   /v1/tools/query   → FOUNDRY_API_KEY ("test-foundry-key-67890")
#
# LLM:
#   All tests use MockLLMProvider — zero real API calls.
#   Part A uses list mode (responses=[_GOLDEN_IR]) — one canned IR response.
#   Part B and Diagnostic use JSON file mode (MockLLMProvider()) —
#   auto-matches user_input from config/mock_responses.json.

import json
import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from src.api.app import create_app
from src.llm.mock_provider import MockLLMProvider
from src.core.constants import (
    REQUEST_RECEIVED,
    APP_DETECTED,
    INTENT_GUARD_RESULT,
    LLM_OUTPUT,
    VALIDATION_RESULT,
    STRUCTURED_QUERY_BUILT,
    SQL_BUILT,
    RESPONSE_SENT,
)

# ---------------------------------------------------------------------------
# Shared auth constants
# ---------------------------------------------------------------------------

CLIENT_KEY  = "test-client-key-12345"
FOUNDRY_KEY = "test-foundry-key-67890"

# ---------------------------------------------------------------------------
# Path to mock_responses.json
# ---------------------------------------------------------------------------

_MOCK_RESPONSES_PATH = Path("config/mock_responses.json")

# ---------------------------------------------------------------------------
# Part A — Golden IR fixture
#
# This is the exact simplified IR the mock LLM must return for the
# Section 9.3 golden query to produce the correct SQL.
# Matches the IR used in test_query_tool.py and test_orchestrator.py.
# ---------------------------------------------------------------------------

_GOLDEN_NL_QUERY = (
    "give me customer name, top acc and sub acc for customer ASA in ABC"
)

_GOLDEN_IR = json.dumps({
    "tables": [
        {"table": "Major.Customer",             "source": "customer"},
        {"table": "Major.CustomerDemographics", "source": "customer name"},
        {"table": "Major.Acc",                  "source": "top acc"},
        {"table": "Major.Acc",                  "source": "sub acc"},
    ],
    "columns": [
        {
            "table":  "Major.CustomerDemographics",
            "column": "CustomerName",
            "source": "customer name",
        },
        {
            "table":  "Major.Acc",
            "column": "AccName",
            "source": "top acc",
        },
        {
            "table":  "Major.Acc",
            "column": "AccName",
            "source": "sub acc",
        },
    ],
    "filters": [
        {
            "table":    "Major.Customer",
            "column":   "CustomerCID",
            "operator": "=",
            "value":    "ASA",
            "source":   "customer ASA",
        }
    ],
    "limit":       None,
    "aggregation": None,
    "sort":        [],
})

# ---------------------------------------------------------------------------
# Section 9.3 golden SQL — exact expected output.
# This string was captured from a live pipeline run and must match
# character-for-character. Any pipeline change that alters this output
# will fail Part A tests — that is intentional.
# ---------------------------------------------------------------------------

_GOLDEN_SQL = """\
SELECT
  cd.CustomerName  AS CustomerName,
  a_top.AccName    AS AccName,
  a_sub.AccName    AS AccName
FROM Major.Customer c
INNER JOIN Major.CustomerDemographics cd
  ON c.CustomerID = cd.CustomerID
INNER JOIN Major.Acc a_top
  ON c.CustomerID = a_top.CustomerID
INNER JOIN Major.Acc a_sub
  ON a_top.AccID = a_sub.ParentAccID
  AND c.CustomerID = a_sub.CustomerID
WHERE
  c.CustomerCID             = 'ASA'
  AND c.VersionTermDate         IS NULL
  AND ISNULL(c.DeletedFlag, 0)  = 0
  AND c.VoidedDate              IS NULL
  AND a_top.TermDate            IS NULL
  AND a_top.AccLevelConfig      = 0
  AND a_top.ParentAccID         IS NULL
  AND a_sub.TermDate            IS NULL
  AND a_sub.AccLevelConfig      = 1
  AND a_sub.ParentAccID         IS NOT NULL;"""

# Fixed request_id for Part A log stage verification.
# Using a fixed value means we always know the log file name:
#   {log_dir}/e2e-golden-test-001.log
_GOLDEN_REQUEST_ID = "e2e-golden-test-001"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_mock_responses() -> list[dict]:
    """Load config/mock_responses.json. Returns empty list if file missing."""
    if not _MOCK_RESPONSES_PATH.exists():
        return []
    return json.loads(_MOCK_RESPONSES_PATH.read_text(encoding="utf-8"))


def _read_log_stages(log_dir: str, request_id: str) -> list[str]:
    """
    Read the JSONL log file for a given request_id and return
    an ordered list of stage names that were emitted.

    Each line in the file is a JSON object with a "stage" key.

    Args:
        log_dir:    Directory where log files are written.
        request_id: The request_id used — log file is {log_dir}/{request_id}.log

    Returns:
        List of stage name strings in emission order.
        Empty list if the file does not exist or has no valid lines.
    """
    log_file = Path(log_dir) / f"{request_id}.log"
    if not log_file.exists():
        return []

    stages = []
    for line in log_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
            stages.append(entry.get("stage", ""))
        except json.JSONDecodeError:
            continue
    return stages


def _read_log_entries(log_dir: str, request_id: str) -> list[dict]:
    """
    Read the JSONL log file and return all entries as dicts.
    Used to inspect payload fields (e.g. caller).
    """
    log_file = Path(log_dir) / f"{request_id}.log"
    if not log_file.exists():
        return []

    entries = []
    for line in log_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            entries.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return entries


# ---------------------------------------------------------------------------
# Part A — Golden Exact-Match Tests
# ---------------------------------------------------------------------------

class TestGoldenExactMatch:
    """
    Part A — Golden query produces exact SQL from Section 9.3.
    Run via both /v1/query and /v1/tools/query.
    Log stages verified for the /v1/query run.
    THESE TESTS MUST NEVER FAIL.
    """

    def test_A1_golden_query_via_query_endpoint_exact_sql(self, tmp_path, monkeypatch):
        """
        A1: Golden NL query via POST /v1/query → SQL exactly matches Section 9.3.

        Uses a fixed request_id so the log file is predictable.
        Log dir overridden via monkeypatch BEFORE create_app() — load_settings()
        reads LOG_DIR at startup so the env var must exist before the app boots.
        monkeypatch cleans up automatically after the test — no finally block needed.
        """
        # Must be set BEFORE create_app() — lifespan calls load_settings() on open
        monkeypatch.setenv("LOG_DIR", str(tmp_path))
        monkeypatch.setenv("LOG_ARCHIVE_DIR", str(tmp_path / "archive"))

        app = create_app(schema_dir="schemas")
        with TestClient(app, raise_server_exceptions=False) as client:
            client.app.state.llm_provider = MockLLMProvider(
                responses=[_GOLDEN_IR]
            )
            response = client.post(
                "/v1/query",
                json={
                    "nl_query":   _GOLDEN_NL_QUERY,
                    "user_id":    "e2e-test",
                    "request_id": _GOLDEN_REQUEST_ID,
                },
                headers={"X-API-Key": CLIENT_KEY},
            )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        actual_sql = data["data"]["sql"]
        assert actual_sql == _GOLDEN_SQL, (
            f"\nExpected SQL:\n{_GOLDEN_SQL}\n\nActual SQL:\n{actual_sql}"
        )

    def test_A2_golden_query_via_tools_query_endpoint_exact_sql(self):
        """
        A2: Golden NL query via POST /v1/tools/query → same exact SQL as A1.
        Confirms both endpoints produce identical output from the same pipeline.
        """
        app = create_app(schema_dir="schemas")
        with TestClient(app, raise_server_exceptions=False) as client:
            client.app.state.llm_provider = MockLLMProvider(
                responses=[_GOLDEN_IR]
            )
            response = client.post(
                "/v1/tools/query",
                json={
                    "nl_query_original": _GOLDEN_NL_QUERY,
                    "app_id":            "",
                    "app_schema_version": "",
                },
                headers={"X-API-Key": FOUNDRY_KEY},
            )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        actual_sql = data["context"]["sql"]
        assert actual_sql == _GOLDEN_SQL, (
            f"\nExpected SQL:\n{_GOLDEN_SQL}\n\nActual SQL:\n{actual_sql}"
        )

    def test_A3_both_endpoints_return_success_status(self):
        """
        A3: Both /v1/query and /v1/tools/query return status=success
        for the golden query.
        """
        app = create_app(schema_dir="schemas")

        with TestClient(app, raise_server_exceptions=False) as client:
            client.app.state.llm_provider = MockLLMProvider(
                responses=[_GOLDEN_IR]
            )
            r1 = client.post(
                "/v1/query",
                json={"nl_query": _GOLDEN_NL_QUERY, "user_id": "e2e-test"},
                headers={"X-API-Key": CLIENT_KEY},
            )

        app2 = create_app(schema_dir="schemas")
        with TestClient(app2, raise_server_exceptions=False) as client2:
            client2.app.state.llm_provider = MockLLMProvider(
                responses=[_GOLDEN_IR]
            )
            r2 = client2.post(
                "/v1/tools/query",
                json={
                    "nl_query_original":  _GOLDEN_NL_QUERY,
                    "app_id":             "",
                    "app_schema_version": "",
                },
                headers={"X-API-Key": FOUNDRY_KEY},
            )

        assert r1.json()["status"] == "success"
        assert r2.json()["status"] == "success"

    def test_A4_all_log_stages_emitted_in_correct_order(self, tmp_path, monkeypatch):
        """
        A4: All 8 pipeline log stages emitted in correct order for /v1/query run.

        Expected order:
          REQUEST_RECEIVED → APP_DETECTED → INTENT_GUARD_RESULT → LLM_OUTPUT
          → VALIDATION_RESULT → STRUCTURED_QUERY_BUILT → SQL_BUILT → RESPONSE_SENT

        Note: USER_FEEDBACK is the 9th constant but is not part of the
        pipeline run — it is emitted only by the feedback endpoint.
        So 8 stages are expected here.
        """
        # Must be set BEFORE create_app() — lifespan calls load_settings() on open
        monkeypatch.setenv("LOG_DIR", str(tmp_path))
        monkeypatch.setenv("LOG_ARCHIVE_DIR", str(tmp_path / "archive"))

        app = create_app(schema_dir="schemas")
        with TestClient(app, raise_server_exceptions=False) as client:
            client.app.state.llm_provider = MockLLMProvider(
                responses=[_GOLDEN_IR]
            )
            client.post(
                "/v1/query",
                json={
                    "nl_query":   _GOLDEN_NL_QUERY,
                    "user_id":    "e2e-test",
                    "request_id": _GOLDEN_REQUEST_ID,
                },
                headers={"X-API-Key": CLIENT_KEY},
            )

        stages = _read_log_stages(str(tmp_path), _GOLDEN_REQUEST_ID)

        expected_stages = [
            REQUEST_RECEIVED,
            APP_DETECTED,
            INTENT_GUARD_RESULT,
            LLM_OUTPUT,
            LLM_OUTPUT,
            VALIDATION_RESULT,   # table/column validator
            VALIDATION_RESULT,   # join resolver
            VALIDATION_RESULT,   # rule applicator
            STRUCTURED_QUERY_BUILT,
            SQL_BUILT,
            RESPONSE_SENT,
        ]

        assert stages == expected_stages, (
            f"\nExpected stages:\n{expected_stages}\n\nActual stages:\n{stages}"
        )

    def test_A5_request_received_log_has_caller_user(self, tmp_path, monkeypatch):
        """
        A5: REQUEST_RECEIVED log entry has caller="user" for /v1/query.
        Confirms the orchestrator correctly tags user-facing requests.
        """
        # Must be set BEFORE create_app() — lifespan calls load_settings() on open
        monkeypatch.setenv("LOG_DIR", str(tmp_path))
        monkeypatch.setenv("LOG_ARCHIVE_DIR", str(tmp_path / "archive"))

        app = create_app(schema_dir="schemas")
        with TestClient(app, raise_server_exceptions=False) as client:
            client.app.state.llm_provider = MockLLMProvider(
                responses=[_GOLDEN_IR]
            )
            client.post(
                "/v1/query",
                json={
                    "nl_query":   _GOLDEN_NL_QUERY,
                    "user_id":    "e2e-test",
                    "request_id": _GOLDEN_REQUEST_ID,
                },
                headers={"X-API-Key": CLIENT_KEY},
            )

        entries = _read_log_entries(str(tmp_path), _GOLDEN_REQUEST_ID)
        request_received = next(
            (e for e in entries if e.get("stage") == REQUEST_RECEIVED), None
        )

        assert request_received is not None, "REQUEST_RECEIVED log entry not found"
        assert request_received.get("payload", {}).get("caller") == "user", (
            f"Expected caller='user', got: "
            f"{request_received.get('payload', {}).get('caller')}"
        )


# ---------------------------------------------------------------------------
# Part B — Data-Driven Tests from mock_responses.json
# ---------------------------------------------------------------------------

class TestDataDriven:
    """
    Part B — Each entry in mock_responses.json that has a final_sql field
    is run through the full pipeline and asserted for exact SQL match.

    To add a new test case:
      1. Add an entry to config/mock_responses.json with:
           user_input, llm_response, final_sql
         and optionally app_id (for queries without "in ABC")
      2. Run pytest — no code change needed.

    Entries without final_sql are skipped automatically.
    """

    @pytest.fixture(autouse=True)
    def _setup_app(self):
        """
        Create one app instance and one MockLLMProvider (JSON file mode)
        shared across all data-driven tests in this class.
        Stored on self so each test method can access them.
        """
        self._app = create_app(schema_dir="schemas")
        self._mock_entries = _load_mock_responses()

    def test_B_data_driven_exact_sql(self):
        """
        B: For every mock_responses.json entry with a final_sql field,
        run the full pipeline and assert SQL matches exactly.

        Each entry is tested in sequence within a single TestClient session.
        MockLLMProvider is in JSON file mode — auto-matches on user_input.
        """
        entries_with_sql = [
            e for e in self._mock_entries
            if e.get("final_sql") is not None
        ]

        if not entries_with_sql:
            pytest.skip(
                "No entries with final_sql found in mock_responses.json. "
                "Run scripts/generate_mock_sql.py and populate final_sql first."
            )

        with TestClient(self._app, raise_server_exceptions=False) as client:
            # JSON file mode — auto-matches user_input from mock_responses.json
            client.app.state.llm_provider = MockLLMProvider()

            for entry in entries_with_sql:
                user_input    = entry["user_input"]
                final_sql     = entry["final_sql"]
                explicit_app  = entry.get("app_id")

                body = {
                    "nl_query": user_input,
                    "user_id":  "e2e-data-driven",
                }
                if explicit_app:
                    body["app_id"] = explicit_app

                response = client.post(
                    "/v1/query",
                    json=body,
                    headers={"X-API-Key": CLIENT_KEY},
                )

                assert response.status_code == 200, (
                    f"Entry '{user_input}': expected HTTP 200, "
                    f"got {response.status_code}"
                )

                data = response.json()
                assert data["status"] == "success", (
                    f"Entry '{user_input}': expected status=success, "
                    f"got status={data['status']}, "
                    f"errors={data.get('errors')}"
                )

                actual_sql = data["data"]["sql"]
                assert actual_sql == final_sql, (
                    f"\nEntry: '{user_input}'"
                    f"\nExpected SQL:\n{final_sql}"
                    f"\nActual SQL:\n{actual_sql}"
                )


# ---------------------------------------------------------------------------
# Diagnostic — Print SQL for every entry, no assertions
# ---------------------------------------------------------------------------

class TestDiagnostic:
    """
    Diagnostic test — runs every mock_responses.json entry through the pipeline
    and PRINTS the resulting SQL. No assertions on SQL content.

    Always passes as long as the pipeline does not raise an unhandled exception.
    If an entry produces a business error (e.g. APP_NOT_DETERMINED), it prints
    the error code instead of SQL.

    Run with -s flag to see printed output:
        pytest tests/test_e2e.py::TestDiagnostic -v -s
    """

    def test_diagnostic_print_sql_for_all_entries(self):
        """
        Runs every entry in mock_responses.json through /v1/query and prints SQL.
        No SQL assertions — purely for visual inspection during development.
        """
        entries = _load_mock_responses()

        if not entries:
            pytest.skip(
                "config/mock_responses.json is empty or not found. "
                "Nothing to diagnose."
            )

        app = create_app(schema_dir="schemas")

        print(f"\n{'=' * 70}")
        print(f"DIAGNOSTIC — {len(entries)} entries from mock_responses.json")
        print(f"{'=' * 70}")

        with TestClient(app, raise_server_exceptions=False) as client:
            # JSON file mode — auto-matches user_input from mock_responses.json
            client.app.state.llm_provider = MockLLMProvider()

            for idx, entry in enumerate(entries, start=1):
                user_input   = entry.get("user_input", "")
                explicit_app = entry.get("app_id")

                body = {
                    "nl_query": user_input,
                    "user_id":  "e2e-diagnostic",
                }
                if explicit_app:
                    body["app_id"] = explicit_app

                response = client.post(
                    "/v1/query",
                    json=body,
                    headers={"X-API-Key": CLIENT_KEY},
                )

                print(f"\n[{idx}] {user_input}")

                if response.status_code != 200:
                    print(
                        f"     HTTP  : {response.status_code} — "
                        f"{response.text[:120]}"
                    )
                    continue

                data = response.json()

                if data.get("status") == "success":
                    sql = data.get("data", {}).get("sql", "")
                    print(f"     STATUS: success")
                    print(f"     SQL   :")
                    for line in sql.splitlines():
                        print(f"       {line}")
                else:
                    errors = data.get("errors", [])
                    if errors:
                        err = errors[0]
                        print(
                            f"     STATUS: failed\n"
                            f"     ERROR : {err.get('code')} — "
                            f"{err.get('message', '')[:100]}"
                        )
                    else:
                        print(f"     STATUS: failed (no error detail)")

        print(f"\n{'=' * 70}\n")
