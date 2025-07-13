# ── src/routers/lcsd/lcsd_af_adminupload_page.py ────────────────────────────
"""
Web-only endpoint   /api/lcsd/lcsd_af_adminupload_timetable   (GET | POST)

GET  → returns a minimal HTML page with a *file picker* + *Upload* button  
POST → accepts a JSON file, pipes it to process_admin_upload(), and shows a
        human-readable confirmation page

Layout and business logic live in separate modules as required:
    • this file  → UI / routing
    • lcsd_af_adminupload_logic.py → heavy lifting
"""
from __future__ import annotations

import json
from typing import Dict

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import HTMLResponse

from .lcsd_af_adminupload_logic import process_admin_upload

router = APIRouter()


# ════════════════════════════════════════════════════════════════════════════
# inline HTML – self-contained, no external assets
# ════════════════════════════════════════════════════════════════════════════
_FORM_HTML = """
<!doctype html>
<title>Admin &middot; Upload LCSD Timetable JSON</title>
<h2>Upload LCSD Timetable JSON</h2>
<p>This form is intended for administrative uploads of <em>combined</em>
timetable JSON files (the ones containing a top-level <code>"records"</code>
array).</p>
<form action="/api/lcsd/lcsd_af_adminupload_timetable" method="post" enctype="multipart/form-data">
  <label>Select file:
    <input type="file" name="file" accept=".json" required>
  </label>
  <br><br>
  <button type="submit">Upload</button>
</form>
"""


# ════════════════════════════════════════════════════════════════════════════
# routes
# ════════════════════════════════════════════════════════════════════════════
@router.get(
    "/api/lcsd/lcsd_af_adminupload_timetable",
    include_in_schema=False,
    response_class=HTMLResponse,
)
def adminupload_form() -> HTMLResponse:
    """Serve the upload form (no Swagger doc)."""
    return HTMLResponse(_FORM_HTML)


@router.post(
    "/api/lcsd/lcsd_af_adminupload_timetable",
    include_in_schema=False,
    response_class=HTMLResponse,
)
async def adminupload_submit(file: UploadFile = File(...)) -> HTMLResponse:
    """Handle the uploaded JSON file and show a success / error page."""
    try:
        raw = await file.read()
        data: Dict = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise HTTPException(status_code=400, detail="Uploaded file is not valid UTF-8 JSON")

    summary = process_admin_upload(data)

    html = f"""
<!doctype html>
<title>Upload result</title>
<h2>Upload successful</h2>
<ul>
  <li><strong>Timestamp&nbsp;&nbsp;</strong> {summary['timestamp']}</li>
  <li><strong>Master&nbsp;item&nbsp;ID&nbsp;&nbsp;</strong> {summary['avail_item_id']}</li>
  <li><strong>Worksheet&nbsp;docs&nbsp;saved&nbsp;&nbsp;</strong> {summary['excel_docs_saved']}</li>
</ul>
<p><a href="/api/lcsd/lcsd_af_adminupload_timetable">Upload another file</a></p>
"""
    return HTMLResponse(html)
