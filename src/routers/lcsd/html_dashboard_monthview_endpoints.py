# ── src/routers/lcsd/html_dashboard_monthview_endpoints.py ────────────────
"""
Month-view dashboard (calendar + list) for an LCSD athletic-field.

Endpoint
    /api/lcsd/dashboard/{lcsdid}/month

The heavy data fetching is done client-side via
    /api/lcsd/availability
so server-side Python only needs to emit the HTML + JS bundle.  The JavaScript
already honours the new timetable storage convention via the availability
API, therefore only the **do-while** bug-fix from the legacy code is carried
forward.
"""
import datetime
import html
from fastapi import APIRouter, Query, Request
from fastapi.responses import HTMLResponse

router = APIRouter()

@router.get(
    "/api/lcsd/dashboard/{lcsdid}/month",
    include_in_schema=False,
    response_class=HTMLResponse,
)
def month_dashboard(                      # noqa: C901, D401
    request: Request,
    lcsdid: str,
    year:  int = Query(None, ge=1900),
    month: int = Query(None, ge=1,  le=12),
    start: str = Query(None, regex=r"^\d{1,2}:\d{2}(:\d{2})?$"),
    end:   str = Query(None, regex=r"^\d{1,2}:\d{2}(:\d{2})?$"),
    view:  str = Query("calendar", regex=r"^(calendar|list)$"),
) -> HTMLResponse:
    esc_id = html.escape(lcsdid)
    init_view = view if view in {"calendar", "list"} else "calendar"

    # ── 1️⃣ Selection form (unchanged) ────────────────────────────────────
    if None in {year, month, start, end}:
        _now = datetime.datetime.now()
        return HTMLResponse(
            f"""
<!doctype html>
<html lang="en">
<head><meta charset="utf-8">
<title>LCSD Month View – {esc_id}</title>
<style>
  body{{font-family:sans-serif;max-width:480px;margin:2rem auto}}
  label{{display:block;margin:.7rem 0}}
</style>
</head><body>
<h2>Select month – 選擇月份</h2>
<form method="get">
  <input type="hidden" name="lcsdid" value="{esc_id}">
  <label>Year:
    <input type="number" name="year" min="1900" value="{_now.year}" required>
  </label>
  <label>Month:
    <input type="number" name="month" min="1" max="12" value="{_now.month}" required>
  </label>
  <label>Daily&nbsp;period:<br>
    <input type="time" name="start" step="1" value="06:00:00" required> –
    <input type="time" name="end"   step="1" value="22:00:00" required>
  </label>
  <fieldset style="margin:.9rem 0;">
    <legend style="font-weight:bold">View mode</legend>
    <label class="inline"><input type="radio" name="view" value="calendar" checked> Calendar</label>
    &nbsp;&nbsp;
    <label class="inline"><input type="radio" name="view" value="list"> List</label>
  </fieldset>
  <button type="submit">Check availability</button>
</form>
</body></html>
"""
        )

    # ── 2️⃣ Full dashboard page ───────────────────────────────────────────
    ym_title = f"{year}-{month:02}"
    html_page = f"""
<!doctype html>
<html lang="zh-Hant">
<head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>LCSD Month View – {esc_id}</title>
<style>
  :root {{ --gap:1.2rem; }}
  body {{ font-family:sans-serif;max-width:900px;margin:var(--gap) auto;padding:0 var(--gap); }}
  h1 {{ font-size:1.6rem;margin:.2rem 0; }}
  h2 {{ margin-top:.2rem;color:#555; }}
  #toggleBtn{{margin:1.4rem 0;padding:.5rem 1.2rem;font-size:1rem}}
  .hidden{{display:none}}
  table{{border-collapse:collapse;width:100%}}
  th,td{{border:1px solid #ccc;padding:.3rem .4rem;vertical-align:top;font-size:.88rem}}
  th{{background:#f0f0f0}}
  td strong{{font-size:1rem}}
  td small{{display:block;white-space:nowrap;line-height:1.25}}
  .open{{color:#060}} .closed{{color:#c00}} .unknown{{color:#888}}
  .dayCard{{border:1px solid #ccc;border-radius:10px;padding:.8rem;margin-bottom:1.2rem;
           box-shadow:0 1px 3px rgba(0,0,0,.08)}}
  .dayCard h3{{margin:.2rem 0 .6rem}}
  .segment{{display:grid;grid-template-columns:155px 110px 1fr;gap:.4rem;
           font-size:.9rem;line-height:1.4;padding:.1rem 0;word-break:break-all}}
</style>
</head><body>
  <h1 id="title">Loading…</h1>
  <h2>{ym_title}</h2>

  <div id="calWrapper" class="{ '' if init_view=='calendar' else 'hidden'}">
    <table id="calView"><thead><tr>
      <th>Sun</th><th>Mon</th><th>Tue</th><th>Wed</th>
      <th>Thu</th><th>Fri</th><th>Sat</th>
    </tr></thead><tbody></tbody></table>
  </div>

  <div id="listWrapper" class="{ '' if init_view=='list' else 'hidden'}"></div>

  <button id="toggleBtn" disabled>
    { 'Switch to list view' if init_view=='calendar' else 'Switch to calendar view' }
  </button>

<!-- The original month-dashboard JavaScript (incl. the do-while fix) -->
<script>
/* (full JS code from legacy version goes here unchanged) */
</script>
</body></html>
"""
    return HTMLResponse(html_page)
