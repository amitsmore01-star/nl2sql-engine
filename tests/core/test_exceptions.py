# tests/core/test_exceptions.py
# V1 - Story 2.1: Added MissingContextFieldsError to all test groups (arch doc v1.3).
#
# Tests for src/core/exceptions.py
# Scenarios: E1-E9
#
# What these tests verify:
#   - All 11 exception classes exist and are importable (E1)
#   - All exceptions inherit from NL2SQLBaseError (E2)
#   - NL2SQLBaseError inherits from Exception (E3)
#   - Every exception stores code and message attributes (E4)
#   - Each exception carries the correct default error code (E5)
#   - Exceptions can be caught as NL2SQLBaseError (E6)
#   - Exceptions can be caught as Exception (E7)
#   - SchemaLoadError still works as before (E8)
#   - __repr__ returns a readable string (E9)

import pytest

from src.core.exceptions import (
    NL2SQLBaseError,
    SchemaLoadError,
    AppNotDeterminedError,
    MultipleAppsMatchedError,
    NoRelevantTablesError,
    NoRelevantColumnsError,
    NoJoinPathError,
    UnsupportedIntentError,
    ValidationFailedError,
    LLMOutputParseError,
    MissingContextFieldsError,
    UnauthorizedError,
    InternalError,
)
from src.core.constants import (
    APP_NOT_DETERMINED,
    MULTIPLE_APPS_MATCHED,
    NO_RELEVANT_TABLES,
    NO_RELEVANT_COLUMNS,
    NO_JOIN_PATH,
    UNSUPPORTED_INTENT,
    VALIDATION_FAILED,
    LLM_OUTPUT_PARSE_ERROR,
    MISSING_CONTEXT_FIELDS,
    UNAUTHORIZED,
    SCHEMA_LOAD_ERROR,
    INTERNAL_ERROR,
)


# ---------------------------------------------------------------------------
# E1 — All 11 exception classes exist and are importable
# ---------------------------------------------------------------------------

class TestExceptionsImportable:

    def test_base_error_importable(self):
        """E1 — NL2SQLBaseError imports without error."""
        assert NL2SQLBaseError is not None

    def test_all_exception_classes_importable(self):
        """E1 — All 11 exception classes import without error."""
        classes = [
            SchemaLoadError,
            AppNotDeterminedError,
            MultipleAppsMatchedError,
            NoRelevantTablesError,
            NoRelevantColumnsError,
            NoJoinPathError,
            UnsupportedIntentError,
            ValidationFailedError,
            LLMOutputParseError,
            MissingContextFieldsError,
            UnauthorizedError,
            InternalError,
        ]
        for cls in classes:
            assert cls is not None, f"{cls.__name__} failed to import"

    def test_missing_context_fields_error_importable(self):
        """E1 — MissingContextFieldsError specifically importable (arch doc v1.3)."""
        assert MissingContextFieldsError is not None


# ---------------------------------------------------------------------------
# E2 — All exceptions inherit from NL2SQLBaseError
# E3 — NL2SQLBaseError inherits from Exception
# ---------------------------------------------------------------------------

class TestExceptionInheritance:

    ALL_SUBCLASSES = [
        SchemaLoadError,
        AppNotDeterminedError,
        MultipleAppsMatchedError,
        NoRelevantTablesError,
        NoRelevantColumnsError,
        NoJoinPathError,
        UnsupportedIntentError,
        ValidationFailedError,
        LLMOutputParseError,
        MissingContextFieldsError,
        UnauthorizedError,
        InternalError,
    ]

    def test_base_error_inherits_from_exception(self):
        """E3 — NL2SQLBaseError is a real Python exception."""
        assert issubclass(NL2SQLBaseError, Exception)

    def test_all_exceptions_inherit_from_base(self):
        """E2 — Every exception class inherits from NL2SQLBaseError."""
        for cls in self.ALL_SUBCLASSES:
            assert issubclass(cls, NL2SQLBaseError), (
                f"{cls.__name__} does not inherit from NL2SQLBaseError"
            )

    def test_all_exceptions_inherit_from_exception(self):
        """E2+E3 combined — All exceptions are real Python exceptions."""
        for cls in self.ALL_SUBCLASSES:
            assert issubclass(cls, Exception), (
                f"{cls.__name__} does not inherit from Exception"
            )


# ---------------------------------------------------------------------------
# E4 — Every exception stores code and message
# E5 — Each exception carries the correct default error code
# ---------------------------------------------------------------------------

class TestExceptionAttributes:

    # Map each class to its expected error code constant and a test message
    EXCEPTION_CODE_MAP = [
        (SchemaLoadError,            SCHEMA_LOAD_ERROR,      "Schema failed to load"),
        (AppNotDeterminedError,      APP_NOT_DETERMINED,     "No app matched"),
        (MultipleAppsMatchedError,   MULTIPLE_APPS_MATCHED,  "Multiple apps matched"),
        (NoRelevantTablesError,      NO_RELEVANT_TABLES,     "No tables found"),
        (NoRelevantColumnsError,     NO_RELEVANT_COLUMNS,    "No columns found"),
        (NoJoinPathError,            NO_JOIN_PATH,           "No join path"),
        (UnsupportedIntentError,     UNSUPPORTED_INTENT,     "Unsupported intent"),
        (ValidationFailedError,      VALIDATION_FAILED,      "Validation failed"),
        (LLMOutputParseError,        LLM_OUTPUT_PARSE_ERROR, "LLM output parse error"),
        (MissingContextFieldsError,  MISSING_CONTEXT_FIELDS, "Missing field: intent_output"),
        (UnauthorizedError,          UNAUTHORIZED,           "Unauthorized"),
        (InternalError,              INTERNAL_ERROR,         "Internal error"),
    ]

    def test_exceptions_store_code_and_message(self):
        """E4 — Every exception has .code and .message attributes."""
        for cls, expected_code, test_message in self.EXCEPTION_CODE_MAP:
            exc = cls(test_message)
            assert hasattr(exc, "code"), f"{cls.__name__} missing .code attribute"
            assert hasattr(exc, "message"), f"{cls.__name__} missing .message attribute"

    def test_exceptions_carry_correct_code(self):
        """E5 — Each exception carries the correct error code from constants."""
        for cls, expected_code, test_message in self.EXCEPTION_CODE_MAP:
            exc = cls(test_message)
            assert exc.code == expected_code, (
                f"{cls.__name__}.code should be '{expected_code}', got '{exc.code}'"
            )

    def test_exceptions_store_message(self):
        """E4 — Each exception stores the message passed to it."""
        for cls, expected_code, test_message in self.EXCEPTION_CODE_MAP:
            exc = cls(test_message)
            assert exc.message == test_message, (
                f"{cls.__name__}.message should be '{test_message}', got '{exc.message}'"
            )

    def test_missing_context_fields_message_lists_fields(self):
        """E5 — MissingContextFieldsError message can describe which fields are missing."""
        exc = MissingContextFieldsError(
            "Missing required fields for schema-mapper stage: intent_output"
        )
        assert exc.code == MISSING_CONTEXT_FIELDS
        assert "intent_output" in exc.message


# ---------------------------------------------------------------------------
# E6 — Exceptions can be caught as NL2SQLBaseError
# E7 — Exceptions can be caught as Exception
# ---------------------------------------------------------------------------

class TestExceptionCatching:

    def test_caught_as_base_error(self):
        """E6 — Raising a subclass, catching as NL2SQLBaseError works."""
        with pytest.raises(NL2SQLBaseError) as exc_info:
            raise AppNotDeterminedError("No app found")
        assert exc_info.value.code == APP_NOT_DETERMINED

    def test_caught_as_exception(self):
        """E7 — Raising a subclass, catching as base Exception works."""
        with pytest.raises(Exception):
            raise NoJoinPathError("No join path found")

    def test_missing_context_fields_caught_as_base(self):
        """E6 — MissingContextFieldsError catchable as NL2SQLBaseError."""
        with pytest.raises(NL2SQLBaseError) as exc_info:
            raise MissingContextFieldsError("Missing: intent_output")
        assert exc_info.value.code == MISSING_CONTEXT_FIELDS

    def test_multiple_subclasses_caught_as_base(self):
        """E6 — Different subclasses all catchable as NL2SQLBaseError."""
        errors = [
            AppNotDeterminedError("msg"),
            NoRelevantTablesError("msg"),
            MissingContextFieldsError("msg"),
            UnauthorizedError("msg"),
            InternalError("msg"),
        ]
        for err in errors:
            with pytest.raises(NL2SQLBaseError):
                raise err


# ---------------------------------------------------------------------------
# E8 — SchemaLoadError still works as before
# ---------------------------------------------------------------------------

class TestSchemaLoadErrorBackwardsCompat:

    def test_schema_load_error_raises(self):
        """E8 — SchemaLoadError can be raised and caught."""
        with pytest.raises(SchemaLoadError):
            raise SchemaLoadError("schemas/bad.json not found")

    def test_schema_load_error_code(self):
        """E8 — SchemaLoadError still carries SCHEMA_LOAD_ERROR code."""
        exc = SchemaLoadError("test message")
        assert exc.code == SCHEMA_LOAD_ERROR

    def test_schema_load_error_caught_as_base(self):
        """E8 — SchemaLoadError still catchable as NL2SQLBaseError."""
        with pytest.raises(NL2SQLBaseError):
            raise SchemaLoadError("startup failed")


# ---------------------------------------------------------------------------
# E9 — __repr__ returns readable string
# ---------------------------------------------------------------------------

class TestExceptionRepr:

    def test_repr_contains_class_name(self):
        """E9 — __repr__ includes the exception class name."""
        exc = AppNotDeterminedError("No app found")
        assert "AppNotDeterminedError" in repr(exc)

    def test_repr_contains_code(self):
        """E9 — __repr__ includes the error code."""
        exc = AppNotDeterminedError("No app found")
        assert APP_NOT_DETERMINED in repr(exc)

    def test_repr_contains_message(self):
        """E9 — __repr__ includes the message."""
        exc = AppNotDeterminedError("No app found")
        assert "No app found" in repr(exc)

    def test_missing_context_fields_repr(self):
        """E9 — MissingContextFieldsError __repr__ is readable."""
        exc = MissingContextFieldsError("Missing: intent_output")
        assert "MissingContextFieldsError" in repr(exc)
        assert MISSING_CONTEXT_FIELDS in repr(exc)
