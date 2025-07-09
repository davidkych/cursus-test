# ── src/routers/log/endpoints.py ──────────────────────────────────────
from typing import Optional, List
from datetime import datetime, date
from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from azure.cosmos import CosmosClient, exceptions
from azure.identity import DefaultAzureCredential
import os

# ── Pydantic payload ---------------------------------------------------
class LogPayload(BaseModel):
    tag:           str                = Field(..., description="Secondary tag")
    tertiary_tag:  Optional[str]      = Field(None, description="Tertiary tag")
    base:          str                = Field(..., description="info | debug | schedule … (without brackets)")
    message:       str                = Field(..., description="Free-text log body")

# ── Router -------------------------------------------------------------
router = APIRouter()

# ── Cosmos setup (same env vars as jsondata module) --------------------
_cosmos_endpoint = os.getenv("COSMOS_ENDPOINT")
_database_name   = os.getenv("COSMOS_DATABASE",  "cursusdb")
_container_name  = os.getenv("COSMOS_CONTAINER", "jsonContainer")
_cosmos_key      = os.getenv("COSMOS_KEY")

if _cosmos_key:
    _client = CosmosClient(_cosmos_endpoint, credential=_cosmos_key)
else:
    _client = CosmosClient(_cosmos_endpoint, credential=DefaultAzureCredential())

_database  = _client.get_database_client(_database_name)
_container = _database.get_container_client(_container_name)

# ── Helpers ------------------------------------------------------------
def _item_id(
    tag: str,
    secondary_tag: Optional[str],
    tertiary_tag:  Optional[str],
    year: int,
    month: int,
    day: int
) -> str:
    """Re-implement the same ID logic used by /api/json."""
    parts = [tag]
    if secondary_tag:
        parts.append(secondary_tag)
    if tertiary_tag:
        parts.append(tertiary_tag)
    parts.extend(map(str, (year, month, day)))
    return "_".join(parts)

def _today_hkt() -> date:
    return datetime.now(ZoneInfo("Asia/Hong_Kong")).date()

def _current_ts_hkt() -> str:
    return datetime.now(ZoneInfo("Asia/Hong_Kong")).isoformat(timespec="seconds")

# ── Endpoint -----------------------------------------------------------
@router.post("/api/log", summary="Append a structured log line")
def append_log(payload: LogPayload):
    today = _today_hkt()
    item_id = _item_id(
        "log",
        payload.tag,
        payload.tertiary_tag,
        today.year, today.month, today.day
    )

    # Try to fetch existing log record
    try:
        item = _container.read_item(item=item_id, partition_key="log")
        logs: List[dict] = item.get("data", [])
    except exceptions.CosmosResourceNotFoundError:
        # First log of the day — start a fresh list
        logs = []
        item = {
            "id":            item_id,
            "tag":           "log",
            "secondary_tag": payload.tag,
            "tertiary_tag":  payload.tertiary_tag,
            "quaternary_tag": None,
            "quinary_tag":    None,
            "year":          today.year,
            "month":         today.month,
            "day":           today.day,
            "data":          logs,
        }

    # Append new log entry (do NOT mutate earlier items)
    logs.append({
        "timestamp":  _current_ts_hkt(),
        "base":       f"[{payload.base}]",
        "message":    payload.message,
        "tertiary_tag": payload.tertiary_tag,
        "secondary_tag": payload.tag
    })

    # Upsert back into Cosmos
    _container.upsert_item(item)

    return {
        "status":  "success",
        "log_id":  item_id,
        "entries": len(logs)
    }
