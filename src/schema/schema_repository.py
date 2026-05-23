# src/schema/schema_repository.py
# V0 - Initial implementation
# V1 - Story 2.4: Removed stale code= kwarg from all SchemaLoadError calls.
#      SchemaLoadError.__init__ was updated in Story 2.1 to take message only
#      (code is injected automatically). schema_repository.py was missed then.

import json
from pathlib import Path

from pydantic import ValidationError

from src.schema.schema_models import AppSchema
from src.core.exceptions import SchemaLoadError


class SchemaRepository:
    """
    Loads and stores all app schema JSON files from the schemas directory.

    Rules enforced at load time:
    - Directory must exist and contain at least one .json file
    - Every .json file must be valid JSON
    - Every .json file must parse into a valid AppSchema
    - Every file must be named {appId}.json — filename must match appId inside JSON
    - appId must not be empty string

    Non-.json files in the directory are silently ignored.
    """

    def __init__(self) -> None:
        self._schemas: dict[str, AppSchema] = {}  # appId → AppSchema

    # ---------------------------------------------------------------------------
    # Public interface
    # ---------------------------------------------------------------------------

    def load(self, schema_dir: str | Path) -> None:
        """
        Load all schema files from schema_dir.

        Args:
            schema_dir: Path to the directory containing schema JSON files.

        Raises:
            SchemaLoadError: If directory missing, empty, or any file is invalid.
        """
        schema_dir = Path(schema_dir)

        # --- 1. Directory must exist ---
        if not schema_dir.exists() or not schema_dir.is_dir():
            raise SchemaLoadError(
                message=f"Schema directory not found: '{schema_dir}'"
            )

        # --- 2. Collect all .json files (non-.json silently ignored) ---
        json_files = list(schema_dir.glob("*.json"))
        if not json_files:
            raise SchemaLoadError(
                message=f"No schema files found in '{schema_dir}'. "
                        "At least one .json schema file is required."
            )

        # --- 3. Load each file ---
        loaded: dict[str, AppSchema] = {}
        for path in json_files:
            schema = self._load_file(path)
            loaded[schema.appId] = schema

        self._schemas = loaded

    def get_schema(self, app_id: str) -> AppSchema:
        """
        Return the AppSchema for the given app_id.

        Raises:
            SchemaLoadError: If app_id not found in loaded schemas.
        """
        schema = self._schemas.get(app_id)
        if schema is None:
            raise SchemaLoadError(
                message=f"No schema loaded for app_id '{app_id}'. "
                        f"Available: {list(self._schemas.keys())}"
            )
        return schema

    def get_all_schemas(self) -> list[AppSchema]:
        """Return all loaded AppSchema objects."""
        return list(self._schemas.values())

    # ---------------------------------------------------------------------------
    # Private helpers
    # ---------------------------------------------------------------------------

    def _load_file(self, path: Path) -> AppSchema:
        """
        Load, parse, and validate a single schema JSON file.

        Raises:
            SchemaLoadError: On empty file, malformed JSON, invalid schema
                             structure, empty appId, or filename mismatch.
        """
        # --- 1. Read raw content ---
        raw = path.read_text(encoding="utf-8").strip()
        if not raw:
            raise SchemaLoadError(
                message=f"Schema file is empty: '{path.name}'"
            )

        # --- 2. Parse JSON ---
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise SchemaLoadError(
                message=f"Malformed JSON in schema file '{path.name}': {exc}"
            ) from exc

        # --- 3. Parse into AppSchema ---
        try:
            schema = AppSchema(**data)
        except (ValidationError, TypeError) as exc:
            raise SchemaLoadError(
                message=f"Schema file '{path.name}' failed validation: {exc}"
            ) from exc

        # --- 4. appId must not be empty ---
        if not schema.appId.strip():
            raise SchemaLoadError(
                message=f"Schema file '{path.name}' has an empty appId."
            )

        # --- 5. Filename must match appId ---
        expected_filename = f"{schema.appId}.json"
        if path.name != expected_filename:
            raise SchemaLoadError(
                message=(
                    f"Schema filename mismatch: file is '{path.name}' "
                    f"but appId inside is '{schema.appId}'. "
                    f"Rename the file to '{expected_filename}'."
                )
            )

        return schema
