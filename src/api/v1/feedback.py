# src/api/v1/feedback.py
# V0 - Initial implementation
#
# POST /v1/feedback — user-facing feedback submission endpoint.
#
# What this file does:
#   1. Accepts a FeedbackRequest body (request_id, status, optional expected_output,
#      optional actual_sql). Pydantic rejects malformed bodies with HTTP 422 before
#      this handler ever runs.
#   2. Enforces CLIENT_API_KEY auth via Depends(require_client_key) — same key as
#      POST /v1/query, since both are user-facing endpoints.
#   3. Logs the feedback as a USER_FEEDBACK log entry (Phase 1: log only — feedback
#      is recorded for later analysis, it does NOT change pipeline behaviour).
#   4. Returns HTTP 200 with a small success envelope echoing the request_id.
#
# Why no data/meta blocks in the response:
#   The QueryResponse data/meta blocks describe a SQL result (sql, structured_query,
#   app_id, tokens, latency). None of that applies to feedback submission. We return
#   only the shared top-level keys every envelope carries — request_id, status,
#   errors — so the shape stays consistent with QueryResponse/ToolResponse without
#   inventing fields that have no meaning here. (Story 6.4 audits response shapes;
#   flagged there if a dedicated FeedbackResponse model is wanted.)

from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import JSONResponse

from src.api.auth import require_client_key
from src.api.models.request import FeedbackRequest
from src.core.constants import USER_FEEDBACK
from src.core.logging.log_models import LogEntry
from src.core.logging.logger import StructuredLogger

# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------
router = APIRouter()


@router.post("/feedback")
def feedback(
    request: Request,
    body: FeedbackRequest,
    _auth: None = Depends(require_client_key),
) -> JSONResponse:
    """
    POST /v1/feedback — Submit feedback on a previously generated SQL result.

    The body references the original query via request_id and reports whether
    the generated SQL was correct ('pass') or wrong ('fail'), optionally with
    the expected and actual SQL.

    Args:
        request: FastAPI Request — gives access to app.state.settings (needed to
                 construct the StructuredLogger) and app.state.settings.client_api_key
                 (read by the auth dependency).
        body:    Validated FeedbackRequest body. Invalid bodies are rejected by
                 Pydantic with HTTP 422 before this function runs.
        _auth:   Auth dependency result — None on success, raises 401 on failure.

    Returns:
        JSONResponse — HTTP 200 with {request_id, status: "success", errors: []}.
    """
    settings = request.app.state.settings
    logger = StructuredLogger(settings)

    # ------------------------------------------------------------------
    # Log the feedback under the USER_FEEDBACK stage.
    #
    # request_id here is the ORIGINAL query's request_id (carried in the body),
    # so the feedback log entry correlates with the original query's log file.
    #
    # FeedbackRequest carries no user_id, so we pass "" — the same "not populated"
    # convention QueryContext uses for app_id. This is safe whether LogEntry.user_id
    # is required or optional.
    # ------------------------------------------------------------------
    logger.log(
        LogEntry(
            stage=USER_FEEDBACK,
            request_id=body.request_id,
            user_id="",
            payload={
                "status": body.status,
                "expected_output": body.expected_output,
                "actual_sql": body.actual_sql,
            },
        )
    )

    # ------------------------------------------------------------------
    # Success envelope — shared top-level keys only (see module docstring).
    # ------------------------------------------------------------------
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={
            "request_id": body.request_id,
            "status": "success",
            "errors": [],
        },
    )
