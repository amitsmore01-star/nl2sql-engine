# tests/sql/test_join_builder.py
# V0 - Initial implementation
#
# Tests for src/sql/join_builder.py — build_join()
#
# All scenarios use hand-constructed StructuredQuery objects.
# No real API calls, no schema lookups, no LLM calls.
#
# Scenarios covered:
#   1. Single table, no joins
#   2. Two tables, single-condition join
#   3. Three tables, all single-condition joins
#   4. Self-join (multi-condition) — golden query (Section 9.3)
#   5. Junction table (three-way, no self-join) — Package + PackagePlan + Plan
#   6. Empty tables list
#   7. Join order preserved

import pytest

from src.core.models import ResolvedJoin, ResolvedTable, StructuredQuery
from src.sql.join_builder import build_join


# ---------------------------------------------------------------------------
# Helpers — build minimal StructuredQuery with only tables + joins populated
# ---------------------------------------------------------------------------

def _make_query(
    tables: list[ResolvedTable],
    joins: list[ResolvedJoin],
) -> StructuredQuery:
    """Build a StructuredQuery with only the fields join_builder cares about."""
    return StructuredQuery(
        app_id="Acme_app",
        tables=tables,
        joins=joins,
    )


# ---------------------------------------------------------------------------
# Scenario 1 — Single table, no joins
# ---------------------------------------------------------------------------

class TestSingleTableNoJoins:
    def test_returns_from_line_only(self):
        """Single table with no joins → only FROM line returned."""
        query = _make_query(
            tables=[ResolvedTable(table_name="Major.Customer", alias="c")],
            joins=[],
        )
        result = build_join(query)
        assert result == "FROM Major.Customer c"

    def test_no_inner_join_text(self):
        """Single table — output must not contain the word JOIN."""
        query = _make_query(
            tables=[ResolvedTable(table_name="Major.Customer", alias="c")],
            joins=[],
        )
        result = build_join(query)
        assert "JOIN" not in result


# ---------------------------------------------------------------------------
# Scenario 2 — Two tables, single-condition join
# ---------------------------------------------------------------------------

class TestTwoTablesSingleConditionJoin:
    def test_from_and_one_inner_join(self):
        """Customer + CustomerDemographics — one INNER JOIN with one ON condition."""
        query = _make_query(
            tables=[
                ResolvedTable(table_name="Major.Customer", alias="c"),
                ResolvedTable(table_name="Major.CustomerDemographics", alias="cd"),
            ],
            joins=[
                ResolvedJoin(
                    join_type="INNER JOIN",
                    table_name="Major.CustomerDemographics",
                    alias="cd",
                    on_conditions=[{"left": "c.CustomerID", "right": "cd.CustomerID"}],
                )
            ],
        )
        result = build_join(query)
        expected = (
            "FROM Major.Customer c\n"
            "INNER JOIN Major.CustomerDemographics cd\n"
            "  ON c.CustomerID = cd.CustomerID"
        )
        assert result == expected

    def test_on_keyword_present(self):
        """ON keyword must appear exactly once."""
        query = _make_query(
            tables=[
                ResolvedTable(table_name="Major.Customer", alias="c"),
                ResolvedTable(table_name="Major.CustomerDemographics", alias="cd"),
            ],
            joins=[
                ResolvedJoin(
                    join_type="INNER JOIN",
                    table_name="Major.CustomerDemographics",
                    alias="cd",
                    on_conditions=[{"left": "c.CustomerID", "right": "cd.CustomerID"}],
                )
            ],
        )
        result = build_join(query)
        assert result.count("  ON ") == 1
        assert "AND" not in result


# ---------------------------------------------------------------------------
# Scenario 3 — Three tables, all single-condition joins
# ---------------------------------------------------------------------------

class TestThreeTablesSingleConditionJoins:
    def test_from_and_two_inner_joins(self):
        """Customer + CustomerDemographics + Acc(a_top) — FROM + two INNER JOINs."""
        query = _make_query(
            tables=[
                ResolvedTable(table_name="Major.Customer", alias="c"),
                ResolvedTable(table_name="Major.CustomerDemographics", alias="cd"),
                ResolvedTable(table_name="Major.Acc", alias="a_top"),
            ],
            joins=[
                ResolvedJoin(
                    join_type="INNER JOIN",
                    table_name="Major.CustomerDemographics",
                    alias="cd",
                    on_conditions=[{"left": "c.CustomerID", "right": "cd.CustomerID"}],
                ),
                ResolvedJoin(
                    join_type="INNER JOIN",
                    table_name="Major.Acc",
                    alias="a_top",
                    on_conditions=[{"left": "c.CustomerID", "right": "a_top.CustomerID"}],
                ),
            ],
        )
        result = build_join(query)
        expected = (
            "FROM Major.Customer c\n"
            "INNER JOIN Major.CustomerDemographics cd\n"
            "  ON c.CustomerID = cd.CustomerID\n"
            "INNER JOIN Major.Acc a_top\n"
            "  ON c.CustomerID = a_top.CustomerID"
        )
        assert result == expected

    def test_two_on_keywords(self):
        """Two joins → exactly two ON keywords."""
        query = _make_query(
            tables=[
                ResolvedTable(table_name="Major.Customer", alias="c"),
                ResolvedTable(table_name="Major.CustomerDemographics", alias="cd"),
                ResolvedTable(table_name="Major.Acc", alias="a_top"),
            ],
            joins=[
                ResolvedJoin(
                    join_type="INNER JOIN",
                    table_name="Major.CustomerDemographics",
                    alias="cd",
                    on_conditions=[{"left": "c.CustomerID", "right": "cd.CustomerID"}],
                ),
                ResolvedJoin(
                    join_type="INNER JOIN",
                    table_name="Major.Acc",
                    alias="a_top",
                    on_conditions=[{"left": "c.CustomerID", "right": "a_top.CustomerID"}],
                ),
            ],
        )
        result = build_join(query)
        assert result.count("  ON ") == 2


# ---------------------------------------------------------------------------
# Scenario 4 — Self-join (multi-condition) — golden query (Section 9.3)
# ---------------------------------------------------------------------------

class TestSelfJoinGoldenQuery:
    """
    Full golden query:
        FROM Major.Customer c
        INNER JOIN Major.CustomerDemographics cd
          ON c.CustomerID = cd.CustomerID
        INNER JOIN Major.Acc a_top
          ON c.CustomerID = a_top.CustomerID
        INNER JOIN Major.Acc a_sub
          ON a_top.AccID = a_sub.ParentAccID
          AND c.CustomerID = a_sub.CustomerID
    """

    @pytest.fixture
    def golden_query(self) -> StructuredQuery:
        return _make_query(
            tables=[
                ResolvedTable(table_name="Major.Customer", alias="c"),
                ResolvedTable(table_name="Major.CustomerDemographics", alias="cd"),
                ResolvedTable(table_name="Major.Acc", alias="a_top"),
                ResolvedTable(table_name="Major.Acc", alias="a_sub"),
            ],
            joins=[
                ResolvedJoin(
                    join_type="INNER JOIN",
                    table_name="Major.CustomerDemographics",
                    alias="cd",
                    on_conditions=[{"left": "c.CustomerID", "right": "cd.CustomerID"}],
                ),
                ResolvedJoin(
                    join_type="INNER JOIN",
                    table_name="Major.Acc",
                    alias="a_top",
                    on_conditions=[{"left": "c.CustomerID", "right": "a_top.CustomerID"}],
                ),
                ResolvedJoin(
                    join_type="INNER JOIN",
                    table_name="Major.Acc",
                    alias="a_sub",
                    on_conditions=[
                        {"left": "a_top.AccID", "right": "a_sub.ParentAccID"},
                        {"left": "c.CustomerID", "right": "a_sub.CustomerID"},
                    ],
                ),
            ],
        )

    def test_exact_golden_output(self, golden_query):
        """Output must match Section 9.3 FROM+JOIN block exactly."""
        result = build_join(golden_query)
        expected = (
            "FROM Major.Customer c\n"
            "INNER JOIN Major.CustomerDemographics cd\n"
            "  ON c.CustomerID = cd.CustomerID\n"
            "INNER JOIN Major.Acc a_top\n"
            "  ON c.CustomerID = a_top.CustomerID\n"
            "INNER JOIN Major.Acc a_sub\n"
            "  ON a_top.AccID = a_sub.ParentAccID\n"
            "  AND c.CustomerID = a_sub.CustomerID"
        )
        assert result == expected

    def test_and_keyword_only_on_self_join(self, golden_query):
        """AND must appear exactly once — only on the multi-condition self-join."""
        result = build_join(golden_query)
        assert result.count("  AND ") == 1

    def test_three_on_keywords(self, golden_query):
        """Three joins → three ON keywords (one per join block, not per condition)."""
        result = build_join(golden_query)
        assert result.count("  ON ") == 3

    def test_self_join_table_appears_twice(self, golden_query):
        """Major.Acc appears twice in output — once as a_top, once as a_sub."""
        result = build_join(golden_query)
        assert "Major.Acc a_top" in result
        assert "Major.Acc a_sub" in result


# ---------------------------------------------------------------------------
# Scenario 5 — Junction table (three-way, no self-join)
# ---------------------------------------------------------------------------

class TestJunctionTableThreeWayJoin:
    """
    Package + PackagePlan (junction) + Plan
        FROM Major.Package p
        INNER JOIN Major.PackagePlan pp
          ON p.PackageId = pp.PackageId
        INNER JOIN Major.Plan pl
          ON pp.PlanId = pl.PlanId
    """

    @pytest.fixture
    def junction_query(self) -> StructuredQuery:
        return _make_query(
            tables=[
                ResolvedTable(table_name="Major.Package", alias="p"),
                ResolvedTable(table_name="Major.Plan", alias="pl"),
            ],
            joins=[
                ResolvedJoin(
                    join_type="INNER JOIN",
                    table_name="Major.PackagePlan",
                    alias="pp",
                    on_conditions=[{"left": "p.PackageId", "right": "pp.PackageId"}],
                ),
                ResolvedJoin(
                    join_type="INNER JOIN",
                    table_name="Major.Plan",
                    alias="pl",
                    on_conditions=[{"left": "pp.PlanId", "right": "pl.PlanId"}],
                ),
            ],
        )

    def test_exact_junction_output(self, junction_query):
        """FROM Package + two INNER JOINs bridging via PackagePlan."""
        result = build_join(junction_query)
        expected = (
            "FROM Major.Package p\n"
            "INNER JOIN Major.PackagePlan pp\n"
            "  ON p.PackageId = pp.PackageId\n"
            "INNER JOIN Major.Plan pl\n"
            "  ON pp.PlanId = pl.PlanId"
        )
        assert result == expected

    def test_no_and_keyword(self, junction_query):
        """No self-join → no AND keyword in output."""
        result = build_join(junction_query)
        assert "AND" not in result


# ---------------------------------------------------------------------------
# Scenario 6 — Empty tables list
# ---------------------------------------------------------------------------

class TestEmptyTablesList:
    def test_empty_tables_returns_empty_string(self):
        """No tables → returns empty string, no crash."""
        query = _make_query(tables=[], joins=[])
        result = build_join(query)
        assert result == ""

    def test_empty_tables_is_string_type(self):
        """Return type is always str even when empty."""
        query = _make_query(tables=[], joins=[])
        result = build_join(query)
        assert isinstance(result, str)


# ---------------------------------------------------------------------------
# Scenario 7 — Join order preserved
# ---------------------------------------------------------------------------

class TestJoinOrderPreserved:
    def test_joins_appear_in_input_order(self):
        """
        Three joins provided A → B → C.
        Output must list them A → B → C — no sorting or reordering.
        """
        query = _make_query(
            tables=[
                ResolvedTable(table_name="Major.Customer", alias="c"),
                ResolvedTable(table_name="Major.CustomerDemographics", alias="cd"),
                ResolvedTable(table_name="Major.Acc", alias="a_top"),
                ResolvedTable(table_name="Major.Package", alias="p"),
            ],
            joins=[
                ResolvedJoin(
                    join_type="INNER JOIN",
                    table_name="Major.CustomerDemographics",
                    alias="cd",
                    on_conditions=[{"left": "c.CustomerID", "right": "cd.CustomerID"}],
                ),
                ResolvedJoin(
                    join_type="INNER JOIN",
                    table_name="Major.Acc",
                    alias="a_top",
                    on_conditions=[{"left": "c.CustomerID", "right": "a_top.CustomerID"}],
                ),
                ResolvedJoin(
                    join_type="INNER JOIN",
                    table_name="Major.Package",
                    alias="p",
                    on_conditions=[{"left": "c.CustomerID", "right": "p.CustomerID"}],
                ),
            ],
        )
        result = build_join(query)
        lines = result.splitlines()

        # Find the positions of each JOIN header
        cd_pos = next(i for i, l in enumerate(lines) if "CustomerDemographics cd" in l)
        acc_pos = next(i for i, l in enumerate(lines) if "Acc a_top" in l)
        pkg_pos = next(i for i, l in enumerate(lines) if "Package p" in l)

        assert cd_pos < acc_pos < pkg_pos
