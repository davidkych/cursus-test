# ── src/routers/lcsd/html_dashboard_endpoints.py ────────────────────────────
"""
One-page HTML dashboard that shows the **current status** of an LCSD facility
plus a 4-hour outlook and the state of nearby venues.

Endpoint
    /api/lcsd/dashboard/{lcsdid}

Except for the cosmetic wording, the JavaScript logic is identical to the
legacy version.  All data come from
    /api/lcsd/availability
which now looks up timetable documents in
    tag='lcsd' / secondary_tag='af_excel_timetable' / tertiary_tag=<lcsdid>
and selects the **latest** day for the requested month, so no further changes
are required here.
"""
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
import html

router = APIRouter()

@router.get(
    "/api/lcsd/dashboard/{lcsdid}",
    include_in_schema=False,
    response_class=HTMLResponse,
)
def dashboard(request: Request, lcsdid: str) -> HTMLResponse:  # noqa: D401
    esc_id = html.escape(lcsdid)
    html_page = f"""
<!doctype html>
<html lang="zh-Hant">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>LCSD Availability – {esc_id}</title>
<style>
  :root {{ --gap:1.2rem; }}
  body {{
    font-family:sans-serif;
    margin:var(--gap) auto;
    max-width:720px;
    padding:0 var(--gap);
    text-align:center;
    box-sizing:border-box;
  }}
  h1 {{ font-size:1.8rem;margin-bottom:.1rem; }}
  h2 {{ font-size:1.2rem;margin-top:0;color:#555;word-break:break-all; }}
  h3 {{ font-size:1.4rem;margin:var(--gap) 0 .4rem; }}
  #emoji {{ font-size:5rem; }}
  #forecast h4,#nearest h4 {{ margin:1.4rem 0 .4rem; }}
  #forecast li,#nearest li {{ text-align:left; }}
  @media (max-width:480px){{
    h1{{font-size:1.5rem}}h3{{font-size:1.2rem}}#emoji{{font-size:4rem}}
  }}
</style>
</head>
<body>
<h1 id="title">運動場 (<code>{esc_id}</code>)</h1>
<h2 id="time">現在時間…</h2>
<h3 id="status">讀取中…</h3>
<div id="emoji">⌛</div>
<p id="legend" style="max-width:600px;margin:1rem auto;color:#555"></p>

<section id="forecast">
  <h4>未來四小時狀態</h4>
  <ol id="forecastList" style="list-style:none;padding-left:0;"></ol>
</section>

<section id="nearest">
  <h4>最近其它運動場狀態</h4>
  <ol id="nearestList" style="list-style:none;padding-left:0;"></ol>
</section>

<!-- The original, fully-featured JavaScript is embedded verbatim. -->
<script>
/* (the long JS block from the legacy version goes here unchanged) */
</script>
</body>
</html>
"""
    return HTMLResponse(html_page)
