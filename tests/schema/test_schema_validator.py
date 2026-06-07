# tests/schema/test_schema_validator.py
# V0 - Initial implementation

import pytest

from src.schema.schema_models import AppSchema
from src.schema.schema_validator import SchemaValidator
from src.core.exceptions import SchemaLoadError


# ---------------------------------------------------------------------------
# Helpers — minimal valid schema builder
# ---------------------------------------------------------------------------

def _make_schema(overrides: dict | None = None) -> AppSchema:
    """
    Build a minimal valid AppSchema. Pass overrides as a dict of
    top-level field overrides to produce invalid variants.
    """
    base = {
        "appId": "Acme_app",
        "app_name": "Acme",
        "version": "1.0",
        "tables": [
            {
                "name": "Major.Customer",
                "synonyms": ["customer"],
                "columns": [{"name": "CustomerID", "type": "INT"}],
            }
        ],
    }
    if overrides:
        base.update(overrides)
    return AppSchema(**base)


def _make_schema_raw(data: dict) -> AppSchema:
    """Build AppSchema directly from a raw dict (for full control)."""
    return AppSchema(**data)


# ---------------------------------------------------------------------------
# Test class
# ---------------------------------------------------------------------------

class TestSchemaValidator:
    """Tests for SchemaValidator — validates AppSchema objects against contract."""

    def setup_method(self):
        self.validator = SchemaValidator()

    # --- Scenario 1 ---
    def test_valid_abc_schema_passes(self):
        """Valid minimal schema passes all validation rules without raising."""
        schema = _make_schema()
        self.validator.validate_one(schema)  # Must not raise

    # --- Scenario 2 ---
    def test_missing_app_id_raises(self):
        """Schema with empty appId raises SchemaLoadError."""
        schema = _make_schema({"appId": ""})
        with pytest.raises(SchemaLoadError) as exc_info:
            self.validator.validate_one(schema)
        assert exc_info.value.code == "SCHEMA_LOAD_ERROR"

    # --- Scenario 3 ---
    def test_missing_app_name_raises(self):
        """Schema with empty app_name raises SchemaLoadError."""
        schema = _make_schema({"app_name": ""})
        with pytest.raises(SchemaLoadError) as exc_info:
            self.validator.validate_one(schema)
        assert exc_info.value.code == "SCHEMA_LOAD_ERROR"

    # --- Scenario 4 ---
    def test_missing_version_raises(self):
        """Schema with empty version raises SchemaLoadError."""
        schema = _make_schema({"version": ""})
        with pytest.raises(SchemaLoadError) as exc_info:
            self.validator.validate_one(schema)
        assert exc_info.value.code == "SCHEMA_LOAD_ERROR"

    # --- Scenario 5 ---
    def test_empty_tables_raises(self):
        """Schema with empty tables list raises SchemaLoadError."""
        schema = _make_schema({"tables": []})
        with pytest.raises(SchemaLoadError) as exc_info:
            self.validator.validate_one(schema)
        assert exc_info.value.code == "SCHEMA_LOAD_ERROR"
        assert "tables" in exc_info.value.message.lower()

    # --- Scenario 6 ---
    def test_table_missing_name_raises(self):
        """Table with empty name raises SchemaLoadError."""
        data = {
            "appId": "Acme_app",
            "app_name": "Acme",
            "version": "1.0",
            "tables": [
                {
                    "name": "",
                    "synonyms": ["customer"],
                    "columns": [{"name": "CustomerID"}],
                }
            ],
        }
        schema = _make_schema_raw(data)
        with pytest.raises(SchemaLoadError) as exc_info:
            self.validator.validate_one(schema)
        assert exc_info.value.code == "SCHEMA_LOAD_ERROR"

    # --- Scenario 7 ---
    def test_table_missing_columns_raises(self):
        """Table with empty columns list raises SchemaLoadError."""
        data = {
            "appId": "Acme_app",
            "app_name": "Acme",
            "version": "1.0",
            "tables": [
                {
                    "name": "Major.Customer",
                    "synonyms": ["customer"],
                    "columns": [],
                }
            ],
        }
        schema = _make_schema_raw(data)
        with pytest.raises(SchemaLoadError) as exc_info:
            self.validator.validate_one(schema)
        assert exc_info.value.code == "SCHEMA_LOAD_ERROR"
        assert "columns" in exc_info.value.message.lower()

    # --- Scenario 8 ---
    def test_non_junction_table_empty_synonyms_raises(self):
        """Non-junction table with empty synonyms[] raises SchemaLoadError."""
        data = {
            "appId": "Acme_app",
            "app_name": "Acme",
            "version": "1.0",
            "tables": [
                {
                    "name": "Major.Customer",
                    "synonyms": [],
                    "columns": [{"name": "CustomerID"}],
                }
            ],
        }
        schema = _make_schema_raw(data)
        with pytest.raises(SchemaLoadError) as exc_info:
            self.validator.validate_one(schema)
        assert exc_info.value.code == "SCHEMA_LOAD_ERROR"
        assert "synonym" in exc_info.value.message.lower()

    # --- Scenario 9 ---
    def test_junction_table_empty_synonyms_passes(self):
        """Junction table with empty synonyms[] passes validation."""
        data = {
            "appId": "Acme_app",
            "app_name": "Acme",
            "version": "1.0",
            "tables": [
                {
                    "name": "Major.Customer",
                    "synonyms": ["customer"],
                    "columns": [{"name": "CustomerID"}],
                },
                {
                    "name": "Major.PackagePlan",
                    "is_junction_table": True,
                    "synonyms": [],
                    "columns": [
                        {"name": "PackagePlanId"},
                        {"name": "PackageId"},
                        {"name": "PlanId"},
                    ],
                },
            ],
        }
        schema = _make_schema_raw(data)
        self.validator.validate_one(schema)  # Must not raise

    # --- Scenario 10 ---
    def test_junction_table_non_empty_synonyms_raises(self):
        """Junction table with non-empty synonyms[] raises SchemaLoadError."""
        data = {
            "appId": "Acme_app",
            "app_name": "Acme",
            "version": "1.0",
            "tables": [
                {
                    "name": "Major.Customer",
                    "synonyms": ["customer"],
                    "columns": [{"name": "CustomerID"}],
                },
                {
                    "name": "Major.PackagePlan",
                    "is_junction_table": True,
                    "synonyms": ["package plan"],
                    "columns": [{"name": "PackagePlanId"}],
                },
            ],
        }
        schema = _make_schema_raw(data)
        with pytest.raises(SchemaLoadError) as exc_info:
            self.validator.validate_one(schema)
        assert exc_info.value.code == "SCHEMA_LOAD_ERROR"
        assert "junction" in exc_info.value.message.lower()

    # --- Scenario 11 ---
    def test_duplicate_app_id_across_schemas_raises(self):
        """Two schemas with same appId raises SchemaLoadError via validate_all."""
        schema_a = _make_schema({"appId": "Acme_app"})
        schema_b = _make_schema({"appId": "Acme_app", "app_name": "Acme Copy"})
        with pytest.raises(SchemaLoadError) as exc_info:
            self.validator.validate_all([schema_a, schema_b])
        assert exc_info.value.code == "SCHEMA_LOAD_ERROR"
        assert "duplicate" in exc_info.value.message.lower()
        assert "Acme_app" in exc_info.value.message

    # --- Scenario 12 ---
    def test_duplicate_synonym_across_tables_raises(self):
        """Two non-junction tables sharing a synonym within same app raises SchemaLoadError."""
        data = {
            "appId": "Acme_app",
            "app_name": "Acme",
            "version": "1.0",
            "tables": [
                {
                    "name": "Major.Customer",
                    "synonyms": ["customer", "org"],
                    "columns": [{"name": "CustomerID"}],
                },
                {
                    "name": "Major.Acc",
                    "synonyms": ["acc", "org"],   # 'org' clashes with Customer
                    "columns": [{"name": "AccID"}],
                },
            ],
        }
        schema = _make_schema_raw(data)
        with pytest.raises(SchemaLoadError) as exc_info:
            self.validator.validate_one(schema)
        assert exc_info.value.code == "SCHEMA_LOAD_ERROR"
        assert "org" in exc_info.value.message

    # --- Scenario 13 ---
    def test_relationship_pointing_to_missing_table_raises(self):
        """Relationship referencing a non-existent table raises SchemaLoadError."""
        data = {
            "appId": "Acme_app",
            "app_name": "Acme",
            "version": "1.0",
            "tables": [
                {
                    "name": "Major.Customer",
                    "synonyms": ["customer"],
                    "columns": [{"name": "CustomerID"}],
                    "relationships": [
                        {
                            "related_table": "Major.NonExistent",
                            "from": "CustomerID",
                            "to": "CustomerID",
                            "type": "one-to-many",
                        }
                    ],
                }
            ],
        }
        schema = _make_schema_raw(data)
        with pytest.raises(SchemaLoadError) as exc_info:
            self.validator.validate_one(schema)
        assert exc_info.value.code == "SCHEMA_LOAD_ERROR"
        assert "NonExistent" in exc_info.value.message

    # --- Scenario 14 ---
    def test_duplicate_column_names_in_table_raises(self):
        """Table with two columns sharing the same name raises SchemaLoadError."""
        data = {
            "appId": "Acme_app",
            "app_name": "Acme",
            "version": "1.0",
            "tables": [
                {
                    "name": "Major.Customer",
                    "synonyms": ["customer"],
                    "columns": [
                        {"name": "CustomerID"},
                        {"name": "CustomerID"},   # duplicate
                    ],
                }
            ],
        }
        schema = _make_schema_raw(data)
        with pytest.raises(SchemaLoadError) as exc_info:
            self.validator.validate_one(schema)
        assert exc_info.value.code == "SCHEMA_LOAD_ERROR"
        assert "duplicate" in exc_info.value.message.lower()
        assert "CustomerID" in exc_info.value.message

    # --- Scenario 15 ---
    def test_column_missing_name_raises(self):
        """Column with empty name raises SchemaLoadError."""
        data = {
            "appId": "Acme_app",
            "app_name": "Acme",
            "version": "1.0",
            "tables": [
                {
                    "name": "Major.Customer",
                    "synonyms": ["customer"],
                    "columns": [{"name": ""}],
                }
            ],
        }
        schema = _make_schema_raw(data)
        with pytest.raises(SchemaLoadError) as exc_info:
            self.validator.validate_one(schema)
        assert exc_info.value.code == "SCHEMA_LOAD_ERROR"

    # --- Scenario 16 ---
    def test_empty_string_synonym_raises(self):
        """Synonym that is an empty string raises SchemaLoadError."""
        data = {
            "appId": "Acme_app",
            "app_name": "Acme",
            "version": "1.0",
            "tables": [
                {
                    "name": "Major.Customer",
                    "synonyms": ["customer", ""],   # empty string
                    "columns": [{"name": "CustomerID"}],
                }
            ],
        }
        schema = _make_schema_raw(data)
        with pytest.raises(SchemaLoadError) as exc_info:
            self.validator.validate_one(schema)
        assert exc_info.value.code == "SCHEMA_LOAD_ERROR"
        assert "blank" in exc_info.value.message.lower() or "whitespace" in exc_info.value.message.lower()

    # --- Scenario 17 ---
    def test_whitespace_only_synonym_raises(self):
        """Synonym that is whitespace-only raises SchemaLoadError."""
        data = {
            "appId": "Acme_app",
            "app_name": "Acme",
            "version": "1.0",
            "tables": [
                {
                    "name": "Major.Customer",
                    "synonyms": ["customer", "   "],   # whitespace only
                    "columns": [{"name": "CustomerID"}],
                }
            ],
        }
        schema = _make_schema_raw(data)
        with pytest.raises(SchemaLoadError) as exc_info:
            self.validator.validate_one(schema)
        assert exc_info.value.code == "SCHEMA_LOAD_ERROR"
        assert "blank" in exc_info.value.message.lower() or "whitespace" in exc_info.value.message.lower()

    # --- Scenario 18 ---
    def test_duplicate_synonym_within_same_table_raises(self):
        """Same synonym appearing twice in the same table raises SchemaLoadError."""
        data = {
            "appId": "Acme_app",
            "app_name": "Acme",
            "version": "1.0",
            "tables": [
                {
                    "name": "Major.Customer",
                    "synonyms": ["customer", "customer"],   # duplicate within table
                    "columns": [{"name": "CustomerID"}],
                }
            ],
        }
        schema = _make_schema_raw(data)
        with pytest.raises(SchemaLoadError) as exc_info:
            self.validator.validate_one(schema)
        assert exc_info.value.code == "SCHEMA_LOAD_ERROR"
        assert "duplicate" in exc_info.value.message.lower()
        assert "customer" in exc_info.value.message.lower()

    # --- Scenario 19 ---
    def test_self_referencing_relationship_passes(self):
        """Self-referencing relationship (e.g. Major.Acc → Major.Acc) passes validation."""
        data = {
            "appId": "Acme_app",
            "app_name": "Acme",
            "version": "1.0",
            "tables": [
                {
                    "name": "Major.Acc",
                    "synonyms": ["acc"],
                    "columns": [
                        {"name": "AccID"},
                        {"name": "ParentAccID"},
                    ],
                    "relationships": [
                        {
                            "related_table": "Major.Acc",   # points to itself
                            "from": "ParentAccID",
                            "to": "AccID",
                            "type": "self",
                        }
                    ],
                }
            ],
        }
        schema = _make_schema_raw(data)
        self.validator.validate_one(schema)  # Must not raise

    # --- Scenario 20 ---
    def test_version_empty_string_raises(self):
        """Schema with version as empty string raises SchemaLoadError."""
        schema = _make_schema({"version": ""})
        with pytest.raises(SchemaLoadError) as exc_info:
            self.validator.validate_one(schema)
        assert "version" in exc_info.value.message.lower()
