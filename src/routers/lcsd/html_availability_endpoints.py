# ── src/routers/lcsd/html_availability_endpoints.py ─────────────────────────
"""
HTML helpers for /api/lcsd/availability

UI and behaviour are identical to the legacy implementation; the only
difference is that the generated form now targets the **new** JSON API
provided by *availability_endpoints.py* at `/api/lcsd/availability`.
"""

from __future__ import annotations

import datetime
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

router = APIRouter()

_HK_TZ = ZoneInfo("Asia/Hong_Kong")
_now = datetime.datetime.now(datetime.timezone.utc).astimezone(_HK_TZ)
_now_hms = _now.strftime("%H:%M:%S")
_today = _now.date().isoformat()

_FORM = f"""
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>LCSD Availability Checker</title>
  <style>
    body   {{ font-family:sans-serif; max-width:540px; margin:2rem auto; }}
    label  {{ display:block; margin-bottom:.8rem; }}
    .hide  {{ display:none; }}
    .inline{{ display:inline-block; vertical-align:middle; }}
  </style>
</head>
<body>
<h2>LCSD Athletic-Field Availability</h2>

<form id="availForm" method="get" action="/api/lcsd/availability">
  <label>
    LCSD&nbsp;ID:<br>
    <input type="text" name="lcsdid" required>
  </label>

  <label>
    Date (YYYY-MM-DD):<br>
    <input type="date" name="date" value="{_today}" required>
  </label>

  <!-- ── query-mode toggle ────────────────────────────────────────── -->
  <fieldset style="margin-bottom:.8rem;">
    <legend style="font-weight:bold;">Query mode</legend>
    <label class="inline"><input type="radio" name="mode" value="time"   checked> Time (single)</label>
    &nbsp;&nbsp;
    <label class="inline"><input type="radio" name="mode" value="period"> Period (range)</label>
  </fieldset>

  <!-- ── point-in-time input ──────────────────────────────────────── -->
  <div id="timeGroup">
    <label>
      Time (HH:MM:SS):<br>
      <input type="time" id="timeInput" name="time" step="1"
             value="{_now_hms}" required>
    </label>
  </div>

  <!-- ── period input ──────────────────────────────────────────────── -->
  <div id="periodGroup" class="hide">
    <label>
      Period (same day):<br>
      <input type="time" id="startTime" step="1"  class="inline" style="width:120px;" value="{_now_hms}">
      <span class="inline"> – </span>
      <input type="time" id="endTime"   step="1"  class="inline" style="width:120px;" value="{_now_hms}">
    </label>
    <input type="hidden" id="periodHidden" value="">
  </div>

  <button type="submit">Check availability</button>
</form>

<p style="max-width:480px;margin-top:1.5rem;">
  Only the timetable of <em>this</em> or <em>next</em> month can be queried.
</p>

<script>
const form        = document.getElementById("availForm");
const modeRadios  = document.querySelectorAll("input[name='mode']");
const timeGroup   = document.getElementById("timeGroup");
const periodGroup = document.getElementById("periodGroup");
const timeInput   = document.getElementById("timeInput");
const startInput  = document.getElementById("startTime");
const endInput    = document.getElementById("endTime");
const periodH     = document.getElementById("periodHidden");

function updateMode() {{
  const isTime = document.querySelector("input[name='mode']:checked").value === "time";
  timeGroup.classList.toggle("hide", !isTime);
  periodGroup.classList.toggle("hide", isTime);

  // ensure only the active param has a name attribute
  if (isTime) {{
    timeInput.name = "time";
    periodH.removeAttribute("name");
    timeInput.required = true;
    startInput.required = endInput.required = false;
  }} else {{
    periodH.name = "period";
    timeInput.removeAttribute("name");
    timeInput.required = false;
    startInput.required = endInput.required = true;
  }}
}}
modeRadios.forEach(r => r.addEventListener("change", updateMode));
updateMode();  // initial call

form.addEventListener("submit", e => {{
  const isTime = document.querySelector("input[name='mode']:checked").value === "time";
  if (!isTime) {{
    if (!startInput.value || !endInput.value) {{
      alert("Please fill both start and end times.");
      e.preventDefault();
      return;
    }}
    periodH.value = `${{startInput.value}}-${{endInput.value}}`;
  }}
}});
</script>
</body>
</html>
"""

@router.get(
    "/api/lcsd/availability/html",
    include_in_schema=False,
    response_class=HTMLResponse,
)
def availability_form(request: Request) -> HTMLResponse:  # noqa: D401 – FastAPI signature
    """Serve the interactive browser form for the availability endpoint."""
    return HTMLResponse(_FORM)
