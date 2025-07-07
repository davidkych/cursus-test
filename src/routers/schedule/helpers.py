# src/routers/schedule/helpers.py
import os
import logging
from typing import Optional
from fastapi import HTTPException

# constants for cold-start retries/delays
COLD_RETRIES = int(os.getenv("SCHEDULER_COLD_START_RETRIES", "4"))
COLD_DELAY   = int(os.getenv("SCHEDULER_COLD_START_DELAY", "5"))

_logger = logging.getLogger(__name__)
_base_cache: Optional[str] = None

def scheduler_base() -> str:
    global _base_cache
    if _base_cache:
        return _base_cache

    base = os.getenv("SCHEDULER_BASE_URL", "").rstrip("/")
    if base.endswith("/api"):
        base = base[:-4]
    if base and not base.startswith(("http://localhost", "http://127.0.0.1")):
        _base_cache = base
        return _base_cache

    if fn := os.getenv("SCHEDULER_FUNCTION_NAME"):
        _base_cache = f"https://{fn}.azurewebsites.net"
        return _base_cache

    _base_cache = "http://localhost:7071"
    _logger.warning("Scheduler base unresolved – falling back to %s", _base_cache)
    return _base_cache

def mgmt_key_qs() -> str:
    key = (os.getenv("SCHEDULER_MGMT_KEY") or "").strip()
    return f"&code={key}" if key else ""

def status_url(instance_id: str) -> str:
    base = scheduler_base()
    key_qs = mgmt_key_qs().lstrip("&")
    if key_qs:
        return f"{base}/runtime/webhooks/durabletask/instances/{instance_id}?{key_qs}"
    return f"{base}/api/status/{instance_id}"

def terminate_url(instance_id: str) -> str:
    key_seg = mgmt_key_qs()
    if key_seg:
        return (
            f"{scheduler_base()}/runtime/webhooks/durabletask/instances/"
            f"{instance_id}/terminate?reason=user+cancelled{key_seg}"
        )
    return f"{scheduler_base()}/api/terminate/{instance_id}"

def list_url() -> str:
    qs = mgmt_key_qs().lstrip("&")
    return f"{scheduler_base()}/api/schedules{('?' + qs) if qs else ''}"

def forward_error(resp):
    try:
        raw = resp.json()
    except ValueError:
        raw = resp.text or f"HTTP {resp.status_code} with empty body"
    detail = {
        "scheduler_status": resp.status_code,
        "scheduler_body":   raw,
        "scheduler_headers": {
            k: v
            for k, v in resp.headers.items()
            if k.lower()
               in ("content-type", "x-functions-execution-id",
                   "retry-after", "durable-functions-instance-id")
        },
    }
    raise HTTPException(status_code=resp.status_code, detail=detail)

def extract_instance(resp) -> str:
    instance_id = None
    try:
        instance_id = resp.json().get("id")
    except ValueError:
        pass

    if not instance_id:
        loc = resp.headers.get("Location") or resp.headers.get("location")
        if loc and "/instances/" in loc:
            instance_id = loc.split("/instances/")[-1].split("?")[0]

    if not instance_id:
        _logger.error(
            "Unable to extract instance-id – status=%s, text=%s",
            resp.status_code, (resp.text or "")[:200]
        )
        raise HTTPException(
            status_code=502,
            detail={
                "error": "Scheduler response missing instance-id",
                "raw": resp.text,
            },
        )

    return instance_id
