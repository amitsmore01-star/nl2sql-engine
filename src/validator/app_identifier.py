# src/validator/app_identifier.py
# V0 - Initial implementation
#
# Contains run_app_identifier(context, schema_repo, logger) — the single internal
# function that identifies which app schema the NL query belongs to.
#
# Two callers (same function, zero duplication):
#   - src/pipeline/orchestrator.py  (full pipeline via POST /v1/query)
#   - src/api/tools/app_identifier_tool.py  (Foundry tool via POST /v1/tools/app-identifier)
#
# Matching rules:
#   1. If context.app_id is already set — validate it exists in loaded schemas,
#      populate app_schema_version, return. No synonym matching needed.
#   2. Otherwise — scan all loaded schemas. For each schema, check if any app
#      synonym appears in the NL query as a whole word (case-insensitive).
#   3. Exactly one match  → populate app_id + app_schema_version, emit APP_DETECTED log.
#   4. Zero matches       → raise AppNotDeterminedError.
#   5. Two or more matches → raise MultipleAppsMatchedError.

import re
import time

from src.core.constants import APP_DETECTED
from src.core.exceptions import AppNotDeterminedError, MultipleAppsMatchedError
from src.core.models import QueryContext
from src.schema.schema_repository import SchemaRepository
from src.core.logging.logger import StructuredLogger


def _is_whole_word_match(synonym: str, text: str) -> bool:
    """
    Returns True if `synonym` appears in `text` as a whole word,
    case-insensitively.

    How whole-word matching works:
        \\b is a "word boundary" in regex — it matches the position between
        a word character (letter/digit/underscore) and a non-word character.

        So \\bABC\\b matches "ABC" in "give me ABC data"
        but NOT in "xyzABC" or "ABCdef".

        re.escape() makes sure any special characters in the synonym
        (like a dot or parenthesis) are treated as literal characters,
        not regex operators.

        re.IGNORECASE makes the match case-insensitive.
    """
    pattern = r"\b" + re.escape(synonym) + r"\b"
    return bool(re.search(pattern, text, re.IGNORECASE))


def run_app_identifier(
    context: QueryContext,
    schema_repo: SchemaRepository,
    logger: StructuredLogger,
) -> QueryContext:
    """
    Identifies which app schema the NL query belongs to.

    Reads:
        context.nl_query_original  — the raw NL query
        context.app_id             — if already set, skips synonym matching

    Writes:
        context.app_id             — the matched appId string
        context.app_schema_version — the version field from the matched schema

    Raises:
        AppNotDeterminedError    — no app matched
        MultipleAppsMatchedError — two or more apps matched

    Args:
        context:     The pipeline state object for this request.
        schema_repo: Loaded schema repository — provides all app schemas.
        logger:      Structured logger — emits APP_DETECTED log on success.

    Returns:
        The same context object with app_id and app_schema_version populated.
    """
    start_time = time.monotonic()
    all_schemas = schema_repo.get_all_schemas()  # dict[str, AppSchema]

    # ------------------------------------------------------------------
    # Path 1 — Explicit app_id already set on context
    # ------------------------------------------------------------------
    if context.app_id:
        matched_schema = all_schemas.get(context.app_id)

        if matched_schema is None:
            raise AppNotDeterminedError(
                f"Explicit app_id '{context.app_id}' does not match any loaded schema. "
                f"Loaded apps: {list(all_schemas.keys())}"
            )

        # app_id already correct — just populate version
        context.app_schema_version = matched_schema.version
        match_method = "explicit"

    # ------------------------------------------------------------------
    # Path 2 — Synonym matching against nl_query_original
    # ------------------------------------------------------------------
    else:
        query_text = context.nl_query_original
        matched_schemas = []  # collect all matches to detect ambiguity

        for app_id, schema in all_schemas.items():
            # Check the app_name itself first, then each synonym
            # appSynonyms is stored on the schema as a list of strings
            candidates = [schema.app_name] + list(schema.appSynonyms)

            for candidate in candidates:
                if _is_whole_word_match(candidate, query_text):
                    matched_schemas.append(schema)
                    break  # one match per schema is enough — move to next app

        if len(matched_schemas) == 0:
            raise AppNotDeterminedError(
                f"No app could be identified from query: '{context.nl_query_original}'. "
                f"Loaded apps: {list(all_schemas.keys())}"
            )

        if len(matched_schemas) > 1:
            matched_ids = [s.appId for s in matched_schemas]
            raise MultipleAppsMatchedError(
                f"Query matched multiple apps: {matched_ids}. "
                f"Please be more specific about which app you mean."
            )

        # Exactly one match
        matched = matched_schemas[0]
        context.app_id = matched.appId
        context.app_schema_version = matched.version
        match_method = "synonym"

    # ------------------------------------------------------------------
    # Log APP_DETECTED — always emitted on success
    # ------------------------------------------------------------------
    latency = int((time.monotonic() - start_time) * 1000)
    context.latency_ms["app_identifier"] = latency

    logger.log(
        stage=APP_DETECTED,
        request_id=context.request_id,
        user_id=context.user_id,
        app_id=context.app_id,
        app_schema_version=context.app_schema_version,
        payload={
            "app_id": context.app_id,
            "schema_version": context.app_schema_version,
            "match_method": match_method,
        },
    )

    return context
