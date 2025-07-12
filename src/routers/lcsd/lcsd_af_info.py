# ── src/routers/lcsd/lcsd_af_info.py ─────────────────────────────────────────
"""
LCSD athletic-field collector API endpoint.

•   URL           : /api/lcsd/lcsd_af_info   (GET or POST)
•   Default range : DID 0 – 20
•   Behaviour     :
        1.  Probe valid DIDs with lcsd_util_af_probe.probe_dids()
        2.  Harvest facility records with lcsd_util_af_master.fetch_facilities()
        3.  For **each** facility record, build the same payload produced by the
            original CLI script and upsert it into Cosmos using the existing
            JSON-data helper – as if the user had uploaded it via `/api/json`.
            Tag scheme:
                 tag            = "lcsd"
                 secondary_tag  = "af_probe"
                 tertiary_tag   = <lcsd_number>      (ensures unique IDs)
                 quaternary_tag = None
                 quinary_tag    = None
                 year/month/day = current Hong Kong date
"""

from __future__ import annotations

from datetime import datetime, date
from zoneinfo import ZoneInfo
from typing import List

from fastapi import APIRouter, Query, HTTPException
from routers.jsondata.endpoints import _upsert          # re-use existing helper

# Local helper modules (placed alongside this file – no need to modify)
from .lcsd_util_af_probe import probe_dids              # type: ignore
from .lcsd_util_af_master import fetch_facilities       # type: ignore

# ── Router ------------------------------------------------------------------
router = APIRouter()

# ── Helpers -----------------------------------------------------------------
_HKT = ZoneInfo("Asia/Hong_Kong")


def _today_hkt() -> date:
    """Current date in Hong Kong."""
    return datetime.now(_HKT).date()


def _build_payload(fac: dict) -> dict:
    """Replicate the JSON structure of the original CLI script."""
    now = datetime.now(_HKT)
    return {
        "metadata": {
            "timestamp": now.isoformat(),
            "did_number": fac.get("did_number"),
        },
        "facility": fac,
    }


def _persist_facilities(facilities: List[dict]) -> int:
    """Store each facility record in Cosmos via the JSON upsert helper.

    Returns the number of records successfully persisted.
    """
    today = _today_hkt()
    year, month, day = today.year, today.month, today.day
    saved = 0

    for fac in facilities:
        tertiary_tag = str(fac.get("lcsd_number") or fac.get("did_number") or saved)
        payload = _build_payload(fac)
        # Same ID-scheme as /api/json; tertiary_tag gives uniqueness
        _upsert(
            tag="lcsd",
            secondary_tag="af_probe",
            tertiary_tag=tertiary_tag,
            quaternary_tag=None,
            quinary_tag=None,
            year=year,
            month=month,
            day=day,
            data=payload,
        )
        saved += 1
    return saved


# ── Endpoint ----------------------------------------------------------------
@router.api_route(
    "/api/lcsd/lcsd_af_info",
    methods=["GET", "POST"],
    summary="Collect LCSD athletic-field information and save to Cosmos",
)
def lcsd_af_info(
    start: int = Query(0, ge=0, description="Starting DID (inclusive)"),
    end: int = Query(20, ge=0, description="Ending DID (inclusive)"),
    delay: float = Query(0.1, ge=0.0, description="Seconds between HTTP requests"),
) -> dict:
    """
    Trigger the LCSD athletic-field data-collection workflow.

    The call may take some time (usually a few seconds) because it performs
    live HTTP requests to www.lcsd.gov.hk.  A simple JSON summary is returned.
    """
    if start > end:
        raise HTTPException(status_code=400, detail="`start` must be ≤ `end`")

    # 1. Probe for valid DIDs
    valid_dids = probe_dids(start=start, end=end, delay=delay, verbose=False)

    # 2. Fetch & parse facility records
    facilities = fetch_facilities(valid_dids, verbose=False)

    # 3. Persist each facility record via existing JSON upsert logic
    saved = _persist_facilities(facilities)

    today = _today_hkt()
    return {
        "status": "success",
        "probed_range": f"{start}-{end}",
        "valid_dids": len(valid_dids),
        "facilities_saved": saved,
        "date": today.isoformat(),
    }
