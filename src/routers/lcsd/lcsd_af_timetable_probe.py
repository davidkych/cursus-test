# ── src/routers/lcsd/lcsd_af_timetable_probe.py ────────────────────────────
"""
FastAPI endpoint **/api/lcsd/lcsd_af_timetable_probe**

• Discovers *valid* LCSD athletic-field DIDs with ``probe_dids``  
• Harvests **jogging-schedule tables only** via ``fetch_timetables``  
• Builds ONE master-JSON identical to the standalone script output  
• Saves the JSON in Cosmos DB through the /api/json helper, as if it were
  uploaded with  

        tag            = "lcsd"
        secondary_tag  = "af_availtimetable"
        year/month/day = (current HKT date)

Existing helper functions (`fetch_timetables`, CLI stubs, …) are preserved.
"""

from __future__ import annotations

# ── stdlib ────────────────────────────────────────────────────────────────
from datetime import datetime
from typing import List
from zoneinfo import ZoneInfo

# ── FastAPI & Cosmos helpers ──────────────────────────────────────────────
from fastapi import APIRouter, HTTPException, Query

from routers.jsondata.endpoints import _upsert, _item_id  # existing helpers

# ── Local LCSD helpers (already present in this folder) ───────────────────
from .lcsd_util_af_probe import probe_dids
from .lcsd_util_af_master_parser import parse_facilities  # re-used internally

# NOTE: fetch_timetables() (defined further down in this file) relies on
#       the helpers above – **no changes needed**.
# -------------------------------------------------------------------------

# ── public FastAPI router -------------------------------------------------
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
    """
    • Discover *valid* DIDs in **[start, end]** (inclusive)  
    • Fetch jogging-schedule tables only (主 / 副 split handled by the parser)  
    • Emit **one** JSON payload and store it in Cosmos DB
    """
    # 1️⃣ Discover valid DIDs --------------------------------------------------
    valid_dids: List[str] = probe_dids(start, end, verbose=False)
    if not valid_dids:
        raise HTTPException(status_code=500, detail="No valid DIDs discovered")

    # 2️⃣ Harvest jogging timetables ------------------------------------------
    facilities = fetch_timetables(valid_dids, verbose=False)

    # 3️⃣ Assemble master payload --------------------------------------------
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
        "lcsd",                 # tag (partition key)
        "af_availtimetable",    # secondary_tag
        None, None, None,       # tertiary / quaternary / quinary
        year, month, day,
        payload,
    )
    item_id = _item_id("lcsd", "af_availtimetable",
                       None, None, None, year, month, day)

    # 5️⃣ Respond with a concise summary --------------------------------------
    return {
        "status":        "success",
        "saved_item_id": item_id,
        "valid_dids":    len(valid_dids),
        "facilities":    len(facilities),
        "timestamp_hkt": payload["metadata"]["timestamp"],
    }


# ─────────────────────────────────────────────────────────────────────────
# The original *utility* code (fetch_timetables, CLI entry-point, …)
# starts here.  **UNCHANGED** apart from moving the imports to the top.
# -------------------------------------------------------------------------

import time
from typing import Iterable, Optional, List

import requests

# ── Defaults (override via keyword args if needed) ──────────────────────────
_BASE_URL: str   = "https://www.lcsd.gov.hk/clpss/tc/webApp/Facility/Details.do"
_FTID: int       = 38                     # LCSD athletic-field facility-type ID
_ERR_MARKER: str = "Sorry, the page you requested cannot be found"
_REQ_DELAY: float = 0.1                   # polite delay between requests (s)
_TIMEOUT: int     = 10                    # per-request timeout (s)


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
    """Trim a full facility record to the four required keys."""
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
    """
    Download LCSD pages for each **valid** DID and harvest *jogging-schedule*
    tables only (主 / 副運動場 split handled by `parse_facilities`).

    Returns a list of minimal facility dicts suitable for JSON serialisation.
    """
    out: List[dict] = []

    for did in valid_dids:
        if verbose:
            print(f"[FETCH] DID {did} …", end="")

        html = _fetch_page_html(did, timeout=timeout)
        if not _is_valid_page(html):
            if verbose:
                print(" error / placeholder")
            time.sleep(delay)
            continue

        facilities = parse_facilities(html, did=str(did))
        out.extend(_minimalise(f) for f in facilities)

        if verbose:
            print(f" {len(facilities)} facility entr{'y' if len(facilities)==1 else 'ies'}")
        time.sleep(delay)

    return out


# ---- CLI stub retained for local use (unchanged) ---------------------------
if __name__ == "__main__":  # pragma: no cover
    import sys
    from pathlib import Path
    import json as _json
    import datetime as _dt

    args = sys.argv[1:]
    if len(args) == 2 and all(a.isdigit() for a in args):
        s, e = map(int, args)
    else:
        s, e = 0, 20

    dids = probe_dids(s, e, verbose=True)
    data = fetch_timetables(dids, verbose=True)

    payload = {
        "metadata": {
            "timestamp": _dt.datetime.now().isoformat(),
            "num_dids": len(dids),
            "num_facilities": len(data),
        },
        "facilities": data,
    }
    fn = Path(f"{_dt.datetime.now():%Y%m%d_%H%M%S}_lcsd_af_availtimetable.json")
    fn.write_text(_json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Saved → {fn}")
