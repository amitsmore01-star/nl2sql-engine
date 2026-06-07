# src/sql/where_builder.py
# V0 - Initial implementation
#
# Where builder.
# Builds the WHERE clause from a validated StructuredQuery.
#
# Single public function:
#   build_where(structured_query) -> str
#
# Responsibilities:
#   - Render each ResolvedFilter as:  alias.ColumnName {operator} '{value}'
#   - Respect connector field on each ResolvedFilter ("AND" | "OR").
#     The first condition never emits a connector prefix.
#     All subsequent conditions prefix with their connector.
#   - IS NULL / IS NOT NULL operators: render as  alias.Column IS NULL
#     (value field is ignored entirely for these operators).
#   - Append all applied_rules strings after user filters.
#     applied_rules are always joined with AND — they are business rules,
#     not user-driven, so OR is never applicable.
#   - Align condition bodies by padding each left-hand side to the same
#     width, so operators line up vertically (matching golden SQL Section 9.3).
#   - Return empty string "" if both filters and applied_rules are empty.
#
# Ordering contract:
#   1. User filters (structured_query.filters) — in list order, connectors respected
#   2. Business rules (structured_query.applied_rules) — always AND, always after filters
#
# This function is pure — no side effects, no logging, no LLM calls, no schema lookups.
# All filter values were validated by the validator (Stories 4.2–4.5) before this
# function is called. String values are wrapped in single quotes. Numeric detection
# is deferred to Phase 2 — Phase 1 wraps all values in quotes.

from src.core.models import StructuredQuery

# Operators that render without a value — value field is ignored for these.
_VALUELESS_OPERATORS = {"IS NULL", "IS NOT NULL"}

# SQL operator tokens used to split rule strings into lhs + remainder for alignment.
# Order matters — longer operators must come before their substrings
# (e.g. "IS NOT NULL" before "IS NULL", ">=" before ">").
_RULE_SPLIT_OPERATORS = [
    "IS NOT NULL",
    "IS NULL",
    ">=",
    "<=",
    "<>",
    "!=",
    "=",
    ">",
    "<",
    "LIKE",
    "NOT IN",
    "IN",
]


def _split_rule(rule: str) -> tuple[str, str]:
    """
    Split a rule string into (lhs, operator_and_rhs) for alignment.

    The lhs is everything before the first recognised SQL operator token.
    The remainder is the operator + rhs — rendered as-is after padding.

    Examples:
        "c.VersionTermDate IS NULL"       → ("c.VersionTermDate", "IS NULL")
        "ISNULL(c.DeletedFlag, 0) = 0"   → ("ISNULL(c.DeletedFlag, 0)", "= 0")
        "a_top.AccLevelConfig = 0"        → ("a_top.AccLevelConfig", "= 0")

    Falls back to splitting on the first space if no operator is found.
    """
    upper_rule = rule.upper()
    for op in _RULE_SPLIT_OPERATORS:
        # Look for " OP" (space + operator) to avoid matching inside identifiers
        search = " " + op
        idx = upper_rule.find(search)
        if idx != -1:
            lhs = rule[:idx].rstrip()
            remainder = rule[idx:].lstrip()
            return lhs, remainder

    # Fallback — no operator token found; split on first space
    parts = rule.split(" ", 1)
    if len(parts) == 2:
        return parts[0], parts[1]
    return rule, ""


def build_where(structured_query: StructuredQuery) -> str:
    """
    Build the WHERE clause from a validated StructuredQuery.

    Filter rendering:
        Each ResolvedFilter renders as one of:
          alias.ColumnName = 'value'          ← equality / comparison
          alias.ColumnName IS NULL            ← valueless operator (value ignored)
          alias.ColumnName IS NOT NULL        ← valueless operator (value ignored)

        First condition:   no connector prefix
        Subsequent conditions:   AND or OR prefix from filter.connector

    Applied rules rendering:
        Each applied_rules string is a fully-qualified SQL condition already.
        Always joined with AND. Always appended after user filters.
        Example: "c.VersionTermDate IS NULL"

    Alignment:
        All left-hand sides padded with ljust() so operators align vertically.
        For filters:  lhs = "alias.ColumnName"
        For rules:    lhs = everything before the first SQL operator token
                      (e.g. "ISNULL(c.DeletedFlag, 0)" from "ISNULL(c.DeletedFlag, 0) = 0")

    Args:
        structured_query: Validated StructuredQuery built by Story 4.5.
                          .filters       — user filter conditions (ResolvedFilter list)
                          .applied_rules — business rule SQL strings (list[str])

    Returns:
        The WHERE clause as a multi-line string, e.g.:

            WHERE
              c.CustomerCID              = 'CUST01'
              AND c.VersionTermDate      IS NULL
              AND ISNULL(c.DeletedFlag, 0) = 0
              AND c.VoidedDate           IS NULL

        Returns "" if both filters and applied_rules are empty.
        No leading or trailing newlines.
    """
    filters = structured_query.filters
    applied_rules = structured_query.applied_rules

    # ------------------------------------------------------------------
    # Nothing to render
    # ------------------------------------------------------------------
    if not filters and not applied_rules:
        return ""

    # ------------------------------------------------------------------
    # Step 1: Normalise all conditions into (connector | None, lhs, remainder)
    #
    # connector:  None  = first condition ever (no prefix emitted)
    #             "AND" = prefix with AND
    #             "OR"  = prefix with OR
    #
    # lhs:        left-hand side string used for padding width calculation
    # remainder:  operator + rhs rendered after the padded lhs
    # ------------------------------------------------------------------

    # Each entry: (connector_or_none, lhs, remainder)
    conditions: list[tuple[str | None, str, str]] = []

    # --- User filters ---
    for idx, f in enumerate(filters):
        connector: str | None = None if idx == 0 else f.connector.upper()
        lhs = f"{f.table_alias}.{f.column_name}"
        op = f.operator.upper()

        if op in _VALUELESS_OPERATORS:
            remainder = op                      # e.g. "IS NULL"
        else:
            remainder = f"{op} '{f.value}'"    # e.g. "= 'CUST01'"

        conditions.append((connector, lhs, remainder))

    # --- Applied rules ---
    for idx, rule in enumerate(applied_rules):
        # First rule is the first condition overall only when there are no filters
        if idx == 0 and not filters:
            connector = None
        else:
            connector = "AND"

        lhs, remainder = _split_rule(rule)
        conditions.append((connector, lhs, remainder))

    # ------------------------------------------------------------------
    # Step 2: Calculate alignment width
    # Width = max lhs length across ALL conditions (filters + rules)
    # ------------------------------------------------------------------
    max_width = max(len(lhs) for _, lhs, _ in conditions)

    # ------------------------------------------------------------------
    # Step 3: Render each condition line
    # ------------------------------------------------------------------
    condition_lines: list[str] = []

    for connector, lhs, remainder in conditions:
        padded_lhs = lhs.ljust(max_width)
        condition_body = f"{padded_lhs}  {remainder}"

        if connector is None:
            condition_lines.append(f"  {condition_body}")
        else:
            condition_lines.append(f"  {connector} {condition_body}")

    # ------------------------------------------------------------------
    # Step 4: Assemble and return
    # ------------------------------------------------------------------
    return "WHERE\n" + "\n".join(condition_lines)
