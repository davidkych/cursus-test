# ── src/routers/lcsd/lcsd_af_timetable.py ───────────────────────────
"""
FastAPI endpoint that probes LCSD athletic-field pages, harvests *jogging-
schedule* tables **without** depending on lcsd_af_timetable_probe.py and
stores the resulting JSON in Cosmos DB.

Route
    /api/lcsd/lcsd_af_timetable_probe   (GET | POST)

Saved to Cosmos (via existing JSON API helper) with:
    tag            = 'lcsd'
    secondary_tag  = 'af_availtimetable'
    year/month/day = current HKT date

2025-07-13 · change
───────────────────
After completing its own work this endpoint now **fire-and-forgets** a
POST to `/api/lcsd/lcsd_af_excel_timetable`, triggering Excel conversion
automatically.  The primary response payload is unchanged.
"""

from __future__ import annotations

import os
import time
from datetime import datetime
from typing import Iterable, List, Optional
from zoneinfo import ZoneInfo

import requests                      # ← NEW (for kick-fire)
from fastapi import APIRouter, HTTPException, Query

# ── project-local helpers ────────────────────────────────────────────
from .lcsd_util_af_probe import probe_dids                 # DID discovery
from .lcsd_util_af_master_parser import parse_facilities   # HTML → list[dict]
from routers.jsondata.endpoints import _upsert, _item_id   # Cosmos helpers

# ── configuration constants (override by editing/env-injecting) ─────
_BASE_URL   = "https://www.lcsd.gov.hk/clpss/tc/webApp/Facility/Details.do"
_FTID       = 38                     # LCSD athletic-field facility-type ID
_ERR_MARKER = "Sorry, the page you requested cannot be found"
_REQ_DELAY  = 0.1                    # polite delay between HTTP requests (s)
_TIMEOUT    = 10                     # per-request timeout (s)

# ─────────────────────────────────────────────────────────────────────
# Internal helpers – lifted from lcsd_util_af_timetable_probe.py
# ─────────────────────────────────────────────────────────────────────
def _fetch_page_html(did: str | int, *, timeout: int = _TIMEOUT) -> Optional[str]:
    params = {"ftid": _FTID, "fcid": "", "did": did}
    try:
        r = requests.get(_BASE_URL, params=params, timeout=timeout)
        r.raise_for_status()
        return r.text
    except requests.RequestException:
        return None


def _is_valid_page(html: str) -> bool:
    return html and _ERR_MARKER not in html


def _minimalise(fac: dict) -> dict:
    return {
        "did_number":      fac["did_number"],
        "lcsd_number":     fac["lcsd_number"],
        "name":            fac["name"],
        "jogging_schedule": fac.get("jogging_schedule", []),
    }


def fetch_timetables(
    valid_dids: Iterable[str | int],
    *,
    delay: float = _REQ_DELAY,
    timeout: int = _TIMEOUT,
    verbose: bool = False,
) -> List[dict]:
    out: List[dict] = []
    for did in valid_dids:
        if verbose:
            print(f"[FETCH] DID {did} …", end="")
        html = _fetch_page_html(did, timeout=timeout)
        if not _is_valid_page(html):
            if verbose:
                print(" error page")
            time.sleep(delay)
            continue
        facilities = parse_facilities(html, did=str(did))
        out.extend(_minimalise(f) for f in facilities)
        if verbose:
            print(f" {len(facilities)} facility entr{'y' if len(facilities)==1 else 'ies'}")
        time.sleep(delay)
    return out


# ─────────────────────────────────────────────────────────────────────
# Helper to resolve internal FastAPI base-URL (avoids hard coding)
# ─────────────────────────────────────────────────────────────────────
def _internal_base() -> str:
    if (base := os.getenv("WEBAPP_BASE_URL")):
        return base.rstrip("/")
    if (site := os.getenv("FASTAPI_SITE_NAME")):
        return f"https://{site}.azurewebsites.net"
    if (site := os.getenv("WEBAPP_SITE_NAME") or os.getenv("WEBSITE_SITE_NAME")):
        return f"https://{site}.azurewebsites.net"
    return "http://localhost:8000"


# ─────────────────────────────────────────────────────────────────────
# FastAPI routing layer
# ─────────────────────────────────────────────────────────────────────
router = APIRouter()


@router.api_route(
    "/api/lcsd/lcsd_af_timetable_probe",
    methods=["GET", "POST"],
    summary="Harvest LCSD jogging timetables and save to Cosmos DB",
)
def lcsd_af_timetable_probe(
    start: int = Query(0,  ge=0, description="Starting DID (inclusive)"),
    end:   int = Query(20, ge=0, description="Ending DID (inclusive)"),
) -> dict:
    # 1️⃣ Discover valid DIDs --------------------------------------------------
    valid_dids: List[str] = probe_dids(start, end, verbose=False)
    if not valid_dids:
        raise HTTPException(status_code=500, detail="No valid DIDs discovered")

    # 2️⃣ Harvest jogging-schedule tables -------------------------------------
    facilities = fetch_timetables(valid_dids, verbose=False)

    # 3️⃣ Assemble payload -----------------------------------------------------
    now_hkt = datetime.now(ZoneInfo("Asia/Hong_Kong"))
    payload = {
        "metadata": {
            "timestamp":      now_hkt.isoformat(timespec="seconds"),
            "num_dids":       len(valid_dids),
            "num_facilities": len(facilities),
        },
        "facilities": facilities,
    }

    # 4️⃣ Save to Cosmos DB ----------------------------------------------------
    year, month, day = now_hkt.year, now_hkt.month, now_hkt.day
    _upsert(
        "lcsd",
        "af_availtimetable",
        None, None, None,
        year, month, day,
        payload,
    )
    item_id = _item_id("lcsd", "af_availtimetable",
                       None, None, None,
                       year, month, day)

    # 5️⃣ Kick-off Excel-timetable harvest (fire-and-forget) -------------------
    try:
        requests.post(
            f"{_internal_base()}/api/lcsd/lcsd_af_excel_timetable",
            timeout=5,
        )
    except Exception:
        # Silent swallow – non-blocking by design
        pass

    # 6️⃣ Return summary -------------------------------------------------------
    return {
        "status":         "success",
        "saved_item_id":  item_id,
        "valid_dids":     len(valid_dids),
        "facilities":     len(facilities),
        "timestamp_hkt":  payload["metadata"]["timestamp"],
    }
