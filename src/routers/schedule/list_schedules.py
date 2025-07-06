# src/routers/schedule/list_schedules.py
import logging
import requests
from fastapi import HTTPException, Response
from .helpers import list_url, forward_error

_logger = logging.getLogger(__name__)

def handle_list():
    for path in (
        list_url(),
        list_url().replace("/api/schedules", "/schedules")
    ):
        try:
            resp = requests.get(path, timeout=15)
        except Exception as exc:
            _logger.warning("Scheduler unreachable at %s: %s", path, exc)
            continue

        if resp.status_code == 200:
            return Response(content=resp.content, media_type="application/json")
        if resp.status_code in (404, 503):
            continue
        forward_error(resp)

    raise HTTPException(status_code=502, detail="Scheduler list endpoint not found")
