# ── src/routers/lcsd/html_probe_endpoints.py ─────────────────────────
"""
Very small HTML helper so a browser can kick off the probe via a form.
GET  /api/lcsd/probe/html
"""
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

router = APIRouter()

_HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>LCSD Probe</title>
<style>
 body {{ font-family:sans-serif; max-width:560px; margin:2rem auto; }}
 input[type=number] {{ width:6rem; }}
</style>
</head>
<body>
<h2>LCSD Athletic-Field Probe</h2>
<form action="/api/lcsd/probe" method="get">
  <label>Start DID:
    <input type="number" name="startDid" value="0" min="0">
  </label><br><br>
  <label>End DID:
    <input type="number" name="endDid" value="20" min="0">
  </label><br><br>
  <label>Delay&nbsp;(sec):
    <input type="number" step="0.05" name="delay" value="0.1" min="0">
  </label><br><br>
  <button type="submit">Run probe</button>
</form>
<p>Results are stored in Cosmos with tag <code>lcsd</code>, secondary_tag <code>probe</code>,
and today’s date – retrievable via existing <code>/api/json</code> endpoints.</p>
</body>
</html>
"""

@router.get("/api/lcsd/probe/html", include_in_schema=False, response_class=HTMLResponse)
def probe_form(request: Request):
    return HTMLResponse(content=_HTML_TEMPLATE)
