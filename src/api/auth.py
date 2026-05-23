# src/api/auth.py
# V0 - Initial implementation
#
# FastAPI dependency functions for API key authentication.
#
# HOW FASTAPI DEPENDENCIES WORK:
#   A dependency is a function FastAPI calls automatically before your route handler.
#   If the dependency raises an exception, the route never runs.
#   Each protected route declares which dependency it needs via Depends():
#
#       @router.post("/v1/query")
#       def query(auth: None = Depends(require_client_key)):
#           ...
#
# TWO KEYS — TWO DEPENDENCIES:
#   require_client_key  → validates X-API-Key against settings.client_api_key
#                         Used on POST /v1/query
#   require_foundry_key → validates X-API-Key against settings.foundry_api_key
#                         Used on POST /v1/tools/*
#
# AUTH FAILURE RESPONSE (both missing and wrong key):
#   HTTP 401  { "detail": "Unauthorized" }
#   Same response for both cases — no information leakage.
#
# KEY MATCHING:
#   Exact match only. No whitespace trimming — caller's responsibility.
#   Empty string treated same as missing key → 401.

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import APIKeyHeader

# ---------------------------------------------------------------------------
# Header extractor
# ---------------------------------------------------------------------------
# APIKeyHeader is a FastAPI utility that extracts a named header value.
# auto_error=False means FastAPI will NOT automatically raise 422 if the
# header is missing — we handle missing headers ourselves (returning 401,
# not 422 Unprocessable Entity).
# ---------------------------------------------------------------------------

_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


# ---------------------------------------------------------------------------
# Shared 401 exception — defined once, raised by both dependencies
# ---------------------------------------------------------------------------

_UNAUTHORIZED = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Unauthorized",
)


# ---------------------------------------------------------------------------
# Dependency: require_client_key
# Protects: POST /v1/query
# Validates: X-API-Key header against settings.client_api_key
# ---------------------------------------------------------------------------

def require_client_key(
    request: Request,
    x_api_key: str | None = Depends(_api_key_header),
) -> None:
    """
    FastAPI dependency — enforces CLIENT_API_KEY authentication.

    Args:
        request:   FastAPI Request object (gives access to app.state.settings).
        x_api_key: Value extracted from X-API-Key header. None if header absent.

    Raises:
        HTTPException 401: If header is missing, empty, or does not exactly
                           match settings.client_api_key.
    """
    # Missing or empty header
    if not x_api_key:
        raise _UNAUTHORIZED

    # Read configured key from app state (set during startup lifespan)
    configured_key: str | None = request.app.state.settings.client_api_key

    # Key not configured (dev only — prod blocked at startup)
    # or provided key does not exactly match
    if not configured_key or x_api_key != configured_key:
        raise _UNAUTHORIZED


# ---------------------------------------------------------------------------
# Dependency: require_foundry_key
# Protects: POST /v1/tools/*
# Validates: X-API-Key header against settings.foundry_api_key
# ---------------------------------------------------------------------------

def require_foundry_key(
    request: Request,
    x_api_key: str | None = Depends(_api_key_header),
) -> None:
    """
    FastAPI dependency — enforces FOUNDRY_API_KEY authentication.

    Args:
        request:   FastAPI Request object (gives access to app.state.settings).
        x_api_key: Value extracted from X-API-Key header. None if header absent.

    Raises:
        HTTPException 401: If header is missing, empty, or does not exactly
                           match settings.foundry_api_key.
    """
    # Missing or empty header
    if not x_api_key:
        raise _UNAUTHORIZED

    # Read configured key from app state (set during startup lifespan)
    configured_key: str | None = request.app.state.settings.foundry_api_key

    # Key not configured (dev only — prod blocked at startup)
    # or provided key does not exactly match
    if not configured_key or x_api_key != configured_key:
        raise _UNAUTHORIZED
