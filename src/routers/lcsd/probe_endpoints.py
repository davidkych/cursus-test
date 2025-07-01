# ── src/routers/lcsd/probe_endpoints.py ──────────────────────────────
"""
LCSD probe router – probes LCSD athletic-field pages, stores result in Cosmos
and (optionally) writes the JSON file to /tmp.

POST /api/lcsd/probe          – JSON body  { "startDid": 0, "endDid": 20 }
GET  /api/lcsd/probe          – query      ?startDid=0&endDid=20
"""

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from typing import List, Optional
import requests, json, datetime, os, time

from azure.cosmos import CosmosClient, exceptions
from azure.identity import DefaultAzureCredential

# ── Constants ────────────────────────────────────────────────────────
BASE_URL          = "https://www.lcsd.gov.hk/clpss/tc/webApp/Facility/Details.do"
FTID              = 38
ERROR_INDICATOR   = "Sorry, the page you requested cannot be found"
DEFAULT_DELAY_SEC = 0.1

# ── Cosmos-DB setup (same env vars as jsondata router) ───────────────
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

# ── Helpers (copied from jsondata router for compatibility) ──────────
def _item_id(tag, secondary_tag, year, month, day) -> str:
    parts = [tag]
    if secondary_tag:
        parts.append(secondary_tag)
    if year is not None:
        parts.append(str(year))
    if month is not None:
        parts.append(str(month))
    if day is not None:
        parts.append(str(day))
    return "_".join(parts)

def _upsert(tag, secondary_tag, year, month, day, data):
    _container.upsert_item({
        "id":            _item_id(tag, secondary_tag, year, month, day),
        "tag":           tag,
        "secondary_tag": secondary_tag,
        "year":          year,
        "month":         month,
        "day":           day,
        "data":          data,
    })

# ── Probe logic ──────────────────────────────────────────────────────
def _is_valid_page(html: str) -> bool:
    return ERROR_INDICATOR not in html

def _probe_dids(start: int, end: int, delay: float = DEFAULT_DELAY_SEC) -> List[str]:
    valid: List[str] = []
    for did in range(start, end + 1):
        params = {"ftid": FTID, "fcid": "", "did": did}
        try:
            r = requests.get(BASE_URL, params=params, timeout=10)
            r.raise_for_status()
        except requests.RequestException:
            time.sleep(delay)
            continue
        if _is_valid_page(r.text):
            valid.append(str(did))
        time.sleep(delay)
    return valid

def _store_result(valid_dids: List[str]) -> str:
    today = datetime.date.today()
    ts    = datetime.datetime.utcnow().isoformat(timespec="seconds") + "Z"
    payload = {"metadata": {"timestamp": ts}, "valid_dids": valid_dids}

    # Save JSON file to /tmp (ephemeral but useful for log scraping)
    fname = today.strftime("%Y%m%d_%H%M%S") + "_lcsd_af_probe.json"
    try:
        with open(f"/tmp/{fname}", "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
    except IOError:
        pass  # non-fatal in App Service

    # Upsert into Cosmos so it’s visible via existing /api/json endpoints
    _upsert(
        tag="lcsd",
        secondary_tag="probe",
        year=today.year,
        month=today.month,
        day=today.day,
        data=payload,
    )
    return _item_id("lcsd", "probe", today.year, today.month, today.day)

# ── Request models ───────────────────────────────────────────────────
class ProbeRequest(BaseModel):
    startDid: int = Field(..., ge=0, description="Start DID (inclusive)")
    endDid:   int = Field(..., ge=0, description="End DID (inclusive)")
    delay:    Optional[float] = Field(None, ge=0, description="Seconds between requests")

# ── FastAPI router ───────────────────────────────────────────────────
router = APIRouter()

@router.post("/api/lcsd/probe", summary="Run LCSD probe (POST body)")
def probe_post(req: ProbeRequest):
    if req.endDid < req.startDid:
        raise HTTPException(status_code=400, detail="endDid must be ≥ startDid")
    valid = _probe_dids(req.startDid, req.endDid, req.delay or DEFAULT_DELAY_SEC)
    cosmos_id = _store_result(valid)
    return {"status": "success", "stored_id": cosmos_id, "count": len(valid)}

@router.get("/api/lcsd/probe", summary="Run LCSD probe (query params)")
def probe_get(
    startDid: int = Query(0, ge=0),
    endDid:   int = Query(20, ge=0),
    delay:    float = Query(DEFAULT_DELAY_SEC, ge=0.0)
):
    if endDid < startDid:
        raise HTTPException(status_code=400, detail="endDid must be ≥ startDid")
    valid = _probe_dids(startDid, endDid, delay)
    cosmos_id = _store_result(valid)
    return {"status": "success", "stored_id": cosmos_id, "count": len(valid)}
