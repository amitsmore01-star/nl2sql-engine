# tests/validator/test_join_resolver.py
# V0 - Initial implementation
# V1 - Story 4.5: Added class H -- Role stamping on columns and filters (H1, H2, H3)
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
        app_id="ABC_app",
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
            query="give me customer name, top acc and sub acc for customer ASA in ABC",
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
        assert _build_alias_candidate("EnrollPlatformIndicator") == "epi"
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
            query="give me top acc name and sub acc name for customer ASA",
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
            query="give me top acc for customer ASA where top acc is TOP1",
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
