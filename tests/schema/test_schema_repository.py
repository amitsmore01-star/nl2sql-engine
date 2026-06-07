# tests/schema/test_schema_repository.py
# V0 - Initial implementation

import json
import pytest
from pathlib import Path

from src.schema.schema_repository import SchemaRepository
from src.schema.schema_models import AppSchema
from src.core.exceptions import SchemaLoadError


# ---------------------------------------------------------------------------
# Helpers — minimal valid schema dict and builder
# ---------------------------------------------------------------------------

def _minimal_schema(app_id: str = "Acme_app") -> dict:
    """Returns a minimal valid schema dict for the given appId."""
    return {
        "appId": app_id,
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


def _write_schema(tmp_path: Path, filename: str, data: dict) -> Path:
    """Write a dict as JSON to tmp_path/filename. Returns the file path."""
    path = tmp_path / filename
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# Test class
# ---------------------------------------------------------------------------

class TestSchemaRepository:
    """Tests for SchemaRepository — loading schemas from disk."""

    # --- Scenario 1 ---
    def test_loads_valid_abc_schema(self, tmp_path):
        """Load valid Acme_app.json — returns AppSchema with correct appId."""
        _write_schema(tmp_path, "Acme_app.json", _minimal_schema("Acme_app"))
        repo = SchemaRepository()
        repo.load(tmp_path)
        schemas = repo.get_all_schemas()
        assert len(schemas) == 1
        assert schemas[0].appId == "Acme_app"

    # --- Scenario 2 ---
    def test_get_schema_returns_correct_schema(self, tmp_path):
        """get_schema('Acme_app') returns AppSchema with all expected tables."""
        _write_schema(tmp_path, "Acme_app.json", _minimal_schema("Acme_app"))
        repo = SchemaRepository()
        repo.load(tmp_path)
        schema = repo.get_schema("Acme_app")
        assert isinstance(schema, AppSchema)
        assert schema.appId == "Acme_app"
        assert len(schema.tables) == 1
        assert schema.tables[0].name == "Major.Customer"

    # --- Scenario 3 ---
    def test_get_all_schemas_returns_list(self, tmp_path):
        """get_all_schemas() returns a list containing the loaded schema."""
        _write_schema(tmp_path, "Acme_app.json", _minimal_schema("Acme_app"))
        repo = SchemaRepository()
        repo.load(tmp_path)
        all_schemas = repo.get_all_schemas()
        assert isinstance(all_schemas, list)
        assert len(all_schemas) == 1
        assert all_schemas[0].appId == "Acme_app"

    # --- Scenario 4 ---
    def test_get_schema_unknown_id_raises(self, tmp_path):
        """get_schema with unknown app_id raises SchemaLoadError."""
        _write_schema(tmp_path, "Acme_app.json", _minimal_schema("Acme_app"))
        repo = SchemaRepository()
        repo.load(tmp_path)
        with pytest.raises(SchemaLoadError) as exc_info:
            repo.get_schema("UNKNOWN_APP")
        assert exc_info.value.code == "SCHEMA_LOAD_ERROR"
        assert "UNKNOWN_APP" in exc_info.value.message

    # --- Scenario 5 ---
    def test_load_raises_if_dir_does_not_exist(self, tmp_path):
        """Load raises SchemaLoadError if schema directory does not exist."""
        missing_dir = tmp_path / "nonexistent"
        repo = SchemaRepository()
        with pytest.raises(SchemaLoadError) as exc_info:
            repo.load(missing_dir)
        assert exc_info.value.code == "SCHEMA_LOAD_ERROR"
        assert "not found" in exc_info.value.message.lower()

    # --- Scenario 6 ---
    def test_load_raises_if_dir_is_empty(self, tmp_path):
        """Load raises SchemaLoadError if schema directory contains no .json files."""
        repo = SchemaRepository()
        with pytest.raises(SchemaLoadError) as exc_info:
            repo.load(tmp_path)
        assert exc_info.value.code == "SCHEMA_LOAD_ERROR"
        assert "no schema files" in exc_info.value.message.lower()

    # --- Scenario 7 ---
    def test_load_raises_if_filename_does_not_match_app_id(self, tmp_path):
        """File named wrong_name.json but appId inside is Acme_app — raises SchemaLoadError."""
        _write_schema(tmp_path, "wrong_name.json", _minimal_schema("Acme_app"))
        repo = SchemaRepository()
        with pytest.raises(SchemaLoadError) as exc_info:
            repo.load(tmp_path)
        assert exc_info.value.code == "SCHEMA_LOAD_ERROR"
        assert "mismatch" in exc_info.value.message.lower()

    # --- Scenario 8 ---
    def test_load_succeeds_when_filename_matches_app_id(self, tmp_path):
        """File named Acme_app.json with appId Acme_app inside — loads successfully."""
        _write_schema(tmp_path, "Acme_app.json", _minimal_schema("Acme_app"))
        repo = SchemaRepository()
        repo.load(tmp_path)  # Must not raise
        assert repo.get_schema("Acme_app").appId == "Acme_app"

    # --- Scenario 9 ---
    def test_non_json_files_are_ignored(self, tmp_path):
        """Non-.json files in the schema dir are silently ignored."""
        _write_schema(tmp_path, "Acme_app.json", _minimal_schema("Acme_app"))
        (tmp_path / "readme.txt").write_text("ignore me", encoding="utf-8")
        (tmp_path / "notes.md").write_text("# notes", encoding="utf-8")
        repo = SchemaRepository()
        repo.load(tmp_path)
        assert len(repo.get_all_schemas()) == 1

    # --- Scenario 10 ---
    def test_load_raises_for_valid_json_but_invalid_schema(self, tmp_path):
        """Valid JSON that is not a valid AppSchema (e.g. {}) raises SchemaLoadError."""
        path = tmp_path / "Acme_app.json"
        path.write_text(json.dumps({}), encoding="utf-8")
        repo = SchemaRepository()
        with pytest.raises(SchemaLoadError) as exc_info:
            repo.load(tmp_path)
        assert exc_info.value.code == "SCHEMA_LOAD_ERROR"

    # --- Scenario 11 ---
    def test_load_raises_for_malformed_json(self, tmp_path):
        """File with malformed JSON (syntax error) raises SchemaLoadError."""
        path = tmp_path / "Acme_app.json"
        path.write_text("{this is not valid json", encoding="utf-8")
        repo = SchemaRepository()
        with pytest.raises(SchemaLoadError) as exc_info:
            repo.load(tmp_path)
        assert exc_info.value.code == "SCHEMA_LOAD_ERROR"
        assert "malformed" in exc_info.value.message.lower()

    # --- Scenario 12 ---
    def test_load_raises_for_empty_file(self, tmp_path):
        """Empty schema file raises SchemaLoadError."""
        path = tmp_path / "Acme_app.json"
        path.write_text("", encoding="utf-8")
        repo = SchemaRepository()
        with pytest.raises(SchemaLoadError) as exc_info:
            repo.load(tmp_path)
        assert exc_info.value.code == "SCHEMA_LOAD_ERROR"
        assert "empty" in exc_info.value.message.lower()

    # --- Scenario 13 ---
    def test_load_two_valid_schemas_get_all_returns_both(self, tmp_path):
        """Two valid schema files load correctly — get_all_schemas() returns both."""
        _write_schema(tmp_path, "Acme_app.json", _minimal_schema("Acme_app"))
        _write_schema(tmp_path, "XYZ_app.json", _minimal_schema("XYZ_app"))
        repo = SchemaRepository()
        repo.load(tmp_path)
        all_schemas = repo.get_all_schemas()
        assert len(all_schemas) == 2
        app_ids = {s.appId for s in all_schemas}
        assert "Acme_app" in app_ids
        assert "XYZ_app" in app_ids

    # --- Scenario 14 ---
    def test_load_raises_for_empty_app_id(self, tmp_path):
        """Schema file with appId as empty string raises SchemaLoadError."""
        data = _minimal_schema("Acme_app")
        data["appId"] = ""
        # File must be named something.json — use placeholder name
        path = tmp_path / "placeholder.json"
        path.write_text(json.dumps(data), encoding="utf-8")
        repo = SchemaRepository()
        with pytest.raises(SchemaLoadError) as exc_info:
            repo.load(tmp_path)
        assert exc_info.value.code == "SCHEMA_LOAD_ERROR"
        assert "empty" in exc_info.value.message.lower()
