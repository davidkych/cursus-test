# ── src/routers/jsondata/html_endpoints.py ─────────────────────────────
from fastapi import APIRouter, HTTPException, Form, File, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse
from typing import List
from urllib.parse import parse_qs
import json

from .endpoints import (
    _upsert,
    _item_id,
    _fetch,
    _container,
    exceptions,
)

router = APIRouter()

# ── 1. HTML upload form --------------------------------------------------
_form_html = """
<!doctype html>
<title>Upload JSON to Cursus</title>
<h2>Upload JSON to Cursus</h2>
<form action="/api/json/upload" method="post" enctype="multipart/form-data">
  <label>Tag:            <input type="text"   name="tag"            required></label><br><br>
  <label>Secondary Tag:  <input type="text"   name="secondary_tag"></label><br><br>
  <label>Tertiary Tag:   <input type="text"   name="tertiary_tag"></label><br><br>
  <label>Quaternary Tag: <input type="text"   name="quaternary_tag"></label><br><br>
  <label>Quinary Tag:    <input type="text"   name="quinary_tag"></label><br><br>
  <label>Year:           <input type="number" name="year"  min="1900"></label><br><br>
  <label>Month:          <input type="number" name="month" min="1" max="12"></label><br><br>
  <label>Day:            <input type="number" name="day"   min="1" max="31"></label><br><br>
  <label>JSON file:      <input type="file"   name="file"  accept=".json" required></label><br><br>
  <button type="submit">Upload</button>
</form>
"""

@router.get("/api/json/upload", include_in_schema=False, response_class=HTMLResponse)
def upload_form():
    return HTMLResponse(_form_html)

@router.post("/api/json/upload", summary="Upload JSON via HTML form")
async def upload_form_post(
    tag:            str = Form(...),
    secondary_tag:  str = Form(None),
    tertiary_tag:   str = Form(None),
    quaternary_tag: str = Form(None),
    quinary_tag:    str = Form(None),
    year:           int = Form(None),
    month:          int = Form(None),
    day:            int = Form(None),
    file: UploadFile = File(...)
):
    try:
        raw = await file.read()
        data = json.loads(raw.decode("utf-8"))
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON file")

    _upsert(tag, secondary_tag, tertiary_tag, quaternary_tag, quinary_tag,
            year, month, day, data)
    return {
        "status": "success",
        "id": _item_id(tag, secondary_tag, tertiary_tag,
                       quaternary_tag, quinary_tag, year, month, day)
    }

# ── 2. HTML list table with bulk‐delete & Select All ---------------------
@router.get("/api/json/list", summary="List all JSON items", response_class=HTMLResponse)
def list_json_items():
    query = """
    SELECT
      c.tag,
      c.secondary_tag,
      c.tertiary_tag,
      c.quaternary_tag,
      c.quinary_tag,
      c.year,
      c.month,
      c.day
    FROM c
    """
    items = list(_container.query_items(query=query, enable_cross_partition_query=True))

    html = """
<!doctype html>
<html>
<head><title>Uploaded JSON Items</title></head>
<body>
  <h2>Uploaded JSON Items</h2>
  <a href="/api/json/upload">Upload new JSON</a><br/><br/>
  <form method="post" action="/api/json/delete-multiple">
  <table border="1" cellpadding="5" cellspacing="0">
    <tr>
      <th>
        Select<br>
        <button type="button" id="select-all">Select All</button>
      </th>
      <th>Tag</th><th>Secondary</th><th>Tertiary</th><th>Quaternary</th><th>Quinary</th>
      <th>Year</th><th>Month</th><th>Day</th>
      <th>Download</th>
    </tr>
"""

    for item in items:
        tag  = item.get("tag", "")
        sec  = item.get("secondary_tag", "")
        ter  = item.get("tertiary_tag", "")
        qua  = item.get("quaternary_tag", "")
        qui  = item.get("quinary_tag", "")
        yr   = item.get("year")
        mo   = item.get("month")
        dy   = item.get("day")

        params = [f"tag={tag}"]
        if sec: params.append(f"secondary_tag={sec}")
        if ter: params.append(f"tertiary_tag={ter}")
        if qua: params.append(f"quaternary_tag={qua}")
        if qui: params.append(f"quinary_tag={qui}")
        if yr is not None: params.append(f"year={yr}")
        if mo is not None: params.append(f"month={mo}")
        if dy is not None: params.append(f"day={dy}")

        qs = "&".join(params)
        html += (
            f"<tr>"
            f"<td><input type=\"checkbox\" name=\"selected\" value=\"{qs}\"></td>"
            f"<td>{tag}</td><td>{sec}</td><td>{ter}</td><td>{qua}</td><td>{qui}</td>"
            f"<td>{yr or ''}</td><td>{mo or ''}</td><td>{dy or ''}</td>"
            f"<td><a href=\"/api/json/download?{qs}\">Download</a></td>"
            f"</tr>\n"
        )

    html += """
  </table>
  <br>
  <button type="submit">Delete Selected</button>
  </form>

  <script>
    document.getElementById('select-all').onclick = function() {
      document.querySelectorAll('input[name="selected"]').forEach(cb => cb.checked = true);
    };
  </script>
</body>
</html>
"""
    return HTMLResponse(html)

# ── 3. Bulk‐delete endpoint ------------------------------------------------
@router.post("/api/json/delete-multiple", include_in_schema=False)
def delete_multiple_json(selected: List[str] = Form(...)):
    for qs in selected:
        params = parse_qs(qs)
        tag  = params.get("tag", [""])[0]
        secondary_tag = params.get("secondary_tag", [None])[0]
        tertiary_tag  = params.get("tertiary_tag", [None])[0]
        quaternary_tag= params.get("quaternary_tag", [None])[0]
        quinary_tag   = params.get("quinary_tag", [None])[0]
        year_val      = params.get("year", [None])[0]
        month_val     = params.get("month", [None])[0]
        day_val       = params.get("day", [None])[0]

        year  = int(year_val)  if year_val  is not None else None
        month = int(month_val) if month_val is not None else None
        day   = int(day_val)   if day_val   is not None else None

        try:
            _container.delete_item(
                item=_item_id(tag, secondary_tag, tertiary_tag,
                              quaternary_tag, quinary_tag, year, month, day),
                partition_key=tag
            )
        except exceptions.CosmosResourceNotFoundError:
            continue

    return RedirectResponse(url="/api/json/list", status_code=303)
