# tests/core/test_constants.py
# V1 - Story 2.1: Added MISSING_CONTEXT_FIELDS to error code tests (C2, C4, C5).
#
# Tests for src/core/constants.py
# Scenarios: C1-C6
#
# What these tests verify:
#   - All 9 log stage constants from Story 1.6 still exist (C1, C3)
#   - All 12 error code constants added in Story 2.1 exist (C2, C4)
#   - Every constant value exactly matches its variable name — no typos (C5)
#   - No numeric limit constants exist — limits live in YAML only (C6)

import src.core.constants as constants


# ---------------------------------------------------------------------------
# C1 — All 9 log stage constants exist
# ---------------------------------------------------------------------------

class TestLogStageConstants:

    LOG_STAGE_NAMES = [
        "REQUEST_RECEIVED",
        "APP_DETECTED",
        "LLM_INTENT_OUTPUT",
        "LLM_SCHEMA_MAPPING_OUTPUT",
        "VALIDATION_RESULT",
        "STRUCTURED_QUERY_BUILT",
        "SQL_BUILT",
        "RESPONSE_SENT",
        "USER_FEEDBACK",
    ]

    def test_all_log_stage_constants_exist(self):
        """C1 — All 9 log stage constants are present in the module."""
        for name in self.LOG_STAGE_NAMES:
            assert hasattr(constants, name), (
                f"Log stage constant '{name}' is missing from constants.py"
            )

    def test_log_stage_constants_are_strings(self):
        """C3 — Every log stage constant is a str."""
        for name in self.LOG_STAGE_NAMES:
            value = getattr(constants, name)
            assert isinstance(value, str), (
                f"Log stage constant '{name}' should be str, got {type(value)}"
            )

    def test_log_stage_constant_values_match_names(self):
        """C5 (log stage portion) — Each constant value equals its variable name."""
        for name in self.LOG_STAGE_NAMES:
            value = getattr(constants, name)
            assert value == name, (
                f"Constant '{name}' has value '{value}' — value must match name exactly"
            )


# ---------------------------------------------------------------------------
# C2 — All 12 error code constants exist
# ---------------------------------------------------------------------------

class TestErrorCodeConstants:

    ERROR_CODE_NAMES = [
        # Business errors
        "APP_NOT_DETERMINED",
        "MULTIPLE_APPS_MATCHED",
        "NO_RELEVANT_TABLES",
        "NO_RELEVANT_COLUMNS",
        "NO_JOIN_PATH",
        "UNSUPPORTED_INTENT",
        "VALIDATION_FAILED",
        "LLM_OUTPUT_PARSE_ERROR",
        # Tool endpoint error
        "MISSING_CONTEXT_FIELDS",
        # Auth error
        "UNAUTHORIZED",
        # Startup error
        "SCHEMA_LOAD_ERROR",
        # Server error
        "INTERNAL_ERROR",
    ]

    def test_all_error_code_constants_exist(self):
        """C2 — All 12 error code constants are present in the module."""
        for name in self.ERROR_CODE_NAMES:
            assert hasattr(constants, name), (
                f"Error code constant '{name}' is missing from constants.py"
            )

    def test_error_code_constants_are_strings(self):
        """C4 — Every error code constant is a str."""
        for name in self.ERROR_CODE_NAMES:
            value = getattr(constants, name)
            assert isinstance(value, str), (
                f"Error code constant '{name}' should be str, got {type(value)}"
            )

    def test_error_code_values_match_names(self):
        """C5 — Each error code value equals its variable name exactly."""
        for name in self.ERROR_CODE_NAMES:
            value = getattr(constants, name)
            assert value == name, (
                f"Constant '{name}' has value '{value}' — value must match name exactly"
            )

    def test_missing_context_fields_exists(self):
        """C2 — MISSING_CONTEXT_FIELDS specifically present (arch doc v1.3 requirement)."""
        assert hasattr(constants, "MISSING_CONTEXT_FIELDS")
        assert constants.MISSING_CONTEXT_FIELDS == "MISSING_CONTEXT_FIELDS"


# ---------------------------------------------------------------------------
# C6 — No numeric limit constants exist
# ---------------------------------------------------------------------------

class TestNoNumericLimitConstants:

    def test_default_top_rows_not_in_constants(self):
        """C6 — DEFAULT_TOP_ROWS must not exist in constants — lives in YAML only."""
        assert not hasattr(constants, "DEFAULT_TOP_ROWS"), (
            "DEFAULT_TOP_ROWS must not be defined in constants.py. "
            "Use settings.sql.default_top_rows from YAML instead."
        )

    def test_max_nl_query_length_not_in_constants(self):
        """C6 — MAX_NL_QUERY_LENGTH must not exist in constants — lives in YAML only."""
        assert not hasattr(constants, "MAX_NL_QUERY_LENGTH"), (
            "MAX_NL_QUERY_LENGTH must not be defined in constants.py. "
            "Use settings.sql.max_nl_query_length from YAML instead."
        )
