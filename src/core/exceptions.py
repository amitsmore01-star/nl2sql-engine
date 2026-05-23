# src/core/exceptions.py
# V0 - Initial implementation
# V1 - Story 2.1: Added 11 exception subclasses total.
# All custom exceptions for the nl2sql-engine.
# Every exception carries a machine-readable code and a human-readable message.
# Codes must match the constants defined in src/core/constants.py exactly.
 
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
 
 
class NL2SQLBaseError(Exception):
    """
    Base exception for all nl2sql-engine errors.
    All custom exceptions inherit from this class.
    Carries a machine-readable code and a human-readable message.
    """
 
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(message)
 
    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(code={self.code!r}, message={self.message!r})"
 
 
# ---------------------------------------------------------------------------
# Startup Errors
# ---------------------------------------------------------------------------
 
class SchemaLoadError(NL2SQLBaseError):
    """
    Raised when a schema file cannot be loaded or fails validation.
    HTTP status: 503 — service cannot start without valid schemas.
    """
    def __init__(self, message: str) -> None:
        super().__init__(code=SCHEMA_LOAD_ERROR, message=message)
 
 
# ---------------------------------------------------------------------------
# Business Errors — HTTP 200
# These are expected pipeline outcomes, not server failures.
# ---------------------------------------------------------------------------
 
class AppNotDeterminedError(NL2SQLBaseError):
    """
    Raised when no app schema matches the NL query.
    The user's query did not contain any recognisable app name or synonym.
    """
    def __init__(self, message: str) -> None:
        super().__init__(code=APP_NOT_DETERMINED, message=message)
 
 
class MultipleAppsMatchedError(NL2SQLBaseError):
    """
    Raised when the NL query matches more than one app schema.
    Ambiguous — engine cannot proceed without knowing which app to use.
    """
    def __init__(self, message: str) -> None:
        super().__init__(code=MULTIPLE_APPS_MATCHED, message=message)
 
 
class NoRelevantTablesError(NL2SQLBaseError):
    """
    Raised when the LLM proposes tables that do not exist in the schema.
    Validator rejects all hallucinated table names.
    """
    def __init__(self, message: str) -> None:
        super().__init__(code=NO_RELEVANT_TABLES, message=message)
 
 
class NoRelevantColumnsError(NL2SQLBaseError):
    """
    Raised when the LLM proposes columns that do not belong to their table.
    Validator rejects all hallucinated or mismatched column names.
    """
    def __init__(self, message: str) -> None:
        super().__init__(code=NO_RELEVANT_COLUMNS, message=message)
 
 
class NoJoinPathError(NL2SQLBaseError):
    """
    Raised when no join path exists between the required tables.
    Join resolver could not connect all resolved tables via schema relationships.
    """
    def __init__(self, message: str) -> None:
        super().__init__(code=NO_JOIN_PATH, message=message)
 
 
class UnsupportedIntentError(NL2SQLBaseError):
    """
    Raised when the LLM extracts an intent other than 'select'.
    Only SELECT queries are supported in Phase 1.
    """
    def __init__(self, message: str) -> None:
        super().__init__(code=UNSUPPORTED_INTENT, message=message)
 
 
class ValidationFailedError(NL2SQLBaseError):
    """
    Raised when the deterministic validator rejects the LLM's proposals.
    General validation failure — more specific errors raised where possible.
    """
    def __init__(self, message: str) -> None:
        super().__init__(code=VALIDATION_FAILED, message=message)
 
 
class LLMOutputParseError(NL2SQLBaseError):
    """
    Raised when the LLM returns a response that cannot be parsed as valid JSON.
    Indicates the LLM did not follow the required output format.
    """
    def __init__(self, message: str) -> None:
        super().__init__(code=LLM_OUTPUT_PARSE_ERROR, message=message)
 
 
# ---------------------------------------------------------------------------
# Tool Endpoint Errors — HTTP 400
# ---------------------------------------------------------------------------
 
class MissingContextFieldsError(NL2SQLBaseError):
    """
    Raised when a Foundry tool endpoint receives a QueryContext that is missing
    one or more required fields for that pipeline stage.
    HTTP status: 400 — the error is in what the agent sent, not in pipeline logic.
 
    The message should list exactly which fields are missing so the agent can fix
    its call. Example: "Missing required fields for schema-mapper: intent_output"
    """
    def __init__(self, message: str) -> None:
        super().__init__(code=MISSING_CONTEXT_FIELDS, message=message)
 
 
# ---------------------------------------------------------------------------
# Auth Errors — HTTP 401
# ---------------------------------------------------------------------------
 
class UnauthorizedError(NL2SQLBaseError):
    """
    Raised when the X-API-Key or X-Foundry-API-Key header is missing or incorrect.
    HTTP status: 401 — client must provide a valid API key.
    """
    def __init__(self, message: str) -> None:
        super().__init__(code=UNAUTHORIZED, message=message)
 
 
# ---------------------------------------------------------------------------
# Server Errors — HTTP 500
# ---------------------------------------------------------------------------
 
class InternalError(NL2SQLBaseError):
    """
    Raised for any unhandled exception in the pipeline.
    HTTP status: 500 — full detail logged, no raw trace exposed to client.
    """
    def __init__(self, message: str) -> None:
        super().__init__(code=INTERNAL_ERROR, message=message)

