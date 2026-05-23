# src/api/tools/feedback_tool.py
# V0 - Initial implementation — TODO Phase 3 placeholder

"""
Foundry tool endpoint: POST /v1/tools/feedback

TODO Phase 3:
    Agent-submitted feedback after a human reviews the SQL produced by the
    Foundry pipeline.  This mirrors the user-facing POST /v1/feedback but
    accepts a QueryContext body and is protected by FOUNDRY_API_KEY.

    Analysis required before implementation:
      - Does the agent carry the full QueryContext when submitting feedback,
        or just request_id + pass/fail status?
      - Should feedback from the agent be stored separately from user feedback?
      - Should this endpoint update QueryContext.status and re-log
        USER_FEEDBACK stage?

Current behaviour:
    Returns HTTP 501 Not Implemented.
"""

from fastapi import APIRouter
from fastapi.responses import JSONResponse

router = APIRouter()


@router.post(
    "/feedback",
    summary="[TODO Phase 3] Agent feedback submission",
    description=(
        "Planned for Phase 3. Allows the Fabric agent to submit pass/fail "
        "feedback on SQL produced by the pipeline. Currently returns 501."
    ),
)
def tools_feedback() -> JSONResponse:
    """
    TODO Phase 3 — not yet implemented.
    Returns 501 so callers know the route exists but is not ready.
    """
    return JSONResponse(
        status_code=501,
        content={
            "status": "not_implemented",
            "message": (
                "POST /v1/tools/feedback is planned for Phase 3. "
                "It is not available in Phase 1."
            ),
        },
    )
