# ── src/routers/lcsd/lcsd_af_adminupload_html.py ────────────────────────────
"""
HTML front-end for the *admin upload* of LCSD timetables.

Route
    GET  /api/lcsd/lcsd_af_adminupload_timetable
Returns a very small page that lets an operator pick a JSON file and upload it.
(Actual processing is implemented in *lcsd_af_adminupload_logic.py*.)
"""
from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter()

_FORM_HTML = """
<!doctype html>
<title>Admin Upload — LCSD Timetable JSON</title>
<h2>Admin Upload: LCSD Timetable JSON</h2>
<form action="/api/lcsd/lcsd_af_adminupload_timetable" method="post" enctype="multipart/form-data">
  <label>Select JSON file:
    <input type="file" name="file" accept=".json" required>
  </label>
  <br><br>
  <button type="submit">Upload</button>
</form>
"""

@router.get("/api/lcsd/lcsd_af_adminupload_timetable",
            include_in_schema=False,
            response_class=HTMLResponse)
def adminupload_form() -> HTMLResponse:
    """Serve the upload form."""
    return HTMLResponse(_FORM_HTML)
