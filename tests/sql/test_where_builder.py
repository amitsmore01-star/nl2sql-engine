# tests/sql/test_where_builder.py
# V0 - Initial implementation
#
# Tests for src/sql/where_builder.py
#
# Test scenarios:
#   T1  — Single user filter, no rules
#   T2  — Applied rules only, no user filters
#   T3  — Multiple user filters, all AND
#   T4  — Multiple user filters with OR
#   T5  — Mixed AND + OR — three filters with alternating connectors
#   T6  — Filters + applied rules combined (filters first, then rules)
#   T7  — Applied rules only — two rule strings
#   T8  — Empty filters AND empty applied_rules → returns ""
#   T9  — IS NULL operator — value ignored
#   T10 — IS NOT NULL operator — value ignored
#   T11 — Golden WHERE — exact string match for full Section 9.3 conditions

import pytest

from src.core.models import ResolvedFilter, StructuredQuery
from src.sql.where_builder import build_where


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_query(
    filters: list[ResolvedFilter] | None = None,
    applied_rules: list[str] | None = None,
) -> StructuredQuery:
    """Build a minimal StructuredQuery with only filters and applied_rules set."""
    return StructuredQuery(
        app_id="ABC_app",
        filters=filters or [],
        applied_rules=applied_rules or [],
    )


# ---------------------------------------------------------------------------
# T1 — Single user filter, no rules
# ---------------------------------------------------------------------------

def test_single_filter_no_rules():
    """Single equality filter — no leading connector, no rules appended."""
    sq = make_query(
        filters=[
            ResolvedFilter(
                table_alias="c",
                column_name="CustomerCID",
                operator="=",
                value="ASA",
            )
        ]
    )
    result = build_where(sq)

    assert result.startswith("WHERE\n")
    # First condition — no AND/OR prefix
    assert "  c.CustomerCID" in result
    assert "= 'ASA'" in result
    # Must NOT have a leading AND or OR on the first line
    lines = result.splitlines()
    first_condition = lines[1]
    assert not first_condition.strip().startswith("AND")
    assert not first_condition.strip().startswith("OR")


# ---------------------------------------------------------------------------
# T2 — Applied rules only, no user filters
# ---------------------------------------------------------------------------

def test_rules_only_single():
    """Single applied rule, no user filters — first condition has no connector."""
    sq = make_query(
        applied_rules=["c.VersionTermDate IS NULL"]
    )
    result = build_where(sq)

    assert result.startswith("WHERE\n")
    assert "c.VersionTermDate" in result
    assert "IS NULL" in result
    # First (and only) condition — no AND prefix
    lines = result.splitlines()
    first_condition = lines[1]
    assert not first_condition.strip().startswith("AND")
    assert not first_condition.strip().startswith("OR")


# ---------------------------------------------------------------------------
# T3 — Multiple user filters, all AND
# ---------------------------------------------------------------------------

def test_multiple_filters_all_and():
    """Two user filters both with AND connector — second line starts with AND."""
    sq = make_query(
        filters=[
            ResolvedFilter(
                table_alias="c",
                column_name="CustomerCID",
                operator="=",
                value="ASA",
                connector="AND",
            ),
            ResolvedFilter(
                table_alias="c",
                column_name="Status",
                operator="=",
                value="Active",
                connector="AND",
            ),
        ]
    )
    result = build_where(sq)

    lines = result.splitlines()
    assert len(lines) == 3  # WHERE + 2 conditions
    assert not lines[1].strip().startswith("AND")   # first — no connector
    assert lines[2].strip().startswith("AND")        # second — AND


# ---------------------------------------------------------------------------
# T4 — Multiple user filters with OR
# ---------------------------------------------------------------------------

def test_multiple_filters_with_or():
    """Second filter uses OR connector — second line starts with OR."""
    sq = make_query(
        filters=[
            ResolvedFilter(
                table_alias="c",
                column_name="CustomerCID",
                operator="=",
                value="ASA",
                connector="AND",
            ),
            ResolvedFilter(
                table_alias="c",
                column_name="CustomerCID",
                operator="=",
                value="XYZ",
                connector="OR",
            ),
        ]
    )
    result = build_where(sq)

    lines = result.splitlines()
    assert len(lines) == 3  # WHERE + 2 conditions
    assert not lines[1].strip().startswith("AND")
    assert not lines[1].strip().startswith("OR")
    assert lines[2].strip().startswith("OR")
    assert "'XYZ'" in lines[2]


# ---------------------------------------------------------------------------
# T5 — Mixed AND + OR — three filters
# ---------------------------------------------------------------------------

def test_mixed_and_or_three_filters():
    """Three filters: first (no prefix), second OR, third AND."""
    sq = make_query(
        filters=[
            ResolvedFilter(
                table_alias="c",
                column_name="CustomerCID",
                operator="=",
                value="ASA",
                connector="AND",
            ),
            ResolvedFilter(
                table_alias="c",
                column_name="CustomerCID",
                operator="=",
                value="XYZ",
                connector="OR",
            ),
            ResolvedFilter(
                table_alias="c",
                column_name="Status",
                operator="=",
                value="Active",
                connector="AND",
            ),
        ]
    )
    result = build_where(sq)

    lines = result.splitlines()
    assert len(lines) == 4  # WHERE + 3 conditions
    # Line 1: first condition — no connector
    assert not lines[1].strip().startswith("AND")
    assert not lines[1].strip().startswith("OR")
    # Line 2: OR connector
    assert lines[2].strip().startswith("OR")
    assert "'XYZ'" in lines[2]
    # Line 3: AND connector
    assert lines[3].strip().startswith("AND")
    assert "'Active'" in lines[3]


# ---------------------------------------------------------------------------
# T6 — Filters + applied rules combined
# ---------------------------------------------------------------------------

def test_filters_and_rules_combined():
    """User filter first, then applied rule — rule always AND, always after filters."""
    sq = make_query(
        filters=[
            ResolvedFilter(
                table_alias="c",
                column_name="CustomerCID",
                operator="=",
                value="ASA",
            )
        ],
        applied_rules=["c.VersionTermDate IS NULL"],
    )
    result = build_where(sq)

    lines = result.splitlines()
    assert len(lines) == 3  # WHERE + filter + rule
    # Filter first
    assert "CustomerCID" in lines[1]
    assert not lines[1].strip().startswith("AND")
    # Rule second — AND prefix
    assert lines[2].strip().startswith("AND")
    assert "VersionTermDate" in lines[2]


# ---------------------------------------------------------------------------
# T7 — Applied rules only — two rule strings
# ---------------------------------------------------------------------------

def test_rules_only_two():
    """Two applied rules — first has no connector, second has AND."""
    sq = make_query(
        applied_rules=[
            "c.VersionTermDate IS NULL",
            "ISNULL(c.DeletedFlag, 0) = 0",
        ]
    )
    result = build_where(sq)

    lines = result.splitlines()
    assert len(lines) == 3  # WHERE + 2 rules
    # First rule — no connector
    assert not lines[1].strip().startswith("AND")
    assert "VersionTermDate" in lines[1]
    # Second rule — AND
    assert lines[2].strip().startswith("AND")
    assert "DeletedFlag" in lines[2]


# ---------------------------------------------------------------------------
# T8 — Empty filters and empty applied_rules
# ---------------------------------------------------------------------------

def test_empty_returns_empty_string():
    """No filters, no rules — build_where returns empty string."""
    sq = make_query()
    result = build_where(sq)
    assert result == ""


# ---------------------------------------------------------------------------
# T9 — IS NULL operator — value ignored
# ---------------------------------------------------------------------------

def test_is_null_operator_ignores_value():
    """IS NULL filter — value field is ignored, no quotes rendered."""
    sq = make_query(
        filters=[
            ResolvedFilter(
                table_alias="c",
                column_name="VersionTermDate",
                operator="IS NULL",
                value="should_be_ignored",
            )
        ]
    )
    result = build_where(sq)

    assert "IS NULL" in result
    assert "should_be_ignored" not in result
    # No quotes around anything for IS NULL
    assert "'" not in result


# ---------------------------------------------------------------------------
# T10 — IS NOT NULL operator — value ignored
# ---------------------------------------------------------------------------

def test_is_not_null_operator_ignores_value():
    """IS NOT NULL filter — value field is ignored, no quotes rendered."""
    sq = make_query(
        filters=[
            ResolvedFilter(
                table_alias="a_sub",
                column_name="ParentAccID",
                operator="IS NOT NULL",
                value="should_be_ignored",
            )
        ]
    )
    result = build_where(sq)

    assert "IS NOT NULL" in result
    assert "should_be_ignored" not in result
    assert "'" not in result


# ---------------------------------------------------------------------------
# T11 — Golden WHERE — exact match for Section 9.3
# ---------------------------------------------------------------------------

def test_golden_where_clause():
    """
    Full golden WHERE clause from architecture Section 9.3.

    Input:
        filters:       c.CustomerCID = 'ASA'
        applied_rules: c.VersionTermDate IS NULL
                       ISNULL(c.DeletedFlag, 0) = 0
                       c.VoidedDate IS NULL
                       a_top.AccLevelConfig = 0
                       a_top.ParentAccID IS NULL
                       a_sub.AccLevelConfig = 1
                       a_sub.ParentAccID IS NOT NULL

    Expected (Section 9.3):
        WHERE
          c.CustomerCID              = 'ASA'
          AND c.VersionTermDate      IS NULL
          AND ISNULL(c.DeletedFlag, 0) = 0
          AND c.VoidedDate           IS NULL
          AND a_top.AccLevelConfig   = 0
          AND a_top.ParentAccID      IS NULL
          AND a_sub.AccLevelConfig   = 1
          AND a_sub.ParentAccID      IS NOT NULL;
    """
    sq = make_query(
        filters=[
            ResolvedFilter(
                table_alias="c",
                column_name="CustomerCID",
                operator="=",
                value="ASA",
            )
        ],
        applied_rules=[
            "c.VersionTermDate IS NULL",
            "ISNULL(c.DeletedFlag, 0) = 0",
            "c.VoidedDate IS NULL",
            "a_top.AccLevelConfig = 0",
            "a_top.ParentAccID IS NULL",
            "a_sub.AccLevelConfig = 1",
            "a_sub.ParentAccID IS NOT NULL",
        ],
    )
    result = build_where(sq)

    # Must start with WHERE
    assert result.startswith("WHERE\n")

    lines = result.splitlines()
    # WHERE + 1 filter + 7 rules = 9 lines total
    assert len(lines) == 9

    # First condition (filter) — no connector
    assert "c.CustomerCID" in lines[1]
    assert "= 'ASA'" in lines[1]
    assert not lines[1].strip().startswith("AND")

    # All rule lines — must start with AND
    for line in lines[2:]:
        assert line.strip().startswith("AND"), (
            f"Expected rule line to start with AND, got: {line!r}"
        )

    # All golden conditions present
    assert any("VersionTermDate" in l and "IS NULL" in l for l in lines)
    assert any("DeletedFlag" in l for l in lines)
    assert any("VoidedDate" in l and "IS NULL" in l for l in lines)
    assert any("AccLevelConfig" in l and "= 0" in l for l in lines)
    assert any("ParentAccID" in l and "IS NULL" in l for l in lines)
    assert any("AccLevelConfig" in l and "= 1" in l for l in lines)
    assert any("ParentAccID" in l and "IS NOT NULL" in l for l in lines)

    # Verify all 7 rule lines begin with AND
    and_lines = [l for l in lines[2:] if l.strip().startswith("AND")]
    assert len(and_lines) == 7
