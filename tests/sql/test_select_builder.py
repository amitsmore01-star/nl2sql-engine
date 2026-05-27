# tests/sql/test_select_builder.py
# V0 - Initial implementation
#
# Tests for src/sql/select_builder.py
#
# Scenarios:
#   S1 — Single column, default TOP applied
#   S2 — Multiple columns from different table aliases, default TOP applied
#   S3 — User-specified top_rows overrides default
#   S4 — default_top_rows=0 → no TOP clause
#   S5 — User-specified top_rows=0 → no TOP clause
#   S6 — Empty columns list → header only, no crash
#   S7 — Column alignment — AS keywords padded to same width
#   S8 — Golden scenario matching architecture Section 9.3 SELECT clause

import pytest

from src.core.models import ResolvedColumn, StructuredQuery
from src.sql.select_builder import build_select


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_col(table_alias: str, column_name: str, output_alias: str) -> ResolvedColumn:
    """Shorthand to build a ResolvedColumn for tests."""
    return ResolvedColumn(
        table_alias=table_alias,
        column_name=column_name,
        output_alias=output_alias,
    )


def _make_query(
    columns: list[ResolvedColumn],
    top_rows: int | None = None,
) -> StructuredQuery:
    """Shorthand to build a minimal StructuredQuery with only columns set."""
    return StructuredQuery(
        app_id="ABC_app",
        top_rows=top_rows,
        columns=columns,
    )


# ---------------------------------------------------------------------------
# S1 — Single column, default TOP applied
# ---------------------------------------------------------------------------

def test_s1_single_column_default_top():
    """
    One column, top_rows=None — default_top_rows=10000 must appear in header.
    Column rendered as: alias.ColumnName  AS OutputAlias
    """
    sq = _make_query(
        columns=[_make_col("c", "CustomerID", "CustomerID")],
        top_rows=None,
    )
    result = build_select(sq, default_top_rows=10000)

    lines = result.splitlines()
    assert lines[0] == "SELECT TOP 10000"
    assert "c.CustomerID" in lines[1]
    assert "AS CustomerID" in lines[1]
    # Single column — no trailing comma
    assert not lines[1].rstrip().endswith(",")


# ---------------------------------------------------------------------------
# S2 — Multiple columns from different table aliases, default TOP applied
# ---------------------------------------------------------------------------

def test_s2_multiple_columns_default_top():
    """
    Three columns from three different aliases.
    All rendered in order, last line has no trailing comma, others do.
    """
    sq = _make_query(
        columns=[
            _make_col("c",  "CustomerID",   "CustomerID"),
            _make_col("cd", "CustomerName", "CustomerName"),
            _make_col("a",  "AccName",      "AccName"),
        ],
        top_rows=None,
    )
    result = build_select(sq, default_top_rows=10000)

    lines = result.splitlines()
    assert lines[0] == "SELECT TOP 10000"
    assert len(lines) == 4  # header + 3 column lines

    assert "c.CustomerID" in lines[1]
    assert "cd.CustomerName" in lines[2]
    assert "a.AccName" in lines[3]

    # Trailing commas: lines 1 and 2 have comma, line 3 does not
    assert lines[1].rstrip().endswith(",")
    assert lines[2].rstrip().endswith(",")
    assert not lines[3].rstrip().endswith(",")


# ---------------------------------------------------------------------------
# S3 — User-specified top_rows overrides default
# ---------------------------------------------------------------------------

def test_s3_user_top_rows_overrides_default():
    """
    top_rows=5 on the StructuredQuery — must use 5, not the default 10000.
    """
    sq = _make_query(
        columns=[_make_col("c", "CustomerID", "CustomerID")],
        top_rows=5,
    )
    result = build_select(sq, default_top_rows=10000)

    assert result.startswith("SELECT TOP 5")
    assert "SELECT TOP 10000" not in result


# ---------------------------------------------------------------------------
# S4 — default_top_rows=0 → no TOP clause
# ---------------------------------------------------------------------------

def test_s4_default_top_rows_zero_omits_top():
    """
    top_rows=None and default_top_rows=0 → SELECT with no TOP keyword.
    """
    sq = _make_query(
        columns=[_make_col("c", "CustomerID", "CustomerID")],
        top_rows=None,
    )
    result = build_select(sq, default_top_rows=0)

    lines = result.splitlines()
    assert lines[0] == "SELECT"
    assert "TOP" not in lines[0]


# ---------------------------------------------------------------------------
# S5 — User-specified top_rows=0 → no TOP clause
# ---------------------------------------------------------------------------

def test_s5_user_top_rows_zero_omits_top():
    """
    top_rows=0 explicitly set — even though default is 10000, no TOP clause.
    """
    sq = _make_query(
        columns=[_make_col("c", "CustomerID", "CustomerID")],
        top_rows=0,
    )
    result = build_select(sq, default_top_rows=10000)

    lines = result.splitlines()
    assert lines[0] == "SELECT"
    assert "TOP" not in lines[0]


# ---------------------------------------------------------------------------
# S6 — Empty columns list → header only, no crash
# ---------------------------------------------------------------------------

def test_s6_empty_columns_returns_header_only():
    """
    No columns in StructuredQuery — function must not crash.
    Returns just the SELECT TOP N header with no column lines.
    """
    sq = _make_query(columns=[], top_rows=None)
    result = build_select(sq, default_top_rows=10000)

    assert result == "SELECT TOP 10000"


# ---------------------------------------------------------------------------
# S7 — Column alignment — AS keywords align vertically
# ---------------------------------------------------------------------------

def test_s7_column_alignment():
    """
    Columns with left-hand sides of different lengths.
    All AS keywords must start at the same character position.
    This verifies the ljust padding logic.
    """
    sq = _make_query(
        columns=[
            _make_col("c",    "CustomerID",   "CustomerID"),    # "c.CustomerID"    = 13 chars
            _make_col("cd",   "CustomerName", "CustomerName"),  # "cd.CustomerName"  = 16 chars
            _make_col("a_top","AccName",      "TopAccName"),    # "a_top.AccName"   = 14 chars
        ],
        top_rows=None,
    )
    result = build_select(sq, default_top_rows=10000)

    lines = result.splitlines()
    col_lines = lines[1:]  # skip header

    # Find the position of "AS" in each column line
    as_positions = [line.index(" AS ") for line in col_lines]

    # All AS keywords must be at the same position
    assert len(set(as_positions)) == 1, (
        f"AS keywords not aligned — positions: {as_positions}\n"
        f"Output:\n{result}"
    )


# ---------------------------------------------------------------------------
# S8 — Golden scenario — architecture Section 9.3 SELECT clause
# ---------------------------------------------------------------------------

def test_s8_golden_select_clause():
    """
    Golden scenario from architecture document Section 9.3.

    Input NL: "give me customer name, top acc and sub acc for customer ASA in ABC"

    Expected SELECT clause (exactly):
        SELECT TOP 10000
          cd.CustomerName  AS CustomerName,
          a_top.AccName    AS TopAccName,
          a_sub.AccName    AS SubAccName

    output_alias is set explicitly here to match the golden output —
    this tests that select_builder trusts output_alias as given.
    The structured_query_builder (Story 4.5) owns the defaulting behaviour.
    In the full pipeline, the two AccName columns will have distinct output_aliases
    assigned before this stage is reached.
    """
    sq = _make_query(
        columns=[
            _make_col("cd",    "CustomerName", "CustomerName"),
            _make_col("a_top", "AccName",      "TopAccName"),
            _make_col("a_sub", "AccName",      "SubAccName"),
        ],
        top_rows=None,
    )
    result = build_select(sq, default_top_rows=10000)

    lines = result.splitlines()

    # Header
    assert lines[0] == "SELECT TOP 10000"

    # Three column lines
    assert len(lines) == 4

    # Each column present with correct alias and output alias
    assert "cd.CustomerName" in lines[1]
    assert "AS CustomerName" in lines[1]
    assert lines[1].rstrip().endswith(",")

    assert "a_top.AccName" in lines[2]
    assert "AS TopAccName" in lines[2]
    assert lines[2].rstrip().endswith(",")

    assert "a_sub.AccName" in lines[3]
    assert "AS SubAccName" in lines[3]
    assert not lines[3].rstrip().endswith(",")

    # AS keywords all aligned (same position in each column line)
    col_lines = lines[1:]
    as_positions = [line.index(" AS ") for line in col_lines]
    assert len(set(as_positions)) == 1, (
        f"AS keywords not aligned in golden output — positions: {as_positions}\n"
        f"Output:\n{result}"
    )
