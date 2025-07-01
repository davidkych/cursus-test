# ── src/routers/lcsd/html_timetablepdf_endpoints.py ──────────────────
"""
Simple browser form to launch the timetable-PDF builder.
"""

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

router = APIRouter()

_HTML = """
<!doctype html>
<html lang="en">
<head><meta charset="utf-8"><title>LCSD Timetable-PDF Builder</title></head>
<body style="font-family:sans-serif;max-width:480px;margin:2rem auto;">
<h2>LCSD Athletic-Field Timetable-PDF Builder</h2>
<form method="get" action="/api/lcsd/timetablepdf">
  <label>Year:
    <input type="number" name="year" min="1900" required>
  </label><br><br>
  <label>Month:
    <input type="number" name="month" min="1" max="12" required>
  </label><br><br>
  <button type="submit">Build timetable (PDF)</button>
</form>
<p>The generated JSON is saved to Cosmos DB with
   tag <code>lcsd</code>, secondary-tag <code>timetablepdf</code>.</p>
</body>
</html>
"""

@router.get("/api/lcsd/timetablepdf/html", include_in_schema=False, response_class=HTMLResponse)
def timetablepdf_form(request: Request):
    return HTMLResponse(_HTML)
