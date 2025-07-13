# ── src/routers/lcsd/lcsd_af_adminupload_logic.py ───────────────────────────
"""
Pure-logic helper for the *admin-upload timetable* feature.

Functions here perform **no FastAPI I/O** – they only validate the uploaded
JSON, convert it into the two required payload shapes, and persist them to
Cosmos DB via the existing JSON helpers.

Public API
~~~~~~~~~~
process_admin_upload(data: dict) -> dict
    • Saves **one** ‘af_availtimetable’ master-JSON
    • Saves **N**  ‘af_excel_timetable’ worksheet-JSONs (N = len(data["records"]))
    • Returns a summary dict for the web layer to display / serialise
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Dict, List, Tuple, Set

from fastapi import HTTPException
from azure.cosmos import exceptions as cosmos_exc  # only to expose in docstring

# ── shared Cosmos helpers ----------------------------------------------------
from routers.jsondata.endpoints import _upsert, _item_id

_TAG = "lcsd"
_AVAIL_SEC = "af_availtimetable"
_EXCEL_SEC = "af_excel_timetable"


# ════════════════════════════════════════════════════════════════════════════
# internal helpers
# ════════════════════════════════════════════════════════════════════════════
def _iso_to_ymd(ts: str) -> Tuple[int, int, int]:
    dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    return dt.year, dt.month, dt.day


def _build_avail_payload(records: List[Dict], timestamp: str) -> Dict:
    facilities_map: Dict[str, Dict] = {}
    did_set: Set[str] = set()

    for rec in records:
        key = rec["lcsd_number"]
        did_set.add(rec["did_number"])

        jog_entry = {
            "month_year": rec["month_year"],
            "excel_url":  rec["excel_url"],
            "pdf_url":    rec.get("pdf_url"),
        }

        if key not in facilities_map:
            facilities_map[key] = {
                "did_number": rec["did_number"],
                "lcsd_number": rec["lcsd_number"],
                "name": rec["name"],
                "jogging_schedule": [jog_entry],
            }
        else:
            facilities_map[key]["jogging_schedule"].append(jog_entry)

    facilities = list(facilities_map.values())

    return {
        "metadata": {
            "timestamp":       timestamp,
            "num_dids":        len(did_set),
            "num_facilities":  len(facilities),
        },
        "facilities": facilities,
    }


# ════════════════════════════════════════════════════════════════════════════
# public façade
# ════════════════════════════════════════════════════════════════════════════
def process_admin_upload(data: Dict) -> Dict:
    """
    Validate *data* (uploaded JSON), generate & save two kinds of Cosmos docs,
    then return a small summary dict.

    Raises
    ------
    fastapi.HTTPException
        • status 400 – bad schema / missing keys
        • status 500 – Cosmos DB write failure
    """
    # 1️⃣ basic schema check ---------------------------------------------------
    if not isinstance(data, dict) or "records" not in data:
        raise HTTPException(status_code=400, detail="Missing top-level 'records' key")

    records = data["records"]
    if not isinstance(records, list) or not records:
        raise HTTPException(status_code=400, detail="'records' must be a non-empty list")

    # Prefer timestamp from metadata; else generate UTC now -------------------
    ts_raw = (
        data.get("metadata", {}).get("timestamp")
        or datetime.now(timezone.utc).isoformat(timespec="seconds")
    )
    year, month, day = _iso_to_ymd(ts_raw)

    # 2️⃣ create & save master ‘avail-timetable’ JSON --------------------------
    avail_payload = _build_avail_payload(records, ts_raw)
    _upsert(_TAG, _AVAIL_SEC, None, None, None, year, month, day, avail_payload)
    avail_id = _item_id(_TAG, _AVAIL_SEC, None, None, None, year, month, day)

    # 3️⃣ save **one** doc per uploaded worksheet -----------------------------
    excel_saved = 0
    for rec in records:
        try:
            _upsert(
                _TAG,
                _EXCEL_SEC,
                rec["lcsd_number"],   # tertiary_tag
                None,
                None,
                year,
                month,
                day,
                rec,
            )
            excel_saved += 1
        except Exception as exc:       # noqa: BLE001
            raise HTTPException(
                status_code=500,
                detail=f"Failed to save record {rec.get('lcsd_number')}: {exc}",
            ) from exc

    return {
        "status":          "success",
        "timestamp":       ts_raw,
        "avail_item_id":   avail_id,
        "excel_docs_saved": excel_saved,
    }
