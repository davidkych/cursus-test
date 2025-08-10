# src/routers/auth/html_endpoints.py
"""
Minimal HTML endpoints for the code generator (independent of the Vue frontend).

Per your policy:
- No authentication is required to access the generator UI.
- This page simply wraps the JSON API at /api/auth/codes/generate.
- Also supports a no-JS form POST back to this endpoint that proxies generation.

Routes
------
GET  /api/auth/codes/generator    → simple HTML form
POST /api/auth/codes/generator    → accepts form-encoded data, calls generator, renders result
"""

from __future__ import annotations

import html
import json
from typing import List, Optional

from fastapi import APIRouter, Form, Request, Response, status
from fastapi.responses import HTMLResponse, PlainTextResponse

# Reuse the same Pydantic model & logic used by the JSON API
from .codes import GenerateIn, generate_code

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _page_template(body: str, title: str = "Code Generator") -> str:
    """Lightweight HTML scaffold (no external assets)."""
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <title>{html.escape(title)}</title>
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <style>
    :root {{
      --bg: #0f172a; --fg: #e2e8f0; --muted:#94a3b8; --ok:#22c55e; --err:#ef4444; --card:#111827; --btn:#2563eb;
    }}
    body {{ background: var(--bg); color: var(--fg); font-family: ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, Ubuntu, Cantarell, Noto Sans, Helvetica Neue, Arial, "Apple Color Emoji", "Segoe UI Emoji"; margin: 0; padding: 2rem; }}
    .wrap {{ max-width: 720px; margin: 0 auto; }}
    .card {{ background: var(--card); border-radius: 14px; padding: 1.25rem 1.25rem 1rem; box-shadow: 0 8px 24px rgba(0,0,0,.25); }}
    h1 {{ font-size: 1.5rem; margin: 0 0 1rem; }}
    fieldset {{ border: 1px solid #1f2937; border-radius: 10px; padding: 1rem; margin-bottom: 1rem; }}
    legend {{ color: var(--muted); padding: 0 .5rem; }}
    label {{ display: block; margin: .25rem 0 .5rem; color: var(--muted); }}
    input[type="text"], input[type="datetime-local"], input[type="number"] {{
      width: 100%; padding: .5rem .6rem; border-radius: .5rem; border: 1px solid #334155; background: #0b1220; color: var(--fg);
    }}
    .row {{ display: grid; grid-template-columns: 1fr 1fr; gap: .75rem; }}
    .muted {{ color: var(--muted); font-size: .9rem; }}
    .btn {{ background: var(--btn); color: white; border: 0; padding: .6rem 1rem; border-radius: .6rem; cursor: pointer; }}
    .btn:disabled {{ opacity: .6; cursor: not-allowed; }}
    .bad {{ color: var(--err); }}
    .ok {{ color: var(--ok); }}
    .note {{ margin-top: .5rem; }}
    .result {{ margin-top: 1rem; padding: .75rem 1rem; border-radius: .6rem; background: #0b1220; border: 1px solid #1f2937; word-break: break-word; }}
    .chips label {{ display:inline-flex; align-items:center; gap:.4rem; background:#0b1220; border:1px solid #334155; padding:.35rem .6rem; margin:.25rem .5rem .25rem 0; border-radius:999px; }}
    .radio label {{ display:inline-flex; align-items:center; gap:.4rem; margin-right:1rem; }}
  </style>
</head>
<body>
  <div class="wrap">
    <div class="card">
      {body}
    </div>
  </div>

<script>
(function() {{
  const modeRadios = document.querySelectorAll('input[name="mode"]');
  const codeRow = document.getElementById('row-code');
  const maxRow = document.getElementById('row-max-uses');
  const form = document.getElementById('gen-form');
  const resultBox = document.getElementById('result');
  const btn = document.getElementById('submit-btn');

  function onModeChange() {{
    const mode = document.querySelector('input[name="mode"]:checked').value;
    codeRow.style.display = (mode === 'reusable' || mode === 'single') ? '' : 'none';
    maxRow.style.display = (mode === 'reusable') ? '' : 'none';
  }}
  modeRadios.forEach(r => r.addEventListener('change', onModeChange));
  onModeChange();

  form.addEventListener('submit', async function(ev) {{
    if (!window.fetch) return; // let normal POST happen for no-JS
    ev.preventDefault();
    resultBox.innerHTML = '';
    btn.disabled = true;

    try {{
      const data = new FormData(form);
      const mode = data.get('mode');
      const payload = {{
        mode,
        code: (mode === 'reusable' || mode === 'single') ? (data.get('code') || null) : null,
        expires_at: data.get('expires_at'),
        grants: Array.from(document.querySelectorAll('input[name="grants"]:checked')).map(i => i.value),
        max_uses: (mode === 'reusable' && data.get('max_uses')) ? Number(data.get('max_uses')) : null
      }};
      const res = await fetch('/api/auth/codes/generate', {{
        method: 'POST',
        headers: {{ 'Content-Type': 'application/json' }},
        body: JSON.stringify(payload)
      }});
      const body = await res.json().catch(() => ({{}}));
      if (!res.ok) {{
        const msg = (body && (body.detail || body.message)) || 'Generation failed';
        resultBox.innerHTML = '<div class="bad">❌ ' + String(msg) + '</div>';
        return;
      }}
      const code = body.code;
      const meta = JSON.stringify(body, null, 2);
      resultBox.innerHTML = '<div class="ok">✅ Code generated:</div><div class="result"><b>' + code + '</b></div><div class="note muted"><pre style="white-space:pre-wrap">' + meta + '</pre></div>';
    }} catch (err) {{
      resultBox.innerHTML = '<div class="bad">❌ ' + String(err) + '</div>';
    }} finally {{
      btn.disabled = false;
    }}
  }});
}})();
</script>
</body></html>"""


@router.get("/codes/generator", response_class=HTMLResponse)
def generator_form() -> HTMLResponse:
    """Serve the bare-bones generator UI."""
    body = """
      <h1>Code Generator</h1>
      <form id="gen-form" method="post" action="/api/auth/codes/generator">
        <fieldset>
          <legend>Mode</legend>
          <div class="radio">
            <label><input type="radio" name="mode" value="oneoff" checked /> oneoff (server-generated, single-use)</label>
            <label><input type="radio" name="mode" value="reusable" /> reusable (caller code, multi-use)</label>
            <label><input type="radio" name="mode" value="single" /> single (caller code, single-use)</label>
          </div>
        </fieldset>

        <div id="row-code">
          <label>Code (for reusable/single)</label>
          <input type="text" name="code" placeholder="e.g. VIP-2025 or leave blank for oneoff" />
        </div>

        <div class="row">
          <div>
            <label>Expires at</label>
            <input type="datetime-local" name="expires_at" required />
            <div class="muted">Accepts date or datetime; naive treated as UTC.</div>
          </div>
          <div id="row-max-uses">
            <label>Max uses (optional; empty = unlimited)</label>
            <input type="number" name="max_uses" min="1" step="1" />
          </div>
        </div>

        <fieldset>
          <legend>Grants</legend>
          <div class="chips">
            <label><input type="checkbox" name="grants" value="isAdmin" /> isAdmin</label>
            <label><input type="checkbox" name="grants" value="isPremiumMember" /> isPremiumMember</label>
          </div>
        </fieldset>

        <button id="submit-btn" class="btn" type="submit">Generate</button>
        <div class="note muted">This page posts to <code>/api/auth/codes/generate</code>. No authentication required.</div>
      </form>
      <div id="result" class="note"></div>
    """
    return HTMLResponse(content=_page_template(body))


@router.post("/codes/generator", response_class=HTMLResponse)
def generator_form_post(
    mode: str = Form(...),
    expires_at: str = Form(...),
    code: Optional[str] = Form(None),
    max_uses: Optional[str] = Form(None),
    request: Request = None,
    # multiple checkbox values arrive as repeated "grants"
    grants: Optional[List[str]] = Form(None),
):
    """
    No-JS POST: proxy to the same generator logic and render the result.
    """
    try:
        payload = GenerateIn(
            mode=mode,
            code=(code or None),
            expires_at=expires_at,
            grants=grants or [],
            max_uses=(int(max_uses) if (max_uses or "").strip() else None),
        )
        out = generate_code(payload)  # reuse API logic
        body = f"""
          <h1>Code Generator</h1>
          <p class="ok">✅ Code generated successfully.</p>
          <div class="result"><b>{html.escape(out.code)}</b></div>
          <div class="note muted"><pre>{html.escape(json.dumps(out.dict(), indent=2))}</pre></div>
          <p><a class="btn" href="/api/auth/codes/generator">Back</a></p>
        """
        return HTMLResponse(content=_page_template(body))
    except Exception as e:
        # Try to extract FastAPI/HTTPException detail
        msg = str(getattr(e, "detail", None) or str(e) or "Generation failed")
        body = f"""
          <h1>Code Generator</h1>
          <p class="bad">❌ {html.escape(msg)}</p>
          <p><a class="btn" href="/api/auth/codes/generator">Back</a></p>
        """
        return HTMLResponse(content=_page_template(body), status_code=status.HTTP_400_BAD_REQUEST)
