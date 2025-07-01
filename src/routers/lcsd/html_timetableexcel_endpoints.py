# ── src/routers/lcsd/html_timetableexcel_endpoints.py ────────────────
"""
Simple browser form to launch the LCSD timetable-EXCEL builder.
"""

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

router = APIRouter()

_HTML = """
<!doctype html>
<html lang="en">
<head><meta charset="utf-8"><title>LCSD Timetable-EXCEL Builder</title></head>
<body style="font-family:sans-serif;max-width:480px;margin:2rem auto;">
<h2>LCSD Athletic-Field Timetable-EXCEL Builder</h2>
<form method="get" action="/api/lcsd/timetableexcel">
  <label>Year:
    <input type="number" name="year" min="1900" required>
  </label><br><br>
  <label>Month:
    <input type="number" name="month" min="1" max="12" required>
  </label><br><br>
  <button type="submit">Build timetable (Excel)</button>
</form>
<p>The generated JSON is saved to Cosmos DB with
   tag <code>lcsd</code>, secondary-tag <code>timetableexcel</code>.</p>
</body>
</html>
"""

@router.get("/api/lcsd/timetableexcel/html", include_in_schema=False, response_class=HTMLResponse)
def timetableexcel_form(request: Request):
    return HTMLResponse(_HTML)
