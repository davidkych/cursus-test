# ── src/routers/lcsd/timetableprobe_endpoints.py ────────────────────
"""
LCSD timetable-probe builder – extracts jogging-schedule links only.

GET  /api/lcsd/timetableprobe           – runs with defaults (newest probe)
POST /api/lcsd/timetableprobe           – body { "delay": 0.1 }  # optional
"""

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional
import requests, datetime, os, time, re

from bs4 import BeautifulSoup
from azure.cosmos import CosmosClient
from azure.identity import DefaultAzureCredential

# ── Constants ────────────────────────────────────────────────────────
BASE_URL        = "https://www.lcsd.gov.hk/clpss/tc/webApp/Facility/Details.do"
FTID            = 38
ERROR_INDICATOR = "Sorry, the page you requested cannot be found"
DEFAULT_DELAY   = 0.1

# ── Cosmos setup (identical to other routers) ────────────────────────
_cosmos_endpoint = os.getenv("COSMOS_ENDPOINT")
_database_name   = os.getenv("COSMOS_DATABASE", "cursusdb")
_container_name  = os.getenv("COSMOS_CONTAINER", "jsonContainer")
_cosmos_key      = os.getenv("COSMOS_KEY")

_client = (
    CosmosClient(_cosmos_endpoint, credential=_cosmos_key)
    if _cosmos_key
    else CosmosClient(_cosmos_endpoint, credential=DefaultAzureCredential())
)
_container = _client.get_database_client(_database_name).get_container_client(_container_name)

# ── Helpers shared with jsondata router ──────────────────────────────
def _item_id(tag, secondary_tag, year, month, day):
    parts = [tag, secondary_tag, str(year), str(month), str(day)]
    return "_".join(parts)

def _upsert(tag, secondary_tag, year, month, day, data):
    _container.upsert_item(
        {
            "id": _item_id(tag, secondary_tag, year, month, day),
            "tag": tag,
            "secondary_tag": secondary_tag,
            "year": year,
            "month": month,
            "day": day,
            "data": data,
        }
    )

# ── Step 1: grab newest probe doc ────────────────────────────────────
def _latest_probe_valid_dids() -> List[str]:
    query = """
        SELECT TOP 1 c.data.valid_dids
        FROM c
        WHERE c.tag = 'lcsd' AND c.secondary_tag = 'probe'
        ORDER BY c._ts DESC
    """
    docs = list(_container.query_items(query=query, enable_cross_partition_query=True))
    if not docs:
        raise HTTPException(status_code=404, detail="No probe data found")
    return docs[0]["valid_dids"]

# ── Step 2: fetch & parse each DID page ─────────────────────────────
def _is_valid_html(html: str) -> bool:
    return ERROR_INDICATOR not in html

def _fetch_html(did: str) -> Optional[str]:
    try:
        resp = requests.get(
            BASE_URL, params={"ftid": FTID, "fcid": "", "did": did}, timeout=10
        )
        resp.raise_for_status()
        return resp.text if _is_valid_html(resp.text) else None
    except requests.RequestException:
        return None

def _parse_block(anchor, did: str) -> Dict[str, Any]:
    """Returns minimal timetable info for one facility block."""
    # Collect siblings until next named anchor – scoping for BeautifulSoup
    block_nodes = []
    for sib in anchor.next_siblings:
        if getattr(sib, "name", None) == "a" and sib.has_attr("name"):
            break
        block_nodes.append(sib)
    block_soup = BeautifulSoup("".join(str(n) for n in block_nodes), "html.parser")

    data = {
        "did_number": did,
        "lcsd_number": anchor["name"].strip(),
        "name": (block_soup.find("h4", class_="details_title") or "").get_text(strip=True),
        "jogging_schedule": [],
    }

    jog = block_soup.find("h4", string=lambda t: t and "緩步跑開放時間" in t)
    if jog:
        sched: Dict[str, Dict[str, Optional[str]]] = {}
        tbl = jog.find_next("table", class_="jogging_pdf")
        if not tbl:
            div = jog.find_next("div")
            if div:
                tbl = div.find("table", class_="jogging_pdf")
        if tbl:
            rows = tbl.find_all("tr")
            if len(rows) >= 2:
                links, labels = rows[0].find_all("td"), rows[1].find_all("td")
                for i in range(min(len(links), len(labels))):
                    month_label = labels[i].get_text(strip=True)
                    if not month_label:
                        continue

                    # ── Extract month & year from label (e.g. “06/2025” or “2025/06”) ──
                    nums = re.findall(r"\d+", month_label)
                    if len(nums) >= 2:
                        if len(nums[0]) == 4:          # YYYY/MM
                            year, month_num = nums[0], nums[1]
                        elif len(nums[1]) == 4:        # MM/YYYY
                            month_num, year = nums[0], nums[1]
                        else:                          # fallback
                            month_num, year = nums[0], nums[1]
                        month_num = month_num.zfill(2)
                    else:                              # fallback – not parseable
                        month_num, year = None, None

                    entry = sched.setdefault(
                        f"{month_num}_{year}",
                        {
                            "month": month_num,
                            "year": year,
                            "excel_url": None,
                            "pdf_url": None,
                        },
                    )

                    for a in links[i].find_all("a", href=True):
                        href = a["href"].strip()
                        if href.endswith(".xlsx"):
                            entry["excel_url"] = href
                        elif href.endswith(".pdf"):
                            entry["pdf_url"] = href
        data["jogging_schedule"] = list(sched.values())

    return data

def _parse_facilities(html: str, did: str) -> List[Dict[str, Any]]:
    soup = BeautifulSoup(html, "html.parser")
    facilities = []
    for anchor in soup.find_all("a", attrs={"name": True}):
        facilities.append(_parse_block(anchor, did))
    return facilities

# ── Step 3: build timetable JSON & store it ─────────────────────────
def _build_and_store(valid_dids: List[str], delay: float) -> Dict[str, Any]:
    all_entries: List[Dict[str, Any]] = []
    for did in valid_dids:
        html = _fetch_html(did)
        if html:
            all_entries.extend(_parse_facilities(html, did))
        time.sleep(delay)

    ts = datetime.datetime.utcnow().isoformat(timespec="seconds") + "Z"
    today = datetime.date.today()
    payload = {
        "metadata": {"timestamp": ts},
        "source": "latest_probe",
        "count": len(all_entries),
        "timetables": all_entries,
    }

    _upsert("lcsd", "timetableprobe", today.year, today.month, today.day, payload)
    return {
        "stored_id": _item_id("lcsd", "timetableprobe", today.year, today.month, today.day),
        "count": len(all_entries),
    }

# ── FastAPI models & router ─────────────────────────────────────────
class TimetableRequest(BaseModel):
    delay: Optional[float] = Field(None, ge=0, description="Seconds between requests")

router = APIRouter()

@router.post("/api/lcsd/timetableprobe", summary="Build LCSD timetable-probe JSON (POST)")
def timetable_post(req: TimetableRequest):
    valid = _latest_probe_valid_dids()
    return _build_and_store(valid, req.delay or DEFAULT_DELAY)

@router.get("/api/lcsd/timetableprobe", summary="Build LCSD timetable-probe JSON (GET)")
def timetable_get(delay: float = Query(DEFAULT_DELAY, ge=0.0)):
    valid = _latest_probe_valid_dids()
    return _build_and_store(valid, delay)
