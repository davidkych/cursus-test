# src/routers/schedule/create.py
import logging
import time
import requests
from fastapi import HTTPException
from .helpers import (
    scheduler_base, forward_error, extract_instance,
    COLD_RETRIES, COLD_DELAY
)

_logger = logging.getLogger(__name__)

def handle_create(req) -> str:
    payload = req.model_dump()

    def attempt_forward(url: str) -> requests.Response:
        for attempt in (1, 2):
            try:
                return requests.post(url, json=payload, timeout=30)
            except requests.Timeout:
                _logger.warning("Scheduler timeout (attempt %s) for %s", attempt, url)
        raise requests.Timeout("Scheduler unreachable (30 s × 2)")

    tried_resp = None
    for path in ("/api/schedule", "/schedule"):
        url = f"{scheduler_base()}{path}"
        _logger.info("Forwarding schedule request → %s", url)
        try:
            resp = attempt_forward(url)
        except Exception as exc:
            _logger.exception("Unable to reach scheduler")
            raise HTTPException(status_code=504, detail=str(exc)) from exc

        if resp.status_code == 404:
            tried_resp = resp
            continue
        if resp.status_code not in (200, 202):
            forward_error(resp)
        return extract_instance(resp)

    # cold-start back-off
    if tried_resp and tried_resp.status_code == 404:
        _logger.info(
            "Scheduler likely cold – retrying %s× after %s s delays",
            COLD_RETRIES, COLD_DELAY
        )
        for _ in range(COLD_RETRIES):
            time.sleep(COLD_DELAY)
            try:
                resp = attempt_forward(f"{scheduler_base()}/api/schedule")
            except Exception:
                continue
            if resp.status_code in (200, 202):
                return extract_instance(resp)
            if resp.status_code not in (404, 503):
                forward_error(resp)

    if tried_resp:
        forward_error(tried_resp)

    raise HTTPException(status_code=502, detail="Scheduler endpoint not found")
