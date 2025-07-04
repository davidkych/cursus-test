# ── src/routers/schedule/endpoints.py ─────────────────────────────────
"""
/api/schedule – façade in front of the Durable-scheduler Function-App.

POST    /api/schedule                       → create a new schedule
GET     /api/schedule/{id}/status           → query runtime status
DELETE  /api/schedule/{id}                  → cancel / terminate a schedule
"""
from __future__ import annotations

import logging
import os
from typing import Any

import requests
from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel, Field

router = APIRouter()
_log = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────────
# Pydantic models
# ----------------------------------------------------------------------
class ScheduleRequest(BaseModel):
    exec_at: str = Field(
        ...,
        description="*Naive* ISO-8601 datetime **in HKT** "
        "(e.g. 2025-07-06T15:30:00 – must be ≥ 60 s in the future)",
    )
    prompt_type: str = Field(..., description="e.g. `log.append`, `http.call`")
    payload: dict[str, Any] = Field(
        ..., description="Arbitrary JSON payload forwarded to the prompt handler"
    )


class ScheduleResponse(BaseModel):
    transaction_id: str


# ──────────────────────────────────────────────────────────────────────
# helpers
# ----------------------------------------------------------------------
def _scheduler_base() -> str:
    """Return https://<scheduler>.azurewebsites.net (or localhost during dev)."""
    if (base := os.getenv("SCHEDULER_BASE_URL")):
        return base.rstrip("/")
    if (fn := os.getenv("SCHEDULER_FUNCTION_NAME")):
        return f"https://{fn}.azurewebsites.net"
    return "http://localhost:7071"


def _mgmt_key_qs() -> str:
    return f"&code={os.getenv('SCHEDULER_MGMT_KEY')}" if os.getenv("SCHEDULER_MGMT_KEY") else ""


def _status_url(instance_id: str) -> str:
    qs = _mgmt_key_qs().lstrip("&")
    return (
        f"{_scheduler_base()}/runtime/webhooks/durabletask/instances/{instance_id}"
        f"{'?' + qs if qs else ''}"
    )


def _terminate_url(instance_id: str) -> str:
    return (
        f"{_scheduler_base()}/runtime/webhooks/durabletask/instances/"
        f"{instance_id}/terminate?reason=user+cancelled{_mgmt_key_qs()}"
    )


def _forward_error(resp: requests.Response) -> None:
    """Mirror the scheduler’s failure payload back to the caller."""
    try:
        detail = resp.json()
    except ValueError:
        detail = resp.text or "scheduler error"
    raise HTTPException(status_code=resp.status_code, detail=detail)


# ──────────────────────────────────────────────────────────────────────
# routes
# ----------------------------------------------------------------------
@router.post("/api/schedule", response_model=ScheduleResponse, summary="Create a new schedule")
def create_schedule(req: ScheduleRequest):
    # NOTE: the Function-App route is **/schedule** (no /api prefix)
    url = f"{_scheduler_base()}/schedule"
    _log.info("Forwarding schedule request → %s", url)

    # — call the Function-App (retry once to soften cold-start hiccups) —
    try:
        for attempt in (1, 2):
            try:
                resp = requests.post(url, json=req.model_dump(), timeout=30)
                break
            except requests.Timeout:
                _log.warning("scheduler timeout (attempt %s)", attempt)
        else:  # pragma: no cover
            raise requests.Timeout("scheduler unreachable (30 s × 2)")
    except Exception as exc:  # noqa: BLE001
        _log.exception("Unable to reach scheduler")
        raise HTTPException(status_code=504, detail=str(exc)) from exc

    # — non-success? just proxy back whatever we got —
    if resp.status_code not in (200, 202):
        _forward_error(resp)

    # — extract instance-id (body *or* Location header) —
    instance_id: str | None = None
    try:
        body = resp.json()
        instance_id = body.get("id")
    except ValueError:  # empty / non-JSON body
        pass

    if not instance_id:
        loc = resp.headers.get("Location") or resp.headers.get("location")
        if loc and "/instances/" in loc:
            instance_id = loc.split("/instances/")[-1].split("?")[0]

    if not instance_id:
        _log.error(
            "Unable to extract instance-id – status=%s, headers=%s, text=%s",
            resp.status_code,
            {k: v for k, v in resp.headers.items() if k.lower() in ("location", "retry-after")},
            (resp.text or "")[:200],
        )
        raise HTTPException(status_code=502, detail="Scheduler response missing instance-id")

    _log.info("Scheduled instance %s", instance_id)
    return ScheduleResponse(transaction_id=instance_id)


@router.get("/api/schedule/{transaction_id}/status", summary="Fetch Durable runtime status")
def get_schedule_status(transaction_id: str):
    url = _status_url(transaction_id)
    _log.debug("Status poll → %s", url)

    try:
        resp = requests.get(url, timeout=15)
    except Exception as exc:  # noqa: BLE001
        _log.exception("Scheduler unreachable")
        raise HTTPException(status_code=504, detail=str(exc)) from exc

    if resp.status_code == 200:
        return Response(content=resp.content, media_type="application/json")
    if resp.status_code == 404:
        raise HTTPException(status_code=404, detail="Transaction not found")
    _forward_error(resp)


@router.delete(
    "/api/schedule/{transaction_id}",
    status_code=204,
    summary="Terminate a pending schedule",
)
def delete_schedule(transaction_id: str):
    url = _terminate_url(transaction_id)
    _log.info("Terminate %s → %s", transaction_id, url)

    try:
        resp = requests.post(url, timeout=15)
    except Exception as exc:  # noqa: BLE001
        _log.exception("Scheduler unreachable")
        raise HTTPException(status_code=504, detail=str(exc)) from exc

    if resp.status_code in (202, 204):
        return
    if resp.status_code == 404:
        raise HTTPException(
            status_code=404, detail="Transaction not found / already completed"
        )
    _forward_error(resp)
