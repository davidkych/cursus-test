# src/routers/schedule/status.py
import logging
import requests
from fastapi import HTTPException, Response
from .helpers import status_url, forward_error

_logger = logging.getLogger(__name__)

def handle_status(transaction_id: str):
    url = status_url(transaction_id)
    try:
        resp = requests.get(url, timeout=15)
    except Exception as exc:
        _logger.exception("Scheduler unreachable")
        raise HTTPException(status_code=504, detail=str(exc)) from exc

    if resp.status_code == 200:
        return Response(content=resp.content, media_type="application/json")
    if resp.status_code == 404:
        raise HTTPException(status_code=404, detail="Transaction not found")
    forward_error(resp)
