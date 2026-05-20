# src/schema/schema_validator.py
# V0 - Initial implementation

from src.schema.schema_models import AppSchema, TableSchema
from src.core.exceptions import SchemaLoadError


class SchemaValidator:
    """
    Validates one or more loaded AppSchema objects against the contract
    defined in the architecture document (Section 5.4).

    All rules are checked at startup. Service refuses to start if any fail.

    Rules enforced:
    - appId, app_name, version present and non-empty
    - tables[] non-empty
    - Every table has name and columns[]
    - Non-junction tables have non-empty synonyms[] with no blank/whitespace entries
    - No duplicate synonyms within same table
    - No duplicate synonyms across non-junction tables in same app
    - Junction tables have empty synonyms[]
    - Every column has a name
    - No duplicate column names within same table
    - Every relationship.related_table exists in the schema
    - Self-referencing relationships are allowed (e.g. Major.Acc → Major.Acc)
    - No duplicate appId across multiple schemas
    - version field must be non-empty
    """

    def validate_all(self, schemas: list[AppSchema]) -> None:
        """
        Validate a list of schemas together (enables cross-schema checks).

        Raises:
            SchemaLoadError: On any validation failure.
        """
        self._check_duplicate_app_ids(schemas)
        for schema in schemas:
            self._validate_schema(schema)

    def validate_one(self, schema: AppSchema) -> None:
        """
        Validate a single schema in isolation.

        Raises:
            SchemaLoadError: On any validation failure.
        """
        self._validate_schema(schema)

    # ---------------------------------------------------------------------------
    # Cross-schema checks
    # ---------------------------------------------------------------------------

    def _check_duplicate_app_ids(self, schemas: list[AppSchema]) -> None:
        seen: set[str] = set()
        for schema in schemas:
            if schema.appId in seen:
                raise SchemaLoadError(
                    code="SCHEMA_LOAD_ERROR",
                    message=f"Duplicate appId '{schema.appId}' found across schema files. "
                            "Each app must have a unique appId."
                )
            seen.add(schema.appId)

    # ---------------------------------------------------------------------------
    # Single schema validation
    # ---------------------------------------------------------------------------

    def _validate_schema(self, schema: AppSchema) -> None:
        self._check_required_top_level_fields(schema)
        self._check_tables_non_empty(schema)

        # Build table name set for relationship checks
        table_names = {t.name for t in schema.tables}

        # Collect all synonyms across non-junction tables for cross-table dupe check
        all_synonyms: dict[str, str] = {}  # synonym → first table name that claimed it

        for table in schema.tables:
            self._check_table_name(table, schema.appId)
            self._check_table_columns(table, schema.appId)
            self._check_synonyms(table, schema.appId, all_synonyms)
            self._check_relationships(table, schema.appId, table_names)

    def _check_required_top_level_fields(self, schema: AppSchema) -> None:
        # appId — enforced by Pydantic (str, required) but check non-empty
        if not schema.appId or not schema.appId.strip():
            raise SchemaLoadError(
                code="SCHEMA_LOAD_ERROR",
                message="Schema has an empty 'appId' field."
            )
        # app_name
        if not schema.app_name or not schema.app_name.strip():
            raise SchemaLoadError(
                code="SCHEMA_LOAD_ERROR",
                message=f"Schema '{schema.appId}' has an empty 'app_name' field."
            )
        # version — must be present and non-empty
        if not schema.version or not schema.version.strip():
            raise SchemaLoadError(
                code="SCHEMA_LOAD_ERROR",
                message=f"Schema '{schema.appId}' has an empty 'version' field."
            )

    def _check_tables_non_empty(self, schema: AppSchema) -> None:
        if not schema.tables:
            raise SchemaLoadError(
                code="SCHEMA_LOAD_ERROR",
                message=f"Schema '{schema.appId}' has an empty 'tables' list. "
                        "At least one table is required."
            )

    def _check_table_name(self, table: TableSchema, app_id: str) -> None:
        if not table.name or not table.name.strip():
            raise SchemaLoadError(
                code="SCHEMA_LOAD_ERROR",
                message=f"Schema '{app_id}' contains a table with an empty 'name' field."
            )

    def _check_table_columns(self, table: TableSchema, app_id: str) -> None:
        # columns[] must be present and non-empty
        if not table.columns:
            raise SchemaLoadError(
                code="SCHEMA_LOAD_ERROR",
                message=f"Table '{table.name}' in schema '{app_id}' "
                        "has an empty 'columns' list. At least one column is required."
            )
        # Each column must have a name; no duplicate column names
        seen_cols: set[str] = set()
        for col in table.columns:
            if not col.name or not col.name.strip():
                raise SchemaLoadError(
                    code="SCHEMA_LOAD_ERROR",
                    message=f"Table '{table.name}' in schema '{app_id}' "
                            "contains a column with an empty 'name' field."
                )
            if col.name in seen_cols:
                raise SchemaLoadError(
                    code="SCHEMA_LOAD_ERROR",
                    message=f"Table '{table.name}' in schema '{app_id}' "
                            f"has duplicate column name '{col.name}'."
                )
            seen_cols.add(col.name)

    def _check_synonyms(
        self,
        table: TableSchema,
        app_id: str,
        all_synonyms: dict[str, str],
    ) -> None:
        if table.is_junction_table:
            # Junction tables must have empty synonyms[]
            if table.synonyms:
                raise SchemaLoadError(
                    code="SCHEMA_LOAD_ERROR",
                    message=f"Junction table '{table.name}' in schema '{app_id}' "
                            "must have an empty 'synonyms' list."
                )
            return  # No further synonym checks for junction tables

        # Non-junction: synonyms[] must be non-empty
        if not table.synonyms:
            raise SchemaLoadError(
                code="SCHEMA_LOAD_ERROR",
                message=f"Non-junction table '{table.name}' in schema '{app_id}' "
                        "has an empty 'synonyms' list. At least one synonym is required."
            )

        # Each synonym must not be blank or whitespace-only
        # No duplicates within the same table
        seen_in_table: set[str] = set()
        for syn in table.synonyms:
            if not syn or not syn.strip():
                raise SchemaLoadError(
                    code="SCHEMA_LOAD_ERROR",
                    message=f"Table '{table.name}' in schema '{app_id}' "
                            "contains a blank or whitespace-only synonym."
                )
            if syn in seen_in_table:
                raise SchemaLoadError(
                    code="SCHEMA_LOAD_ERROR",
                    message=f"Table '{table.name}' in schema '{app_id}' "
                            f"has duplicate synonym '{syn}' within the same table."
                )
            seen_in_table.add(syn)

            # Cross-table duplicate check within same app
            if syn in all_synonyms:
                raise SchemaLoadError(
                    code="SCHEMA_LOAD_ERROR",
                    message=(
                        f"Duplicate synonym '{syn}' in schema '{app_id}': "
                        f"claimed by both '{all_synonyms[syn]}' and '{table.name}'."
                    )
                )
            all_synonyms[syn] = table.name

    def _check_relationships(
        self,
        table: TableSchema,
        app_id: str,
        table_names: set[str],
    ) -> None:
        for rel in table.relationships:
            if rel.related_table not in table_names:
                raise SchemaLoadError(
                    code="SCHEMA_LOAD_ERROR",
                    message=(
                        f"Table '{table.name}' in schema '{app_id}' has a relationship "
                        f"pointing to '{rel.related_table}', which does not exist in the schema."
                    )
                )
