# tests/validator/test_app_identifier.py
# V0 - Initial implementation
#
# Test scenarios:
#   Group A — Synonym matching (no explicit app_id)
#     A1  Query contains "Acme" — matches Acme_app via appSynonyms
#     A2  Query contains "abc" (lowercase) — case-insensitive match
#     A3  Query contains "Acme office" — multi-word synonym match
#     A4  Query contains "Acme system" — another synonym
#     A5  Query contains "xyzABC" — whole-word guard, no match
#     A6  Query contains "ABCdef" — whole-word guard, no match
#     A7  Query has no app reference — raises AppNotDeterminedError
#   Group B — Explicit app_id (pre-set on context)
#     B1  Valid explicit app_id — skips synonym matching, populates version
#     B2  Unknown explicit app_id — raises AppNotDeterminedError
#     B3  Valid explicit app_id, query mentions no synonym — still works
#   Group C — Multiple app match
#     C1  Query matches two apps — raises MultipleAppsMatchedError
#   Group D — Logging and context output
#     D1  Successful match — APP_DETECTED log emitted
#     D2  Synonym match — match_method = "synonym" in log payload
#     D3  Explicit match — match_method = "explicit" in log payload
#   Group E — Error code integrity
#     E1  AppNotDeterminedError has code APP_NOT_DETERMINED
#     E2  MultipleAppsMatchedError has code MULTIPLE_APPS_MATCHED

import json
import re
import pytest
from unittest.mock import MagicMock, patch

from src.core.constants import APP_DETECTED, APP_NOT_DETERMINED, MULTIPLE_APPS_MATCHED
from src.core.exceptions import AppNotDeterminedError, MultipleAppsMatchedError
from src.core.models import QueryContext
from src.validator.app_identifier import run_app_identifier, _is_whole_word_match


# ---------------------------------------------------------------------------
# Helpers — build fake schemas for tests
# ---------------------------------------------------------------------------

def _make_schema(app_id: str, app_name: str, synonyms: list[str], version: str = "1.0"):
    """
    Builds a minimal fake AppSchema-like object using MagicMock.

    Why MagicMock?
        AppSchema is a Pydantic model defined in schema_models.py.
        To avoid loading real JSON files in these unit tests, we create a
        lightweight fake object that has the same attributes our function reads.
        MagicMock lets us set any attribute freely.
    """
    schema = MagicMock()
    schema.appId = app_id
    schema.app_name = app_name
    schema.appSynonyms = synonyms
    schema.version = version
    return schema


def _make_repo(schemas: list) -> MagicMock:
    """
    Builds a fake SchemaRepository whose get_all_schemas() returns
    a lis of {appId: schema} built from the provided list.
    """
    repo = MagicMock()
    repo.get_all_schemas.return_value = schemas
    return repo


def _make_logger() -> MagicMock:
    """
    Builds a fake StructuredLogger.
    We capture calls to logger.log() to verify log payloads in Group D tests.
    """
    return MagicMock()


def _make_context(nl_query: str, app_id: str = "") -> QueryContext:
    """
    Builds a minimal QueryContext for testing.
    app_id defaults to "" (not pre-set) for synonym-matching tests.
    """
    return QueryContext(
        nl_query_original=nl_query,
        app_id=app_id,
        user_id="test_user",
    )


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def abc_schema():
    """The Acme_app schema with its real synonyms from Acme_app.json."""
    return _make_schema(
        app_id="Acme_app",
        app_name="Acme",
        synonyms=["Acme", "Acme office", "Acme system"],
        version="1.0",
    )


@pytest.fixture
def abc_repo(abc_schema):
    """A repo containing only Acme_app."""
    return _make_repo([abc_schema])


@pytest.fixture
def logger():
    return _make_logger()


# ---------------------------------------------------------------------------
# Group A — Synonym matching
# ---------------------------------------------------------------------------

class TestSynonymMatching:
    """NL query synonym matching — no explicit app_id pre-set."""

    def test_A1_matches_uppercase_ABC(self, abc_repo, logger):
        """A1 — 'Acme' in query matches Acme_app via appSynonyms."""
        ctx = _make_context("give me customer name in Acme")
        result = run_app_identifier(ctx, abc_repo, logger)
        assert result.app_id == "Acme_app"
        assert result.app_schema_version == "1.0"

    def test_A2_matches_lowercase_abc(self, abc_repo, logger):
        """A2 — 'acme' (lowercase) matches due to case-insensitive matching."""
        ctx = _make_context("give me customer name in acme")
        result = run_app_identifier(ctx, abc_repo, logger)
        assert result.app_id == "Acme_app"

    def test_A3_matches_multiword_synonym_abc_office(self, abc_repo, logger):
        """A3 — 'Acme office' as a multi-word synonym matches Acme_app."""
        ctx = _make_context("give me customers in Acme office")
        result = run_app_identifier(ctx, abc_repo, logger)
        assert result.app_id == "Acme_app"

    def test_A4_matches_synonym_abc_system(self, abc_repo, logger):
        """A4 — 'Acme system' synonym matches Acme_app."""
        ctx = _make_context("show me data from Acme system")
        result = run_app_identifier(ctx, abc_repo, logger)
        assert result.app_id == "Acme_app"

    def test_A5_no_match_when_embedded_xyzABC(self, abc_repo, logger):
        """A5 — 'xyzABC' is not a whole-word match — raises AppNotDeterminedError."""
        ctx = _make_context("give me data from xyzABC")
        with pytest.raises(AppNotDeterminedError):
            run_app_identifier(ctx, abc_repo, logger)

    def test_A6_no_match_when_embedded_ABCdef(self, abc_repo, logger):
        """A6 — 'ABCdef' is not a whole-word match — raises AppNotDeterminedError."""
        ctx = _make_context("query ABCdef system")
        with pytest.raises(AppNotDeterminedError):
            run_app_identifier(ctx, abc_repo, logger)

    def test_A7_no_match_when_no_app_in_query(self, abc_repo, logger):
        """A7 — Query has no recognisable app name — raises AppNotDeterminedError."""
        ctx = _make_context("give me all customers")
        with pytest.raises(AppNotDeterminedError):
            run_app_identifier(ctx, abc_repo, logger)


# ---------------------------------------------------------------------------
# Group B — Explicit app_id
# ---------------------------------------------------------------------------

class TestExplicitAppId:
    """Explicit app_id pre-set on context — synonym matching is skipped."""

    def test_B1_valid_explicit_app_id_populates_version(self, abc_repo, logger):
        """B1 — Valid explicit app_id skips matching and populates version."""
        ctx = _make_context("give me customers", app_id="Acme_app")
        result = run_app_identifier(ctx, abc_repo, logger)
        assert result.app_id == "Acme_app"
        assert result.app_schema_version == "1.0"

    def test_B2_unknown_explicit_app_id_raises_error(self, abc_repo, logger):
        """B2 — Unknown explicit app_id raises AppNotDeterminedError."""
        ctx = _make_context("give me customers", app_id="nonexistent_app")
        with pytest.raises(AppNotDeterminedError):
            run_app_identifier(ctx, abc_repo, logger)

    def test_B3_explicit_app_id_works_without_synonym_in_query(self, abc_repo, logger):
        """B3 — Explicit app_id works even when query mentions no synonym at all."""
        ctx = _make_context("give me all customers", app_id="Acme_app")
        result = run_app_identifier(ctx, abc_repo, logger)
        assert result.app_id == "Acme_app"
        assert result.app_schema_version == "1.0"


# ---------------------------------------------------------------------------
# Group C — Multiple app match
# ---------------------------------------------------------------------------

class TestMultipleAppMatch:
    """Two loaded apps — query matches both — ambiguous."""

    def test_C1_multiple_apps_matched_raises_error(self, logger):
        """
        C1 — Query matches two different apps.
        We create a second fake app whose synonym 'Acme' overlaps with Acme_app's synonym.
        Both apps match — MultipleAppsMatchedError raised.
        """
        schema_a = _make_schema("Acme_app", "Acme", ["Acme", "Acme office"], "1.0")
        schema_b = _make_schema("XYZ_app", "XYZ", ["Acme", "XYZ system"], "2.0")
        # schema_b deliberately has "Acme" as a synonym to force a collision
        repo = _make_repo([schema_a, schema_b])

        ctx = _make_context("give me data from Acme")
        with pytest.raises(MultipleAppsMatchedError):
            run_app_identifier(ctx, repo, logger)


# ---------------------------------------------------------------------------
# Group D — Logging and context output
# ---------------------------------------------------------------------------

class TestLogging:
    """APP_DETECTED log is emitted correctly on success."""

    def test_D1_app_detected_log_emitted_on_success(self, abc_repo, logger):
        """D1 — APP_DETECTED stage logged after successful synonym match."""
        ctx = _make_context("give me customers in Acme")
        run_app_identifier(ctx, abc_repo, logger)

        # logger.log() must have been called exactly once
        logger.log.assert_called_once()

        # First positional arg to logger.log is the stage name
        entry = logger.log.call_args.args[0] # LogEntry object is the first positional argument
        assert entry.stage  == APP_DETECTED

    def test_D2_synonym_match_method_logged(self, abc_repo, logger):
        """D2 — match_method = 'synonym' when matched via synonym."""
        ctx = _make_context("give me customers in Acme office")
        run_app_identifier(ctx, abc_repo, logger)
        entry = logger.log.call_args.args[0]
        assert entry.payload["match_method"] == "synonym"

    def test_D3_explicit_match_method_logged(self, abc_repo, logger):
        """D3 — match_method = 'explicit' when app_id was pre-set."""
        ctx = _make_context("give me customers", app_id="Acme_app")
        run_app_identifier(ctx, abc_repo, logger)
        entry = logger.log.call_args.args[0]
        assert entry.payload["match_method"] == "explicit"

    def test_D1b_log_payload_contains_app_id_and_version(self, abc_repo, logger):
        """D1b — Log payload contains app_id and schema_version."""
        ctx = _make_context("give me customers in Acme")
        run_app_identifier(ctx, abc_repo, logger)
        entry = logger.log.call_args.args[0]
        assert entry.payload["app_id"] == "Acme_app"
        assert entry.payload["schema_version"] == "1.0"

    def test_D1c_latency_recorded_in_context(self, abc_repo, logger):
        """D1c — latency_ms['app_identifier'] is set after the call."""
        ctx = _make_context("give me customers in Acme")
        result = run_app_identifier(ctx, abc_repo, logger)
        assert "app_identifier" in result.latency_ms
        assert isinstance(result.latency_ms["app_identifier"], int)


# ---------------------------------------------------------------------------
# Group E — Error code integrity
# ---------------------------------------------------------------------------

class TestErrorCodes:
    """Raised exceptions carry the correct machine-readable error codes."""

    def test_E1_app_not_determined_error_code(self, abc_repo, logger):
        """E1 — AppNotDeterminedError.code == APP_NOT_DETERMINED."""
        ctx = _make_context("give me all customers")
        with pytest.raises(AppNotDeterminedError) as exc_info:
            run_app_identifier(ctx, abc_repo, logger)
        assert exc_info.value.code == APP_NOT_DETERMINED

    def test_E2_multiple_apps_matched_error_code(self, logger):
        """E2 — MultipleAppsMatchedError.code == MULTIPLE_APPS_MATCHED."""
        schema_a = _make_schema("Acme_app", "Acme", ["Acme"], "1.0")
        schema_b = _make_schema("XYZ_app", "XYZ", ["Acme"], "2.0")
        repo = _make_repo([schema_a, schema_b])

        ctx = _make_context("give me data from Acme")
        with pytest.raises(MultipleAppsMatchedError) as exc_info:
            run_app_identifier(ctx, repo, logger)
        assert exc_info.value.code == MULTIPLE_APPS_MATCHED


# ---------------------------------------------------------------------------
# Helper function unit tests — _is_whole_word_match
# ---------------------------------------------------------------------------

class TestIsWholeWordMatch:
    """Unit tests for the private matching helper — tests the regex logic directly."""

    def test_matches_exact_word(self):
        assert _is_whole_word_match("Acme", "give me data in Acme") is True

    def test_case_insensitive(self):
        assert _is_whole_word_match("Acme", "give me data in acme") is True

    def test_no_match_when_embedded_prefix(self):
        assert _is_whole_word_match("Acme", "xyzAcme") is False

    def test_no_match_when_embedded_suffix(self):
        assert _is_whole_word_match("Acme", "Acmedef") is False

    def test_matches_multiword_synonym(self):
        assert _is_whole_word_match("Acme office", "data from Acme office today") is True

    def test_no_match_empty_query(self):
        assert _is_whole_word_match("Acme", "") is False
