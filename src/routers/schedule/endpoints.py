# ── src/routers/schedule/endpoints.py ─────────────────────────────────
"""
/api/schedule – façade in front of the Durable-scheduler Function-App.
"""
from __future__ import annotations

import logging
import os
import time                       # ← NEW
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
_base_cache: str | None = None               # resolved once, reused thereafter


def _scheduler_base() -> str:
    """
    Resolve the Function-App base URL with robust fallbacks.

    1. `SCHEDULER_BASE_URL` – unless it points to localhost / dev.
    2. `SCHEDULER_FUNCTION_NAME` – → https://<name>.azurewebsites.net
    3. localhost default.
    """
    global _base_cache
    if _base_cache:
        return _base_cache

    base = os.getenv("SCHEDULER_BASE_URL", "").rstrip("/")

    # strip accidental “/api”
    if base.endswith("/api"):
        base = base[:-4]

    if base and not base.startswith(("http://localhost", "http://127.0.0.1")):
        _base_cache = base
        return _base_cache

    if fn := os.getenv("SCHEDULER_FUNCTION_NAME"):
        _base_cache = f"https://{fn}.azurewebsites.net"
        return _base_cache

    _base_cache = "http://localhost:7071"
    _log.warning("Scheduler base unresolved – falling back to %s", _base_cache)
    return _base_cache


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
    """
    Mirror the scheduler’s failure payload back to the caller **with context**,
    so callers can see *why* the Function-App rejected the request.
    """
    try:
        raw_detail = resp.json()
    except ValueError:
        raw_detail = resp.text or f"HTTP {resp.status_code} with empty body"

    detail = {
        "scheduler_status": resp.status_code,
        "scheduler_body": raw_detail,
        "scheduler_headers": {
            k: v
            for k, v in resp.headers.items()
            if k.lower()
            in (
                "content-type",
                "x-functions-execution-id",
                "retry-after",
                "durable-functions-instance-id",
            )
        },
    }
    raise HTTPException(status_code=resp.status_code, detail=detail)

def _list_url() -> str:
    qs = _mgmt_key_qs().lstrip("&")          # re-use system key if present
    return f"{_scheduler_base()}/api/schedules{('?' + qs) if qs else ''}"

# ──────────────────────────────────────────────────────────────────────
# routes
# ----------------------------------------------------------------------
_COLD_RETRIES = int(os.getenv("SCHEDULER_COLD_START_RETRIES", "4"))   # ← NEW
_COLD_DELAY   = int(os.getenv("SCHEDULER_COLD_START_DELAY",   "5"))   # ← NEW


@router.post(
    "/api/schedule",
    response_model=ScheduleResponse,
    summary="Create a new schedule",
)
def create_schedule(req: ScheduleRequest):
    """
    Forwards the request to the scheduler Function-App, coping with **cold-start**
    404s by retrying a few times before giving up.

    Azure Functions prepend **/api** by default; if the host has
    `routePrefix=''` we quietly fall back to `/schedule`.
    """
    payload = req.model_dump()

    def _attempt_forward(url: str) -> requests.Response:
        """POST once, retrying on `requests.Timeout`."""
        for attempt in (1, 2):
            try:
                return requests.post(url, json=payload, timeout=30)
            except requests.Timeout:
                _log.warning("Scheduler timeout (attempt %s) for %s", attempt, url)
        raise requests.Timeout("Scheduler unreachable (30 s × 2)")

    # ── main try (fast path) ─────────────────────────────────────────
    tried_resp: requests.Response | None = None
    for path in ("/api/schedule", "/schedule"):
        url   = f"{_scheduler_base()}{path}"
        _log.info("Forwarding schedule request → %s", url)

        try:
            resp = _attempt_forward(url)
        except Exception as exc:                    # noqa: BLE001
            _log.exception("Unable to reach scheduler")
            raise HTTPException(status_code=504, detail=str(exc)) from exc

        if resp.status_code == 404:
            tried_resp = resp
            continue
        if resp.status_code not in (200, 202):      # propagate any other error
            _forward_error(resp)
        return _extract_instance(resp)              # success

    # ── cold-start back-off loop (only if *both* paths returned 404) ─
    if tried_resp is not None and tried_resp.status_code == 404:
        _log.info("Scheduler likely cold – retrying %s× after %s s delays",
                  _COLD_RETRIES, _COLD_DELAY)
        for n in range(_COLD_RETRIES):
            time.sleep(_COLD_DELAY)                 # blocking delay – acceptable
            try:
                resp = _attempt_forward(f"{_scheduler_base()}/api/schedule")
            except Exception:
                continue                            # network issue – try next loop

            if resp.status_code in (200, 202):
                return _extract_instance(resp)
            if resp.status_code not in (404, 503):
                _forward_error(resp)                # some other error → abort

    # ── still no luck → bubble up last 404 so clients see why ────────
    if tried_resp is not None:
        _forward_error(tried_resp)
    raise HTTPException(status_code=502, detail="Scheduler endpoint not found")


def _extract_instance(resp: requests.Response) -> ScheduleResponse:
    """Pull Durable `instance_id` from body or Location header."""
    instance_id: str | None = None
    try:
        instance_id = resp.json().get("id")
    except ValueError:
        pass

    if not instance_id:
        loc = resp.headers.get("Location") or resp.headers.get("location")
        if loc and "/instances/" in loc:
            instance_id = loc.split("/instances/")[-1].split("?")[0]

    if not instance_id:
        _log.error(
            "Unable to extract instance-id – status=%s, text=%s",
            resp.status_code,
            (resp.text or "")[:200],
        )
        raise HTTPException(
            status_code=502,
            detail={
                "error": "Scheduler response missing instance-id",
                "raw": resp.text,
            },
        )

    return ScheduleResponse(transaction_id=instance_id)


@router.get(
    "/api/schedule/{transaction_id}/status",
    summary="Fetch Durable runtime status",
)
def get_schedule_status(transaction_id: str):
    url = _status_url(transaction_id)

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

    try:
        resp = requests.post(url, timeout=15)
    except Exception as exc:  # noqa: BLE001
        _log.exception("Scheduler unreachable")
        raise HTTPException(status_code=504, detail=str(exc)) from exc

    if resp.status_code in (202, 204):
        return
    if resp.status_code == 404:
        raise HTTPException(
            status_code=404,
            detail="Transaction not found / already completed",
        )
    _forward_error(resp)

@router.get(
    "/api/schedule",
    summary="List all scheduled jobs and their statuses",
)
def list_schedules():
    """
    Returns whatever the scheduler Function-App reports, typically:

        {
          "jobs": [
            { "instanceId": "...", "exec_at_utc": "...", "prompt_type": "...",
              "runtimeStatus": "Completed" | "Running" | "Pending" | ... },
            ...
          ]
        }
    """
    # try /api/schedules first (Functions’ default), then plain /schedules
    for path in (_list_url(), _list_url().replace("/api/schedules", "/schedules")):
        try:
            resp = requests.get(path, timeout=15)
        except Exception as exc:                       # noqa: BLE001
            _log.warning("Scheduler unreachable at %s: %s", path, exc)
            continue

        if resp.status_code == 200:
            return Response(content=resp.content, media_type="application/json")
        if resp.status_code in (404, 503):            # cold-start? try alt path
            continue
        _forward_error(resp)

    raise HTTPException(status_code=502, detail="Scheduler list endpoint not found")
