# src/sql/select_builder.py
# V0 - Initial implementation
#
# Select builder.
# Builds the SELECT clause (including TOP guard) from a validated StructuredQuery.
#
# Single public function:
#   build_select(structured_query, default_top_rows) -> str
#
# Responsibilities:
#   - Apply TOP guard: use structured_query.top_rows if set by user,
#     otherwise fall back to default_top_rows from settings.
#     If the effective top value is 0 → omit TOP clause entirely.
#   - Render each column as:  alias.ColumnName  AS OutputAlias
#   - Align AS keywords by padding all "alias.ColumnName" parts to the same width.
#   - Return only the SELECT ... clause — no FROM, no JOIN, no WHERE.
#     SQL builder (Story 5.4) assembles the full statement.
#
# This function is pure — no side effects, no logging, no LLM calls, no schema lookups.
# It trusts output_alias exactly as given — defaulting to column_name is the
# responsibility of structured_query_builder.py (Story 4.5), not this function.

from src.core.models import StructuredQuery


def build_select(
    structured_query: StructuredQuery,
    default_top_rows: int,
) -> str:
    """
    Build the SELECT clause from a validated StructuredQuery.

    TOP logic:
        structured_query.top_rows is not None  → use that value (user specified)
        structured_query.top_rows is None       → use default_top_rows (from settings)
        effective value == 0                    → omit TOP clause entirely

    Column rendering:
        Each column renders as:  {table_alias}.{column_name}  AS {output_alias}
        All left-hand sides (alias.column) are padded to the same width so the
        AS keywords align vertically — matching the golden SQL in Section 9.3.

    Args:
        structured_query:  Validated StructuredQuery built by Story 4.5.
        default_top_rows:  Fallback TOP value from settings (e.g. 10000).
                           Pass 0 to disable TOP entirely when no user limit is set.

    Returns:
        The SELECT clause as a multi-line string, e.g.:
            SELECT TOP 10000
              cd.CustomerName  AS CustomerName,
              a_top.AccName    AS TopAccName,
              a_sub.AccName    AS SubAccName

        Trailing comma is on every line except the last.
        No trailing newline at the end of the returned string.
    """
    # ------------------------------------------------------------------
    # Determine effective TOP value
    # ------------------------------------------------------------------
    if structured_query.top_rows is not None:
        effective_top = structured_query.top_rows
    else:
        effective_top = default_top_rows

    # ------------------------------------------------------------------
    # Build SELECT header line
    # ------------------------------------------------------------------
    if effective_top and effective_top > 0:
        header = f"SELECT TOP {effective_top}"
    else:
        header = "SELECT"

    # ------------------------------------------------------------------
    # Build column lines
    # ------------------------------------------------------------------
    columns = structured_query.columns

    if not columns:
        return header

    # Render the left-hand side of each column: "alias.ColumnName"
    # These are padded so all AS keywords line up.
    left_parts = [
        f"{col.table_alias}.{col.column_name}"
        for col in columns
    ]

    # Width of the longest left-hand side — used for padding
    max_width = max(len(part) for part in left_parts)

    # Build each column line
    col_lines = []
    for i, col in enumerate(columns):
        left = left_parts[i]
        padded_left = left.ljust(max_width)
        is_last = (i == len(columns) - 1)
        trailing = "" if is_last else ","
        col_lines.append(f"  {padded_left}  AS {col.output_alias}{trailing}")

    # ------------------------------------------------------------------
    # Assemble and return
    # ------------------------------------------------------------------
    return header + "\n" + "\n".join(col_lines)
