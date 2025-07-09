# src/routers/schedule/delete.py
import logging
import requests
from fastapi import HTTPException
from .helpers import terminate_url, forward_error

_logger = logging.getLogger(__name__)

def handle_delete(transaction_id: str):
    url = terminate_url(transaction_id)
    try:
        resp = requests.post(url, timeout=15)
    except Exception as exc:
        _logger.exception("Scheduler unreachable")
        raise HTTPException(status_code=504, detail=str(exc)) from exc

    if resp.status_code in (202, 204):
        return
    if resp.status_code == 404:
        raise HTTPException(
            status_code=404,
            detail="Transaction not found / already completed",
        )
    forward_error(resp)
