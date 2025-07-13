# ── src/routers/lcsd/html_dashboard_endpoints.py ────────────────────────────
"""
Standalone HTML dashboard for LCSD facility availability.

The dashboard queries
    • /api/lcsd/availability                   – point-in-time and outlook
    • /api/json?tag=lcsd&secondary_tag=rapid   – static facility meta-data

Those back-end endpoints already read their data from
*af_excel_timetable* documents (see availability_endpoints.py), so the
dashboard logic itself needs no further changes.
"""

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
import html as _html

router = APIRouter()


@router.get(
    "/api/lcsd/dashboard/{lcsdid}",
    include_in_schema=False,
    response_class=HTMLResponse,
)
def dashboard(request: Request, lcsdid: str) -> HTMLResponse:  # noqa: D401
    """Serve the single-page availability dashboard."""
    esc_id = _html.escape(lcsdid)
    html_page = f"""
<!doctype html>
<html lang="zh-Hant">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>LCSD Availability – {esc_id}</title>
<style>
  :root {{ --gap: 1.2rem; }}
  body {{
    font-family: sans-serif;
    margin: var(--gap) auto;
    max-width: 720px;
    padding: 0 var(--gap);
    text-align: center;
    box-sizing: border-box;
  }}
  h1 {{ font-size: 1.8rem; margin-bottom: 0.1rem; }}
  h2 {{ font-size: 1.2rem; margin-top: 0; color:#555; word-break:break-all; }}
  h3 {{ font-size: 1.4rem; margin: var(--gap) 0 .4rem; }}
  #emoji {{ font-size: 5rem; }}
  #forecast h4, #nearest h4 {{ margin: 1.4rem 0 .4rem; }}
  #forecast li, #nearest li {{ text-align:left; }}
  @media (max-width: 480px) {{
    h1 {{ font-size: 1.5rem; }}
    h3 {{ font-size: 1.2rem; }}
    #emoji {{ font-size: 4rem; }}
  }}
</style>
</head>
<body>
<h1 id="title">運動場 (<code>{esc_id}</code>)</h1>
<h2 id="time">現在時間…</h2>
<h3 id="status">讀取中…</h3>
<div id="emoji">⌛</div>
<p id="legend" style="max-width:600px;margin:1rem auto;color:#555"></p>

<!-- ── 4-hour outlook ─────────────────────────────────────────────── -->
<section id="forecast">
  <h4>未來四小時狀態</h4>
  <ol id="forecastList" style="list-style:none;padding-left:0;"></ol>
</section>

<!-- ── nearest facilities (ordered) ───────────────────────────────── -->
<section id="nearest">
  <h4>最近其它運動場狀態</h4>
  <ol id="nearestList" style="list-style:none;padding-left:0;"></ol>
</section>

<script>
const id = "{esc_id}";
let nameMap   = null;     // Map<lcsdid, name>
let rapidData = null;     // full rapid JSON array

function pad(n) {{ return n.toString().padStart(2,"0"); }}
function fmtTime(d) {{ return `${{pad(d.getHours())}}:${{pad(d.getMinutes())}}:${{pad(d.getSeconds())}}`; }}
function fmtDate(d) {{ return `${{d.getFullYear()}}-${{pad(d.getMonth()+1)}}-${{pad(d.getDate())}}`; }}
function fmtDisplayDateTime(d) {{
  return `${{pad(d.getDate())}}/${{pad(d.getMonth()+1)}}/${{d.getFullYear()}} ` +
         `${{pad(d.getHours())}}:${{pad(d.getMinutes())}}:${{pad(d.getSeconds())}}`;
}}
function labelFor(avail) {{
  if (avail === "true")  return "可用 ✅";
  if (avail === "false") return "未能使用 ❌";
  return "未知 ❓";
}}
function bigStatus(avail) {{
  if (avail === "true")  return "可用 正在開放";
  if (avail === "false") return "未能使用";
  return "狀態不明";
}}
function hardTitle(code) {{
  if (code === "1060a") return "將軍澳運動場 (主場)(1060a)";
  if (code === "1060b") return "將軍澳運動場 (副場)(1060b)";
  return null;
}}
function nameFor(code) {{
  const hard = hardTitle(code);
  if (hard) return hard.replace(/\\(.+\\)$/, "");
  return nameMap?.get(code) ?? code;
}}
function titleFor(code) {{
  const hard = hardTitle(code);
  if (hard) return hard;
  return `${{nameFor(code)}} (${{code}})`;
}}

async function fetchRapid() {{
  if (nameMap && rapidData) return;
  const res = await fetch("/api/json?tag=lcsd&secondary_tag=rapid");
  rapidData = await res.json();
  nameMap   = new Map(rapidData.map(r => [r.lcsd_number, r.name]));
}}

async function fetchPointInTime() {{
  try {{
    await fetchRapid();
    document.getElementById("title").textContent = titleFor(id);

    const res = await fetch(`/api/lcsd/availability?lcsdid=${{id}}`);
    if (!res.ok) throw new Error();
    const data = await res.json();

    document.getElementById("status").textContent = bigStatus(data.availability);
    document.getElementById("emoji").textContent =
      data.availability === "true" ? "✔️" :
      data.availability === "false" ? "❌" : "❓";
    document.getElementById("legend").textContent = data.legend || "";
  }} catch {{
    document.getElementById("status").textContent = "無法讀取資料";
    document.getElementById("emoji").textContent  = "❓";
  }}
}}

async function fetchOutlook() {{
  const list = document.getElementById("forecastList");
  const now = new Date();
  const start = new Date(now);
  let end = new Date(now.getTime() + 4*60*60*1000);
  if (end.getMinutes() || end.getSeconds()) end.setHours(end.getHours()+1,0,0,0);
  if (end.getDate() !== start.getDate())    end = new Date(start).setHours(23,59,59,0);
  const period = `${{fmtTime(start)}}-${{fmtTime(new Date(end))}}`;
  const date   = fmtDate(start);

  try {{
    const res = await fetch(`/api/lcsd/availability?lcsdid=${{id}}&date=${{date}}&period=${{encodeURIComponent(period)}}`);
    if (!res.ok) throw new Error();
    const data = await res.json();

    (data.segments||[]).forEach(s => {{
      const li = document.createElement("li");
      li.textContent = `${{s.time_range}} – ${{labelFor(s.availability)}}` +
                       (s.legend ? `(${{s.legend}})` : "");
      list.appendChild(li);
    }});
    if (!list.childElementCount) list.innerHTML = "<li>無法取得資料</li>";
  }} catch {{
    list.innerHTML = "<li>無法取得資料</li>";
  }}
}}

async function fetchNearest() {{
  const list = document.getElementById("nearestList");
  try {{
    await fetchRapid();

    const baseId = (id === "1060a" || id === "1060b") ? "1060" : id;
    const rec = rapidData.find(r => r.lcsd_number === baseId);
    const neighbours = rec?.nearest || [];
    const ordered = [];
    neighbours.forEach(c => c === "1060" ? ordered.push("1060a","1060b") : ordered.push(c));

    if (!ordered.length) {{ list.innerHTML = "<li>無資料</li>"; return; }}

    ordered.forEach(code => {{
      const li = document.createElement("li");
      li.textContent = `${{nameFor(code)}}(${{code}}): 讀取中…`;
      list.appendChild(li);

      fetch(`/api/lcsd/availability?lcsdid=${{code}}`)
        .then(r => r.ok ? r.json() : Promise.reject())
        .then(a => {{
          li.textContent = `${{nameFor(code)}}(${{code}}): ` +
                           `${{labelFor(a.availability)}}` +
                           (a.legend ? `(${{a.legend}})` : "");
        }})
        .catch(() => {{
          li.textContent = `${{nameFor(code)}}(${{code}}) 無法取得資料`;
        }});
    }});
  }} catch {{
    list.innerHTML = "<li>無法取得資料</li>";
  }}
}}

document.addEventListener("DOMContentLoaded", () => {{
  const now = new Date();
  document.getElementById("time").textContent =
    `現在時間是 ${{fmtDisplayDateTime(now)}}`;

  fetchPointInTime();
  fetchOutlook();
  fetchNearest();
}});
</script>
</body>
</html>
"""
    return HTMLResponse(html_page)
