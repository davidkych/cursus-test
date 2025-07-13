# ── src/routers/lcsd/lcsd_cleanup_validator.py ──────────────────────────────
"""
Clean-up & validation endpoint for LCSD Excel timetables.

Public route
    /api/lcsd/lcsd_cleanup_validator   (GET | POST)

Behaviour
─────────
1. Load **current-month** timetable docs created by *lcsd_af_excel_timetable*
     tag='lcsd', secondary_tag='af_excel_timetable',
     year == today.year, month == today.month
2. For every `tertiary_tag` (LCSD number) keep **one** document whose date
   (day) is *nearest* to today; delete all others.
3. Validate that at least 20 timetable docs remain.
4. Every significant step is logged through `/api/log`
     tag="lcsd", tertiary_tag="cleanup_validator", base="[info]".
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Dict, List
from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException
from azure.cosmos import exceptions as cosmos_exc

# ── shared Cosmos helpers ----------------------------------------------------
from routers.jsondata.endpoints import _container
# ── log helper ---------------------------------------------------------------
from routers.log.endpoints import append_log, LogPayload

router = APIRouter()


# ─────────────────────────────────────────────────────────────────────────────
# Small helpers
# ─────────────────────────────────────────────────────────────────────────────
def _today_hkt() -> date:
    return datetime.now(ZoneInfo("Asia/Hong_Kong")).date()


def _log_append(base: str, message: str) -> None:
    """
    Wrapper that strips square brackets before forwarding to `/api/log`.
    The caller supplies base **with** brackets (e.g. “[info]”).
    """
    base_clean = base.strip("[]")
    payload = LogPayload(
        tag="lcsd",
        tertiary_tag="cleanup_validator",
        base=base_clean,
        message=message,
    )
    append_log(payload)


# ─────────────────────────────────────────────────────────────────────────────
# FastAPI endpoint
# ─────────────────────────────────────────────────────────────────────────────
@router.api_route(
    "/api/lcsd/lcsd_cleanup_validator",
    methods=["GET", "POST"],
    summary="Clean up duplicate LCSD timetables and validate current month",
)
def lcsd_cleanup_validator() -> Dict:
    today = _today_hkt()
    yr, mon = today.year, today.month

    # 1️⃣ load current-month timetables ---------------------------------------
    query = """
        SELECT c.id, c.tertiary_tag, c.day
        FROM   c
        WHERE  c.tag = @tag
          AND  c.secondary_tag = @sec
          AND  c.year = @yr
          AND  c.month = @mon
    """
    params = [
        {"name": "@tag", "value": "lcsd"},
        {"name": "@sec", "value": "af_excel_timetable"},
        {"name": "@yr",  "value": yr},
        {"name": "@mon", "value": mon},
    ]
    try:
        items: List[Dict] = list(
            _container.query_items(
                query=query,
                parameters=params,
                partition_key="lcsd",
                enable_cross_partition_query=False,
            )
        )
    except cosmos_exc.CosmosHttpResponseError as exc:
        raise HTTPException(
            status_code=500, detail=f"Cosmos DB query failed: {exc.message}"
        ) from exc

    total_loaded = len(items)
    _log_append("[info]", f"{total_loaded} timetables loaded for {mon}/{yr}")

    # 2️⃣ group by `tertiary_tag`; pick the one closest to today ---------------
    groups: Dict[str, List[Dict]] = {}
    for itm in items:
        key = itm.get("tertiary_tag")
        if not key:  # skip malformed docs
            continue
        groups.setdefault(key, []).append(itm)

    deleted = 0
    for key, docs in groups.items():
        if len(docs) <= 1:
            continue

        # distance to today; tie-breaker → larger day (more recent)
        def _metric(d):
            day_val = int(d.get("day", 1))
            return abs(day_val - today.day), -day_val

        docs.sort(key=_metric)
        keep_id = docs[0]["id"]

        for doc in docs[1:]:
            doc_id = doc["id"]
            try:
                _container.delete_item(item=doc_id, partition_key="lcsd")
                deleted += 1
                _log_append("[info]", f"Deleted duplicate timetable: id={doc_id}")
            except cosmos_exc.CosmosHttpResponseError as exc:
                _log_append("[info]", f"Failed to delete {doc_id}: {exc.message}")

    remaining = len(groups)
    if remaining >= 20:
        validation = "passed"
        _log_append("[info]", f"{remaining} timetables are present, validation passed.")
    else:
        validation = "failed"
        _log_append("[info]", f"{remaining} timetables are present, validation failed.")

    return {
        "status": "success",
        "loaded": total_loaded,
        "deleted": deleted,
        "remaining": remaining,
        "validation": validation,
    }
