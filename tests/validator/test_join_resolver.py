# tests/validator/test_join_resolver.py
# V0 - Initial implementation
# V1 - Story 4.5: Added class H -- Role stamping on columns and filters (H1, H2, H3)
# V2 - Story 5.9: Added class I -- Single-instance hierarchy role stamping (JR-S1 to JR-S4)
# V3 - Story 5.9 (cont.): Added JR-S5 to JR-S8 -- role stamping on columns/filters
#      for single-instance hierarchy tables (fixes empty-alias ".AccName" bug)
# V4 - Bug fix (deferred join): Added class J (TestDeferredJoin) -- 8 tests.
#      J1-J4 test multi-pass deferred resolution and true no-path detection.
#      J5-J8 are regression guards confirming direct join, ordered join, self-join,
#      and junction bridge all still produce identical output after the algorithm change.
#
# Test scenarios:
# A -- Single table (no join needed)
#   A1: Single table -> resolved_joins = [], alias assigned, status = "success"
#
# B -- Direct joins
#   B1: Customer + CustomerDemographics -> one INNER JOIN, on_conditions with CustomerID
#   B2: Customer + Acc (single, no hierarchy) -> one INNER JOIN on CustomerID
#   B3: Customer + CustomerDemographics + Acc -> two INNER JOINs
#
# C -- Self-join with hierarchy role assignment
#   C1: Acc twice, "top acc" + "sub acc" -> roles top_Acc + sub_Acc, aliases a_top + a_sub
#   C1 extended: self-join on_conditions has AccID -> ParentAccID AND CustomerID -> CustomerID
#   C2: Acc twice, source matches no synonym -> role=None, warning logged
#   C3: Full golden query -- Customer + CustomerDemographics + Acc(top) + Acc(sub)
#
# D -- Junction table auto-bridging
#   D1: Package + Plan -> PackagePlan auto-inserted, two joins produced
#   D2: Junction table does NOT appear in resolved_tables after bridging
#
# E -- No join path
#   E1: Two tables with no relationship -> NoJoinPathError raised
#
# F -- Alias generation
#   F1: CamelCase display_name -> initials e.g. CustomerDemographics -> cd
#   F2: Underscore display_name -> first letter each part
#   F3: All-lowercase display_name -> first 3 chars
#   F4: Collision -> second table gets _2 suffix
#
# G -- Logging
#   G1: Successful run emits VALIDATION_RESULT log

import pytest

from src.core.exceptions import NoJoinPathError
from src.core.models import QueryContext
from src.validator.join_resolver import (
    _build_alias_candidate,
    _resolve_alias,
    run_join_resolver,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_context(tables: list, query: str = "test query") -> QueryContext:
    ctx = QueryContext(
        nl_query_original=query,
        app_id="Acme_app",
        app_schema_version="1.0",
    )
    ctx.resolved_tables = tables
    return ctx


# ---------------------------------------------------------------------------
# A -- Single table
# ---------------------------------------------------------------------------

class TestSingleTable:

    def test_A1_single_table_no_joins(self, abc_schema_repo, capturing_logger):
        """A1: Single table -> resolved_joins = [], alias assigned, status = success."""
        ctx = _make_context([
            {"table": "Major.Customer", "source": "customer"}
        ])
        result = run_join_resolver(ctx, abc_schema_repo, capturing_logger)

        assert result.resolved_joins == []
        assert result.status == "success"
        assert result.resolved_tables[0]["alias"] == "c"


# ---------------------------------------------------------------------------
# B -- Direct joins
# ---------------------------------------------------------------------------

class TestDirectJoins:

    def test_B1_customer_and_demographics(self, abc_schema_repo, capturing_logger):
        """B1: Customer + CustomerDemographics -> one INNER JOIN with on_conditions."""
        ctx = _make_context([
            {"table": "Major.Customer", "source": "customer"},
            {"table": "Major.CustomerDemographics", "source": "customer name"},
        ])
        result = run_join_resolver(ctx, abc_schema_repo, capturing_logger)

        assert result.status == "success"
        assert len(result.resolved_joins) == 1

        join = result.resolved_joins[0]
        assert join["join_type"] == "INNER JOIN"
        assert join["table_name"] == "Major.CustomerDemographics"
        assert join["alias"] == "cd"
        assert "on_conditions" in join
        assert len(join["on_conditions"]) >= 1
        # CustomerID must appear in the condition
        cond = join["on_conditions"][0]
        assert "CustomerID" in cond["left"]
        assert "CustomerID" in cond["right"]

        aliases = {e["alias"] for e in result.resolved_tables}
        assert "c" in aliases
        assert "cd" in aliases

    def test_B2_customer_and_acc_single(self, abc_schema_repo, capturing_logger):
        """B2: Customer + Acc (single instance) -> one INNER JOIN on CustomerID."""
        ctx = _make_context([
            {"table": "Major.Customer", "source": "customer"},
            {"table": "Major.Acc", "source": "acc"},
        ])
        result = run_join_resolver(ctx, abc_schema_repo, capturing_logger)

        assert result.status == "success"
        assert len(result.resolved_joins) == 1

        join = result.resolved_joins[0]
        assert join["table_name"] == "Major.Acc"
        cond = join["on_conditions"][0]
        assert "CustomerID" in cond["left"]
        assert "CustomerID" in cond["right"]

    def test_B3_customer_demographics_acc(self, abc_schema_repo, capturing_logger):
        """B3: Customer + CustomerDemographics + Acc -> two INNER JOINs."""
        ctx = _make_context([
            {"table": "Major.Customer", "source": "customer"},
            {"table": "Major.CustomerDemographics", "source": "customer name"},
            {"table": "Major.Acc", "source": "acc"},
        ])
        result = run_join_resolver(ctx, abc_schema_repo, capturing_logger)

        assert result.status == "success"
        assert len(result.resolved_joins) == 2

        join_tables = [j["table_name"] for j in result.resolved_joins]
        assert "Major.CustomerDemographics" in join_tables
        assert "Major.Acc" in join_tables


# ---------------------------------------------------------------------------
# C -- Self-join with hierarchy role assignment
# ---------------------------------------------------------------------------

class TestSelfJoinHierarchy:

    def test_C1_acc_top_and_sub(self, abc_schema_repo, capturing_logger):
        """C1: Acc twice with top acc + sub acc -> roles + correct aliases."""
        ctx = _make_context([
            {"table": "Major.Customer", "source": "customer"},
            {"table": "Major.Acc", "source": "top acc"},
            {"table": "Major.Acc", "source": "sub acc"},
        ])
        result = run_join_resolver(ctx, abc_schema_repo, capturing_logger)

        assert result.status == "success"

        acc_entries = [e for e in result.resolved_tables if e["table"] == "Major.Acc"]
        assert len(acc_entries) == 2

        roles = {e.get("role") for e in acc_entries}
        aliases = {e.get("alias") for e in acc_entries}

        assert "top_Acc" in roles
        assert "sub_Acc" in roles
        assert "a_top" in aliases
        assert "a_sub" in aliases

    def test_C1_acc_self_join_on_conditions(self, abc_schema_repo, capturing_logger):
        """C1 extended: a_sub join has AccID->ParentAccID AND CustomerID->CustomerID."""
        ctx = _make_context([
            {"table": "Major.Customer", "source": "customer"},
            {"table": "Major.Acc", "source": "top acc"},
            {"table": "Major.Acc", "source": "sub acc"},
        ])
        result = run_join_resolver(ctx, abc_schema_repo, capturing_logger)

        # Find the a_sub join
        sub_joins = [
            j for j in result.resolved_joins
            if j["table_name"] == "Major.Acc" and j.get("alias") == "a_sub"
        ]
        assert len(sub_joins) == 1
        join = sub_joins[0]

        # Must have at least 2 on_conditions
        assert len(join["on_conditions"]) >= 2

        all_lefts = [c["left"] for c in join["on_conditions"]]
        all_rights = [c["right"] for c in join["on_conditions"]]
        all_sides = all_lefts + all_rights

        # Self-join condition: AccID and ParentAccID must appear
        assert any("AccID" in s for s in all_sides)
        assert any("ParentAccID" in s for s in all_sides)

        # Additional condition: CustomerID must appear
        assert any("CustomerID" in s for s in all_sides)

    def test_C2_acc_no_synonym_match(self, abc_schema_repo, capturing_logger):
        """C2: Acc twice, source matches no synonym -> warning logged, unique aliases."""
        ctx = _make_context([
            {"table": "Major.Acc", "source": "unknown phrase"},
            {"table": "Major.Acc", "source": "another unknown"},
        ])
        result = run_join_resolver(ctx, abc_schema_repo, capturing_logger)

        acc_entries = [e for e in result.resolved_tables if e["table"] == "Major.Acc"]
        for entry in acc_entries:
            assert "role" not in entry or entry.get("role") is None

        assert len(result.warnings) >= 1
        assert any("matched no hierarchy synonym" in w for w in result.warnings)

        aliases = [e["alias"] for e in acc_entries]
        assert len(set(aliases)) == 2  # unique aliases

    def test_C3_golden_query(self, abc_schema_repo, capturing_logger):
        """C3: Full golden query -- all joins and aliases correct."""
        ctx = _make_context(
            [
                {"table": "Major.Customer", "source": "customer"},
                {"table": "Major.CustomerDemographics", "source": "customer name"},
                {"table": "Major.Acc", "source": "top acc"},
                {"table": "Major.Acc", "source": "sub acc"},
            ],
            query="give me customer name, top acc and sub acc for customer CUST01 in Acme",
        )
        result = run_join_resolver(ctx, abc_schema_repo, capturing_logger)

        assert result.status == "success"
        # 3 joins: Customer->Demographics, Customer->Acc(top), Acc(top+Customer)->Acc(sub)
        assert len(result.resolved_joins) == 3

        join_tables = [j["table_name"] for j in result.resolved_joins]
        assert "Major.CustomerDemographics" in join_tables
        assert join_tables.count("Major.Acc") == 2

        aliases = {e["alias"] for e in result.resolved_tables}
        assert {"c", "cd", "a_top", "a_sub"} == aliases


# ---------------------------------------------------------------------------
# D -- Junction table auto-bridging
# ---------------------------------------------------------------------------

class TestJunctionBridge:

    def test_D1_package_and_plan_bridged(self, abc_schema_repo, capturing_logger):
        """D1: Package + Plan -> PackagePlan auto-inserted, two joins produced."""
        ctx = _make_context([
            {"table": "Major.Package", "source": "package"},
            {"table": "Major.Plan", "source": "plan"},
        ])
        result = run_join_resolver(ctx, abc_schema_repo, capturing_logger)

        assert result.status == "success"
        assert len(result.resolved_joins) == 2

        join_tables = [j["table_name"] for j in result.resolved_joins]
        assert "Major.PackagePlan" in join_tables
        assert "Major.Plan" in join_tables

    def test_D2_junction_not_in_resolved_tables(self, abc_schema_repo, capturing_logger):
        """D2: Auto-inserted junction table does NOT appear in resolved_tables."""
        ctx = _make_context([
            {"table": "Major.Package", "source": "package"},
            {"table": "Major.Plan", "source": "plan"},
        ])
        result = run_join_resolver(ctx, abc_schema_repo, capturing_logger)

        table_names = [e["table"] for e in result.resolved_tables]
        assert "Major.PackagePlan" not in table_names


# ---------------------------------------------------------------------------
# E -- No join path
# ---------------------------------------------------------------------------

class TestNoJoinPath:

    def test_E1_no_path_raises_error(self, abc_schema_repo, capturing_logger):
        """E1: Two tables with no relationship -> NoJoinPathError."""
        ctx = _make_context([
            {"table": "Major.Plan", "source": "plan"},
            {"table": "Major.CustomerDemographics", "source": "customer name"},
        ])
        with pytest.raises(NoJoinPathError) as exc_info:
            run_join_resolver(ctx, abc_schema_repo, capturing_logger)

        assert exc_info.value.code == "NO_JOIN_PATH"


# ---------------------------------------------------------------------------
# F -- Alias generation (unit tests on helpers)
# ---------------------------------------------------------------------------

class TestAliasGeneration:

    def test_F1_camel_case(self):
        """F1: CamelCase display_name -> initials extracted correctly."""
        assert _build_alias_candidate("CustomerDemographics") == "cd"
        assert _build_alias_candidate("OrderLineItem") == "oli"
        assert _build_alias_candidate("Customer") == "c"
        assert _build_alias_candidate("Acc") == "a"

    def test_F2_underscore(self):
        """F2: Underscore display_name -> first letter each part."""
        assert _build_alias_candidate("client_detail") == "cd"
        assert _build_alias_candidate("enroll_platform") == "ep"

    def test_F3_all_lowercase(self):
        """F3: All-lowercase display_name -> first 3 chars."""
        assert _build_alias_candidate("clientdetail") == "cli"
        assert _build_alias_candidate("orders") == "ord"
        assert _build_alias_candidate("ab") == "ab"

    def test_F4_collision_resolved(self):
        """F4: Collision -> second table gets _2 suffix."""
        assigned: set = set()
        alias1 = _resolve_alias("Package", None, assigned)
        assigned.add(alias1)
        alias2 = _resolve_alias("Plan", None, assigned)
        assigned.add(alias2)

        assert alias1 == "p"
        assert alias2 == "p_2"


# ---------------------------------------------------------------------------
# G -- Logging
# ---------------------------------------------------------------------------

class TestLogging:

    def test_G1_emits_validation_result_log(self, abc_schema_repo, capturing_logger):
        """G1: Successful run emits VALIDATION_RESULT log with correct payload."""
        ctx = _make_context([
            {"table": "Major.Customer", "source": "customer"},
            {"table": "Major.CustomerDemographics", "source": "customer name"},
        ])
        run_join_resolver(ctx, abc_schema_repo, capturing_logger)

        assert len(capturing_logger.entries) == 1
        entry = capturing_logger.entries[0]
        assert entry.stage == "VALIDATION_RESULT"
        assert "resolved_joins" in entry.payload
        assert "resolved_tables" in entry.payload
# ---------------------------------------------------------------------------
# H -- Role stamping on columns and filters  [V1]
# ---------------------------------------------------------------------------

class TestRoleStampingOnColumnsAndFilters:

    def test_H1_role_stamped_on_column_for_self_join_table(self, abc_schema_repo, capturing_logger):
        """H1: Self-join -- role stamped on matching column entry."""
        ctx = _make_context(
            tables=[
                {"table": "Major.Customer", "source": "customer"},
                {"table": "Major.Acc",      "source": "top acc"},
                {"table": "Major.Acc",      "source": "sub acc"},
            ],
            query="give me top acc name and sub acc name for customer CUST01",
        )
        ctx.resolved_columns = [
            {"table": "Major.Acc", "column": "AccName", "source": "top acc name"},
            {"table": "Major.Acc", "column": "AccName", "source": "sub acc name"},
        ]

        result = run_join_resolver(ctx, abc_schema_repo, capturing_logger)

        acc_cols = result.resolved_columns
        assert len(acc_cols) == 2

        roles = [e.get("role") for e in acc_cols]
        assert "top_Acc" in roles
        assert "sub_Acc" in roles

    def test_H2_role_stamped_on_filter_for_self_join_table(self, abc_schema_repo, capturing_logger):
        """H2: Self-join -- role stamped on matching filter entry."""
        ctx = _make_context(
            tables=[
                {"table": "Major.Customer", "source": "customer"},
                {"table": "Major.Acc",      "source": "top acc"},
                {"table": "Major.Acc",      "source": "sub acc"},
            ],
            query="give me top acc for customer CUST01 where top acc is TOP1",
        )
        ctx.resolved_filters = [
            {"table": "Major.Acc", "column": "AccCID", "operator": "=",
             "value": "TOP1", "source": "top acc TOP1"},
        ]

        result = run_join_resolver(ctx, abc_schema_repo, capturing_logger)

        assert len(result.resolved_filters) == 1
        assert result.resolved_filters[0].get("role") == "top_Acc"

    def test_H3_no_role_stamped_on_columns_for_non_self_join(self, abc_schema_repo, capturing_logger):
        """H3: Non-self-join -- no role key added to column entries."""
        ctx = _make_context(
            tables=[
                {"table": "Major.Customer",             "source": "customer"},
                {"table": "Major.CustomerDemographics", "source": "customer name"},
            ],
        )
        ctx.resolved_columns = [
            {"table": "Major.Customer",             "column": "CustomerCID",  "source": "customer"},
            {"table": "Major.CustomerDemographics", "column": "CustomerName", "source": "name"},
        ]

        result = run_join_resolver(ctx, abc_schema_repo, capturing_logger)

        for col in result.resolved_columns:
            assert "role" not in col

# ---------------------------------------------------------------------------
# I -- Single-instance hierarchy role stamping  [V3 Story 5.9]
# ---------------------------------------------------------------------------

class TestSingleInstanceHierarchy:
    """
    Story 5.9 — single-instance hierarchy tables must have their role stamped
    even when the table appears only once in resolved_tables (not a self-join).

    Before V3, role was only stamped on self-join tables (count > 1).
    A query like "give me top acc for customer CUST01" has one Major.Acc entry —
    but rule_applicator needs role=top_Acc to apply AccLevelConfig=0 and
    ParentAccID IS NULL conditions.
    """

    def test_JR_S1_single_acc_top_acc_source_gets_role(self, abc_schema_repo, capturing_logger):
        """JR-S1: Single Major.Acc with source 'top acc' → role=top_Acc stamped."""
        ctx = _make_context([
            {"table": "Major.Customer", "source": "customer"},
            {"table": "Major.Acc", "source": "top acc"},
        ])
        result = run_join_resolver(ctx, abc_schema_repo, capturing_logger)

        assert result.status == "success"
        acc_entries = [e for e in result.resolved_tables if e["table"] == "Major.Acc"]
        assert len(acc_entries) == 1
        assert acc_entries[0].get("role") == "top_Acc"

    def test_JR_S2_single_acc_sub_acc_source_gets_role(self, abc_schema_repo, capturing_logger):
        """JR-S2: Single Major.Acc with source 'sub acc' → role=sub_Acc stamped."""
        ctx = _make_context([
            {"table": "Major.Customer", "source": "customer"},
            {"table": "Major.Acc", "source": "sub acc"},
        ])
        result = run_join_resolver(ctx, abc_schema_repo, capturing_logger)

        assert result.status == "success"
        acc_entries = [e for e in result.resolved_tables if e["table"] == "Major.Acc"]
        assert len(acc_entries) == 1
        assert acc_entries[0].get("role") == "sub_Acc"

    def test_JR_S3_single_acc_unmatched_source_warns_no_role(self, abc_schema_repo, capturing_logger):
        """JR-S3: Single Major.Acc with source 'acc' → no role, warning in context.warnings."""
        ctx = _make_context([
            {"table": "Major.Customer", "source": "customer"},
            {"table": "Major.Acc", "source": "acc"},
        ])
        result = run_join_resolver(ctx, abc_schema_repo, capturing_logger)

        assert result.status == "success"
        acc_entries = [e for e in result.resolved_tables if e["table"] == "Major.Acc"]
        assert len(acc_entries) == 1
        # No role stamped — "acc" matches no specific level synonym
        assert acc_entries[0].get("role") is None
        # Warning must be present
        assert any("matched no hierarchy synonym" in w for w in result.warnings)

    def test_JR_S4_self_join_still_stamps_roles_regression(self, abc_schema_repo, capturing_logger):
        """JR-S4: Regression — self-join (top acc + sub acc) still stamps roles correctly."""
        ctx = _make_context([
            {"table": "Major.Customer", "source": "customer"},
            {"table": "Major.Acc", "source": "top acc"},
            {"table": "Major.Acc", "source": "sub acc"},
        ])
        result = run_join_resolver(ctx, abc_schema_repo, capturing_logger)

        assert result.status == "success"
        acc_entries = [e for e in result.resolved_tables if e["table"] == "Major.Acc"]
        assert len(acc_entries) == 2
        roles = {e.get("role") for e in acc_entries}
        assert "top_Acc" in roles
        assert "sub_Acc" in roles

    # -----------------------------------------------------------------------
    # JR-S5 to JR-S8  [Story 5.9 cont.] — role stamping on columns/filters
    # for single-instance hierarchy tables (the empty-alias ".AccName" bug)
    # -----------------------------------------------------------------------

    def test_JR_S5_single_acc_column_gets_role_stamped(self, abc_schema_repo, capturing_logger):
        """JR-S5: Single Major.Acc 'top acc' + a column on it → column gets role=top_Acc."""
        ctx = _make_context([
            {"table": "Major.Customer", "source": "customer"},
            {"table": "Major.Acc", "source": "top acc"},
        ])
        # Column on the single-instance hierarchy table
        ctx.resolved_columns = [
            {"table": "Major.Acc", "column": "AccName", "source": "top acc name"},
        ]
        result = run_join_resolver(ctx, abc_schema_repo, capturing_logger)

        assert result.status == "success"
        col = result.resolved_columns[0]
        assert col.get("role") == "top_Acc"

    def test_JR_S6_single_acc_filter_gets_role_stamped(self, abc_schema_repo, capturing_logger):
        """JR-S6: Single Major.Acc 'sub acc' + a filter on it → filter gets role=sub_Acc."""
        ctx = _make_context([
            {"table": "Major.Customer", "source": "customer"},
            {"table": "Major.Acc", "source": "sub acc"},
        ])
        ctx.resolved_filters = [
            {"table": "Major.Acc", "column": "AccName", "operator": "=",
             "value": "X", "source": "sub acc named X"},
        ]
        result = run_join_resolver(ctx, abc_schema_repo, capturing_logger)

        assert result.status == "success"
        filt = result.resolved_filters[0]
        assert filt.get("role") == "sub_Acc"

    def test_JR_S7_non_hierarchy_column_not_stamped(self, abc_schema_repo, capturing_logger):
        """JR-S7: Column on a single non-hierarchy table → no role stamped (regression guard)."""
        ctx = _make_context([
            {"table": "Major.Customer", "source": "customer"},
            {"table": "Major.Acc", "source": "top acc"},
        ])
        # Column on Major.Customer — not a hierarchy table
        ctx.resolved_columns = [
            {"table": "Major.Customer", "column": "CustomerCID", "source": "customer"},
        ]
        result = run_join_resolver(ctx, abc_schema_repo, capturing_logger)

        assert result.status == "success"
        col = result.resolved_columns[0]
        # Non-hierarchy table column must NOT get a role key (left untouched)
        assert col.get("role") is None

    def test_JR_S8_single_acc_column_unmatched_source_role_none(self, abc_schema_repo, capturing_logger):
        """JR-S8: Single Acc column whose source matches no synonym → role None, no crash."""
        ctx = _make_context([
            {"table": "Major.Customer", "source": "customer"},
            {"table": "Major.Acc", "source": "top acc"},
        ])
        # Column source "acc name" matches no specific level synonym
        ctx.resolved_columns = [
            {"table": "Major.Acc", "column": "AccName", "source": "acc name"},
        ]
        result = run_join_resolver(ctx, abc_schema_repo, capturing_logger)

        assert result.status == "success"
        col = result.resolved_columns[0]
        # role key is present (stamped) but None — consistent with table-level behaviour
        assert col.get("role") is None


# ---------------------------------------------------------------------------
# J -- Deferred join (multi-pass algorithm)  [V4 Bug fix]
# ---------------------------------------------------------------------------

class TestDeferredJoin:
    """
    Tests for the multi-pass deferred join algorithm introduced in V6 of
    join_resolver.py.

    Background: the old strict for-loop raised NoJoinPathError immediately when
    a table could not join the current anchor set, even if it would have been
    joinable once another table was anchored first. The new algorithm defers such
    tables to a pending list and retries after each successful anchor — matching
    the industry-standard Kahn topological resolution pattern.

    J1-J2: The deferred scenario — table order the LLM may return.
    J3-J4: True no-path scenarios — error must still be raised correctly.
    J5-J8: Regression guards — existing join patterns must be unaffected.
    """

    def test_J1_deferred_cd_before_customer(self, abc_schema_repo, capturing_logger):
        """
        J1: [Acc, CustomerDemographics, Customer]
        CustomerDemographics has no direct path to Acc, so it is deferred in
        pass 1. Customer joins Acc in pass 1. CD then joins Customer in pass 2.
        Previously raised NoJoinPathError — must now succeed with 2 joins.
        """
        ctx = _make_context([
            {"table": "Major.Acc",                  "source": "acc"},
            {"table": "Major.CustomerDemographics", "source": "customer name"},
            {"table": "Major.Customer",             "source": "customer"},
        ])
        result = run_join_resolver(ctx, abc_schema_repo, capturing_logger)

        assert result.status == "success"
        assert len(result.resolved_joins) == 2

        join_tables = [j["table_name"] for j in result.resolved_joins]
        assert "Major.Customer" in join_tables
        assert "Major.CustomerDemographics" in join_tables

        # CustomerDemographics must join via Customer (CustomerID), not directly to Acc
        cd_join = next(j for j in result.resolved_joins
                       if j["table_name"] == "Major.CustomerDemographics")
        all_sides = [c["left"] for c in cd_join["on_conditions"]] + \
                    [c["right"] for c in cd_join["on_conditions"]]
        assert any("CustomerID" in s for s in all_sides)

    def test_J2_full_deferred_query_four_tables(self, abc_schema_repo, capturing_logger):
        """
        J2: [Acc, CustomerDemographics, Customer, EPInd]
        CD deferred in pass 1; Customer and EPI join Acc in pass 1.
        CD joins Customer in pass 2. All 4 tables resolved with 3 joins.
        """
        ctx = _make_context([
            {"table": "Major.Acc",                       "source": "acc"},
            {"table": "Major.CustomerDemographics",      "source": "customer name"},
            {"table": "Major.Customer",                  "source": "customer"},
            {"table": "Config.EPInd",  "source": "platform"},
        ])
        result = run_join_resolver(ctx, abc_schema_repo, capturing_logger)

        assert result.status == "success"
        assert len(result.resolved_joins) == 3

        join_tables = [j["table_name"] for j in result.resolved_joins]
        assert "Major.Customer" in join_tables
        assert "Major.CustomerDemographics" in join_tables
        assert "Config.EPInd" in join_tables

    def test_J3_genuine_no_path_raises_error(self, abc_schema_repo, capturing_logger):
        """
        J3: [Acc, Package] — Package has no relationship to Acc and no junction bridge.
        After one full pass with zero progress, NoJoinPathError must be raised.
        """
        ctx = _make_context([
            {"table": "Major.Acc",     "source": "acc"},
            {"table": "Major.Package", "source": "package"},
        ])
        with pytest.raises(NoJoinPathError) as exc_info:
            run_join_resolver(ctx, abc_schema_repo, capturing_logger)

        assert exc_info.value.code == "NO_JOIN_PATH"

    def test_J4_both_tables_deferred_no_progress(self, abc_schema_repo, capturing_logger):
        """
        J4: [CustomerDemographics, EPInd]
        CD connects only to Customer; EPI connects only to Acc.
        Neither can join the other. Zero progress on first pass → NoJoinPathError.
        """
        ctx = _make_context([
            {"table": "Major.CustomerDemographics",     "source": "customer name"},
            {"table": "Config.EPInd", "source": "platform"},
        ])
        with pytest.raises(NoJoinPathError) as exc_info:
            run_join_resolver(ctx, abc_schema_repo, capturing_logger)

        assert exc_info.value.code == "NO_JOIN_PATH"

    def test_J5_regression_direct_join_unchanged(self, abc_schema_repo, capturing_logger):
        """
        J5: Regression — [Customer, Acc] direct join still resolves in one pass.
        """
        ctx = _make_context([
            {"table": "Major.Customer", "source": "customer"},
            {"table": "Major.Acc",      "source": "acc"},
        ])
        result = run_join_resolver(ctx, abc_schema_repo, capturing_logger)

        assert result.status == "success"
        assert len(result.resolved_joins) == 1
        assert result.resolved_joins[0]["table_name"] == "Major.Acc"

    def test_J6_regression_ordered_three_tables_unchanged(self, abc_schema_repo, capturing_logger):
        """
        J6: Regression — [Customer, CustomerDemographics, Acc] all joinable in order.
        Must still produce 2 joins in one pass (no deferral needed).
        """
        ctx = _make_context([
            {"table": "Major.Customer",             "source": "customer"},
            {"table": "Major.CustomerDemographics", "source": "customer name"},
            {"table": "Major.Acc",                  "source": "acc"},
        ])
        result = run_join_resolver(ctx, abc_schema_repo, capturing_logger)

        assert result.status == "success"
        assert len(result.resolved_joins) == 2

        join_tables = [j["table_name"] for j in result.resolved_joins]
        assert "Major.CustomerDemographics" in join_tables
        assert "Major.Acc" in join_tables

    def test_J7_regression_self_join_conditions_unchanged(self, abc_schema_repo, capturing_logger):
        """
        J7: Regression — [Customer, Acc top, Acc sub] self-join.
        a_sub must still receive both the primary AccID condition and the
        additional CustomerID condition (Customer is anchored before a_sub).
        """
        ctx = _make_context([
            {"table": "Major.Customer", "source": "customer"},
            {"table": "Major.Acc",      "source": "top acc"},
            {"table": "Major.Acc",      "source": "sub acc"},
        ])
        result = run_join_resolver(ctx, abc_schema_repo, capturing_logger)

        assert result.status == "success"
        assert len(result.resolved_joins) == 2

        sub_join = next(
            j for j in result.resolved_joins
            if j["table_name"] == "Major.Acc" and j.get("alias") == "a_sub"
        )
        assert len(sub_join["on_conditions"]) >= 2

        all_sides = (
            [c["left"]  for c in sub_join["on_conditions"]] +
            [c["right"] for c in sub_join["on_conditions"]]
        )
        assert any("AccID" in s for s in all_sides)
        assert any("ParentAccID" in s for s in all_sides)
        assert any("CustomerID" in s for s in all_sides)

    def test_J8_regression_junction_bridge_unchanged(self, abc_schema_repo, capturing_logger):
        """
        J8: Regression — [Package, Plan] junction bridge via PackagePlan still works.
        Two joins produced: Package→PackagePlan and PackagePlan→Plan.
        """
        ctx = _make_context([
            {"table": "Major.Package", "source": "package"},
            {"table": "Major.Plan",    "source": "plan"},
        ])
        result = run_join_resolver(ctx, abc_schema_repo, capturing_logger)

        assert result.status == "success"
        assert len(result.resolved_joins) == 2

        join_tables = [j["table_name"] for j in result.resolved_joins]
        assert "Major.PackagePlan" in join_tables
        assert "Major.Plan" in join_tables
