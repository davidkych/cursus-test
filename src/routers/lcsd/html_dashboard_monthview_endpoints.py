# ── src/routers/lcsd/html_dashboard_monthview_endpoints.py ────────────────
"""
Monthly (calendar / list) availability dashboard for an LCSD athletic-field.

Path
    /api/lcsd/dashboard/{lcsd_number}/month        (GET)

This is the modernised rewrite of the legacy *html_dashboard_monthview_endpoints*
module.  The UI and overall behaviour stay the same, but it now:

• Talks to the **new** `/api/lcsd/availability` endpoint introduced in
  refactor 3 (2025-07-13).
• Removes all hard-coded special-cases for 「將軍澳運動場 主／副場」
  (1060a / 1060b) – those are handled upstream by the timetable-generation
  pipeline.
"""

import datetime
import html
from fastapi import APIRouter, Query, Request
from fastapi.responses import HTMLResponse

router = APIRouter()


@router.get(
    "/api/lcsd/dashboard/{lcsd_number}/month",
    include_in_schema=False,
    response_class=HTMLResponse,
)
def month_dashboard(                       # noqa: C901  (long HTML string)
    request: Request,
    lcsd_number: str,
    year:  int  = Query(None, ge=1900),
    month: int  = Query(None, ge=1,  le=12),
    start: str  = Query(None, regex=r"^\d{1,2}:\d{2}(:\d{2})?$"),
    end:   str  = Query(None, regex=r"^\d{1,2}:\d{2}(:\d{2})?$"),
    view:  str  = Query("calendar", regex=r"^(calendar|list)$"),
):
    esc_id    = html.escape(lcsd_number)
    init_view = view if view in {"calendar", "list"} else "calendar"

    # ── 1️⃣ picker form ───────────────────────────────────────────────────────
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
  .inline{{display:inline-block;vertical-align:middle}}
</style>
</head><body>
<h2>Select month – 選擇月份</h2>
<form method="get">
  <input type="hidden" name="lcsd_number" value="{esc_id}">
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
  <!-- view toggle -->
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

    # ── 2️⃣ dashboard (calendar + list views) ────────────────────────────────
    ym_title = f"{year}-{month:02}"
    html_page = f"""
<!doctype html>
<html lang="zh-Hant">
<head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>LCSD Month View – {esc_id}</title>
<style>
  :root {{ --gap:1.2rem; }}
  body  {{ font-family:sans-serif;max-width:900px;margin:var(--gap) auto;padding:0 var(--gap); }}
  h1    {{ font-size:1.6rem;margin:.2rem 0; }}
  h2    {{ margin-top:.2rem;color:#555; }}
  /* ---- toggle button ---- */
  #toggleBtn{{margin:1.4rem 0;padding:.5rem 1.2rem;font-size:1rem}}
  .hidden{{display:none}}
  /* ---- CALENDAR styles ---- */
  table {{ border-collapse:collapse;width:100%; }}
  th,td {{ border:1px solid #ccc;padding:.3rem .4rem;vertical-align:top;font-size:.88rem; }}
  th    {{ background:#f0f0f0; }}
  td strong {{ font-size:1rem; }}
  td small  {{ display:block;white-space:nowrap;line-height:1.25; }}
  .open    {{ color:#060; }}
  .closed  {{ color:#c00; }}
  .unknown {{ color:#888; }}
  /* ---- LIST styles ---- */
  .dayCard {{
    border:1px solid #ccc;border-radius:10px;padding:.8rem;margin-bottom:1.2rem;
    box-shadow:0 1px 3px rgba(0,0,0,.08);
  }}
  .dayCard h3{{margin:.2rem 0 .6rem}}
  .segment {{ display:grid;grid-template-columns:155px 110px 1fr;gap:.4rem;
             font-size:.9rem;line-height:1.4;padding:.1rem 0;word-break:break-all; }}
</style>
</head><body>
  <h1 id="title">Loading…</h1>
  <h2>{ym_title}</h2>

  <!-- ---------- CALENDAR container ---------- -->
  <div id="calWrapper" class="{ '' if init_view=='calendar' else 'hidden'}">
    <table id="calView"><thead><tr>
      <th>Sun</th><th>Mon</th><th>Tue</th><th>Wed</th>
      <th>Thu</th><th>Fri</th><th>Sat</th>
    </tr></thead><tbody></tbody></table>
  </div>

  <!-- ---------- LIST container ---------- -->
  <div id="listWrapper" class="{ '' if init_view=='list' else 'hidden'}">
    <!-- day cards injected by JS -->
  </div>

  <button id="toggleBtn" disabled>
    { 'Switch to list view' if init_view=='calendar' else 'Switch to calendar view' }
  </button>

<script>
(() => {{
/* ---------- constants ---------------------------------------- */
const id       = "{esc_id}";
const initView = "{init_view}";
let   curView  = initView;

const YEAR  = {year};
const MONTH = {month - 1};            /* JS months are 0-based */
const START = "{start}";
const END   = "{end}";
const DAY_MS = 86400000;

/* ---------- neighbour / name caches -------------------------- */
let nameMap   = null;   // Map<lcsd_number, name>
let rapidData = null;   // raw rapid array

/* ---------- DOM refs ----------------------------------------- */
const calWrap  = document.getElementById('calWrapper');
const listWrap = document.getElementById('listWrapper');
const toggleBtn= document.getElementById('toggleBtn');

/* ---------- helpers ------------------------------------------ */
const pad  = n => String(n).padStart(2,'0');
const iso  = d => d.getFullYear() + '-' + pad(d.getMonth()+1) + '-' + pad(d.getDate());
const hhmm = t => t.slice(0,5);
const mark = v => v==='true'   ? '可用 ✅'
                : v==='false'  ? '未能使用 ❌'
                : v==='partial'? '部分可用 🔶'
                :               '未知 ❓';

/* ---- title (facility name) ---------------------------------- */
fetch('/api/lcsd/availability?lcsd_number=' + id)
  .then(r => r.ok ? r.json() : null)
  .then(j => {{
    document.getElementById('title').textContent =
      (j && j.facility_name ? j.facility_name : '運動場') + ' (' + id + ')';
  }});

/* ---------- rapid / neighbour helpers ------------------------ */
async function fetchRapid() {{
  if (nameMap && rapidData) return;
  const res = await fetch("/api/json?tag=lcsd&secondary_tag=rapid");
  rapidData = await res.json();
  nameMap   = new Map(rapidData.map(r => [r.lcsd_number, r.name]));
}}
function nameFor(code) {{
  return nameMap?.get(code) ?? code;
}}
function aggregateAvail(segs) {{
  if (!segs.length) return 'unknown';
  let hasTrue=false, hasFalse=false;
  segs.forEach(s => {{
    if (s.availability === 'true')  hasTrue  = true;
    if (s.availability === 'false') hasFalse = true;
  }});
  if (hasTrue && hasFalse) return 'partial';
  if (hasTrue)  return 'true';
  if (hasFalse) return 'false';
  return 'unknown';
}}

/* ---------- containers pre-build ----------------------------- */
prebuildListCards();
prebuildCalendarTable();

/* ---------- data fetch & rendering --------------------------- */
const monthData = Object.create(null);   // isoDate -> segments[]
populateViews().then(() => {{ toggleBtn.disabled = false; }});

/* ---------- toggle handler ----------------------------------- */
toggleBtn.addEventListener('click', () => {{
  if (curView === 'calendar') {{
    calWrap.classList.add('hidden');
    listWrap.classList.remove('hidden');
    toggleBtn.textContent = 'Switch to calendar view';
    curView = 'list';
  }} else {{
    listWrap.classList.add('hidden');
    calWrap.classList.remove('hidden');
    toggleBtn.textContent = 'Switch to list view';
    curView = 'calendar';
  }}
}});

/* ============================================================= */
/* ===== functions ============================================= */
/* ============================================================= */

function prebuildListCards() {{
  const daysInMonth = new Date(YEAR, MONTH + 1, 0).getDate();
  for (let d = 1; d <= daysInMonth; d++) {{
    const dStr = iso(new Date(YEAR, MONTH, d));
    const card = document.createElement('div');
    card.className = 'dayCard';
    card.id = 'card-' + dStr;

    const h3 = document.createElement('h3');
    h3.textContent = dStr;
    card.appendChild(h3);

    const holder = document.createElement('div');
    holder.className = 'segmentsHolder';
    card.appendChild(holder);

    listWrap.appendChild(card);
  }}
}}

/* =============================================================
   >>>>  FIXED  function  (do-while guarantees first row)  <<<<
   ============================================================= */
function prebuildCalendarTable() {{
  const tbody = document.querySelector('#calView tbody');
  const first = new Date(YEAR, MONTH, 1);
  let cur     = new Date(first);
  cur.setDate(cur.getDate() - cur.getDay());   /* back to Sunday */

  /* Ensure at least one iteration so the week that straddles the
     previous month is rendered when the target month starts on
     Mon-Sat (e.g. 2025-07-01 → Sunday 2025-06-29). */
  do {{
    const tr = document.createElement('tr');
    for (let i = 0; i < 7; i++) {{
      const td = document.createElement('td');
      if (cur.getMonth() === MONTH) {{
        td.id = 'td-' + iso(cur);
        td.innerHTML = '<strong>' + cur.getDate() + '</strong>';
      }}
      tr.appendChild(td);
      cur = new Date(cur.getTime() + DAY_MS);
    }}
    tbody.appendChild(tr);
  }} while (cur.getMonth() === MONTH || cur.getDay() !== 0);
}}

async function populateViews() {{
  const daysInMonth = new Date(YEAR, MONTH + 1, 0).getDate();
  const tasks = [];

  for (let d = 1; d <= daysInMonth; d++) {{
    const dStr  = iso(new Date(YEAR, MONTH, d));
    const period = encodeURIComponent(START + '-' + END);
    const url = `/api/lcsd/availability?lcsd_number=${{id}}&date=${{dStr}}&period=${{period}}`;

    tasks.push(
      fetch(url)
        .then(r => r.ok ? r.json() : null)
        .then(data => {{
          const segs = data && data.segments ? data.segments : [];
          monthData[dStr] = segs;
          renderListDay(dStr, segs);
          renderCalendarCell(dStr, segs);
        }})
        .catch(() => {{
          monthData[dStr] = [];
          renderListDay(dStr, []);
          renderCalendarCell(dStr, []);
        }})
    );
  }}
  await Promise.allSettled(tasks);
}}

function renderListDay(dateStr, segs) {{
  const holder = document.querySelector('#card-' + dateStr + ' .segmentsHolder');
  holder.innerHTML = '';
  if (!segs.length) {{
    holder.textContent = '無資料';
    return;
  }}
  segs.forEach(s => {{
    const div = document.createElement('div');
    div.className = 'segment';

    const legendText = s.legend ? `(${{s.legend}})` : '';
    div.innerHTML =
      `<span>${{s.time_range}}</span>` +
      `<span>${{mark(s.availability)}}</span>` +
      `<span class="legendCell">${{legendText}}</span>`;
    holder.appendChild(div);

    /* ---------- neighbour look-up for “extreme-time” slots ----- */
    const needsNeighbours = (s.availability === 'false') &&
                            (!s.legend || !s.legend.includes('運動場關閉時間'));
    if (needsNeighbours) {{
      const legendCell = div.querySelector('.legendCell');
      legendCell.innerHTML += '<br><em>附近場地查詢中…</em>';
      addNeighbourLines(dateStr, s.time_range, legendCell);
    }}
  }});
}}

async function addNeighbourLines(dateStr, timeRange, cell) {{
  try {{
    await fetchRapid();

    const rec = rapidData.find(r => r.lcsd_number === id);
    const neighbours = rec?.nearest || [];
    if (!neighbours.length) {{
      cell.innerHTML = cell.innerHTML.replace(/<em[^>]*>.*<\\/em>/,'無鄰近場地資料');
      return;
    }}

    const lines = await Promise.all(neighbours.map(async code => {{
      try {{
        const url = `/api/lcsd/availability?lcsd_number=${{code}}&date=${{dateStr}}&period=${{encodeURIComponent(timeRange)}}`;
        const res = await fetch(url);
        if (!res.ok) throw new Error();
        const data = await res.json();
        const agg  = aggregateAvail(data.segments || []);
        return `&gt;&nbsp;${{nameFor(code)}}(${{code}}): ${{mark(agg)}}`;
      }} catch {{
        return `&gt;&nbsp;${{nameFor(code)}}(${{code}}): 無法取得資料`;
      }}
    }}));

    cell.innerHTML = cell.innerHTML.replace(/<em[^>]*>.*<\\/em>/,'') + '<br>' + lines.join('<br>');
  }} catch {{
    cell.innerHTML = cell.innerHTML.replace(/<em[^>]*>.*<\\/em>/,'鄰近資料讀取失敗');
  }}
}}

function renderCalendarCell(dateStr, segs) {{
  const td = document.getElementById('td-' + dateStr);
  if (!td) return;
  // determine class
  let cls = 'unknown';
  if (segs.length === 1) {{
    cls = segs[0].availability === 'true' ? 'open'
       : (segs[0].availability === 'false' ? 'closed' : 'unknown');
  }}
  td.classList.add(cls);
  // add mini lines
  segs.forEach(s => {{
    const small = document.createElement('small');
    const times = s.time_range.split('-',2);
    small.textContent = hhmm(times[0]) + '-' + hhmm(times[1]) + ' ' + mark(s.availability);
    td.appendChild(document.createElement('br'));
    td.appendChild(small);
  }});
}}
}})();
</script>
</body></html>
"""
    return HTMLResponse(html_page)
