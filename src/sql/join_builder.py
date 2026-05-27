# src/sql/join_builder.py
# V0 - Initial implementation
#
# Join builder.
# Builds the FROM clause and all INNER JOIN blocks from a validated StructuredQuery.
#
# Single public function:
#   build_join(structured_query) -> str
#
# Responsibilities:
#   - Render the FROM line using the first entry in structured_query.tables.
#   - Render one INNER JOIN block per entry in structured_query.joins.
#   - Single-condition join:
#       INNER JOIN schema.Table alias
#         ON left = right
#   - Multi-condition join (e.g. self-join):
#       INNER JOIN schema.Table alias
#         ON left = right
#         AND left = right
#   - Preserve join order exactly as given — no sorting.
#   - Empty tables list → return empty string.
#
# This function is pure — no side effects, no logging, no LLM calls, no schema lookups.
# It reads only from StructuredQuery; all aliases and conditions were resolved by
# the validator (Stories 4.3–4.5) before this function is called.

from src.core.models import StructuredQuery


def build_join(structured_query: StructuredQuery) -> str:
    """
    Build the FROM clause and all INNER JOIN blocks from a validated StructuredQuery.

    FROM clause:
        Uses the first entry in structured_query.tables:
            FROM {table_name} {alias}

    INNER JOIN blocks:
        One block per entry in structured_query.joins.
        Single-condition:
            INNER JOIN {table_name} {alias}
              ON {left} = {right}
        Multi-condition (two or more on_conditions):
            INNER JOIN {table_name} {alias}
              ON {left0} = {right0}
              AND {left1} = {right1}

    Empty input:
        structured_query.tables is empty → returns "".

    Args:
        structured_query: Validated StructuredQuery built by Story 4.5.
                          .tables  — all tables in join order; first is the FROM table.
                          .joins   — all ResolvedJoin entries in application order.

    Returns:
        The FROM + JOIN block as a multi-line string, e.g.:

            FROM Major.Customer c
            INNER JOIN Major.CustomerDemographics cd
              ON c.CustomerID = cd.CustomerID
            INNER JOIN Major.Acc a_top
              ON c.CustomerID = a_top.CustomerID
            INNER JOIN Major.Acc a_sub
              ON a_top.AccID = a_sub.ParentAccID
              AND c.CustomerID = a_sub.CustomerID

        No leading or trailing newlines.
    """
    tables = structured_query.tables
    joins = structured_query.joins

    # ------------------------------------------------------------------
    # Empty tables → nothing to build
    # ------------------------------------------------------------------
    if not tables:
        return ""

    # ------------------------------------------------------------------
    # FROM line — first table in the list
    # ------------------------------------------------------------------
    from_table = tables[0]
    lines: list[str] = [f"FROM {from_table.table_name} {from_table.alias}"]

    # ------------------------------------------------------------------
    # INNER JOIN blocks — one per resolved join, in order
    # ------------------------------------------------------------------
    for join in joins:
        # Header line: INNER JOIN schema.Table alias
        lines.append(f"{join.join_type} {join.table_name} {join.alias}")

        # ON conditions
        conditions = join.on_conditions
        for idx, condition in enumerate(conditions):
            left = condition.get("left", "")
            right = condition.get("right", "")
            if idx == 0:
                # First condition — prefix with ON
                lines.append(f"  ON {left} = {right}")
            else:
                # Subsequent conditions — prefix with AND
                lines.append(f"  AND {left} = {right}")

    # ------------------------------------------------------------------
    # Assemble and return
    # ------------------------------------------------------------------
    return "\n".join(lines)
