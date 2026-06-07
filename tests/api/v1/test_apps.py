# tests/api/v1/test_apps.py
# V0 - Initial implementation
#
# Tests for GET /v1/apps — lists all loaded app schemas with versions.
#
# Test groups:
#   A — Auth (missing / wrong / foundry key / correct client key)
#   B — Success response content (apps list populated, correct data)
#   C — Response shape (envelope keys, status, errors)
#   D — Edge case (schema_repo None → structured 500, not a crash)
#
# Pattern mirrors test_query.py:
#   make_client() → create_app(schema_dir="schemas") → TestClient with
#   raise_server_exceptions=False so the global exception handler fires on D1.
#   VALID_KEY / WRONG_KEY / FOUNDRY_KEY match conftest-injected env vars.

from fastapi.testclient import TestClient

from src.api.app import create_app

# ---------------------------------------------------------------------------
# Shared test constants
# ---------------------------------------------------------------------------

VALID_KEY   = "test-client-key-12345"
WRONG_KEY   = "wrong-key"
FOUNDRY_KEY = "test-foundry-key-67890"


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def make_client(schema_dir: str = "schemas") -> TestClient:
    """
    Create a TestClient backed by the real Acme schema directory.
    raise_server_exceptions=False is required so that the global exception
    handler (middleware.py) can return a structured response for Group D.
    """
    app = create_app(schema_dir=schema_dir)
    return TestClient(app, raise_server_exceptions=False)


# ---------------------------------------------------------------------------
# Group A — Auth
# ---------------------------------------------------------------------------

class TestAuth:
    """Auth enforcement on GET /v1/apps — uses the CLIENT key (user-facing)."""

    def test_a1_missing_api_key_returns_401(self):
        """No X-API-Key header → 401 Unauthorized."""
        with make_client() as client:
            response = client.get("/v1/apps")
        assert response.status_code == 401

    def test_a2_wrong_api_key_returns_401(self):
        """Wrong X-API-Key value → 401 Unauthorized."""
        with make_client() as client:
            response = client.get(
                "/v1/apps",
                headers={"X-API-Key": WRONG_KEY},
            )
        assert response.status_code == 401

    def test_a3_foundry_key_rejected_on_user_endpoint(self):
        """
        Foundry key on a user-facing endpoint → 401.
        GET /v1/apps is protected by require_client_key, not require_foundry_key.
        """
        with make_client() as client:
            response = client.get(
                "/v1/apps",
                headers={"X-API-Key": FOUNDRY_KEY},
            )
        assert response.status_code == 401

    def test_a4_correct_client_key_is_not_blocked(self):
        """Correct client key → request is not rejected by auth."""
        with make_client() as client:
            response = client.get(
                "/v1/apps",
                headers={"X-API-Key": VALID_KEY},
            )
        assert response.status_code != 401


# ---------------------------------------------------------------------------
# Group B — Success response content
# ---------------------------------------------------------------------------

class TestSuccessContent:
    """Verify the apps list is correctly populated from the loaded schemas."""

    def test_b1_returns_200(self):
        """GET /v1/apps with valid auth → HTTP 200."""
        with make_client() as client:
            response = client.get(
                "/v1/apps",
                headers={"X-API-Key": VALID_KEY},
            )
        assert response.status_code == 200

    def test_b2_data_apps_is_non_empty_list(self):
        """data.apps contains at least one entry (Acme_app schema is loaded)."""
        with make_client() as client:
            response = client.get(
                "/v1/apps",
                headers={"X-API-Key": VALID_KEY},
            )
        data = response.json()
        assert "apps" in data["data"]
        assert isinstance(data["data"]["apps"], list)
        assert len(data["data"]["apps"]) >= 1

    def test_b3_each_app_entry_has_app_id_and_version(self):
        """Every entry in data.apps has both app_id and version fields."""
        with make_client() as client:
            response = client.get(
                "/v1/apps",
                headers={"X-API-Key": VALID_KEY},
            )
        apps = response.json()["data"]["apps"]
        for entry in apps:
            assert "app_id" in entry, f"Missing app_id in entry: {entry}"
            assert "version" in entry, f"Missing version in entry: {entry}"

    def test_b4_abc_app_present_with_correct_version(self):
        """
        Acme_app is in the list with version '1.0'.
        This is the real Acme_app.json loaded from the schemas/ directory.
        """
        with make_client() as client:
            response = client.get(
                "/v1/apps",
                headers={"X-API-Key": VALID_KEY},
            )
        apps = response.json()["data"]["apps"]
        abc = next((a for a in apps if a["app_id"] == "Acme_app"), None)
        assert abc is not None, "Acme_app not found in /v1/apps response"
        assert abc["version"] == "1.0"


# ---------------------------------------------------------------------------
# Group C — Response shape
# ---------------------------------------------------------------------------

class TestResponseShape:
    """The envelope must follow the project-wide convention."""

    def test_c1_status_is_success(self):
        """status == 'success' on a healthy response."""
        with make_client() as client:
            response = client.get(
                "/v1/apps",
                headers={"X-API-Key": VALID_KEY},
            )
        assert response.json()["status"] == "success"

    def test_c2_errors_is_empty_list(self):
        """errors == [] on a successful response."""
        with make_client() as client:
            response = client.get(
                "/v1/apps",
                headers={"X-API-Key": VALID_KEY},
            )
        assert response.json()["errors"] == []

    def test_c3_request_id_is_present_and_non_empty(self):
        """
        request_id is generated per call (no body to read one from).
        Must be a non-empty string.
        """
        with make_client() as client:
            response = client.get(
                "/v1/apps",
                headers={"X-API-Key": VALID_KEY},
            )
        request_id = response.json().get("request_id")
        assert request_id, "request_id must be present and non-empty"


# ---------------------------------------------------------------------------
# Group D — Edge case: broken startup
# ---------------------------------------------------------------------------

class TestBrokenStartup:
    """
    If app.state.schema_repo is None (startup failed), the endpoint must
    return a structured error response — not a raw Python crash.

    The global exception handler (middleware.py, Story 6.2) catches the
    RuntimeError raised by the endpoint and returns HTTP 500 INTERNAL_ERROR.
    """

    def test_d1_none_schema_repo_returns_500_not_crash(self):
        """
        Simulate broken startup: set app.state.schema_repo = None after
        the TestClient lifespan runs.
        Expect HTTP 500, status='failed', errors[0].code='INTERNAL_ERROR'.
        """
        app = create_app(schema_dir="schemas")
        with TestClient(app, raise_server_exceptions=False) as client:
            app.state.schema_repo = None
            response = client.get(
                "/v1/apps",
                headers={"X-API-Key": VALID_KEY},
            )
        assert response.status_code == 500
        data = response.json()
        assert data["status"] == "failed"
        assert len(data["errors"]) > 0
        assert data["errors"][0]["code"] == "INTERNAL_ERROR"
