# tests/api/conftest.py
# V0 - Initial implementation
#
# Shared test configuration for all API tests.
#
# WHY THIS FILE EXISTS:
#   load_settings() reads ENV, API_KEY, LLM_PROVIDER from environment variables.
#   On the developer's machine, these come from a .env file in the project root.
#   But during tests, we cannot rely on .env existing — the test environment must
#   be self-contained.
#
#   This conftest.py uses pytest's monkeypatch (via autouse=True) to inject the
#   required environment variables BEFORE every test in this folder runs.
#   This means tests work on any machine, with or without a .env file.
#
# autouse=True means the fixture applies automatically to every test —
# no need to add it explicitly to each test function.

import os
import pytest


@pytest.fixture(autouse=True)
def set_test_env_vars(monkeypatch):
    """
    Inject required environment variables for every test in tests/api/.

    These mirror what a developer's .env file would contain in dev mode.
    Using monkeypatch ensures the variables are cleaned up after each test —
    no leakage between tests.
    """
    monkeypatch.setenv("ENV", "dev")
    monkeypatch.setenv("API_KEY", "test-api-key-12345")
    monkeypatch.setenv("LLM_PROVIDER", "mock")
