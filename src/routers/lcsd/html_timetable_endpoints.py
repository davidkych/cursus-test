# ── src/routers/lcsd/html_timetable_endpoints.py ────────────────────────────
"""
Simple browser form to launch the LCSD timetable builder.

The builder continues to POST to **/api/lcsd/timetable** exactly as before.
Internally, that endpoint must now look up timetable data in Cosmos DB at

    tag           = 'lcsd'
    secondary_tag = 'af_excel_timetable'
    tertiary_tag  = <lcsdid>
    year / month  = of the requested date
    day           = the *latest* document day inside the month

No data access happens here – this module only serves the HTML form.
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
  The service builds the timetable from the monthly
  <strong>Excel</strong> sheet stored in Cosmos DB
  (<code>tag='lcsd', secondary_tag='af_excel_timetable'</code>).  
  If the Excel sheet is missing or cannot be parsed the back-end will
  automatically fall back to the corresponding <strong>PDF</strong>.
</p>
<p>
  The generated JSON is saved back under the same tag / secondary-tag
  with the day-field set to the current (HKT) date.
</p>
</body>
</html>
"""

@router.get(
    "/api/lcsd/timetable/html",
    include_in_schema=False,
    response_class=HTMLResponse,
)
def timetable_form(request: Request) -> HTMLResponse:  # noqa: D401 – simple wrapper
    """Serve the interactive timetable-builder form."""
    return HTMLResponse(_HTML)
