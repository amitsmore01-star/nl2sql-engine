# src/api/v1/apps.py
# V0 - Initial implementation
#
# GET /v1/apps — list all app schemas currently loaded in memory.
#
# What this file does:
#   1. Enforces CLIENT_API_KEY auth via Depends(require_client_key).
#   2. Reads app.state.schema_repo (loaded at startup by the lifespan).
#   3. Calls get_all_schemas() and returns each schema's app_id + version.
#   4. Returns a consistent envelope: {request_id, status, data, errors}.
#
# Why this endpoint exists:
#   Callers (user-facing app, Foundry agent, ops) can discover which app
#   schemas are live and at what version without reading schema files directly.
#   Useful for populating dropdowns, pre-validating app_id before a query,
#   and confirming a schema reload took effect after a service restart.
#
# Response shape:
#   {
#     "request_id": "uuid",
#     "status":     "success",
#     "data": {
#       "apps": [
#         {"app_id": "Acme_app", "version": "1.0"},
#         ...
#       ]
#     },
#     "errors": []
#   }
#
# No request body (GET) — request_id is generated fresh per call.
# No meta block — there is no SQL result, token count, or latency to report.
#
# Error path:
#   schema_repo None (startup failed) → RuntimeError raised →
#   global exception handler (Story 6.2) catches → HTTP 500 INTERNAL_ERROR.
#   This is consistent with how query.py handles the same broken-startup case.

import uuid

from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import JSONResponse

from src.api.auth import require_client_key

# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------
router = APIRouter()


@router.get("/apps")
def apps(
    request: Request,
    _auth: None = Depends(require_client_key),
) -> JSONResponse:
    """
    GET /v1/apps — return the list of all loaded app schemas.

    No request body. A fresh request_id is generated for each call.
    Auth: CLIENT_API_KEY (same key as POST /v1/query).

    Args:
        request: FastAPI Request — provides access to app.state.schema_repo.
        _auth:   Auth dependency — None on success, raises 401 on failure.

    Returns:
        JSONResponse 200 with {request_id, status, data.apps, errors}.
        If schema_repo is None (broken startup), raises RuntimeError →
        global exception handler returns HTTP 500.
    """
    # Generate a request_id — GET has no body, so there is nothing to read one from.
    request_id = str(uuid.uuid4())

    schema_repo = request.app.state.schema_repo

    # Guard: startup may have failed and left schema_repo as None.
    # Raising RuntimeError here lets the global exception handler (middleware.py)
    # produce a structured 500 response — consistent with query.py's same guard.
    if schema_repo is None:
        raise RuntimeError(
            "schema_repo is not initialised — startup may have failed."
        )

    # Read all loaded schemas and build the response list.
    # AppSchema.appId is camelCase (matches the JSON key).
    # We normalise to snake_case app_id in the API response to match the
    # convention used everywhere else in the API (QueryContext, QueryResponse, etc.)
    schemas = schema_repo.get_all_schemas()

    apps_list = [
        {"app_id": schema.appId, "version": schema.version}
        for schema in schemas
    ]

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={
            "request_id": request_id,
            "status": "success",
            "data": {
                "apps": apps_list,
            },
            "errors": [],
        },
    )
