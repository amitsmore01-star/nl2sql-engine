# src/api/tools/context_validator.py
# V0 - Initial implementation
# V1 - Story 3.5: Architecture v1.6 redesign.
#      - Removed SchemMapperRequirements (schema-mapper stage no longer exists)
#      - Renamed IntentExtractorRequirements → NLToIRRequirements (stage: nl-to-ir)
#      - Updated ValidatorRequirements: requires llm_output instead of
#        intent_output + mapping_output
#      - Updated _build_registry() to use renamed/removed classes

"""
Context Validator for Foundry tool endpoints.

Design Patterns used:
  - Strategy Pattern : Each StageRequirements subclass encapsulates
                       the validation rules for one stage. Adding a new
                       stage means adding one new class — zero changes
                       to ContextValidator logic (Open/Closed Principle).
  - Factory Pattern  : ContextValidator._build_registry() constructs all
                       StageRequirements instances once at startup.
  - Single Responsibility : StageRequirements validates fields.
                            ContextValidator orchestrates lookup + dispatch.

Why request_id is NOT validated here:
  QueryContext.request_id has default_factory=lambda: str(uuid.uuid4()).
  Pydantic auto-generates it before this validator ever runs, so it is
  always guaranteed to be present.

Stage registry (architecture v1.6):
  app-identifier  → nl_query_original
  nl-to-ir        → nl_query_original, app_id, app_schema_version
  validator       → app_id, app_schema_version, llm_output
  sql-builder     → app_id, structured_query
  query           → nl_query_original
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import final

from src.core.exceptions import MissingContextFieldsError
from src.core.models import QueryContext


# ---------------------------------------------------------------------------
# Abstract base — one strategy per stage
# ---------------------------------------------------------------------------

class StageRequirements(ABC):
    """
    Abstract base class for per-stage field requirements.

    Each concrete subclass knows:
      - which stage it belongs to  (stage_name property)
      - which QueryContext fields must be non-null / non-empty  (required_fields property)

    Subclasses must NOT override validate() — the logic lives here once.
    """

    @property
    @abstractmethod
    def stage_name(self) -> str:
        """Human-readable stage identifier matching the URL slug."""
        ...

    @property
    @abstractmethod
    def required_fields(self) -> list[str]:
        """
        List of QueryContext field names that must be present and non-empty
        before this stage may run.
        """
        ...

    @final
    def validate(self, context: QueryContext) -> None:
        """
        Check every required field on *context*.

        Rules:
          - None  → missing
          - ""    → missing (empty string is treated the same as absent)
          - {}    → NOT missing (an empty dict is a valid value for dict fields)

        Raises:
            MissingContextFieldsError: if one or more required fields are absent.
        """
        missing: list[str] = []

        for field in self.required_fields:
            value = getattr(context, field, None)

            # None is always missing
            if value is None:
                missing.append(field)
                continue

            # Empty string counts as missing for string fields only
            if isinstance(value, str) and value.strip() == "":
                missing.append(field)

        if missing:
            field_list = ", ".join(missing)
            raise MissingContextFieldsError(
                message=(
                    f"Stage '{self.stage_name}' is missing required context "
                    f"field(s): {field_list}"
                ),
                missing_fields=missing,
            )


# ---------------------------------------------------------------------------
# Concrete strategies — one per stage
# ---------------------------------------------------------------------------

class AppIdentifierRequirements(StageRequirements):
    """
    Stage: app-identifier
    The agent calls this first — it only knows the raw NL query.
    app_id is NOT required here; this stage PRODUCES it.
    """

    @property
    def stage_name(self) -> str:
        return "app-identifier"

    @property
    def required_fields(self) -> list[str]:
        return ["nl_query_original"]


class NLToIRRequirements(StageRequirements):
    """
    Stage: nl-to-ir  (architecture v1.6 — replaces intent-extractor + schema-mapper)
    Single LLM call that produces the full simplified IR.
    App must already be identified before this stage runs.
    """

    @property
    def stage_name(self) -> str:
        return "nl-to-ir"

    @property
    def required_fields(self) -> list[str]:
        return ["nl_query_original", "app_id", "app_schema_version"]


class ValidatorRequirements(StageRequirements):
    """
    Stage: validator
    Deterministic validation needs llm_output from the NL-to-IR Strategy.
    llm_output={} (empty dict) is valid — None means the strategy never ran.
    """

    @property
    def stage_name(self) -> str:
        return "validator"

    @property
    def required_fields(self) -> list[str]:
        return ["app_id", "app_schema_version", "llm_output"]


class SqlBuilderRequirements(StageRequirements):
    """
    Stage: sql-builder
    SQL generation requires the validated StructuredQuery object.
    """

    @property
    def stage_name(self) -> str:
        return "sql-builder"

    @property
    def required_fields(self) -> list[str]:
        return ["app_id", "structured_query"]


class FullQueryRequirements(StageRequirements):
    """
    Stage: query  (full pipeline, Foundry-facing)
    Same entry point as app-identifier — only the raw NL query is needed.
    The orchestrator runs all stages internally.
    """

    @property
    def stage_name(self) -> str:
        return "query"

    @property
    def required_fields(self) -> list[str]:
        return ["nl_query_original"]


# ---------------------------------------------------------------------------
# Orchestrator — lookup + dispatch
# ---------------------------------------------------------------------------

class ContextValidator:
    """
    Orchestrates context validation for all Foundry tool endpoints.

    Usage:
        validator = ContextValidator()
        validator.validate(context, stage_name="nl-to-ir")

    Raises:
        ValueError:                  if stage_name is not recognised.
        MissingContextFieldsError:   if required fields are absent/empty.
    """

    def __init__(self) -> None:
        # Build registry once at construction time — Factory pattern.
        # Key   : stage slug that matches the URL path segment
        # Value : StageRequirements strategy instance
        self._registry: dict[str, StageRequirements] = self._build_registry()

    @staticmethod
    def _build_registry() -> dict[str, StageRequirements]:
        """
        Construct all StageRequirements instances and index them by stage name.
        Adding a new stage = add a new class above + one entry here.
        """
        strategies: list[StageRequirements] = [
            AppIdentifierRequirements(),
            NLToIRRequirements(),
            ValidatorRequirements(),
            SqlBuilderRequirements(),
            FullQueryRequirements(),
        ]
        return {s.stage_name: s for s in strategies}

    @property
    def supported_stages(self) -> list[str]:
        """Return sorted list of recognised stage names — useful for error messages."""
        return sorted(self._registry.keys())

    def validate(self, context: QueryContext, stage_name: str) -> None:
        """
        Validate that *context* has all required fields for *stage_name*.

        Args:
            context:    The QueryContext received in the HTTP request body.
            stage_name: The stage slug, e.g. "nl-to-ir".

        Raises:
            ValueError:                Unknown stage_name (programming error).
            MissingContextFieldsError: One or more required fields missing.
        """
        requirements = self._registry.get(stage_name)

        if requirements is None:
            raise ValueError(
                f"Unknown stage '{stage_name}'. "
                f"Supported stages: {self.supported_stages}"
            )

        requirements.validate(context)
