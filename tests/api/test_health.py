# tests/api/test_health.py
# V0 - Initial implementation
#
# Tests for GET /health and GET /ready endpoints.
#
# Key techniques used:
#   - TestClient: calls endpoints without running a real server
#   - tmp_path:   pytest fixture that creates a real temporary directory
#                 cleaned up after each test automatically
#   - create_app(schema_dir=...): factory override so tests never
#                 touch the real schemas/ folder on disk
#   - conftest.py: sets ENV/API_KEY/LLM_PROVIDER env vars automatically
#   - No real API calls. No permanent files created.
#
# IMPORTANT — why we use "with TestClient(...) as client":
#   FastAPI's lifespan startup code ONLY runs when TestClient is used
#   as a context manager. Without "with", startup never fires and
#   app.state values stay at their uninitialised defaults.
#   Every test that needs startup to have run uses this pattern.

import json
import os
import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from src.api.app import create_app

# ---------------------------------------------------------------------------
# Path to the real ABC_app.json — copied into temp dirs during tests
# ---------------------------------------------------------------------------
REAL_SCHEMA_FILE = Path(__file__).parent.parent.parent / "schemas" / "ABC_app.json"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_schema_dir(tmp_path: Path, valid: bool = True) -> Path:
    """
    Create a temp schema directory for tests.

    Args:
        tmp_path: pytest-provided temp directory (unique per test).
        valid:    True  → copies real ABC_app.json (valid schema).
                  False → writes broken JSON (triggers load failure).

    Returns:
        Path to the temp schema directory.
    """
    schema_dir = tmp_path / "schemas"
    schema_dir.mkdir(parents=True, exist_ok=True)

    if valid:
        shutil.copy(REAL_SCHEMA_FILE, schema_dir / "ABC_app.json")
    else:
        (schema_dir / "bad_schema.json").write_text(
            "{ not valid json }", encoding="utf-8"
        )
    return schema_dir


# ===========================================================================
# Group 1 — GET /health  (Liveness)
# ===========================================================================

class TestHealthLiveness:
    """H1–H5, E1, E5: Basic liveness checks."""

    def test_h1_returns_200(self, tmp_path):
        """H1 — GET /health returns 200."""
        with TestClient(create_app(schema_dir=_make_schema_dir(tmp_path)),
                        raise_server_exceptions=False) as client:
            response = client.get("/health")
        assert response.status_code == 200

    def test_h2_response_has_status_ok(self, tmp_path):
        """H2 — Response body contains status: ok."""
        with TestClient(create_app(schema_dir=_make_schema_dir(tmp_path)),
                        raise_server_exceptions=False) as client:
            response = client.get("/health")
        assert response.json()["status"] == "ok"

    def test_h3_response_has_timestamp_utc(self, tmp_path):
        """H3 — Response contains timestamp_utc field."""
        with TestClient(create_app(schema_dir=_make_schema_dir(tmp_path)),
                        raise_server_exceptions=False) as client:
            response = client.get("/health")
        assert "timestamp_utc" in response.json()

    def test_h3b_timestamp_is_valid_utc_format(self, tmp_path):
        """H3b — timestamp_utc is ISO 8601 ending in Z."""
        with TestClient(create_app(schema_dir=_make_schema_dir(tmp_path)),
                        raise_server_exceptions=False) as client:
            response = client.get("/health")
        ts = response.json()["timestamp_utc"]
        assert isinstance(ts, str)
        assert ts.endswith("Z"), f"Expected timestamp to end with Z, got: {ts}"
        from datetime import datetime
        datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ")  # raises if format wrong

    def test_h4_no_auth_header_needed(self, tmp_path):
        """H4 — /health works without any API key header."""
        with TestClient(create_app(schema_dir=_make_schema_dir(tmp_path)),
                        raise_server_exceptions=False) as client:
            response = client.get("/health", headers={})
        assert response.status_code == 200

    def test_e1_returns_json_content_type(self, tmp_path):
        """E1 — /health returns application/json content type."""
        with TestClient(create_app(schema_dir=_make_schema_dir(tmp_path)),
                        raise_server_exceptions=False) as client:
            response = client.get("/health")
        assert "application/json" in response.headers["content-type"]

    def test_e5_returns_200_not_201(self, tmp_path):
        """E5 — /health returns exactly 200, not 201."""
        with TestClient(create_app(schema_dir=_make_schema_dir(tmp_path)),
                        raise_server_exceptions=False) as client:
            response = client.get("/health")
        assert response.status_code == 200


# ===========================================================================
# Group 2 — GET /ready  Happy Path (all checks pass)
# ===========================================================================

class TestReadyHappyPath:
    """R1–R7, E2, E4: All readiness checks pass → 200."""

    @pytest.fixture
    def ready_response(self, tmp_path):
        """
        Shared fixture — runs the full happy path startup and returns
        the /ready response. Used by all tests in this group.

        The 'with' block triggers lifespan startup. The response is
        captured inside and returned for assertions outside.
        """
        with TestClient(
            create_app(schema_dir=_make_schema_dir(tmp_path, valid=True)),
            raise_server_exceptions=False
        ) as client:
            return client.get("/ready")

    def test_r1_returns_200(self, ready_response):
        """R1 — GET /ready returns 200 when all checks pass."""
        assert ready_response.status_code == 200

    def test_r1_status_is_ready(self, ready_response):
        """R1 — Response body status is 'ready'."""
        assert ready_response.json()["status"] == "ready"

    def test_r2_all_four_check_keys_present(self, ready_response):
        """R2 — Response contains all 4 expected check keys."""
        checks = ready_response.json()["checks"]
        assert "schemas_loaded" in checks
        assert "schemas_valid" in checks
        assert "llm_provider" in checks
        assert "log_dir_writable" in checks

    def test_r3_all_checks_status_ok(self, ready_response):
        """R3 — Every check shows status: ok."""
        checks = ready_response.json()["checks"]
        for check_name, check_data in checks.items():
            assert check_data["status"] == "ok", (
                f"Check '{check_name}' expected 'ok', got: {check_data}"
            )

    def test_r4_schemas_loaded_includes_app_count(self, ready_response):
        """R4 — schemas_loaded includes app_count = 1 for ABC schema."""
        schemas_loaded = ready_response.json()["checks"]["schemas_loaded"]
        assert "app_count" in schemas_loaded
        assert schemas_loaded["app_count"] == 1

    def test_r5_llm_provider_includes_provider_name(self, ready_response):
        """R5 — llm_provider check includes provider name (mock in dev)."""
        llm_check = ready_response.json()["checks"]["llm_provider"]
        assert "provider" in llm_check
        assert llm_check["provider"] == "mock"

    def test_r6_response_has_timestamp_utc(self, ready_response):
        """R6 — /ready response contains valid timestamp_utc."""
        body = ready_response.json()
        assert "timestamp_utc" in body
        ts = body["timestamp_utc"]
        assert ts.endswith("Z")
        from datetime import datetime
        datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ")

    def test_r7_no_auth_header_needed(self, tmp_path):
        """R7 — /ready works without any API key header."""
        with TestClient(
            create_app(schema_dir=_make_schema_dir(tmp_path, valid=True)),
            raise_server_exceptions=False
        ) as client:
            response = client.get("/ready", headers={})
        assert response.status_code == 200

    def test_e2_returns_json_content_type(self, ready_response):
        """E2 — /ready returns application/json content type."""
        assert "application/json" in ready_response.headers["content-type"]

    def test_e4_returns_200_not_201(self, ready_response):
        """E4 — /ready returns exactly 200 on success."""
        assert ready_response.status_code == 200


# ===========================================================================
# Group 3 — GET /ready  Failure Path (503)
# ===========================================================================

class TestReadyFailures:
    """F1–F7: Individual check failures return 503."""

    def test_f1_schema_load_fails_returns_503(self, tmp_path):
        """F1 — Schema dir missing at startup → /ready returns 503."""
        missing_dir = tmp_path / "does_not_exist"
        with TestClient(create_app(schema_dir=missing_dir),
                        raise_server_exceptions=False) as client:
            response = client.get("/ready")
        assert response.status_code == 503

    def test_f1_status_is_not_ready(self, tmp_path):
        """F1 — status field is 'not_ready' when schema load fails."""
        missing_dir = tmp_path / "does_not_exist"
        with TestClient(create_app(schema_dir=missing_dir),
                        raise_server_exceptions=False) as client:
            response = client.get("/ready")
        assert response.json()["status"] == "not_ready"

    def test_f2_failed_check_shows_error_status(self, tmp_path):
        """F2 — schemas_loaded shows status: error when load fails."""
        missing_dir = tmp_path / "does_not_exist"
        with TestClient(create_app(schema_dir=missing_dir),
                        raise_server_exceptions=False) as client:
            response = client.get("/ready")
        assert response.json()["checks"]["schemas_loaded"]["status"] == "error"

    def test_f3_failed_check_includes_message(self, tmp_path):
        """F3 — schemas_loaded includes a non-empty message when load fails."""
        missing_dir = tmp_path / "does_not_exist"
        with TestClient(create_app(schema_dir=missing_dir),
                        raise_server_exceptions=False) as client:
            response = client.get("/ready")
        check = response.json()["checks"]["schemas_loaded"]
        assert "message" in check
        assert len(check["message"]) > 0

    def test_f4_schema_validation_fails_returns_503(self, tmp_path):
        """F4 — Schema loads but fails validator → 503."""
        schema_dir = tmp_path / "schemas"
        schema_dir.mkdir(parents=True, exist_ok=True)

        # Valid JSON structure but fails validator:
        # non-junction table with empty synonyms[]
        bad_schema = {
            "appId": "bad_app",
            "app_name": "Bad App",
            "version": "1.0",
            "appSynonyms": ["bad"],
            "description": "Test",
            "database_type": "SQL Server",
            "tables": [
                {
                    "name": "Major.SomeTable",
                    "display_name": "SomeTable",
                    "schema": "Major",
                    "synonyms": [],   # invalid — non-junction must have synonyms
                    "description": "A table",
                    "identifier": "SomeID",
                    "columns": [
                        {"name": "SomeID", "type": "INT", "key": "primary"}
                    ],
                    "relationships": []
                }
            ]
        }
        (schema_dir / "bad_app.json").write_text(
            json.dumps(bad_schema), encoding="utf-8"
        )

        with TestClient(create_app(schema_dir=schema_dir),
                        raise_server_exceptions=False) as client:
            response = client.get("/ready")

        assert response.status_code == 503
        assert response.json()["checks"]["schemas_valid"]["status"] == "error"

    def test_f5_log_dir_is_file_not_dir_returns_503(self, tmp_path):
        """F5 — Log dir path is a file (not a dir) → log_dir_writable fails → 503."""
        # Create a FILE where the log dir should be
        fake_log_path = tmp_path / "fakelogs"
        fake_log_path.write_text("I am a file, not a directory", encoding="utf-8")

        # Valid schema in a separate sub-path
        schema_dir = tmp_path / "sc" / "schemas"
        schema_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy(REAL_SCHEMA_FILE, schema_dir / "ABC_app.json")

        app = create_app(schema_dir=schema_dir)

        with TestClient(app, raise_server_exceptions=False) as client:
            # Startup succeeds — now override log_dir to point at the fake file
            app.state.settings.logging.log_dir = str(fake_log_path)
            response = client.get("/ready")

        assert response.status_code == 503
        assert response.json()["checks"]["log_dir_writable"]["status"] == "error"

    def test_f6_other_checks_still_present_when_schema_load_fails(self, tmp_path):
        """F6 — All 4 check keys present even when schema load fails."""
        missing_dir = tmp_path / "does_not_exist"
        with TestClient(create_app(schema_dir=missing_dir),
                        raise_server_exceptions=False) as client:
            response = client.get("/ready")
        checks = response.json()["checks"]
        assert "schemas_loaded" in checks
        assert "schemas_valid" in checks
        assert "llm_provider" in checks
        assert "log_dir_writable" in checks

    def test_f7_empty_llm_provider_returns_503(self, tmp_path):
        """F7 — Empty LLM provider string → llm_provider check fails → 503."""
        schema_dir = tmp_path / "sc" / "schemas"
        schema_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy(REAL_SCHEMA_FILE, schema_dir / "ABC_app.json")

        app = create_app(schema_dir=schema_dir)

        with TestClient(app, raise_server_exceptions=False) as client:
            # Startup succeeds — now blank out the provider
            app.state.settings.llm.provider = ""
            response = client.get("/ready")

        assert response.status_code == 503
        assert response.json()["checks"]["llm_provider"]["status"] == "error"


# ===========================================================================
# Group 4 — Edge Cases
# ===========================================================================

class TestEdgeCases:
    """E3, plus extra edge cases."""

    def test_e3_unknown_path_returns_404(self, tmp_path):
        """E3 — GET /nonexistent returns 404."""
        with TestClient(create_app(schema_dir=_make_schema_dir(tmp_path)),
                        raise_server_exceptions=False) as client:
            response = client.get("/nonexistent")
        assert response.status_code == 404

    def test_bad_json_file_causes_503(self, tmp_path):
        """Extra — A .json file with bad content → schema load failure → 503."""
        schema_dir = tmp_path / "schemas"
        schema_dir.mkdir(parents=True, exist_ok=True)
        (schema_dir / "broken.json").write_text("{ not valid json }", encoding="utf-8")

        with TestClient(create_app(schema_dir=schema_dir),
                        raise_server_exceptions=False) as client:
            response = client.get("/ready")
        assert response.status_code == 503
