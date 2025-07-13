# ── src/routers/lcsd/lcsd_af_excel_timetable.py ─────────────────────────────
"""
Public endpoint
    /api/lcsd/lcsd_af_excel_timetable   (GET | POST)

Workflow
────────
1.  Fetch the **newest** JSON created by `/api/lcsd/lcsd_af_timetable_probe`
    (tag =`lcsd`, secondary_tag =`af_availtimetable`).

2.  For every facility listed there, download & parse its jogging-schedule
    Excel(s) via `excel_to_timetable()`.

3.  Save **one JSON per worksheet** back to Cosmos DB using the existing JSON
    helper:
        tag            = 'lcsd'
        secondary_tag  = 'af_excel_timetable'
        tertiary_tag   = <lcsd_number>
        year/month/day = date when this endpoint runs
"""
from __future__ import annotations

from datetime import datetime, date
from typing import List, Dict
from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException, Query
from azure.cosmos import exceptions as cosmos_exc

# ── shared helpers (reuse existing Cosmos wiring) ───────────────────────────
from routers.jsondata.endpoints import (
    _container,            # Cosmos client – partition key 'lcsd'
    _upsert,               # save helper
    _item_id,              # build ID helper
)

from .lcsd_util_excel_timetable_parser import excel_to_timetable

router = APIRouter()


# ─────────────────────────────────────────────────────────────────────────────
# Internal helpers
# ─────────────────────────────────────────────────────────────────────────────
def _today_hkt() -> date:
    return datetime.now(ZoneInfo("Asia/Hong_Kong")).date()


def _load_latest_avail_json() -> Dict:
    """
    Return the *data* field of the most-recent
        tag='lcsd', secondary_tag='af_availtimetable'
    document in Cosmos DB (same partition, so no cross-partition query).
    """
    query = """
        SELECT c.id, c.data, c.year, c.month, c.day
        FROM   c
        WHERE  c.tag = @tag AND c.secondary_tag = @sec
    """
    params = [
        {"name": "@tag", "value": "lcsd"},
        {"name": "@sec", "value": "af_availtimetable"},
    ]
    items = list(
        _container.query_items(
            query=query,
            parameters=params,
            partition_key="lcsd",           # single-partition query
            enable_cross_partition_query=False,
        )
    )
    if not items:
        raise HTTPException(
            status_code=404,
            detail="No 'af_availtimetable' data found in Cosmos DB.",
        )

    # newest first
    items.sort(
        key=lambda r: (r.get("year", 0), r.get("month", 0), r.get("day", 0)),
        reverse=True,
    )
    return items[0]["data"]


def _save_record(payload: Dict, today: date) -> None:
    """
    Save one Excel-timetable JSON back into Cosmos DB.
    Overwrites (upserts) if the same ID already exists.
    """
    _upsert(
        "lcsd",                      # tag  (partition key)
        "af_excel_timetable",        # secondary_tag
        payload.get("lcsd_number"),  # tertiary_tag
        None, None,                  # quaternary / quinary
        today.year,
        today.month,
        today.day,
        payload,
    )


# ─────────────────────────────────────────────────────────────────────────────
# FastAPI route
# ─────────────────────────────────────────────────────────────────────────────
@router.api_route(
    "/api/lcsd/lcsd_af_excel_timetable",
    methods=["GET", "POST"],
    summary="Harvest LCSD jogging timetables (Excel) and save to Cosmos DB",
)
def lcsd_af_excel_timetable(
    timeout: int = Query(15, ge=5, le=60, description="Per-download timeout (s)"),
    debug:   bool = Query(False, description="Verbose stdout logging"),
) -> Dict:
    """
    Trigger Excel download / parse for all facilities discovered by the latest
    *avail-timetable* probe.
    """
    try:
        avail_data = _load_latest_avail_json()
    except HTTPException:
        # re-raise HTTPException untouched so FastAPI keeps status code
        raise
    except cosmos_exc.CosmosHttpResponseError as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Cosmos DB query failed: {exc.message}",
        ) from exc

    today = _today_hkt()
    saved   = 0        # how many JSON docs written
    skipped = 0        # how many worksheets skipped / errored

    for fac in avail_data.get("facilities", []):
        fac_info = {
            "did_number":  fac.get("did_number"),
            "lcsd_number": fac.get("lcsd_number"),
            "name":        fac.get("name"),
        }
        for sched in fac.get("jogging_schedule", []):
            url = sched.get("excel_url")
            mm  = sched.get("month_year")
            if not url or not mm:
                continue

            try:
                sheet_dicts: List[Dict] = excel_to_timetable(
                    url,
                    mm,
                    timeout=timeout,
                    debug=debug,
                )
            except Exception as exc:            # noqa: BLE001
                if debug:
                    print(f"[WARN] Skipped {url} → {exc}")
                skipped += 1
                continue

            # one Cosmos document per worksheet
            for sheet in sheet_dicts:
                payload = {**fac_info, **sheet}
                _save_record(payload, today)
                saved += 1

    return {
        "status":        "success",
        "timestamp_hkt": datetime.now(ZoneInfo("Asia/Hong_Kong"))
                             .isoformat(timespec="seconds"),
        "docs_saved":    saved,
        "docs_skipped":  skipped,
    }
