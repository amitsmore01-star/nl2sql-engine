# src/api/health.py
# V0 - Initial implementation
#
# Two health check endpoints — both exempt from authentication.
#
# GET /health  — Liveness check. Always 200 if the process is alive.
# GET /ready   — Readiness check. 200 if all 4 checks pass, 503 if any fail.
#
# The 4 readiness checks:
#   schemas_loaded    — at least 1 schema was loaded from disk
#   schemas_valid     — schemas passed validation
#   llm_provider      — provider name is a non-empty known string
#   log_dir_writable  — log directory exists or can be created

import os
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

router = APIRouter()

# Known valid LLM provider strings — from architecture Section 7.2
_KNOWN_PROVIDERS = {"mock", "openai", "azure_openai", "anthropic"}


# ---------------------------------------------------------------------------
# GET /health — Liveness
# ---------------------------------------------------------------------------

@router.get("/health")
async def health() -> JSONResponse:
    """
    Liveness endpoint.
    Returns 200 as long as the process is running.
    No checks — just proves the server is alive.
    """
    return JSONResponse(
        status_code=200,
        content={
            "status": "ok",
            "timestamp_utc": _utc_now(),
        },
    )


# ---------------------------------------------------------------------------
# GET /ready — Readiness
# ---------------------------------------------------------------------------

@router.get("/ready")
async def ready(request: Request) -> JSONResponse:
    """
    Readiness endpoint.
    Runs 4 checks and returns their individual results.
    Returns 200 if all pass, 503 if any fail.
    """
    checks = {}

    # ----------------------------------------------------------------
    # Check 1 — schemas_loaded
    # ----------------------------------------------------------------
    if getattr(request.app.state, "schemas_loaded_ok", False):
        repo = request.app.state.schema_repo
        app_count = len(repo.get_all_schemas()) if repo else 0
        checks["schemas_loaded"] = {
            "status": "ok",
            "app_count": app_count,
        }
    else:
        error_msg = getattr(request.app.state, "startup_error", None) or "Schema load failed"
        checks["schemas_loaded"] = {
            "status": "error",
            "message": error_msg,
        }

    # ----------------------------------------------------------------
    # Check 2 — schemas_valid
    # ----------------------------------------------------------------
    if getattr(request.app.state, "schemas_valid_ok", False):
        checks["schemas_valid"] = {"status": "ok"}
    else:
        # Only report validation error if schemas loaded successfully
        # (if load failed, validation never ran — avoid double error message)
        if getattr(request.app.state, "schemas_loaded_ok", False):
            error_msg = getattr(request.app.state, "startup_error", None) or "Schema validation failed"
            checks["schemas_valid"] = {
                "status": "error",
                "message": error_msg,
            }
        else:
            checks["schemas_valid"] = {
                "status": "error",
                "message": "Skipped — schemas did not load successfully",
            }

    # ----------------------------------------------------------------
    # Check 3 — llm_provider
    # ----------------------------------------------------------------
    checks["llm_provider"] = _check_llm_provider(request)

    # ----------------------------------------------------------------
    # Check 4 — log_dir_writable
    # ----------------------------------------------------------------
    checks["log_dir_writable"] = _check_log_dir(request)

    # ----------------------------------------------------------------
    # Determine overall status
    # ----------------------------------------------------------------
    all_ok = all(c["status"] == "ok" for c in checks.values())
    http_status = 200 if all_ok else 503

    return JSONResponse(
        status_code=http_status,
        content={
            "status": "ready" if all_ok else "not_ready",
            "checks": checks,
            "timestamp_utc": _utc_now(),
        },
    )


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _check_llm_provider(request: Request) -> dict:
    """
    Check 3 — LLM provider.
    Reads provider name from settings. No real API call made.
    Passes if provider is a non-empty known string.
    """
    settings = getattr(request.app.state, "settings", None)
    if settings is None:
        return {
            "status": "error",
            "message": "Settings not loaded — cannot determine LLM provider",
        }

    provider = getattr(settings.llm, "provider", "").strip()
    if not provider:
        return {
            "status": "error",
            "message": "LLM provider is empty in settings",
        }

    if provider not in _KNOWN_PROVIDERS:
        return {
            "status": "error",
            "message": f"Unknown LLM provider '{provider}'. "
                       f"Must be one of: {sorted(_KNOWN_PROVIDERS)}",
        }

    return {
        "status": "ok",
        "provider": provider,
    }


def _check_log_dir(request: Request) -> dict:
    """
    Check 4 — Log directory writable.
    Tries to create the log directory if it does not exist.
    Passes if the path is (or becomes) a writable directory.
    No actual file is written — existence + is_dir is sufficient.
    """
    settings = getattr(request.app.state, "settings", None)
    log_dir_str = settings.log_dir if settings else "logs"

    log_dir = Path(log_dir_str)

    try:
        log_dir.mkdir(parents=True, exist_ok=True)
    except Exception as exc:
        return {
            "status": "error",
            "message": f"Cannot create log directory '{log_dir}': {exc}",
        }

    if not log_dir.is_dir():
        return {
            "status": "error",
            "message": f"Log dir path '{log_dir}' exists but is not a directory",
        }

    # Check write permission using os.access
    if not os.access(log_dir, os.W_OK):
        return {
            "status": "error",
            "message": f"Log directory '{log_dir}' is not writable",
        }

    return {"status": "ok"}


def _utc_now() -> str:
    """Return current UTC time as ISO 8601 string ending in Z."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
