# src/core/constants.py
# V0 - Initial implementation
# V1 - Story 2.1: Added 12 error code constants total.
#      No numeric limit constants — all limits live in settings YAML only.
# V2 - Story 3.1: Added UNKNOWN_PROVIDER error code constant.
#
# Shared constants for the nl2sql-engine.
# Story 1.6: Log stage constants.
# Story 2.1: Error code constants.

# ---------------------------------------------------------------------------
# Log Stage Constants
# Used by StructuredLogger to identify which pipeline stage emitted an entry.
# Every stage in the pipeline emits exactly one log entry using these constants.
# ---------------------------------------------------------------------------

REQUEST_RECEIVED          = "REQUEST_RECEIVED"
APP_DETECTED              = "APP_DETECTED"
LLM_INTENT_OUTPUT         = "LLM_INTENT_OUTPUT"
LLM_SCHEMA_MAPPING_OUTPUT = "LLM_SCHEMA_MAPPING_OUTPUT"
VALIDATION_RESULT         = "VALIDATION_RESULT"
STRUCTURED_QUERY_BUILT    = "STRUCTURED_QUERY_BUILT"
SQL_BUILT                 = "SQL_BUILT"
RESPONSE_SENT             = "RESPONSE_SENT"
USER_FEEDBACK             = "USER_FEEDBACK"
 
# ---------------------------------------------------------------------------
# Error Code Constants
# Used in all NL2SQLBaseError subclasses and API error responses.
# Every error code value must match its variable name exactly — no typos.
# HTTP status notes are for reference only — enforced in the API layer.
# ---------------------------------------------------------------------------
 
# Business errors — HTTP 200 (pipeline handled the error gracefully)
APP_NOT_DETERMINED        = "APP_NOT_DETERMINED"        # No app matched in NL query
MULTIPLE_APPS_MATCHED     = "MULTIPLE_APPS_MATCHED"     # NL query matched 2+ apps
NO_RELEVANT_TABLES        = "NO_RELEVANT_TABLES"        # LLM proposed tables not in schema
NO_RELEVANT_COLUMNS       = "NO_RELEVANT_COLUMNS"       # LLM proposed columns not in table
NO_JOIN_PATH              = "NO_JOIN_PATH"              # No join path between required tables
UNSUPPORTED_INTENT        = "UNSUPPORTED_INTENT"        # Intent is not 'select'
VALIDATION_FAILED         = "VALIDATION_FAILED"         # Validator rejected LLM proposals
LLM_OUTPUT_PARSE_ERROR    = "LLM_OUTPUT_PARSE_ERROR"    # LLM returned malformed JSON
 
# Tool endpoint error — HTTP 400
# Returned when a Foundry tool endpoint receives a QueryContext missing required fields.
MISSING_CONTEXT_FIELDS    = "MISSING_CONTEXT_FIELDS"    # Required QueryContext fields absent
 
# Auth error — HTTP 401
UNAUTHORIZED              = "UNAUTHORIZED"              # Missing or wrong API key
 
# Startup error — HTTP 503
SCHEMA_LOAD_ERROR         = "SCHEMA_LOAD_ERROR"         # Schema file missing or invalid
 
# Server error — HTTP 500
INTERNAL_ERROR            = "INTERNAL_ERROR"            # Unhandled exception

# LLM provider error — raised at startup or factory creation time
UNKNOWN_PROVIDER          = "UNKNOWN_PROVIDER"          # Provider string not recognised
