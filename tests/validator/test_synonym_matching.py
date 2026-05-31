# tests/validator/test_synonym_matching.py
# V0 - Initial implementation (Story 5.9, Bug #13)
#
# Tests for src/validator/synonym_matching.py — the shared matcher module.
#
# Uses the real ABC_app.json schema via the abc_schema_repo fixture.
#
# Scenarios:
#   HM-1 — match_hierarchy_role("top acc", Acc)        -> "top_Acc"
#   HM-2 — match_hierarchy_role("sub acc", Acc)        -> "sub_Acc"
#   HM-3 — match_hierarchy_role("acc", Acc)            -> None  (no level word)
#   HM-4 — match_hierarchy_role("subaccount", Acc)     -> None  (fused — Bug #14, Phase 2)
#   HM-5 — table_has_hierarchy(Acc) True; (Customer) False
#   HM-6 — match_table_reference("top acc", Acc)       -> True  (table synonym)
#   HM-7 — match_table_reference("accKey", Acc)        -> False (column synonym, not table)
#   HM-8 — match_table_reference("customer", Customer) -> True

import pytest

from src.validator.synonym_matching import (
    match_hierarchy_role,
    match_table_reference,
    table_has_hierarchy,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _table(schema_repo, name: str):
    """Fetch a TableSchema by name from the ABC_app schema."""
    app_schema = schema_repo.get_schema("ABC_app")
    for t in app_schema.tables:
        if t.name == name:
            return t
    raise AssertionError(f"Table {name} not found in ABC_app schema")


# ---------------------------------------------------------------------------
# Hierarchy role matching
# ---------------------------------------------------------------------------

class TestHierarchyRoleMatching:

    def test_HM1_top_acc_matches_top_role(self, abc_schema_repo):
        acc = _table(abc_schema_repo, "Major.Acc")
        assert match_hierarchy_role("top acc", acc) == "top_Acc"

    def test_HM2_sub_acc_matches_sub_role(self, abc_schema_repo):
        acc = _table(abc_schema_repo, "Major.Acc")
        assert match_hierarchy_role("sub acc", acc) == "sub_Acc"

    def test_HM3_bare_acc_matches_no_role(self, abc_schema_repo):
        acc = _table(abc_schema_repo, "Major.Acc")
        # "acc" alone carries no level word (top/sub) → no role
        assert match_hierarchy_role("acc", acc) is None

    def test_HM4_fused_subaccount_matches_no_role(self, abc_schema_repo):
        """Documents Bug #14: fused words do not match under whole-word matching."""
        acc = _table(abc_schema_repo, "Major.Acc")
        assert match_hierarchy_role("subaccount", acc) is None


# ---------------------------------------------------------------------------
# table_has_hierarchy
# ---------------------------------------------------------------------------

class TestTableHasHierarchy:

    def test_HM5_acc_has_hierarchy_customer_does_not(self, abc_schema_repo):
        acc = _table(abc_schema_repo, "Major.Acc")
        customer = _table(abc_schema_repo, "Major.Customer")
        assert table_has_hierarchy(acc) is True
        assert table_has_hierarchy(customer) is False

    def test_HM5b_none_schema_returns_false(self):
        assert table_has_hierarchy(None) is False


# ---------------------------------------------------------------------------
# table reference matching
# ---------------------------------------------------------------------------

class TestTableReferenceMatching:

    def test_HM6_top_acc_matches_acc_table(self, abc_schema_repo):
        acc = _table(abc_schema_repo, "Major.Acc")
        # "top acc" → table synonym "top Acc"
        assert match_table_reference("top acc", acc) is True

    def test_HM7_acckey_does_not_match_acc_table(self, abc_schema_repo):
        """accKey is a column synonym, NOT a table synonym → must not match the table."""
        acc = _table(abc_schema_repo, "Major.Acc")
        assert match_table_reference("accKey", acc) is False

    def test_HM8_customer_matches_customer_table(self, abc_schema_repo):
        customer = _table(abc_schema_repo, "Major.Customer")
        assert match_table_reference("customer", customer) is True
