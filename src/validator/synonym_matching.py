# src/validator/synonym_matching.py
# V0 - Initial implementation (Story 5.9, Bug #13 — Option 2 shared module)
#
# Single source of truth for matching a user's source phrase against schema-defined
# synonyms. Extracted from join_resolver so that both the join resolver and the
# table/column validator use identical matching logic — no duplicated rules.
#
# Three pure functions, all schema-driven (zero app-specific hardcoding):
#   match_table_reference(source, table_schema) -> bool
#       Does the source phrase match the table's display name or a table-level synonym?
#   match_hierarchy_role(source, table_schema) -> str | None
#       Does the source phrase match a hierarchy level's synonyms? Returns the level name.
#   table_has_hierarchy(table_schema) -> bool
#       Does this table define a hierarchy with at least one level?
#
# Matching strategy (current — Phase 1):
#   Case-insensitive, whole-word (regex word-boundary) matching. A synonym matches
#   only when it appears as a standalone word in the source — never as a substring
#   of a larger word. This prevents short synonyms (e.g. "sub") from matching inside
#   unrelated words (e.g. "subsidiary").
#
# KNOWN LIMITATION (Bug #14, deferred to Phase 2):
#   Whole-word matching does NOT match fused words. A source like "subaccount"
#   will not match the synonym "sub Acc" or "sub account", because there is no word
#   boundary inside the fused token. The Phase 2 fix is space-insensitive
#   normalisation PLUS schema synonyms that include the fused/word forms. Because
#   all matching lives in this one module, that upgrade happens here and applies
#   uniformly to every app schema and every caller.

import re


def _whole_word_match(needle: str, haystack_lower: str) -> bool:
    """
    Return True if `needle` appears as a whole word in `haystack_lower`.

    Both inputs are compared case-insensitively (caller passes haystack already
    lowercased; needle is lowered here). Uses regex word boundaries so the needle
    must be a standalone token, not a substring of a larger word.

    Example:
        _whole_word_match("sub", "sub account")  -> True
        _whole_word_match("sub", "subsidiary")   -> False
        _whole_word_match("sub", "subaccount")   -> False  (Bug #14 — Phase 2)
    """
    pattern = r"\b" + re.escape(needle.lower()) + r"\b"
    return re.search(pattern, haystack_lower) is not None


def match_table_reference(source: str, table_schema) -> bool:
    """
    Return True if `source` matches the table's display name or any table-level synonym.

    Used by the table/column validator to decide whether a (duplicate) table entry's
    source is a genuine reference to that table, or a phantom (e.g. a column name the
    LLM mistakenly emitted as a second table entry).

    Matching is case-insensitive, whole-word. The table's own `name` is NOT used for
    matching — only the human-facing display_name and synonyms, since those are what
    a user phrase would correspond to.

    Args:
        source:       The phrase the LLM attributed to this table entry (e.g. "top acc").
        table_schema: TableSchema for the table.

    Returns:
        True if the source matches display_name or a synonym; False otherwise.
    """
    if not source:
        return False

    source_lower = source.lower()

    # Display name (optional on the model)
    if table_schema.display_name:
        if _whole_word_match(table_schema.display_name, source_lower):
            return True

    # Table-level synonyms
    for synonym in table_schema.synonyms:
        if _whole_word_match(synonym, source_lower):
            return True

    return False


def match_hierarchy_role(source: str, table_schema):
    """
    Match a source phrase against hierarchy synonyms defined in the schema.
    Returns the role key (e.g. "top_Acc") if matched, None otherwise.
    Matching is case-insensitive whole-word using regex boundaries.

    Args:
        source:       The phrase the LLM attributed to this entry (e.g. "top acc").
        table_schema: TableSchema for the table.

    Returns:
        The hierarchy level name (str) if a synonym matches, else None.
    """
    if not table_schema.business_rules or not table_schema.business_rules.hierarchy:
        return None

    hierarchy = table_schema.business_rules.hierarchy
    source_lower = source.lower()

    for level_name in hierarchy.level_names():
        level = hierarchy.get_level(level_name)
        if level is None:
            continue
        for synonym in level.synonyms:
            if _whole_word_match(synonym, source_lower):
                return level_name

    return None


def table_has_hierarchy(table_schema) -> bool:
    """
    Return True if this table has a hierarchy schema with at least one level.
    Used to decide whether a single-instance table should be checked for a role.
    """
    if table_schema is None:
        return False
    if not table_schema.business_rules:
        return False
    if not table_schema.business_rules.hierarchy:
        return False
    return len(table_schema.business_rules.hierarchy.level_names()) > 0
