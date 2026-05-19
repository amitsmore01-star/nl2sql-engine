# src/schema/schema_models.py
# V0 - Initial implementation

from typing import Optional
from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Column-level models
# ---------------------------------------------------------------------------

class ColumnReference(BaseModel):
    """Foreign key reference — table and column the FK points to."""

    table: str
    column: str


class ColumnSchema(BaseModel):
    """Single column definition within a table."""

    name: str
    type: Optional[str] = None
    key: Optional[str] = None                        # primary | foreign
    is_identifier: Optional[bool] = None
    is_default_text: Optional[bool] = None
    synonyms: list[str] = Field(default_factory=list)
    references: Optional[ColumnReference] = None
    default_value: Optional[int | str | float] = None
    description: Optional[str] = None


# ---------------------------------------------------------------------------
# Relationship model
# ---------------------------------------------------------------------------

class RelationshipSchema(BaseModel):
    """Join relationship between two tables."""

    related_table: str
    from_: str = Field(alias="from")
    to: str
    type: str                                        # one-to-one | one-to-many | many-to-one | self

    model_config = {"populate_by_name": True}


# ---------------------------------------------------------------------------
# Versioning block
# ---------------------------------------------------------------------------

class VersioningConfig(BaseModel):
    """Versioning metadata for slowly-changing tables."""

    is_versioned: bool
    business_key: str
    row_key: str
    version_key: str
    effective_date: str
    termination_date: str
    active_condition: str


# ---------------------------------------------------------------------------
# Business rules block
# ---------------------------------------------------------------------------

class HierarchyLevel(BaseModel):
    """Single level in a table hierarchy (e.g. top_Acc, sub_Acc)."""

    condition: str
    parent_condition: str
    synonyms: list[str] = Field(default_factory=list)


class HierarchyConfig(BaseModel):
    """Hierarchy configuration — keyed by level name."""

    model_config = {"extra": "allow"}               # dynamic keys: top_Acc, sub_Acc etc.

    def get_level(self, name: str) -> Optional[HierarchyLevel]:
        data = self.model_extra.get(name)
        if data is None:
            return None
        return HierarchyLevel(**data)

    def level_names(self) -> list[str]:
        return list(self.model_extra.keys())


class BusinessRules(BaseModel):
    """Business rule conditions attached to a table."""

    active_record: list[str] = Field(default_factory=list)
    exclude_record: list[str] = Field(default_factory=list)
    latest_version: list[str] = Field(default_factory=list)
    hierarchy: Optional[HierarchyConfig] = None


# ---------------------------------------------------------------------------
# Filter control block
# ---------------------------------------------------------------------------

class FilterControl(BaseModel):
    """Controls when active-record filters are applied or suppressed."""

    apply_when: list[str] = Field(default_factory=list)
    suppress_tokens: list[str] = Field(default_factory=list)
    apply_tokens: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Table model
# ---------------------------------------------------------------------------

class TableSchema(BaseModel):
    """Full definition of a single table in an app schema."""

    name: str
    display_name: Optional[str] = None
    schema_name: Optional[str] = Field(None, alias="schema")
    synonyms: list[str] = Field(default_factory=list)
    description: Optional[str] = None
    identifier: Optional[str] = None
    is_junction_table: bool = False                  # absent in JSON → defaults False

    versioning: Optional[VersioningConfig] = None
    business_rules: Optional[BusinessRules] = None
    filter_control: Optional[FilterControl] = None

    columns: list[ColumnSchema]
    relationships: list[RelationshipSchema] = Field(default_factory=list)
    default_filters: Optional[list[str]] = None

    model_config = {"populate_by_name": True}


# ---------------------------------------------------------------------------
# Top-level app schema model
# ---------------------------------------------------------------------------

class AppSchema(BaseModel):
    """Root model — represents one app schema JSON file."""

    appId: str
    app_name: str
    version: str
    appSynonyms: list[str] = Field(default_factory=list)
    description: Optional[str] = None
    database_type: Optional[str] = None
    tables: list[TableSchema]
