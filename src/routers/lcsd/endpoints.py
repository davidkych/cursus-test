# ── src/routers/lcsd/endpoints.py ────────────────────────────────────────────
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo
from typing import List

from fastapi import APIRouter, HTTPException, Query
from routers.jsondata.endpoints import _upsert, _item_id

from .lcsd_util_af_probe import probe_dids
from .lcsd_util_af_master import fetch_facilities

router = APIRouter()


@router.api_route(
    "/api/lcsd/lcsd_af_info",
    methods=["GET", "POST"],
    summary="Harvest LCSD athletic-field info and save to Cosmos-DB",
)
def lcsd_af_info(
    start: int = Query(0,  ge=0, description="Starting DID (inclusive)"),
    end:   int = Query(20, ge=0, description="Ending DID (inclusive)"),
) -> dict:
    """
    • Probe LCSD DIDs **start … end** to find valid pages.  
    • Scrape each page into structured facility records.  
    • Build one master-JSON and upsert it to Cosmos-DB with

          tag = 'lcsd'
          secondary_tag = 'af_probe'
          year/month/day = current HKT date
    """
    # 1️⃣ Discover valid DIDs -------------------------------------------------
    valid_dids: List[str] = probe_dids(start, end, verbose=False)
    if not valid_dids:
        raise HTTPException(status_code=500, detail="No valid DIDs discovered")

    # 2️⃣ Harvest facilities --------------------------------------------------
    facilities = fetch_facilities(valid_dids, verbose=False)

    # 3️⃣ Build master payload ------------------------------------------------
    now_hkt = datetime.now(ZoneInfo("Asia/Hong_Kong"))
    payload = {
        "metadata": {
            "timestamp":       now_hkt.isoformat(timespec="seconds"),
            "num_dids":        len(valid_dids),
            "num_facilities":  len(facilities),
        },
        "facilities": facilities,
    }

    # 4️⃣ Save to Cosmos using existing helper --------------------------------
    year, month, day = now_hkt.year, now_hkt.month, now_hkt.day
    _upsert(
        "lcsd",               # tag  (partition key)
        "af_probe",           # secondary_tag
        None, None, None,     # tertiary/quaternary/quinary tags
        year, month, day,
        payload,
    )
    item_id = _item_id("lcsd", "af_probe", None, None, None, year, month, day)

    return {
        "status":          "success",
        "saved_item_id":   item_id,
        "valid_dids":      len(valid_dids),
        "facilities":      len(facilities),
        "timestamp_hkt":   payload["metadata"]["timestamp"],
    }
