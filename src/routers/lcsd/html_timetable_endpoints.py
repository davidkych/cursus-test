# ── src/routers/lcsd/html_timetable_endpoints.py ────────────────────────────
"""
Simple browser form that lets an operator trigger the LCSD *timetable builder*.

🔍 How it works
──────────────
* Submitting the form issues a **GET** request to `/api/lcsd/timetable`
  (unchanged from the legacy version).  
* The builder itself is implemented elsewhere; this endpoint is purely UI.

Nothing in the page needs to know about Cosmos-DB internals -–
the heavy lifting now happens inside the newer `/api/lcsd/availability`
stack, which already pulls its data from
    tag='lcsd', secondary_tag='af_excel_timetable', tertiary_tag=<lcsdid>
with the *latest* day of the requested month.
"""
from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter()

_FORM_HTML = """
<!doctype html>
<html lang="en">
<head><meta charset="utf-8">
<title>LCSD Timetable Builder</title>
<style>
  body{font-family:sans-serif;max-width:480px;margin:2rem auto}
  label{display:block;margin:.7rem 0}
</style>
</head>
<body>
<h2>LCSD Athletic-Field Timetable Builder</h2>

<form method="get" action="/api/lcsd/timetable">
  <label>Year:
    <input type="number" name="year" min="1900" required>
  </label>
  <label>Month:
    <input type="number" name="month" min="1" max="12" required>
  </label>
  <button type="submit">Build timetable</button>
</form>

<p style="margin-top:1.4rem;max-width:440px;">
  The builder first attempts to create a timetable from the monthly
  <strong>Excel</strong> sheet stored in Cosmos DB.<br>
  If no Excel data are available it automatically falls back to the matching
  <strong>PDF</strong>.  
  Either way the JSON is saved under tag <code>lcsd/timetable</code>.
</p>
</body>
</html>
"""

@router.get(
    "/api/lcsd/timetable/html",
    include_in_schema=False,
    response_class=HTMLResponse,
)
def timetable_form() -> HTMLResponse:
    """Serve the interactive builder launcher form."""
    return HTMLResponse(_FORM_HTML)
