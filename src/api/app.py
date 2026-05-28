# src/api/app.py
# V0 - Initial implementation
# V1 - Story 2.6: Registered query router (POST /v1/query) under prefix="/v1".
# V2 - Story 3.7: Added LLM provider initialisation at startup.
#                 app.state.llm_provider and app.state.llm_provider_ok now set.
#                 Orchestrator and tool endpoints read llm_provider from app.state.
# V3 - Story 4.1: Registered nl_to_ir_tool router under prefix="/v1/tools".
# V4 - Story 4.6: Registered validator_tool router under prefix="/v1/tools".
# V5 - Story 5.5: Registered sql_builder_tool router under /v1/tools.
# V6 - Story 5.6: Registered app_identifier_tool router under /v1/tools.
# Factory function that creates and configures the FastAPI application.
# Runs a startup event that:
#   1. Loads settings (YAML + .env)
#   2. Loads schemas from disk into SchemaRepository
#   3. Validates schemas via SchemaValidator
#   4. Initialises the LLM provider via LLMProviderFactory
#   5. Stores all results on app.state for health endpoints and pipeline to read
#
# Usage:
#   app = create_app()                        # uses settings.app.schema_dir
#   app = create_app(schema_dir="/tmp/test")  # override — used in tests only

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI

from src.config.settings import load_settings
from src.schema.schema_repository import SchemaRepository
from src.schema.schema_validator import SchemaValidator
from src.core.exceptions import SchemaLoadError
from src.llm.factory import LLMProviderFactory


def create_app(schema_dir: str | Path | None = None) -> FastAPI:
    """
    Create and return a configured FastAPI application.

    Args:
        schema_dir: Override the schema directory path.
                    If None, reads from settings.app.schema_dir.
                    Pass a value in tests to avoid touching real files on disk.

    Returns:
        A FastAPI instance with startup logic wired in.
    """

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        """
        Lifespan context manager — runs startup logic before the app
        accepts any requests, and could run teardown after (not needed yet).

        Why lifespan instead of @app.on_event("startup")?
        FastAPI recommends lifespan as the modern approach.
        It is also easier to test.
        """
        # ----------------------------------------------------------------
        # Initialise all state fields with safe defaults.
        # Health endpoint reads these — they must always exist.
        # ----------------------------------------------------------------
        app.state.settings = None
        app.state.schema_repo = None
        app.state.schemas_loaded_ok = False
        app.state.schemas_valid_ok = False
        app.state.llm_provider = None
        app.state.llm_provider_ok = False
        app.state.startup_error = None
        app.state.schema_dir = None

        # ----------------------------------------------------------------
        # Step 1 — Load settings
        # ----------------------------------------------------------------
        try:
            settings = load_settings()
            app.state.settings = settings
        except Exception as exc:
            # Settings failure is fatal — we cannot proceed at all.
            # Record the error so /ready can report it.
            app.state.startup_error = f"Settings load failed: {exc}"
            yield  # still yield so the app starts and can serve /ready → 503
            return

        # ----------------------------------------------------------------
        # Step 2 — Resolve schema directory
        # schema_dir argument (test override) wins over settings value.
        # ----------------------------------------------------------------
        resolved_schema_dir = (
            Path(schema_dir)
            if schema_dir is not None
            else Path(settings.app.schema_dir)
        )
        app.state.schema_dir = resolved_schema_dir

        # ----------------------------------------------------------------
        # Step 3 — Load schemas
        # ----------------------------------------------------------------
        repo = SchemaRepository()
        try:
            repo.load(resolved_schema_dir)
            app.state.schema_repo = repo
            app.state.schemas_loaded_ok = True
        except SchemaLoadError as exc:
            app.state.startup_error = exc.message
            app.state.schemas_loaded_ok = False
            yield
            return

        # ----------------------------------------------------------------
        # Step 4 — Validate schemas
        # ----------------------------------------------------------------
        validator = SchemaValidator()
        try:
            validator.validate_all(repo.get_all_schemas())
            app.state.schemas_valid_ok = True
        except SchemaLoadError as exc:
            app.state.startup_error = exc.message
            app.state.schemas_valid_ok = False
            yield
            return

        # ----------------------------------------------------------------
        # Step 5 — Initialise LLM provider
        # LLMProviderFactory reads settings.llm.provider to pick the right
        # provider class. In dev/test this will be MockLLMProvider.
        # Tests override app.state.llm_provider directly after startup.
        # ----------------------------------------------------------------
        try:
            llm_provider = LLMProviderFactory.create(settings)
            app.state.llm_provider = llm_provider
            app.state.llm_provider_ok = True
        except Exception as exc:
            app.state.startup_error = f"LLM provider init failed: {exc}"
            app.state.llm_provider_ok = False
            yield
            return

        # ----------------------------------------------------------------
        # All startup steps passed — app is fully ready
        # ----------------------------------------------------------------
        yield
        # (teardown code would go here — nothing needed yet)

    # Create the FastAPI instance, passing in the lifespan manager
    app = FastAPI(
        title="nl2sql-engine",
        version="1.0",
        lifespan=lifespan,
    )

    # ----------------------------------------------------------------
    # Register routers
    # ----------------------------------------------------------------

    # Health endpoints — no prefix, no auth (GET /health, GET /ready)
    from src.api.health import router as health_router
    app.include_router(health_router)

    # User-facing query endpoint — POST /v1/query
    # prefix="/v1" means the route defined as "/query" becomes "/v1/query"
    from src.api.v1.query import router as query_router
    app.include_router(query_router, prefix="/v1")

    # Foundry tool routers — all under /v1/tools
    # feedback_tool: POST /v1/tools/feedback — Phase 3 placeholder, returns 501
    from src.api.tools.feedback_tool import router as feedback_tool_router
    app.include_router(feedback_tool_router, prefix="/v1/tools")

    # nl_to_ir_tool: POST /v1/tools/nl-to-ir — Story 4.1
    from src.api.tools.nl_to_ir_tool import router as nl_to_ir_tool_router
    app.include_router(nl_to_ir_tool_router, prefix="/v1/tools")

    # validator_tool: POST /v1/tools/validator — Story 4.6
    from src.api.tools.validator_tool import router as validator_tool_router
    app.include_router(validator_tool_router, prefix="/v1/tools")

    # sql_builder_tool: POST /v1/tools/sql-builder — Story 5.5
    from src.api.tools.sql_builder_tool import router as sql_builder_tool_router
    app.include_router(sql_builder_tool_router, prefix="/v1/tools")

    # app_identifier_tool: POST /v1/tools/app-identifier — Story 5.6
    from src.api.tools.app_identifier_tool import router as app_identifier_tool_router
    app.include_router(app_identifier_tool_router, prefix="/v1/tools")

    # app_identifier_tool: POST /v1/tools/query_tool — Story 5.7
    from src.api.tools.query_tool import router as query_tool_router
    app.include_router(query_tool_router, prefix="/v1/tools", tags=["tools"])
    return app
