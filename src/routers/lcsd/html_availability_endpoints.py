# ── src/routers/lcsd/html_availability_endpoints.py ──────────────────
"""
Interactive HTML helper for /api/lcsd/availability

Changes (2025-07-14)
────────────────────
* Form parameter renamed **lcsd_number** (was lcsdid).  
* Default date/time are injected client-side so the form never goes stale.
"""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

router = APIRouter()

# ── static HTML form (runtime-fresh values are injected via JS) ──
_FORM_HTML = """
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>LCSD Availability Checker</title>
<style>
  body   { font-family:sans-serif; max-width:540px; margin:2rem auto; }
  label  { display:block; margin-bottom:.8rem; }
  .hide  { display:none; }
  .inline{ display:inline-block; vertical-align:middle; }
</style>
</head>
<body>
<h2>LCSD Athletic-Field Availability</h2>

<form id="availForm" method="get" action="/api/lcsd/availability">
  <label>
    LCSD&nbsp;Number:<br>
    <input type="text" name="lcsd_number" required>
  </label>

  <label>
    Date (YYYY-MM-DD):<br>
    <input type="date" name="date" required>
  </label>

  <!-- ── query-mode toggle ─────────────────────────────────────────── -->
  <fieldset style="margin-bottom:.8rem;">
    <legend style="font-weight:bold;">Query mode</legend>
    <label class="inline"><input type="radio" name="mode" value="time"   checked> Time (single)</label>
    &nbsp;&nbsp;
    <label class="inline"><input type="radio" name="mode" value="period"> Period (range)</label>
  </fieldset>

  <!-- ── point-in-time input ───────────────────────────────────────── -->
  <div id="timeGroup">
    <label>
      Time (HH:MM:SS):<br>
      <input type="time" id="timeInput" name="time" step="1" required>
    </label>
  </div>

  <!-- ── period input ──────────────────────────────────────────────── -->
  <div id="periodGroup" class="hide">
    <label>
      Period (same day):<br>
      <input type="time" id="startTime" step="1"  class="inline" style="width:120px;">
      <span class="inline"> – </span>
      <input type="time" id="endTime"   step="1"  class="inline" style="width:120px;">
    </label>
    <input type="hidden" id="periodHidden" value="">
  </div>

  <button type="submit">Check availability</button>
</form>

<p style="max-width:480px;margin-top:1.5rem;">
  Only the timetable of <em>this</em> or <em>next</em> month can be queried.
</p>

<script>
/* ── set fresh default date & time ─────────────────────────────────── */
const now       = new Date();
const pad       = n => n.toString().padStart(2,'0');
const isoDate   = now.getFullYear() + "-" + pad(now.getMonth()+1) + "-" + pad(now.getDate());
const isoTime   = pad(now.getHours()) + ":" + pad(now.getMinutes()) + ":" + pad(now.getSeconds());
document.querySelector('input[name="date"]').value = isoDate;
document.getElementById("timeInput").value         = isoTime;
document.getElementById("startTime").value         = isoTime;
document.getElementById("endTime").value           = isoTime;

/* ── form-toggle logic (unchanged) ─────────────────────────────────── */
const form        = document.getElementById("availForm");
const modeRadios  = document.querySelectorAll("input[name='mode']");
const timeGroup   = document.getElementById("timeGroup");
const periodGroup = document.getElementById("periodGroup");
const timeInput   = document.getElementById("timeInput");
const startInput  = document.getElementById("startTime");
const endInput    = document.getElementById("endTime");
const periodH     = document.getElementById("periodHidden");

function updateMode() {
  const isTime = document.querySelector("input[name='mode']:checked").value === "time";
  timeGroup.classList.toggle("hide", !isTime);
  periodGroup.classList.toggle("hide", isTime);

  // ensure only the active param has a name attribute
  if (isTime) {
    timeInput.name = "time";
    periodH.removeAttribute("name");
    timeInput.required = true;
    startInput.required = endInput.required = false;
  } else {
    periodH.name = "period";
    timeInput.removeAttribute("name");
    timeInput.required = false;
    startInput.required = endInput.required = true;
  }
}
modeRadios.forEach(r => r.addEventListener("change", updateMode));
updateMode();  // initial call

form.addEventListener("submit", e => {
  const isTime = document.querySelector("input[name='mode']:checked").value === "time";
  if (!isTime) {
    if (!startInput.value || !endInput.value) {
      alert("Please fill both start and end times.");
      e.preventDefault();
      return;
    }
    periodH.value = `${startInput.value}-${endInput.value}`;
  }
});
</script>
</body>
</html>
"""

# ── FastAPI route (visible in schema) ─────────────────────────────────
@router.get(
    "/api/lcsd/availability/html",
    response_class=HTMLResponse,
    summary="Interactive HTML form for /api/lcsd/availability",
)
def availability_form(request: Request) -> HTMLResponse:
    """Serve the interactive browser form for the availability endpoint."""
    return HTMLResponse(_FORM_HTML)
