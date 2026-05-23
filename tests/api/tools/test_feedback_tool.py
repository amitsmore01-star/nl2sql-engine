# tests/api/tools/test_feedback_tool.py
# V0 - Initial implementation — TODO Phase 3 placeholder test

"""
Tests for POST /v1/tools/feedback.

Phase 1: endpoint exists but returns 501 Not Implemented.
Phase 3: replace this file with full feedback submission tests.
"""

import pytest
from fastapi.testclient import TestClient

from src.api.app import create_app


class TestFeedbackToolPlaceholder:
    """Confirms the placeholder endpoint exists and returns 501."""

    @pytest.fixture
    def client(self, tmp_path, monkeypatch):
        """Minimal test client — schema dir not needed for a 501 response."""
        monkeypatch.setenv("ENV", "dev")
        monkeypatch.setenv("CLIENT_API_KEY", "test-client-key")
        monkeypatch.setenv("FOUNDRY_API_KEY", "test-foundry-key")
        monkeypatch.setenv("LLM_PROVIDER", "mock")

        schema_dir = tmp_path / "schemas"
        schema_dir.mkdir()

        with TestClient(create_app(schema_dir=str(schema_dir))) as c:
            yield c

    def test_returns_501_not_implemented(self, client):
        """POST /v1/tools/feedback → 501 in Phase 1."""
        response = client.post(
            "/v1/tools/feedback",
            headers={"X-API-Key": "test-foundry-key"},
            json={},
        )
        assert response.status_code == 501

    def test_response_body_mentions_phase_3(self, client):
        """Response message explains this is a Phase 3 feature."""
        response = client.post(
            "/v1/tools/feedback",
            headers={"X-API-Key": "test-foundry-key"},
            json={},
        )
        body = response.json()
        assert "Phase 3" in body.get("message", "")
