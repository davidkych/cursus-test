# ── src/routers/schedule/endpoints.py ────────────────────────────────
"""
/api/schedule – façade in front of the Durable-scheduler Function-App.

Adds robust cold-start back-off for **wipe-all** so that the first call made
immediately after a fresh deployment no longer fails with

    {"detail":"Scheduler wipe endpoint not found"}
"""
from __future__ import annotations

import logging
import os
import time
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
_base_cache: str | None = None           # resolved once, reused thereafter


def _scheduler_base() -> str:
    """
    Resolve the Function-App base URL with robust fallbacks.

    1. `SCHEDULER_BASE_URL`   – unless it points to localhost / dev
    2. `SCHEDULER_FUNCTION_NAME` → https://<name>.azurewebsites.net
    3. localhost default
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
    """Return “&code=…” segment only when a **non-empty** key exists."""
    key = (os.getenv("SCHEDULER_MGMT_KEY") or "").strip()
    return f"&code={key}" if key else ""


def _status_url(instance_id: str) -> str:
    """
    Build a status-polling URL.

    • If a host/function key is configured we return the richer Durable
      runtime endpoint (requires the key).
    • Otherwise we fall back to the anonymous helper endpoint exposed by
      the scheduler (`/api/status/{id}`) to avoid 401s.
    """
    base = _scheduler_base()
    key_qs = _mgmt_key_qs().lstrip("&")

    if key_qs:                         # key available ⇒ runtime endpoint
        return f"{base}/runtime/webhooks/durabletask/instances/{instance_id}?{key_qs}"

    return f"{base}/api/status/{instance_id}"        # anonymous endpoint


def _terminate_url(instance_id: str) -> str:
    return (
        f"{_scheduler_base()}/runtime/webhooks/durabletask/instances/"
        f"{instance_id}/terminate?reason=user+cancelled{_mgmt_key_qs()}"
    )


def _forward_error(resp: requests.Response) -> None:
    """
    Mirror the scheduler’s failure payload back to the caller **with context**
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
    qs = _mgmt_key_qs().lstrip("&")                # reuse system key if present
    return f"{_scheduler_base()}/api/schedules{('?' + qs) if qs else ''}"


# ──────────────────────────────────────────────────────────────────────
# routes
# ----------------------------------------------------------------------
_COLD_RETRIES = int(os.getenv("SCHEDULER_COLD_START_RETRIES", "4"))
_COLD_DELAY   = int(os.getenv("SCHEDULER_COLD_START_DELAY", "5"))   # seconds


@router.post(
    "/api/schedule",
    response_model=ScheduleResponse,
    summary="Create a new schedule",
)
def create_schedule(req: ScheduleRequest):
    """
    Forward the request to the scheduler Function-App, coping with cold-start
    404s by retrying a few times before giving up.
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

    tried_resp: requests.Response | None = None
    for path in ("/api/schedule", "/schedule"):
        url = f"{_scheduler_base()}{path}"
        _log.info("Forwarding schedule request → %s", url)

        try:
            resp = _attempt_forward(url)
        except Exception as exc:                    # noqa: BLE001
            _log.exception("Unable to reach scheduler")
            raise HTTPException(status_code=504, detail=str(exc)) from exc

        if resp.status_code == 404:
            tried_resp = resp
            continue
        if resp.status_code not in (200, 202):
            _forward_error(resp)
        return _extract_instance(resp)              # success

    # cold-start back-off -----------------------------------------------------
    if tried_resp is not None and tried_resp.status_code == 404:
        _log.info("Scheduler likely cold – retrying %s× after %s s delays",
                  _COLD_RETRIES, _COLD_DELAY)
        for _ in range(_COLD_RETRIES):
            time.sleep(_COLD_DELAY)
            try:
                resp = _attempt_forward(f"{_scheduler_base()}/api/schedule")
            except Exception:
                continue                            # network issue – try again

            if resp.status_code in (200, 202):
                return _extract_instance(resp)
            if resp.status_code not in (404, 503):
                _forward_error(resp)

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
        _log.error("Unable to extract instance-id – status=%s, text=%s",
                   resp.status_code, (resp.text or "")[:200])
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
    except Exception as exc:                         # noqa: BLE001
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
    except Exception as exc:                         # noqa: BLE001
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
    Returns whatever the scheduler reports, typically::

        { "jobs": [ { … }, … ] }
    """
    for path in (_list_url(), _list_url().replace("/api/schedules", "/schedules")):
        try:
            resp = requests.get(path, timeout=15)
        except Exception as exc:                     # noqa: BLE001
            _log.warning("Scheduler unreachable at %s: %s", path, exc)
            continue

        if resp.status_code == 200:
            return Response(content=resp.content, media_type="application/json")
        if resp.status_code in (404, 503):
            continue                                # cold-start? try alt path
        _forward_error(resp)

    raise HTTPException(status_code=502, detail="Scheduler list endpoint not found")


# ──────────────────────────────────────────────────────────────────────
# NEW – wipe-all route  (now with cold-start back-off)
# ----------------------------------------------------------------------
@router.delete(
    "/api/schedule",
    summary="Wipe **all** schedules (terminate, purge, clear registry)",
)
def wipe_schedules():
    """
    Instruct the scheduler Function-App to terminate & purge **every**
    orchestration instance and clear the registry entity.

    Falls back to plain `/wipe` when the host sets `routePrefix=''`.
    Retries on 404/503 for freshly-deployed (cold) Functions.
    """
    for retry in range(_COLD_RETRIES + 1):
        for path in ("/api/wipe", "/wipe"):
            url = f"{_scheduler_base()}{path}"
            try:
                resp = requests.post(url, timeout=30)
            except Exception as exc:                 # noqa: BLE001
                _log.warning("Scheduler unreachable at %s: %s", url, exc)
                continue

            if resp.status_code == 200:
                return Response(content=resp.content, media_type="application/json")
            if resp.status_code in (404, 503):
                continue                             # cold / not yet loaded
            _forward_error(resp)                     # other errors → bubble up

        # give the Function-App a moment to warm up
        if retry < _COLD_RETRIES:
            _log.info("wipe: scheduler cold – backing off %s s (retry %s/%s)",
                      _COLD_DELAY, retry + 1, _COLD_RETRIES)
            time.sleep(_COLD_DELAY)

    raise HTTPException(status_code=502, detail="Scheduler wipe endpoint not found")
