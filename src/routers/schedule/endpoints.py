# ── src/routers/schedule/endpoints.py ────────────────────────────────
from fastapi import APIRouter
from pydantic import BaseModel, Field
from typing import Any, Optional, List

from .create import handle_create
from .status import handle_status
from .delete import handle_delete
from .list_schedules import handle_list
from .search import handle_search          # ← NEW
from .wipe import handle_wipe

router = APIRouter()

# ── Pydantic models ──────────────────────────────────────────────────
class ScheduleRequest(BaseModel):
    exec_at: str = Field(
        ...,
        description=(
            "ISO-8601 datetime **with offset** "
            "(e.g. 2025-07-06T15:30:00+08:00 or +00:00 – must be ≥ 60 s in the future)"
        ),
    )
    prompt_type: str = Field(..., description="e.g. `log.append`, `http.call`")
    payload: dict[str, Any] = Field(
        ..., description="Arbitrary JSON payload forwarded to the prompt handler"
    )

    # optional tagging metadata
    tag: Optional[str]          = Field(None, description="Primary tag (optional)")
    secondary_tag: Optional[str] = Field(None, description="Secondary tag (optional)")
    tertiary_tag: Optional[str]  = Field(None, description="Tertiary tag (optional)")


class ScheduleResponse(BaseModel):
    transaction_id: str


# ── Routes ───────────────────────────────────────────────────────────
@router.post(
    "/api/schedule",
    response_model=ScheduleResponse,
    summary="Create a new schedule",
)
def create_schedule(req: ScheduleRequest):
    transaction_id = handle_create(req)
    return ScheduleResponse(transaction_id=transaction_id)


@router.get(
    "/api/schedule/{transaction_id}/status",
    summary="Fetch Durable runtime status",
)
def get_schedule_status(transaction_id: str):
    return handle_status(transaction_id)


@router.delete(
    "/api/schedule/{transaction_id}",
    status_code=204,
    summary="Terminate a pending schedule",
)
def delete_schedule(transaction_id: str):
    handle_delete(transaction_id)


@router.get(
    "/api/schedule",
    summary="List all scheduled jobs and their statuses",
)
def list_schedules():
    return handle_list()


@router.delete(
    "/api/schedule",
    summary="Wipe **all** schedules (terminate, purge, clear registry)",
)
def wipe_schedules():
    return handle_wipe()


# ─────────────── NEW: tag-based search endpoint ──────────────────────
@router.get(
    "/api/schedule/search",
    summary="Search instanceIds by tag metadata",
)
def search_schedules(
    tag: Optional[str] = None,
    secondary_tag: Optional[str] = None,
    tertiary_tag: Optional[str] = None,
):
    """
    Return a list of `instance_id` strings whose **tag, secondary_tag, and
    tertiary_tag** match the supplied filters.  Any parameter left blank or
    omitted acts as a wildcard and does **not** restrict the search.
    """
    instance_ids = handle_search(tag, secondary_tag, tertiary_tag)
    return {"instance_ids": instance_ids}
