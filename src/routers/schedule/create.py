# ── src/routers/schedule/create.py ───────────────────────────────────
import logging
import time
import requests
from fastapi import HTTPException
from .helpers import (
    scheduler_base,
    forward_error,
    extract_instance,
    COLD_RETRIES,
    COLD_DELAY,
)

_logger = logging.getLogger(__name__)

# Valid paths Azure Functions may expose (always prefixed with /api/)
_SCHED_PATHS = ("/api/schedule", "/schedule")  # second item is a safety-net


def handle_create(req) -> str:
    """
    Forward the schedule-creation request to the Durable scheduler.

    • Tries every known route once.
    • If the scheduler is cold (404) it retries *both* routes,
      waiting COLD_DELAY seconds between attempts, up to COLD_RETRIES times.
    • Raises HTTP 502 only after all attempts still return 404/503.
    """
    payload = req.model_dump()

    # ── inner helper with 2 × 30 s timeout and logging -----------------
    def _attempt_forward(url: str) -> requests.Response:
        for attempt in (1, 2):
            try:
                return requests.post(url, json=payload, timeout=30)
            except requests.Timeout:
                _logger.warning("Scheduler timeout (attempt %s) for %s", attempt, url)
        raise requests.Timeout("Scheduler unreachable (30 s × 2)")

    # ── first pass – try immediately -----------------------------------
    tried_resp = None
    for path in _SCHED_PATHS:
        url = f"{scheduler_base()}{path}"
        _logger.info("Forwarding schedule request → %s", url)
        try:
            resp = _attempt_forward(url)
        except Exception as exc:
            _logger.exception("Unable to reach scheduler")
            raise HTTPException(status_code=504, detail=str(exc)) from exc

        if resp.status_code == 404:                 # likely cold start
            tried_resp = resp
            continue
        if resp.status_code not in (200, 202):
            forward_error(resp)
        return extract_instance(resp)

    # ── cold-start loop ------------------------------------------------
    if tried_resp and tried_resp.status_code == 404:
        _logger.info(
            "Scheduler likely cold – retrying %s× every %s s",
            COLD_RETRIES, COLD_DELAY,
        )
        for retry in range(1, COLD_RETRIES + 1):
            time.sleep(COLD_DELAY)
            for path in _SCHED_PATHS:               # probe both routes
                try:
                    resp = _attempt_forward(f"{scheduler_base()}{path}")
                except Exception:
                    continue

                if resp.status_code in (200, 202):
                    _logger.info("Cold start resolved after %s attempt(s)", retry)
                    return extract_instance(resp)
                if resp.status_code not in (404, 503):
                    forward_error(resp)

    # ── still no luck – bubble the last error up -----------------------
    if tried_resp:
        forward_error(tried_resp)

    raise HTTPException(status_code=502, detail="Scheduler endpoint not found")
