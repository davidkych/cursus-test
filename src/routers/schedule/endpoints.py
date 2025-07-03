"""
/api/schedule – thin façade in front of the Durable-scheduler Function-App.

POST   /api/schedule               → create a new schedule
DELETE /api/schedule/{instanceId}  → cancel an existing schedule
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
import os, requests, logging

router = APIRouter()
_log   = logging.getLogger(__name__)

# ── Pydantic schemas ─────────────────────────────────────────────────
class ScheduleRequest(BaseModel):
    exec_at:     str  = Field(..., description="Naive ISO-8601 datetime in **HKT**")
    prompt_type: str  = Field(..., description="e.g. log.append, http.call")
    payload:     dict = Field(..., description="Arbitrary JSON payload for the prompt")

class ScheduleResponse(BaseModel):
    transaction_id: str


# ── helpers ──────────────────────────────────────────────────────────
def _scheduler_base() -> str:
    """
    Resolve the base URL of the scheduler Function-App.

    Preferred:   SCHEDULER_BASE_URL=https://<name>.azurewebsites.net
    Fallback:    SCHEDULER_FUNCTION_NAME -> inferred hostname
    Last resort: http://localhost:7071 (Azurite / func start)
    """
    if (base := os.getenv("SCHEDULER_BASE_URL")):
        return base.rstrip("/")
    if (name := os.getenv("SCHEDULER_FUNCTION_NAME")):
        return f"https://{name}.azurewebsites.net"
    return "http://localhost:7071"


def _terminate_url(instance_id: str) -> str:
    """
    Build the Durable‐Functions management URI for termination.
    Adds the host-level function key if SCHEDULER_MGMT_KEY is set.
    """
    key = os.getenv("SCHEDULER_MGMT_KEY")
    url = (
        f"{_scheduler_base()}/runtime/webhooks/durabletask"
        f"/instances/{instance_id}/terminate?reason=user+cancelled"
    )
    if key:
        url += f"&code={key}"
    return url


# ── routes ───────────────────────────────────────────────────────────
@router.post("/api/schedule", response_model=ScheduleResponse, summary="Create a new schedule")
def create_schedule(req: ScheduleRequest):
    url = f"{_scheduler_base()}/api/schedule"
    _log.info("Forwarding schedule request to %s", url)

    try:
        resp = requests.post(url, json=req.dict(), timeout=10)
    except Exception as exc:                    # noqa: BLE001
        _log.exception("Scheduler unreachable")
        raise HTTPException(status_code=502, detail=f"Scheduler unreachable: {exc}") from exc

    if resp.status_code not in (200, 202):
        _log.error("Scheduler error (%s): %s", resp.status_code, resp.text)
        raise HTTPException(status_code=resp.status_code, detail=resp.text)

    body = resp.json()
    _log.info("Scheduled instance %s", body.get("id"))
    return ScheduleResponse(transaction_id=body["id"])


@router.delete("/api/schedule/{transaction_id}", status_code=204,
               summary="Delete (terminate) a pending schedule")
def delete_schedule(transaction_id: str):
    url = _terminate_url(transaction_id)
    _log.info("Terminating instance %s via %s", transaction_id, url)

    try:
        resp = requests.post(url, timeout=10)
    except Exception as exc:                    # noqa: BLE001
        _log.exception("Scheduler unreachable")
        raise HTTPException(status_code=502, detail=f"Scheduler unreachable: {exc}") from exc

    if resp.status_code == 202:                 # Accepted – termination queued
        return
    if resp.status_code == 404:
        raise HTTPException(status_code=404, detail="Transaction not found or already completed")

    _log.error("Termination failed (%s): %s", resp.status_code, resp.text)
    raise HTTPException(status_code=resp.status_code, detail=resp.text)
