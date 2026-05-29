# tests/conftest.py
# V0 - Initial implementation
#
# Root-level shared test configuration.
# Applies to ALL tests under tests/ — including test_e2e.py at root level.
#
# WHY THIS FILE EXISTS:
#   tests/api/conftest.py injects env vars for tests/api/** only.
#   tests/test_e2e.py lives at tests/ root — outside tests/api/ — so it never
#   picked up tests/api/conftest.py. Every request returned 401 because
#   CLIENT_API_KEY and FOUNDRY_API_KEY were never set.
#
#   This root conftest.py uses autouse=True so env vars are injected
#   for every test in the project, regardless of subfolder.
#   tests/api/conftest.py can remain as-is — monkeypatch is idempotent,
#   setting the same value twice has no side effect.

import pytest


@pytest.fixture(autouse=True)
def set_test_env_vars(monkeypatch):
    """
    Inject required environment variables for every test in the project.

    These mirror what a developer's .env file contains in dev mode.
    monkeypatch cleans up after each test — no leakage between tests.
    """
    monkeypatch.setenv("ENV", "dev")
    monkeypatch.setenv("CLIENT_API_KEY", "test-client-key-12345")
    monkeypatch.setenv("FOUNDRY_API_KEY", "test-foundry-key-67890")
    monkeypatch.setenv("LLM_PROVIDER", "mock")
