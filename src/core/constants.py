# src/core/constants.py
# V0 - Initial implementation
#
# Shared constants for the nl2sql-engine.
# Story 1.6: Log stage constants only.
# Remaining constants (error codes, limits) added in Story 2.1.

# ---------------------------------------------------------------------------
# Log Stage Constants
# Used by StructuredLogger to identify which pipeline stage emitted an entry.
# Every stage in the pipeline emits exactly one log entry using these constants.
# ---------------------------------------------------------------------------

REQUEST_RECEIVED         = "REQUEST_RECEIVED"
APP_DETECTED             = "APP_DETECTED"
LLM_INTENT_OUTPUT        = "LLM_INTENT_OUTPUT"
LLM_SCHEMA_MAPPING_OUTPUT = "LLM_SCHEMA_MAPPING_OUTPUT"
VALIDATION_RESULT        = "VALIDATION_RESULT"
STRUCTURED_QUERY_BUILT   = "STRUCTURED_QUERY_BUILT"
SQL_BUILT                = "SQL_BUILT"
RESPONSE_SENT            = "RESPONSE_SENT"
USER_FEEDBACK            = "USER_FEEDBACK"
