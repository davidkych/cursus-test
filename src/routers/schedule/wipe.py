# src/routers/schedule/wipe.py
import logging
import time
import requests
from fastapi import HTTPException, Response
from .helpers import scheduler_base, forward_error, COLD_RETRIES, COLD_DELAY

_logger = logging.getLogger(__name__)

def handle_wipe():
    for retry in range(COLD_RETRIES + 1):
        for path in ("/api/wipe", "/wipe"):
            url = f"{scheduler_base()}{path}"
            try:
                resp = requests.post(url, timeout=30)
            except Exception as exc:
                _logger.warning("Scheduler unreachable at %s: %s", url, exc)
                continue

            if resp.status_code == 200:
                return Response(content=resp.content, media_type="application/json")
            if resp.status_code in (404, 503):
                continue
            forward_error(resp)

        if retry < COLD_RETRIES:
            _logger.info(
                "wipe: scheduler cold – backing off %s s (retry %s/%s)",
                COLD_DELAY, retry + 1, COLD_RETRIES
            )
            time.sleep(COLD_DELAY)

    raise HTTPException(status_code=502, detail="Scheduler wipe endpoint not found")
