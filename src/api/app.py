# src/api/app.py
# V0 - Initial implementation
#
# Factory function that creates and configures the FastAPI application.
# Runs a startup event that:
#   1. Loads settings (YAML + .env)
#   2. Loads schemas from disk into SchemaRepository
#   3. Validates schemas via SchemaValidator
#   4. Stores all results on app.state for health endpoints to read
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

    # Register routers
    from src.api.health import router as health_router
    app.include_router(health_router)

    # Foundry tool routers
    # feedback_tool: POST /v1/tools/feedback — Phase 3 placeholder, returns 501
    from src.api.tools.feedback_tool import router as feedback_tool_router
    app.include_router(feedback_tool_router, prefix="/v1/tools")

    return app
