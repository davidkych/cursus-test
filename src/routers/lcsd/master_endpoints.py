# ── src/routers/lcsd/master_endpoints.py ─────────────────────────────
"""
LCSD master builder – consolidates detailed athletic-field data.

GET /api/lcsd/master            – runs with defaults (newest probe)
POST /api/lcsd/master           – body { "delay": 0.1 }  # optional
"""

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional
import requests, json, datetime, os, time

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

# ── Helpers reused from jsondata router ──────────────────────────────
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

# ── Step 2: fetch & parse each DID page ──────────────────────────────
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
    # Gather siblings until the next named anchor – creates a scoped soup
    block_nodes = []
    for sib in anchor.next_siblings:
        if getattr(sib, "name", None) == "a" and sib.has_attr("name"):
            break
        block_nodes.append(sib)
    block_soup = BeautifulSoup("".join(str(n) for n in block_nodes), "html.parser")

    # Helper to locate section headers
    def find_h4(keyword: str):
        return block_soup.find("h4", string=lambda t: t and keyword in t)

    data = {
        "did_number": did,
        "lcsd_number": anchor["name"].strip(),
        "name": (block_soup.find("h4", class_="details_title") or "").get_text(strip=True),
        "address": None,
        "phone": None,
        "fax": None,
        "email": None,
        "description": None,
        "facilities": [],
        "opening_hours": None,
        "maintenance_days": [],
        "jogging_schedule": [],
    }

    # Description
    descr = find_h4("簡介")
    if descr:
        p = descr.find_next("p")
        if p:
            data["description"] = p.get_text(strip=True)

    # Facilities list
    fac = find_h4("設施")
    if fac:
        ul = fac.find_next("ul")
        if ul:
            data["facilities"] = [
                li.get_text(strip=True) for li in ul.find_all("li") if li.get_text(strip=True)
            ]

    # Jogging schedule (table with .jogging_pdf)
    jog = find_h4("緩步跑開放時間")
    if jog:
        sched = {}
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
                    month = labels[i].get_text(strip=True)
                    if not month:
                        continue
                    entry = sched.setdefault(
                        month, {"month_year": month, "excel_url": None, "pdf_url": None}
                    )
                    for a in links[i].find_all("a", href=True):
                        href = a["href"].strip()
                        if href.endswith(".xlsx"):
                            entry["excel_url"] = href
                        elif href.endswith(".pdf"):
                            entry["pdf_url"] = href
        data["jogging_schedule"] = list(sched.values())

    # Opening hours
    op = find_h4("開放時間")
    if op:
        paras = []
        for n in op.next_siblings:
            if getattr(n, "name", None) == "h4":
                break
            if n.name == "p":
                txt = n.get_text(strip=True)
                if txt:
                    paras.append(txt)
            if n.name == "div":
                for p in n.find_all("p"):
                    txt = p.get_text(strip=True)
                    if txt:
                        paras.append(txt)
        if paras:
            data["opening_hours"] = " ".join(paras)

    # Maintenance days
    maint = find_h4("定期保養日")
    if maint:
        p = maint.find_next("p")
        if p:
            sentences = [s.strip() for s in p.get_text(strip=True).split("。") if s.strip()]
            data["maintenance_days"] = sentences

    # Contact info table
    tbl = block_soup.find("table", class_="table table-responsive table-striped")
    if tbl:
        for row in tbl.find_all("tr"):
            cells = row.find_all("td")
            if len(cells) < 2:
                continue
            label, value = cells[0].get_text(strip=True), cells[1].get_text(strip=True)
            if label in ("地址", "郵寄地址"):
                data["address"] = value
            elif label == "電話":
                data["phone"] = value
            elif label == "傳真":
                data["fax"] = value
            elif label == "電郵":
                data["email"] = value

    return data

def _parse_facilities(html: str, did: str) -> List[Dict[str, Any]]:
    soup = BeautifulSoup(html, "html.parser")
    facilities = []
    for anchor in soup.find_all("a", attrs={"name": True}):
        facilities.append(_parse_block(anchor, did))
    return facilities

# ── Step 3: build master JSON & store ────────────────────────────────
def _build_and_store(valid_dids: List[str], delay: float) -> Dict[str, Any]:
    all_entries = []
    for did in valid_dids:
        html = _fetch_html(did)
        if html:
            all_entries.extend(_parse_facilities(html, did))
        time.sleep(delay)

    ts = datetime.datetime.utcnow().isoformat(timespec="seconds") + "Z"
    today = datetime.date.today()
    payload = {"metadata": {"timestamp": ts}, "source": "latest_probe", "count": len(all_entries),
               "facilities": all_entries}

    _upsert("lcsd", "master", today.year, today.month, today.day, payload)
    return {"stored_id": _item_id("lcsd", "master", today.year, today.month, today.day),
            "count": len(all_entries)}

# ── FastAPI models & router ──────────────────────────────────────────
class MasterRequest(BaseModel):
    delay: Optional[float] = Field(None, ge=0, description="Seconds between requests")

router = APIRouter()

@router.post("/api/lcsd/master", summary="Build LCSD master JSON (POST)")
def master_post(req: MasterRequest):
    valid = _latest_probe_valid_dids()
    return _build_and_store(valid, req.delay or DEFAULT_DELAY)

@router.get("/api/lcsd/master", summary="Build LCSD master JSON (GET)")
def master_get(delay: float = Query(DEFAULT_DELAY, ge=0.0)):
    valid = _latest_probe_valid_dids()
    return _build_and_store(valid, delay)
