# src/pipeline/intent_guard.py
# V0 - Initial implementation
#
# Deterministic pre-LLM safety gate.
# Scans nl_query_original for SQL keywords that indicate a non-SELECT intent.
# If any blocked keyword is found (whole-word, case-insensitive), the context
# is marked failed with UNSUPPORTED_INTENT and returned immediately.
# No LLM call is ever made for a blocked query.
#
# Called from:
#   - src/pipeline/orchestrator.py  (full pipeline)
#   - src/api/tools/app_identifier_tool.py  (Story 5.6)
#   - src/api/tools/nl_to_ir_tool.py        (Story 4.1)
#   - src/api/tools/query_tool.py            (Story 5.7)
#
# One function, multiple callers — zero duplication.

import re

from src.core.models import QueryContext
from src.core.constants import UNSUPPORTED_INTENT, INTENT_GUARD_RESULT
from src.core.exceptions import UnsupportedIntentError
from src.core.logging.logger import StructuredLogger
from src.core.logging.log_models import LogEntry

# Keywords that indicate a non-SELECT SQL intent.
# Whole-word matching via \b boundaries means:
#   "DELETE" is blocked  — exact word
#   "deleted" is NOT blocked — different word
#   "updates" is NOT blocked — different word
_BLOCKED_KEYWORDS: list[str] = [
    "DELETE",
    "DROP",
    "UPDATE",
    "INSERT",
    "TRUNCATE",
    "ALTER",
    "CREATE",
]

# Pre-compile one regex per keyword for efficiency.
# re.IGNORECASE makes matching case-insensitive.
# \b is a word boundary — matches position between a word char and a non-word char.
_BLOCKED_PATTERNS: list[re.Pattern] = [
    re.compile(rf"\b{kw}\b", re.IGNORECASE)
    for kw in _BLOCKED_KEYWORDS
]


def run_intent_guard(context: QueryContext, logger: StructuredLogger) -> QueryContext:
    """
    Scan nl_query_original for non-SELECT SQL keywords.

    If a blocked keyword is found:
      - context.status is set to "failed"
      - context.error is populated with UNSUPPORTED_INTENT code
      - INTENT_GUARD_RESULT log is emitted with passed=False and the detected keywords
      - context is returned immediately (no exception raised — caller checks status)

    If no blocked keyword is found:
      - context is returned unchanged (status stays as-is, no error set)
      - INTENT_GUARD_RESULT log is emitted with passed=True

    Args:
        context: The pipeline state object. Reads nl_query_original.
        logger:  StructuredLogger instance for emitting the log entry.

    Returns:
        The same context object, possibly with error fields populated.
    """
    query = context.nl_query_original

    # Check every keyword pattern against the query.
    detected: list[str] = [
        kw
        for kw, pattern in zip(_BLOCKED_KEYWORDS, _BLOCKED_PATTERNS)
        if pattern.search(query)
    ]

    passed = len(detected) == 0

    # Emit log regardless of outcome — always want a trace of the guard result.
    logger.log(
        LogEntry(
            stage=INTENT_GUARD_RESULT,
            request_id=context.request_id,
            user_id=context.user_id,
            app_id=context.app_id,
            app_schema_version=context.app_schema_version,
            payload={
                "passed": passed,
                "keywords_detected": detected,
            },
        )
    )

    if not passed:
        context.status = "failed"
        context.error = {
            "code": UNSUPPORTED_INTENT,
            "message": (
                f"Query contains non-SELECT keyword(s): {', '.join(detected)}. "
                "Only SELECT queries are supported."
            ),
        }

    return context
