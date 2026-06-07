# tests/schema/test_schema_models.py
# V0 - Initial implementation

import json
import pytest
from pathlib import Path
from pydantic import ValidationError

from src.schema.schema_models import (
    AppSchema,
    TableSchema,
    ColumnSchema,
)

# ---------------------------------------------------------------------------
# Fixture — load Acme_app.json once for the whole module
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def abc_schema() -> AppSchema:
    """Parse Acme_app.json into AppSchema — used by all tests."""
    schema_path = Path("schemas/Acme_app.json")
    raw = json.loads(schema_path.read_text(encoding="utf-8"))
    return AppSchema(**raw)


@pytest.fixture(scope="module")
def customer_table(abc_schema: AppSchema) -> TableSchema:
    """Major.Customer table — used by multiple test groups."""
    table = next(t for t in abc_schema.tables if t.name == "Major.Customer")
    return table


@pytest.fixture(scope="module")
def acc_table(abc_schema: AppSchema) -> TableSchema:
    """Major.Acc table."""
    return next(t for t in abc_schema.tables if t.name == "Major.Acc")


@pytest.fixture(scope="module")
def demographics_table(abc_schema: AppSchema) -> TableSchema:
    """Major.CustomerDemographics table."""
    return next(t for t in abc_schema.tables if t.name == "Major.CustomerDemographics")


@pytest.fixture(scope="module")
def package_plan_table(abc_schema: AppSchema) -> TableSchema:
    """Major.PackagePlan — junction table."""
    return next(t for t in abc_schema.tables if t.name == "Major.PackagePlan")


# ---------------------------------------------------------------------------
# Group 1 — Full Schema Load
# ---------------------------------------------------------------------------

class TestFullSchemaLoad:
    """Group 1 — Acme_app.json parses into AppSchema correctly."""

    def test_1_1_schema_parses_without_error(self, abc_schema: AppSchema):
        """1.1 — Acme_app.json parses without error into AppSchema."""
        assert abc_schema is not None

    def test_1_2_top_level_scalar_fields(self, abc_schema: AppSchema):
        """1.2 — appId, app_name, version correct."""
        assert abc_schema.appId == "Acme_app"
        assert abc_schema.app_name == "Acme"
        assert abc_schema.version == "1.0"

    def test_1_3_app_synonyms(self, abc_schema: AppSchema):
        """1.3 — appSynonyms list loads correctly."""
        assert abc_schema.appSynonyms == ["Acme", "Acme office", "Acme system"]

    def test_1_4_database_type(self, abc_schema: AppSchema):
        """1.4 — database_type is SQL Server."""
        assert abc_schema.database_type == "SQL Server"

    def test_1_5_table_count(self, abc_schema: AppSchema):
        """1.5 — exactly 7 tables loaded."""
        assert len(abc_schema.tables) == 7


# ---------------------------------------------------------------------------
# Group 2 — Table-Level Fields
# ---------------------------------------------------------------------------

class TestTableLevelFields:
    """Group 2 — table name, display_name, schema, description, synonyms, junction flag."""

    def test_2_1_customer_core_fields(self, customer_table: TableSchema):
        """2.1 — Major.Customer core fields correct."""
        assert customer_table.name == "Major.Customer"
        assert customer_table.display_name == "Customer"
        assert customer_table.schema_name == "Major"
        assert "Versioned Customer organization records" in customer_table.description

    def test_2_2_customer_synonyms(self, customer_table: TableSchema):
        """2.2 — Major.Customer synonyms load correctly."""
        assert "Customer" in customer_table.synonyms
        assert "customer" in customer_table.synonyms
        assert "organization" in customer_table.synonyms
        assert "org" in customer_table.synonyms

    def test_2_3_package_plan_is_junction(self, package_plan_table: TableSchema):
        """2.3 — Major.PackagePlan has is_junction_table = True."""
        assert package_plan_table.is_junction_table is True

    def test_2_4_non_junction_tables_default_false(self, abc_schema: AppSchema):
        """2.4 — Non-junction tables have is_junction_table = False (field absent in JSON)."""
        non_junction_names = [
            "Major.Customer",
            "Major.CustomerDemographics",
            "Major.Acc",
            "Config.EPInd",
            "Major.Package",
            "Major.Plan",
        ]
        for table in abc_schema.tables:
            if table.name in non_junction_names:
                assert table.is_junction_table is False, (
                    f"{table.name} should have is_junction_table=False"
                )

    def test_2_5_package_plan_synonyms_empty(self, package_plan_table: TableSchema):
        """2.5 — Major.PackagePlan synonyms is empty list."""
        assert package_plan_table.synonyms == []


# ---------------------------------------------------------------------------
# Group 3 — Versioning Block
# ---------------------------------------------------------------------------

class TestVersioningBlock:
    """Group 3 — versioning config loads correctly, absent where expected."""

    def test_3_1_customer_versioning_is_versioned(self, customer_table: TableSchema):
        """3.1 — Major.Customer versioning.is_versioned = True."""
        assert customer_table.versioning is not None
        assert customer_table.versioning.is_versioned is True

    def test_3_2_customer_versioning_all_fields(self, customer_table: TableSchema):
        """3.2 — All versioning fields on Major.Customer correct."""
        v = customer_table.versioning
        assert v.business_key == "CustomerCID"
        assert v.row_key == "CustomerID"
        assert v.version_key == "CustomerVersionKey"
        assert v.effective_date == "VersionEffDate"
        assert v.termination_date == "VersionTermDate"
        assert v.active_condition == "VersionTermDate IS NULL"

    def test_3_3_acc_versioning_is_none(self, acc_table: TableSchema):
        """3.3 — Major.Acc has no versioning block."""
        assert acc_table.versioning is None

    def test_3_4_demographics_versioning_is_none(self, demographics_table: TableSchema):
        """3.4 — Major.CustomerDemographics has no versioning block."""
        assert demographics_table.versioning is None


# ---------------------------------------------------------------------------
# Group 4 — Business Rules Block
# ---------------------------------------------------------------------------

class TestBusinessRulesBlock:
    """Group 4 — business rules, hierarchy config."""

    def test_4_1_customer_active_record_count(self, customer_table: TableSchema):
        """4.1 — Major.Customer active_record has 3 conditions."""
        assert customer_table.business_rules is not None
        assert len(customer_table.business_rules.active_record) == 3

    def test_4_2_customer_exclude_record_count(self, customer_table: TableSchema):
        """4.2 — Major.Customer exclude_record has 2 conditions."""
        assert len(customer_table.business_rules.exclude_record) == 2

    def test_4_3_acc_hierarchy_has_top_and_sub(self, acc_table: TableSchema):
        """4.3 — Major.Acc hierarchy has top_Acc and sub_Acc levels."""
        assert acc_table.business_rules is not None
        hierarchy = acc_table.business_rules.hierarchy
        assert hierarchy is not None
        assert "top_Acc" in hierarchy.level_names()
        assert "sub_Acc" in hierarchy.level_names()

    def test_4_4_acc_top_acc_condition(self, acc_table: TableSchema):
        """4.4 — top_Acc condition = AccLevelConfig = 0."""
        top = acc_table.business_rules.hierarchy.get_level("top_Acc")
        assert top is not None
        assert top.condition == "AccLevelConfig = 0"

    def test_4_5_acc_top_acc_synonyms_non_empty(self, acc_table: TableSchema):
        """4.5 — top_Acc synonyms list is non-empty."""
        top = acc_table.business_rules.hierarchy.get_level("top_Acc")
        assert len(top.synonyms) > 0

    def test_4_6_demographics_business_rules_none(self, demographics_table: TableSchema):
        """4.6 — Major.CustomerDemographics has no business_rules."""
        assert demographics_table.business_rules is None


# ---------------------------------------------------------------------------
# Group 5 — Filter Control Block
# ---------------------------------------------------------------------------

class TestFilterControlBlock:
    """Group 5 — filter_control loads, suppress/apply tokens correct."""

    def test_5_1_customer_filter_control_present(self, customer_table: TableSchema):
        """5.1 — Major.Customer filter_control block loads."""
        assert customer_table.filter_control is not None
        assert customer_table.filter_control.suppress_tokens is not None
        assert customer_table.filter_control.apply_tokens is not None

    def test_5_2_suppress_tokens(self, customer_table: TableSchema):
        """5.2 — suppress_tokens contains history and historical."""
        tokens = customer_table.filter_control.suppress_tokens
        assert "history" in tokens
        assert "historical" in tokens

    def test_5_3_apply_tokens(self, customer_table: TableSchema):
        """5.3 — apply_tokens contains active, current, latest."""
        tokens = customer_table.filter_control.apply_tokens
        assert "active" in tokens
        assert "current" in tokens
        assert "latest" in tokens

    def test_5_4_acc_filter_control_none(self, acc_table: TableSchema):
        """5.4 — Major.Acc has no filter_control."""
        assert acc_table.filter_control is None


# ---------------------------------------------------------------------------
# Group 6 — Columns
# ---------------------------------------------------------------------------

class TestColumns:
    """Group 6 — column fields load correctly."""

    def _get_column(self, table: TableSchema, col_name: str):
        return next(c for c in table.columns if c.name == col_name)

    def test_6_1_customer_column_count(self, customer_table: TableSchema):
        """6.1 — Major.Customer has correct number of columns."""
        assert len(customer_table.columns) == 12

    def test_6_2_customer_id_primary_key(self, customer_table: TableSchema):
        """6.2 — CustomerID type=INT, key=primary."""
        col = self._get_column(customer_table, "CustomerID")
        assert col.type == "INT"
        assert col.key == "primary"

    def test_6_3_customer_cid_identifier_and_synonyms(self, customer_table: TableSchema):
        """6.3 — CustomerCID is_identifier=True and has synonyms."""
        col = self._get_column(customer_table, "CustomerCID")
        assert col.is_identifier is True
        assert len(col.synonyms) > 0

    def test_6_4_deleted_flag_default_value(self, customer_table: TableSchema):
        """6.4 — DeletedFlag type=BIT, default_value=0."""
        col = self._get_column(customer_table, "DeletedFlag")
        assert col.type == "BIT"
        assert col.default_value == 0

    def test_6_5_created_from_customer_id_foreign_key(self, customer_table: TableSchema):
        """6.5 — CreatedFromCustomerID key=foreign, references correct."""
        col = self._get_column(customer_table, "CreatedFromCustomerID")
        assert col.key == "foreign"
        assert col.references is not None
        assert col.references.table == "Major.Customer"
        assert col.references.column == "CustomerID"

    def test_6_6_column_with_no_optional_fields(self, customer_table: TableSchema):
        """6.6 — VersionNumber loads without error despite no optional fields."""
        col = self._get_column(customer_table, "VersionNumber")
        assert col.name == "VersionNumber"
        assert col.key is None
        assert col.is_identifier is None
        assert col.references is None


# ---------------------------------------------------------------------------
# Group 7 — Relationships
# ---------------------------------------------------------------------------

class TestRelationships:
    """Group 7 — relationship fields load correctly."""

    def test_7_1_customer_relationship_count(self, customer_table: TableSchema):
        """7.1 — Major.Customer has 3 relationships."""
        assert len(customer_table.relationships) == 3

    def test_7_2_customer_to_demographics_relationship(self, customer_table: TableSchema):
        """7.2 — Relationship to CustomerDemographics fields correct."""
        rel = next(
            r for r in customer_table.relationships
            if r.related_table == "Major.CustomerDemographics"
        )
        assert rel.from_ == "CustomerID"
        assert rel.to == "CustomerID"
        assert rel.type == "one-to-one"

    def test_7_3_customer_self_referencing_relationship(self, customer_table: TableSchema):
        """7.3 — Self-referencing relationship type=self."""
        self_rel = next(
            r for r in customer_table.relationships
            if r.type == "self"
        )
        assert self_rel.related_table == "Major.Customer"

    def test_7_4_package_plan_relationships(self, package_plan_table: TableSchema):
        """7.4 — PackagePlan has relationships to both Package and Plan."""
        related = {r.related_table for r in package_plan_table.relationships}
        assert "Major.Package" in related
        assert "Major.Plan" in related


# ---------------------------------------------------------------------------
# Group 8 — Default Filters
# ---------------------------------------------------------------------------

class TestDefaultFilters:
    """Group 8 — default_filters load correctly."""

    def test_8_1_customer_default_filters_count(self, customer_table: TableSchema):
        """8.1 — Major.Customer default_filters has 2 entries."""
        assert customer_table.default_filters is not None
        assert len(customer_table.default_filters) == 2

    def test_8_2_customer_first_default_filter(self, customer_table: TableSchema):
        """8.2 — First default filter is DeletedFlag check."""
        assert "ISNULL(Major.Customer.DeletedFlag, 0) = 0" in customer_table.default_filters

    def test_8_3_acc_default_filters_absent(self, acc_table: TableSchema):
        """8.3 — Major.Acc has no default_filters."""
        assert acc_table.default_filters is None


# ---------------------------------------------------------------------------
# Group 9 — Invalid / Malformed Input
# ---------------------------------------------------------------------------

class TestInvalidInput:
    """Group 9 — malformed JSON raises ValidationError."""

    def test_9_1_missing_app_id_raises(self):
        """9.1 — Missing appId raises ValidationError."""
        with pytest.raises(ValidationError):
            AppSchema(app_name="Acme", version="1.0", tables=[])

    def test_9_2_missing_tables_raises(self):
        """9.2 — Missing tables raises ValidationError."""
        with pytest.raises(ValidationError):
            AppSchema(appId="Acme_app", app_name="Acme", version="1.0")

    def test_9_3_table_missing_name_raises(self):
        """9.3 — Table missing name raises ValidationError."""
        with pytest.raises(ValidationError):
            TableSchema(columns=[])

    def test_9_4_table_missing_columns_raises(self):
        """9.4 — Table missing columns raises ValidationError."""
        with pytest.raises(ValidationError):
            TableSchema(name="Major.Customer")

    def test_9_5_column_missing_name_raises(self):
        """9.5 — Column missing name raises ValidationError."""
        with pytest.raises(ValidationError):
            ColumnSchema()

    def test_9_6_empty_json_raises(self):
        """9.6 — Completely empty JSON raises ValidationError."""
        with pytest.raises(ValidationError):
            AppSchema(**{})
