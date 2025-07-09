# ── src/routers/lcsd/html_master_endpoints.py ───────────────────────
"""
Simple browser form to trigger the master builder.
"""

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

router = APIRouter()

_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>LCSD Master Builder</title>
<style>
 body { font-family:sans-serif; max-width:560px; margin:2rem auto; }
</style>
</head>
<body>
<h2>LCSD Athletic-Field Master Builder</h2>
<form action="/api/lcsd/master" method="get">
  <label>Delay between requests (sec):
    <input type="number" step="0.05" name="delay" value="0.1" min="0">
  </label><br><br>
  <button type="submit">Run master build</button>
</form>
<p>Uses the most recent probe (tag <code>lcsd/probe</code>) and writes the consolidated
result back as <code>tag=lcsd</code>, <code>secondary_tag=master</code> with today’s date.</p>
</body>
</html>
"""

router = APIRouter()

@router.get("/api/lcsd/master/html", include_in_schema=False, response_class=HTMLResponse)
def master_form(request: Request):
    return HTMLResponse(content=_HTML)
