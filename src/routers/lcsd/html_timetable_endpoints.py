# ── src/routers/lcsd/html_timetable_endpoints.py ──────────────────────
"""
Simple browser form to launch the LCSD timetable builder.

The builder will **first** try to use the monthly Excel spreadsheets;  
if none are available (or they cannot be parsed) it falls back to the
corresponding PDF files automatically.  
Either way the JSON is stored with tag ``lcsd/timetable``.
"""

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

router = APIRouter()

_HTML = """
<!doctype html>
<html lang="en">
<head><meta charset="utf-8"><title>LCSD Timetable Builder</title></head>
<body style="font-family:sans-serif;max-width:480px;margin:2rem auto;">
<h2>LCSD Athletic-Field Timetable Builder</h2>
<form method="get" action="/api/lcsd/timetable">
  <label>Year:
    <input type="number" name="year" min="1900" required>
  </label><br><br>
  <label>Month:
    <input type="number" name="month" min="1" max="12" required>
  </label><br><br>
  <button type="submit">Build timetable</button>
</form>
<p>
  The service first attempts to build the timetable from the monthly
  <strong>Excel</strong> sheet.  
  If the Excel sheet is missing or cannot be parsed it will
  automatically fall back to the matching <strong>PDF</strong>.
</p>
<p>The generated JSON is saved to Cosmos DB with tag <code>lcsd/timetable</code>.</p>
</body>
</html>
"""

@router.get("/api/lcsd/timetable/html", include_in_schema=False, response_class=HTMLResponse)
def timetable_form(request: Request):
    return HTMLResponse(_HTML)
