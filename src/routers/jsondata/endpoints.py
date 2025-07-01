# ── src/routers/jsondata/endpoints.py ────────────────────────────────
from typing import Union, Optional
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel, Field
import json, os, datetime
from azure.cosmos import CosmosClient, exceptions
from azure.identity import DefaultAzureCredential

# ── Pydantic model --------------------------------------------------------
class JSONPayload(BaseModel):
    tag:            str            = Field(..., description="Primary tag")
    secondary_tag:  Optional[str]  = Field(None, description="Secondary tag (optional)")
    tertiary_tag:   Optional[str]  = Field(None, description="Tertiary tag (optional)")
    quaternary_tag: Optional[str]  = Field(None, description="Quaternary tag (optional)")
    quinary_tag:    Optional[str]  = Field(None, description="Quinary tag (optional)")
    year:           Optional[int]  = Field(None, ge=1900, description="Year (optional)")
    month:          Optional[int]  = Field(None, ge=1,  le=12,  description="Month (optional)")
    day:            Optional[int]  = Field(None, ge=1,  le=31,  description="Day (optional)")
    data:           Union[dict, list] = Field(..., description="JSON content")

router = APIRouter()

# ── Environment & Cosmos client ------------------------------------------
_cosmos_endpoint = os.getenv("COSMOS_ENDPOINT")
_database_name   = os.getenv("COSMOS_DATABASE", "cursusdb")
_container_name  = os.getenv("COSMOS_CONTAINER", "jsonContainer")
_cosmos_key      = os.getenv("COSMOS_KEY")

if _cosmos_key:
    _client = CosmosClient(_cosmos_endpoint, credential=_cosmos_key)
else:
    _client = CosmosClient(_cosmos_endpoint, credential=DefaultAzureCredential())

_database  = _client.get_database_client(_database_name)
_container = _database.get_container_client(_container_name)

# ── Helpers ---------------------------------------------------------------
def _item_id(
    tag: str,
    secondary_tag: Optional[str],
    tertiary_tag: Optional[str],
    quaternary_tag: Optional[str],
    quinary_tag: Optional[str],
    year: Optional[int],
    month: Optional[int],
    day: Optional[int],
) -> str:
    """Build a unique ID by concatenating the available parts."""
    parts = [tag]
    for part in (secondary_tag, tertiary_tag, quaternary_tag, quinary_tag):
        if part:
            parts.append(part)
    for part in (year, month, day):
        if part is not None:
            parts.append(str(part))
    return "_".join(parts)

def _upsert(
    tag, secondary_tag, tertiary_tag, quaternary_tag, quinary_tag,
    year, month, day, data
):
    _container.upsert_item({
        "id":             _item_id(tag, secondary_tag, tertiary_tag,
                                   quaternary_tag, quinary_tag, year, month, day),
        "tag":            tag,
        "secondary_tag":  secondary_tag,
        "tertiary_tag":   tertiary_tag,
        "quaternary_tag": quaternary_tag,
        "quinary_tag":    quinary_tag,
        "year":           year,
        "month":          month,
        "day":            day,
        "data":           data,
    })

def _fetch(
    tag, secondary_tag, tertiary_tag, quaternary_tag, quinary_tag,
    year, month, day
):
    return _container.read_item(
        item=_item_id(tag, secondary_tag, tertiary_tag,
                      quaternary_tag, quinary_tag, year, month, day),
        partition_key=tag
    )["data"]

# ── 1. JSON-body API ------------------------------------------------------
@router.post("/api/json", summary="Upload JSON data (raw body)")
def upload_json(payload: JSONPayload):
    _upsert(
        payload.tag,
        payload.secondary_tag,
        payload.tertiary_tag,
        payload.quaternary_tag,
        payload.quinary_tag,
        payload.year,
        payload.month,
        payload.day,
        payload.data
    )
    return {
        "status": "success",
        "id": _item_id(
            payload.tag,
            payload.secondary_tag,
            payload.tertiary_tag,
            payload.quaternary_tag,
            payload.quinary_tag,
            payload.year,
            payload.month,
            payload.day
        )
    }

@router.get("/api/json", summary="Download JSON by tag/year/month/day")
def download_json(
    tag:            str  = Query(...),
    secondary_tag:  Optional[str] = Query(None),
    tertiary_tag:   Optional[str] = Query(None),
    quaternary_tag: Optional[str] = Query(None),
    quinary_tag:    Optional[str] = Query(None),
    year:           Optional[int] = Query(None, ge=1900),
    month:          Optional[int] = Query(None, ge=1,  le=12),
    day:            Optional[int] = Query(None, ge=1,  le=31)
):
    try:
        return _fetch(tag, secondary_tag, tertiary_tag, quaternary_tag,
                      quinary_tag, year, month, day)
    except exceptions.CosmosResourceNotFoundError:
        raise HTTPException(status_code=404, detail="Item not found")

# ── DELETE via GET for easy browser delete -------------------------------
@router.get("/api/json/delete", summary="Delete JSON by tag/year/month/day")
def delete_json(
    tag:            str  = Query(...),
    secondary_tag:  Optional[str] = Query(None),
    tertiary_tag:   Optional[str] = Query(None),
    quaternary_tag: Optional[str] = Query(None),
    quinary_tag:    Optional[str] = Query(None),
    year:           Optional[int] = Query(None, ge=1900),
    month:          Optional[int] = Query(None, ge=1,  le=12),
    day:            Optional[int] = Query(None, ge=1,  le=31)
):
    try:
        _container.delete_item(
            item=_item_id(tag, secondary_tag, tertiary_tag,
                          quaternary_tag, quinary_tag, year, month, day),
            partition_key=tag
        )
    except exceptions.CosmosResourceNotFoundError:
        raise HTTPException(status_code=404, detail="Item not found")
    return {
        "status": "deleted",
        "id": _item_id(tag, secondary_tag, tertiary_tag,
                       quaternary_tag, quinary_tag, year, month, day)
    }

# ── 2. Download attachment endpoint --------------------------------------
@router.get("/api/json/download", summary="Download JSON as attachment")
def download_json_file(
    tag:            str  = Query(...),
    secondary_tag:  Optional[str] = Query(None),
    tertiary_tag:   Optional[str] = Query(None),
    quaternary_tag: Optional[str] = Query(None),
    quinary_tag:    Optional[str] = Query(None),
    year:           Optional[int] = Query(None, ge=1900),
    month:          Optional[int] = Query(None, ge=1,  le=12),
    day:            Optional[int] = Query(None, ge=1,  le=31)
):
    try:
        data = _fetch(tag, secondary_tag, tertiary_tag, quaternary_tag,
                      quinary_tag, year, month, day)
    except exceptions.CosmosResourceNotFoundError:
        raise HTTPException(status_code=404, detail="Item not found")

    # Pretty-print JSON for human readability (indent = 2, keep Chinese characters unescaped)
    payload = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")

    filename = _item_id(tag, secondary_tag, tertiary_tag,
                        quaternary_tag, quinary_tag, year, month, day) + ".json"
    headers = {
        "Content-Disposition": f'attachment; filename="{filename}"',
        "Content-Type":        "application/json",
        "Last-Modified":       datetime.datetime.utcnow()
                                  .strftime("%a, %d %b %Y %H:%M:%S GMT"),
    }
    return Response(content=payload, media_type="application/json", headers=headers)
