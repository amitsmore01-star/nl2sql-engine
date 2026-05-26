# tests/validator/conftest.py
# V0 - Initial implementation
#
# Shared fixtures for all tests in tests/validator/.
#
# Fixtures provided:
#   abc_schema_repo   — SchemaRepository loaded with the real ABC_app.json schema.
#                       Used by all validator tests that need schema lookups.
#   test_logger       — Real StructuredLogger writing to a tmp directory.
#                       Used when tests need a logger but do not inspect log output.
#   capturing_logger  — In-memory logger that records LogEntry objects.
#                       Used when tests need to assert what was logged.
#
# Why real settings for test_logger:
#   StructuredLogger requires a settings object to know log_dir and log_archive_dir.
#   We load real settings with ENV overridden to "dev" and log paths pointed at
#   tmp_path so no real log files are written to the project logs/ directory.

import pytest

from src.core.logging.log_models import LogEntry
from src.core.logging.logger import StructuredLogger
from src.schema.schema_repository import SchemaRepository


# ---------------------------------------------------------------------------
# Schema repo fixture — loaded once per test session for speed
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def abc_schema_repo() -> SchemaRepository:
    """
    Load the real ABC_app.json schema from the schemas/ directory.
    Scoped to session — loaded once, shared across all validator tests.
    SchemaRepository is read-only after load, so sharing is safe.
    """
    repo = SchemaRepository()
    repo.load("schemas")
    return repo


# ---------------------------------------------------------------------------
# Capturing logger — records entries in memory for assertion
# ---------------------------------------------------------------------------

class CapturingLogger:
    """
    In-memory logger that records every LogEntry passed to log().
    Does not write any files — purely for test assertions.

    Usage:
        capturing_logger.entries  → list of LogEntry objects logged so far
    """

    def __init__(self) -> None:
        self.entries: list[LogEntry] = []

    def log(self, entry: LogEntry) -> None:
        self.entries.append(entry)


@pytest.fixture
def capturing_logger() -> CapturingLogger:
    """
    Fresh CapturingLogger for each test.
    Use this fixture when the test needs to assert what was logged.
    """
    return CapturingLogger()


# ---------------------------------------------------------------------------
# Real logger fixture — writes to tmp_path, not project logs/
# ---------------------------------------------------------------------------

@pytest.fixture
def test_logger(tmp_path, monkeypatch) -> StructuredLogger:
    """
    Real StructuredLogger that writes to a temporary directory.
    Used when tests need a real logger but do not inspect log output.

    Loads real settings with:
      - ENV=dev (so missing keys do not raise at startup)
      - log_dir and log_archive_dir redirected to tmp_path

    Why not mock the logger:
      The validator calls logger.log() — we want to confirm it does not
      raise. A real logger gives us that confidence without cluttering
      test assertions.
    """
    import os
    monkeypatch.setenv("ENV", "dev")
    monkeypatch.setenv("LLM_PROVIDER", "mock")
    monkeypatch.setenv("CLIENT_API_KEY", "test-key")
    monkeypatch.setenv("FOUNDRY_API_KEY", "test-foundry-key")

    from src.config.settings import load_settings
    settings = load_settings()

    # Override log paths to write into pytest's tmp_path — never the real logs/
    settings.logging.log_dir = str(tmp_path / "logs")
    settings.logging.log_archive_dir = str(tmp_path / "logs" / "archive")

    return StructuredLogger(settings)
