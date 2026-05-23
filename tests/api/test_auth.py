# tests/api/test_auth.py
# V0 - Initial implementation
#
# Tests for API key authentication (Story 2.4).
#
# APPROACH — minimal dummy routes:
#   POST /v1/query and POST /v1/tools/* do not exist yet (later stories).
#   We mount two minimal dummy routes on a test-only FastAPI app that use
#   the real require_client_key and require_foundry_key dependencies.
#   This tests the auth logic in isolation without depending on route handlers
#   that have not been built yet.
#
# TEST GROUPS:
#   A — Client key on /v1/query        (A1-A5)
#   B — Foundry key on /v1/tools/test  (B1-B5)
#   C — Exempt routes /health /ready   (C1-C3)
#   D — Edge cases                     (D1-D2)

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from src.api.auth import require_client_key, require_foundry_key

# ---------------------------------------------------------------------------
# Test app factory
# ---------------------------------------------------------------------------
# We build a minimal FastAPI app with:
#   - Two dummy protected routes using the real auth dependencies
#   - Two exempt routes (/health, /ready) with no auth
#   - settings injected into app.state so auth.py can read the keys
#
# We use a simple namespace object to simulate app.state.settings
# rather than running the full lifespan startup — auth only needs the keys.
# ---------------------------------------------------------------------------

class _FakeSettings:
    """Minimal settings object with only the fields auth.py needs."""
    def __init__(self, client_api_key, foundry_api_key):
        self.client_api_key = client_api_key
        self.foundry_api_key = foundry_api_key


def make_test_app(client_key: str | None, foundry_key: str | None) -> FastAPI:
    """
    Build a minimal FastAPI app with dummy protected routes.

    Args:
        client_key:  Value to store as settings.client_api_key in app.state.
        foundry_key: Value to store as settings.foundry_api_key in app.state.
    """
    app = FastAPI()
    app.state.settings = _FakeSettings(
        client_api_key=client_key,
        foundry_api_key=foundry_key,
    )

    @app.post("/v1/query")
    def dummy_query(_auth: None = Depends(require_client_key)):
        """Dummy route — returns 200 if auth passes."""
        return {"ok": True}

    @app.post("/v1/tools/test")
    def dummy_tool(_auth: None = Depends(require_foundry_key)):
        """Dummy route — returns 200 if auth passes."""
        return {"ok": True}

    @app.get("/health")
    def dummy_health():
        """Exempt — no auth dependency."""
        return {"status": "ok"}

    @app.get("/ready")
    def dummy_ready():
        """Exempt — no auth dependency."""
        return {"status": "ok"}

    return app


# ---------------------------------------------------------------------------
# Shared test keys — match conftest.py values
# ---------------------------------------------------------------------------

CLIENT_KEY = "test-client-key-12345"
FOUNDRY_KEY = "test-foundry-key-67890"
WRONG_KEY = "wrong-key-000"


# ---------------------------------------------------------------------------
# Group A — Client key on POST /v1/query
# ---------------------------------------------------------------------------

class TestClientKeyAuth:

    @pytest.fixture(autouse=True)
    def client(self):
        app = make_test_app(client_key=CLIENT_KEY, foundry_key=FOUNDRY_KEY)
        self._client = TestClient(app, raise_server_exceptions=True)

    def test_a1_valid_client_key_returns_200(self):
        """A1: Valid CLIENT_API_KEY in X-API-Key header → 200 OK."""
        resp = self._client.post("/v1/query", headers={"X-API-Key": CLIENT_KEY})
        assert resp.status_code == 200

    def test_a2_wrong_key_returns_401(self):
        """A2: Wrong key value → 401 Unauthorized."""
        resp = self._client.post("/v1/query", headers={"X-API-Key": WRONG_KEY})
        assert resp.status_code == 401
        assert resp.json() == {"detail": "Unauthorized"}

    def test_a3_missing_header_returns_401(self):
        """A3: X-API-Key header absent entirely → 401 Unauthorized."""
        resp = self._client.post("/v1/query")
        assert resp.status_code == 401
        assert resp.json() == {"detail": "Unauthorized"}

    def test_a4_empty_header_returns_401(self):
        """A4: X-API-Key header present but empty string → 401 Unauthorized."""
        resp = self._client.post("/v1/query", headers={"X-API-Key": ""})
        assert resp.status_code == 401
        assert resp.json() == {"detail": "Unauthorized"}

    def test_a5_foundry_key_on_query_route_returns_401(self):
        """A5: FOUNDRY_API_KEY used on /v1/query → 401 (wrong key for this route)."""
        resp = self._client.post("/v1/query", headers={"X-API-Key": FOUNDRY_KEY})
        assert resp.status_code == 401
        assert resp.json() == {"detail": "Unauthorized"}


# ---------------------------------------------------------------------------
# Group B — Foundry key on POST /v1/tools/test
# ---------------------------------------------------------------------------

class TestFoundryKeyAuth:

    @pytest.fixture(autouse=True)
    def client(self):
        app = make_test_app(client_key=CLIENT_KEY, foundry_key=FOUNDRY_KEY)
        self._client = TestClient(app, raise_server_exceptions=True)

    def test_b1_valid_foundry_key_returns_200(self):
        """B1: Valid FOUNDRY_API_KEY in X-API-Key header → 200 OK."""
        resp = self._client.post("/v1/tools/test", headers={"X-API-Key": FOUNDRY_KEY})
        assert resp.status_code == 200

    def test_b2_wrong_key_returns_401(self):
        """B2: Wrong key value → 401 Unauthorized."""
        resp = self._client.post("/v1/tools/test", headers={"X-API-Key": WRONG_KEY})
        assert resp.status_code == 401
        assert resp.json() == {"detail": "Unauthorized"}

    def test_b3_missing_header_returns_401(self):
        """B3: X-API-Key header absent entirely → 401 Unauthorized."""
        resp = self._client.post("/v1/tools/test")
        assert resp.status_code == 401
        assert resp.json() == {"detail": "Unauthorized"}

    def test_b4_empty_header_returns_401(self):
        """B4: X-API-Key header present but empty string → 401 Unauthorized."""
        resp = self._client.post("/v1/tools/test", headers={"X-API-Key": ""})
        assert resp.status_code == 401
        assert resp.json() == {"detail": "Unauthorized"}

    def test_b5_client_key_on_tools_route_returns_401(self):
        """B5: CLIENT_API_KEY used on /v1/tools/* → 401 (wrong key for this route)."""
        resp = self._client.post("/v1/tools/test", headers={"X-API-Key": CLIENT_KEY})
        assert resp.status_code == 401
        assert resp.json() == {"detail": "Unauthorized"}


# ---------------------------------------------------------------------------
# Group C — Exempt routes (/health, /ready)
# ---------------------------------------------------------------------------

class TestExemptRoutes:

    @pytest.fixture(autouse=True)
    def client(self):
        app = make_test_app(client_key=CLIENT_KEY, foundry_key=FOUNDRY_KEY)
        self._client = TestClient(app, raise_server_exceptions=True)

    def test_c1_health_with_no_key_returns_200(self):
        """C1: GET /health with no X-API-Key → 200 OK (exempt)."""
        resp = self._client.get("/health")
        assert resp.status_code == 200

    def test_c2_ready_with_no_key_returns_200(self):
        """C2: GET /ready with no X-API-Key → 200 OK (exempt)."""
        resp = self._client.get("/ready")
        assert resp.status_code == 200

    def test_c3_health_with_random_key_returns_200(self):
        """C3: GET /health with any X-API-Key value → 200 OK (key ignored on exempt routes)."""
        resp = self._client.get("/health", headers={"X-API-Key": "random-key-ignored"})
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Group D — Edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:

    def test_d1_key_with_whitespace_returns_401(self):
        """D1: Key with leading/trailing whitespace → 401 (exact match only, no trimming)."""
        app = make_test_app(client_key=CLIENT_KEY, foundry_key=FOUNDRY_KEY)
        client = TestClient(app, raise_server_exceptions=True)
        # Key with spaces around it — should NOT match even though base value matches
        resp = client.post("/v1/query", headers={"X-API-Key": f"  {CLIENT_KEY}  "})
        assert resp.status_code == 401
        assert resp.json() == {"detail": "Unauthorized"}

    def test_d2_unconfigured_key_in_dev_returns_401(self):
        """
        D2: Key not configured in settings (None) — dev environment.
        Auth always returns 401 when key is not set.
        Prod startup validation (blocking at startup) is tested via settings tests.
        """
        # client_api_key is None — simulates dev with missing CLIENT_API_KEY in .env
        app = make_test_app(client_key=None, foundry_key=FOUNDRY_KEY)
        client = TestClient(app, raise_server_exceptions=True)
        # Even sending the foundry key or any key → 401 on query route
        resp = client.post("/v1/query", headers={"X-API-Key": CLIENT_KEY})
        assert resp.status_code == 401
        assert resp.json() == {"detail": "Unauthorized"}
