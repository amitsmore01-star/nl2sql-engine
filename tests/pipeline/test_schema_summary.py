# tests/pipeline/test_schema_summary.py
# V0 - Initial implementation
# V1 - Updated test_a5 assertion: CustomerName now has two synonyms
#      ["Customer name","customername"] after "customername" was added to
#      ABC_app.json during Bug C investigation. Output is now
#      "CustomerName [Customer name, customername]".
#
# Tests for build_schema_summary() in src/pipeline/schema_summary.py
#
# Test groups:
#   A — Output content correctness (A1-A6)
#   B — Token budget (B1)
#   C — Edge cases (C1-C3)

import json
from pathlib import Path

import pytest
from src.schema.schema_models import AppSchema
from src.pipeline.schema_summary import build_schema_summary


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def load_abc_schema() -> AppSchema:
    """Load the real ABC_app.json schema — used in most tests."""
    schema_path = Path("schemas/ABC_app.json")
    with schema_path.open() as f:
        data = json.load(f)
    return AppSchema.model_validate(data)


def make_minimal_schema(tables: list[dict]) -> AppSchema:
    """Build a minimal AppSchema from a list of raw table dicts."""
    return AppSchema.model_validate({
        "appId": "test_app",
        "app_name": "Test",
        "version": "1.0",
        "tables": tables,
    })


# ---------------------------------------------------------------------------
# Group A — Output content correctness
# ---------------------------------------------------------------------------

class TestOutputContent:
    """build_schema_summary() includes the right tables, columns, and synonyms."""

    def test_a1_non_junction_tables_appear(self):
        """A1: All non-junction tables appear in the summary."""
        schema = load_abc_schema()
        result = build_schema_summary(schema)

        expected_tables = [
            "Major.Customer",
            "Major.CustomerDemographics",
            "Major.Acc",
            "Config.EnrollPlatformIndicator",
            "Major.Package",
            "Major.Plan",
        ]
        for table_name in expected_tables:
            assert table_name in result, (
                f"Expected non-junction table '{table_name}' to appear in summary"
            )

    def test_a2_junction_table_excluded(self):
        """A2: Major.PackagePlan (is_junction_table=true) is excluded from summary."""
        schema = load_abc_schema()
        result = build_schema_summary(schema)

        assert "Major.PackagePlan" not in result, (
            "Junction table 'Major.PackagePlan' must not appear in schema summary"
        )

    def test_a3_table_line_includes_name_and_synonyms(self):
        """A3: Each table line contains the table name and its synonyms in brackets."""
        schema = load_abc_schema()
        result = build_schema_summary(schema)

        # Major.Customer synonyms: Customer, customer, organization, org
        assert "table: Major.Customer [" in result
        assert "organization" in result
        assert "org" in result

        # Major.Acc synonyms: Acc, Accs, top Acc, sub Acc
        assert "table: Major.Acc [" in result
        assert "top Acc" in result
        assert "sub Acc" in result

    def test_a4_cols_line_contains_column_names(self):
        """A4: Each table block has a cols: line with all column names."""
        schema = load_abc_schema()
        result = build_schema_summary(schema)

        # CustomerDemographics columns
        assert "CustomerName" in result
        assert "CustomerLegalName" in result
        assert "CustomerDemographicsID" in result

        # Acc columns
        assert "AccName" in result
        assert "AccLevelConfig" in result
        assert "ParentAccID" in result

    def test_a5_column_synonyms_appear_in_brackets(self):
        """A5: Columns with synonyms show them in brackets after the column name."""
        schema = load_abc_schema()
        result = build_schema_summary(schema)

        # CustomerCID has synonyms: ["Customer id", "Customer cid"]
        assert "CustomerCID [Customer id, Customer cid]" in result, (
            "CustomerCID synonyms must appear in brackets in the summary"
        )

        # CustomerName has synonyms: ["Customer name", "customername"]
        # (second synonym added to ABC_app.json during Bug C investigation)
        assert "CustomerName [Customer name, customername]" in result, (
            "CustomerName synonyms must appear in brackets in the summary"
        )

    def test_a6_no_types_rules_or_versioning_in_output(self):
        """A6: Column types, business rules, and versioning config not in summary."""
        schema = load_abc_schema()
        result = build_schema_summary(schema)

        # Column types must not appear
        assert "INT" not in result
        assert "VARCHAR" not in result
        assert "DATETIME" not in result
        assert "BIT" not in result

        # Business rule SQL must not appear
        assert "VersionTermDate IS NULL" not in result
        assert "ISNULL(DeletedFlag" not in result
        assert "VoidedDate IS NULL" not in result

        # Versioning config keys must not appear
        assert "is_versioned" not in result
        assert "business_key" not in result
        assert "active_condition" not in result


# ---------------------------------------------------------------------------
# Group B — Token budget
# ---------------------------------------------------------------------------

class TestTokenBudget:
    """build_schema_summary() output stays within the LLM token budget."""

    def test_b1_output_under_1200_tokens(self):
        """B1: Full ABC_app.json summary is under ~1,200 tokens (~4,800 characters)."""
        schema = load_abc_schema()
        result = build_schema_summary(schema)

        # Approximate: 1 token ≈ 4 characters. Budget = 1,200 tokens = 4,800 chars.
        char_count = len(result)
        assert char_count < 4800, (
            f"Schema summary is {char_count} characters — exceeds ~1,200 token budget.\n"
            f"Summary:\n{result}"
        )


# ---------------------------------------------------------------------------
# Group C — Edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    """Edge cases for build_schema_summary()."""

    def test_c1_table_with_no_synonyms_shows_empty_brackets(self):
        """C1: A non-junction table with no synonyms shows empty brackets []."""
        schema = make_minimal_schema([
            {
                "name": "Major.SomeTable",
                "synonyms": [],
                "columns": [{"name": "SomeID", "type": "INT"}],
            }
        ])

        result = build_schema_summary(schema)

        assert "table: Major.SomeTable []" in result, (
            f"Expected 'table: Major.SomeTable []' in output. Got:\n{result}"
        )

    def test_c2_column_without_synonyms_shows_name_only(self):
        """C2: A column with no synonyms appears as plain name — no brackets."""
        schema = make_minimal_schema([
            {
                "name": "Major.SomeTable",
                "synonyms": ["some table"],
                "columns": [
                    {"name": "SomeID", "type": "INT"},           # no synonyms
                    {"name": "SomeName", "synonyms": ["some name"]},  # has synonym
                ],
            }
        ])

        result = build_schema_summary(schema)

        # SomeID has no synonyms — plain name only, no brackets
        assert "SomeID," in result or result.endswith("SomeID"), (
            f"SomeID should appear without brackets. Got:\n{result}"
        )
        # SomeName has a synonym — must show brackets
        assert "SomeName [some name]" in result, (
            f"SomeName synonym must appear in brackets. Got:\n{result}"
        )

    def test_c3_returns_string(self):
        """C3: build_schema_summary() accepts AppSchema and returns a non-empty str."""
        schema = load_abc_schema()
        result = build_schema_summary(schema)

        assert isinstance(result, str)
        assert len(result) > 0, "Summary must not be empty for a schema with tables"

    def test_c4_output_is_deterministic(self):
        """C4: Same input always produces the same output."""
        schema = load_abc_schema()

        result_1 = build_schema_summary(schema)
        result_2 = build_schema_summary(schema)

        assert result_1 == result_2
