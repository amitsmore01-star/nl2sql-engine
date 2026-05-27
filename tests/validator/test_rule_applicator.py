# tests/validator/test_rule_applicator.py
# V0 - Initial implementation
#
# Test scenarios:
# A — Business rules (active_record)
#   A1: Customer → three active_record conditions with alias c.
#   A2: Acc (no role) → TermDate IS NULL with alias prefix
#   A3: Table with no active_record in schema → no rules added, no error
#
# B — Versioning rules
#   B1: Customer (is_versioned=true) → VersionTermDate IS NULL with alias
#   B2: Non-versioned table → no versioning condition added
#
# C — Hierarchy conditions
#   C1: Acc role top_Acc alias a_top → AccLevelConfig=0 and ParentAccID IS NULL
#   C2: Acc role sub_Acc alias a_sub → AccLevelConfig=1 and ParentAccID IS NOT NULL
#   C3: Acc with no role → no hierarchy conditions applied
#
# D — Suppress tokens
#   D1: nl_query_original contains suppress token → active_record suppressed
#   D2: No suppress token → rules applied normally
#   D3: Table has no filter_control → rules applied normally, no error
#
# E — Deduplication
#   E1: Same rule would appear twice → only once in applied_rules
#
# F — Logging
#   F1: Successful run emits VALIDATION_RESULT log with applied_rules

import pytest

from src.core.models import QueryContext
from src.validator.rule_applicator import _qualify_condition, run_rule_applicator


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_context(
    tables: list[dict],
    query: str = "give me customers in ABC",
) -> QueryContext:
    """Build a minimal QueryContext with resolved_tables pre-populated."""
    ctx = QueryContext(
        nl_query_original=query,
        app_id="ABC_app",
        app_schema_version="1.0",
    )
    ctx.resolved_tables = tables
    return ctx


# ---------------------------------------------------------------------------
# A — Business rules (active_record)
# ---------------------------------------------------------------------------

class TestActiveRecordRules:

    def test_A1_customer_active_record(self, abc_schema_repo, capturing_logger):
        """A1: Customer → three active_record conditions with alias c."""
        ctx = _make_context([
            {"table": "Major.Customer", "source": "customer", "alias": "c"}
        ])
        result = run_rule_applicator(ctx, abc_schema_repo, capturing_logger)

        assert result.status == "success"
        rules = result.applied_rules

        # Major.Customer has 3 active_record rules:
        # "VersionTermDate IS NULL", "ISNULL(DeletedFlag, 0) = 0", "VoidedDate IS NULL"
        assert any("c.VersionTermDate IS NULL" in r for r in rules)
        assert any("c.DeletedFlag" in r for r in rules)
        assert any("c.VoidedDate IS NULL" in r for r in rules)

    def test_A2_acc_active_record(self, abc_schema_repo, capturing_logger):
        """A2: Acc (no role) → TermDate IS NULL with alias prefix."""
        ctx = _make_context([
            {"table": "Major.Acc", "source": "acc", "alias": "a"}
        ])
        result = run_rule_applicator(ctx, abc_schema_repo, capturing_logger)

        assert result.status == "success"
        assert any("a.TermDate IS NULL" in r for r in result.applied_rules)

    def test_A3_table_no_active_record(self, abc_schema_repo, capturing_logger):
        """A3: Table with no active_record → no rules added, no error."""
        # Major.CustomerDemographics has no business_rules in ABC_app.json
        ctx = _make_context([
            {"table": "Major.CustomerDemographics", "source": "customer name", "alias": "cd"}
        ])
        result = run_rule_applicator(ctx, abc_schema_repo, capturing_logger)

        assert result.status == "success"
        assert result.applied_rules == []


# ---------------------------------------------------------------------------
# B — Versioning rules
# ---------------------------------------------------------------------------

class TestVersioningRules:

    def test_B1_customer_versioning(self, abc_schema_repo, capturing_logger):
        """B1: Customer (is_versioned=true) → VersionTermDate IS NULL applied."""
        ctx = _make_context([
            {"table": "Major.Customer", "source": "customer", "alias": "c"}
        ])
        result = run_rule_applicator(ctx, abc_schema_repo, capturing_logger)

        # VersionTermDate IS NULL appears (from versioning.active_condition)
        # Note: it also appears in active_record — deduplication should keep only one
        versioning_rules = [r for r in result.applied_rules if "VersionTermDate IS NULL" in r]
        assert len(versioning_rules) >= 1
        # Due to deduplication, it appears exactly once
        assert len(versioning_rules) == 1

    def test_B2_non_versioned_table(self, abc_schema_repo, capturing_logger):
        """B2: Non-versioned table → no versioning condition added."""
        # Major.Acc is not versioned
        ctx = _make_context([
            {"table": "Major.Acc", "source": "acc", "alias": "a"}
        ])
        result = run_rule_applicator(ctx, abc_schema_repo, capturing_logger)

        assert not any("VersionTermDate" in r for r in result.applied_rules)


# ---------------------------------------------------------------------------
# C — Hierarchy conditions
# ---------------------------------------------------------------------------

class TestHierarchyConditions:

    def test_C1_top_acc_conditions(self, abc_schema_repo, capturing_logger):
        """C1: Acc role top_Acc → AccLevelConfig=0 and ParentAccID IS NULL."""
        ctx = _make_context([
            {"table": "Major.Acc", "source": "top acc", "alias": "a_top", "role": "top_Acc"}
        ])
        result = run_rule_applicator(ctx, abc_schema_repo, capturing_logger)

        assert result.status == "success"
        rules = result.applied_rules
        assert any("a_top.AccLevelConfig" in r and "0" in r for r in rules)
        assert any("a_top.ParentAccID IS NULL" in r for r in rules)

    def test_C2_sub_acc_conditions(self, abc_schema_repo, capturing_logger):
        """C2: Acc role sub_Acc → AccLevelConfig=1 and ParentAccID IS NOT NULL."""
        ctx = _make_context([
            {"table": "Major.Acc", "source": "sub acc", "alias": "a_sub", "role": "sub_Acc"}
        ])
        result = run_rule_applicator(ctx, abc_schema_repo, capturing_logger)

        assert result.status == "success"
        rules = result.applied_rules
        assert any("a_sub.AccLevelConfig" in r and "1" in r for r in rules)
        assert any("a_sub.ParentAccID IS NOT NULL" in r for r in rules)

    def test_C3_acc_no_role_no_hierarchy(self, abc_schema_repo, capturing_logger):
        """C3: Acc with no role → no hierarchy conditions applied."""
        ctx = _make_context([
            {"table": "Major.Acc", "source": "acc", "alias": "a"}
            # No "role" key
        ])
        result = run_rule_applicator(ctx, abc_schema_repo, capturing_logger)

        assert not any("AccLevelConfig" in r for r in result.applied_rules)
        assert not any("ParentAccID" in r for r in result.applied_rules)


# ---------------------------------------------------------------------------
# D — Suppress tokens
# ---------------------------------------------------------------------------

class TestSuppressTokens:

    def test_D1_suppress_token_skips_active_record(self, abc_schema_repo, capturing_logger):
        """D1: Query contains suppress token → active_record rules suppressed."""
        # "history" is a suppress token for Major.Customer
        ctx = _make_context(
            [{"table": "Major.Customer", "source": "customer", "alias": "c"}],
            query="give me all customer history in ABC",
        )
        result = run_rule_applicator(ctx, abc_schema_repo, capturing_logger)

        # Active record rules should NOT be present
        # (DeletedFlag, VoidedDate come from active_record)
        assert not any("DeletedFlag" in r for r in result.applied_rules)
        assert not any("VoidedDate" in r for r in result.applied_rules)

    def test_D2_no_suppress_token_rules_applied(self, abc_schema_repo, capturing_logger):
        """D2: No suppress token → rules applied normally."""
        ctx = _make_context(
            [{"table": "Major.Customer", "source": "customer", "alias": "c"}],
            query="give me all customers in ABC",
        )
        result = run_rule_applicator(ctx, abc_schema_repo, capturing_logger)

        assert any("DeletedFlag" in r for r in result.applied_rules)
        assert any("VoidedDate" in r for r in result.applied_rules)

    def test_D3_table_no_filter_control(self, abc_schema_repo, capturing_logger):
        """D3: Table has no filter_control → rules applied normally, no error."""
        # Major.Acc has no filter_control in ABC_app.json
        ctx = _make_context(
            [{"table": "Major.Acc", "source": "acc", "alias": "a"}],
            query="give me all acc history in ABC",
        )
        result = run_rule_applicator(ctx, abc_schema_repo, capturing_logger)

        assert result.status == "success"
        # active_record rules still applied (no filter_control to suppress them)
        assert any("a.TermDate IS NULL" in r for r in result.applied_rules)


# ---------------------------------------------------------------------------
# E — Deduplication
# ---------------------------------------------------------------------------

class TestDeduplication:

    def test_E1_no_duplicate_rules(self, abc_schema_repo, capturing_logger):
        """E1: Same rule string cannot appear twice in applied_rules."""
        # Major.Customer has VersionTermDate IS NULL in BOTH
        # active_record AND versioning.active_condition
        # Deduplication must ensure it appears only once
        ctx = _make_context([
            {"table": "Major.Customer", "source": "customer", "alias": "c"}
        ])
        result = run_rule_applicator(ctx, abc_schema_repo, capturing_logger)

        # Count occurrences of VersionTermDate IS NULL
        version_rules = [r for r in result.applied_rules if "c.VersionTermDate IS NULL" in r]
        assert len(version_rules) == 1


# ---------------------------------------------------------------------------
# F — Logging
# ---------------------------------------------------------------------------

class TestLogging:

    def test_F1_emits_validation_result_log(self, abc_schema_repo, capturing_logger):
        """F1: Successful run emits VALIDATION_RESULT log with applied_rules."""
        ctx = _make_context([
            {"table": "Major.Customer", "source": "customer", "alias": "c"}
        ])
        run_rule_applicator(ctx, abc_schema_repo, capturing_logger)

        assert len(capturing_logger.entries) == 1
        entry = capturing_logger.entries[0]
        assert entry.stage == "VALIDATION_RESULT"
        assert "applied_rules" in entry.payload


# ---------------------------------------------------------------------------
# Unit tests for _qualify_condition helper
# ---------------------------------------------------------------------------

class TestQualifyCondition:

    def test_simple_column_is_null(self):
        assert _qualify_condition("VersionTermDate IS NULL", "c") == "c.VersionTermDate IS NULL"

    def test_isnull_expression_uppercase(self):
        # ISNULL uppercase — function skipped, column prefixed
        assert _qualify_condition("ISNULL(DeletedFlag, 0) = 0", "c") == "ISNULL(c.DeletedFlag, 0) = 0"

    def test_isnull_expression_lowercase(self):
        # isnull lowercase — still recognised as keyword, column still prefixed
        assert _qualify_condition("isnull(DeletedFlag, 0) = 0", "c") == "isnull(c.DeletedFlag, 0) = 0"

    def test_isnull_expression_mixed_case(self):
        # Isnull mixed case — still recognised as keyword
        assert _qualify_condition("Isnull(DeletedFlag, 0) = 0", "c") == "Isnull(c.DeletedFlag, 0) = 0"

    def test_column_equals_value(self):
        assert _qualify_condition("AccLevelConfig = 0", "a_top") == "a_top.AccLevelConfig = 0"

    def test_already_qualified_unchanged(self):
        condition = "c.VersionTermDate IS NULL"
        assert _qualify_condition(condition, "c") == condition

    def test_is_not_null(self):
        assert _qualify_condition("ParentAccID IS NOT NULL", "a_sub") == "a_sub.ParentAccID IS NOT NULL"

    def test_voided_date(self):
        assert _qualify_condition("VoidedDate IS NULL", "c") == "c.VoidedDate IS NULL"
