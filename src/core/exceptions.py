# src/core/exceptions.py
# V0 - Initial implementation
# Note: Only SchemaLoadError defined here in Story 1.4.
# Remaining exceptions added in Story 2.1.


class NL2SQLBaseError(Exception):
    """Base exception for all nl2sql-engine errors."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(message)

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(code={self.code!r}, message={self.message!r})"


class SchemaLoadError(NL2SQLBaseError):
    """
    Raised when a schema file cannot be loaded or fails validation.
    HTTP status: 503 — service cannot start without valid schemas.
    """
