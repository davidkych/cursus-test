# ── src/routers/auth/html_codegen.py ──────────────────────────────────────────
"""
Lightweight HTML form for creating redemption codes (independent of the SPA).
Per requirements, this endpoint is OPEN (no admin/auth required).

- GET  /api/auth/codes/form   → render HTML form
- POST /api/auth/codes/form   → create codes and show results

This reuses the JSON creation logic from codes.py to avoid duplication.
"""

from fastapi import APIRouter, Request, status
from fastapi.responses import HTMLResponse
from typing import List, Dict, Any

# Reuse models/handler from codes.py to keep logic in one place
from .codes import CodeCreateIn, create_codes  # noqa: F401
from .common import FUNCTION_KEYS

router = APIRouter(
    prefix="/api/auth",
    tags=["auth"]
)

_FORM_HTML = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8"/>
  <title>Code Generator</title>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <style>
    body { font-family: system-ui, -apple-system, Segoe UI, Roboto, Ubuntu, Cantarell, 'Helvetica Neue', Arial, 'Noto Sans', 'Apple Color Emoji', 'Segoe UI Emoji', 'Noto Color Emoji'; margin: 2rem; color: #111; background: #fafafa; }
    h1 { margin-bottom: 0.25rem; }
    .subtle { color: #555; margin-top: 0; }
    form { background: #fff; border: 1px solid #e5e7eb; border-radius: 10px; padding: 1rem; max-width: 720px; }
    fieldset { border: 0; padding: 0; margin: 0 0 1rem 0; display: grid; grid-template-columns: 1fr 1fr; gap: 0.75rem 1rem; }
    label { font-size: 0.9rem; color: #374151; display: block; margin-bottom: 0.25rem; }
    input, select { width: 100%; padding: 0.5rem 0.6rem; border: 1px solid #cbd5e1; border-radius: 8px; background: #fff; }
    .row { grid-column: span 2; }
    .hint { font-size: 0.8rem; color: #6b7280; }
    button { background: #111827; color: #fff; border: 0; border-radius: 999px; padding: 0.6rem 1rem; cursor: pointer; }
    button:disabled { background: #9ca3af; cursor: not-allowed; }
    table { border-collapse: collapse; margin-top: 1rem; width: 100%; max-width: 720px; background: #fff; border: 1px solid #e5e7eb; border-radius: 10px; overflow: hidden; }
    th, td { padding: 0.6rem 0.8rem; border-bottom: 1px solid #f1f5f9; text-align: left; font-size: 0.9rem; }
    th { background: #f8fafc; color: #111827; }
    .copy { font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, 'Liberation Mono', monospace; background: #f8fafc; padding: 0.2rem 0.35rem; border-radius: 6px; }
    .notice { margin: 1rem 0; color: #374151; }
  </style>
</head>
<body>
  <h1>Code Generator</h1>
  <p class="subtle">OPEN endpoint. Create redemption codes without the SPA.</p>

  <form method="post" action="/api/auth/codes/form">
    <fieldset>
      <div>
        <label for="mode">Mode</label>
        <select id="mode" name="mode" required>
          <option value="oneoff">oneoff (system 20-char, single use)</option>
          <option value="single">single (custom code, single use)</option>
          <option value="reusable">reusable (custom code, multi-user)</option>
        </select>
      </div>

      <div>
        <label for="function">Function</label>
        <select id="function" name="function" required>
          {function_options}
        </select>
      </div>

      <div class="row">
        <label for="expiresAt">Expiry</label>
        <input type="text" id="expiresAt" name="expiresAt" placeholder="YYYY-MM-DD or ISO-8601 (UTC)" required />
        <div class="hint">Dates are treated as 23:59:59Z.</div>
      </div>

      <div class="row">
        <label for="code">Code (required for single/reusable; leave blank for oneoff)</label>
        <input type="text" id="code" name="code" placeholder="VIP2025 or leave blank for oneoff" />
      </div>

      <div class="row">
        <label for="count">Count (for oneoff batches; 1–1000)</label>
        <input type="number" id="count" name="count" min="1" max="1000" value="1" />
      </div>
    </fieldset>

    <button type="submit">Create</button>
  </form>

  {results}

  <p class="notice">Tip: This page also honours an Authorization: Bearer header if present, and records the username in metadata — but it is <strong>not required</strong>.</p>
</body>
</html>
"""

def _render(select_options: List[str], results_html: str = "") -> HTMLResponse:
    html = _FORM_HTML.format(
        function_options="\n".join(select_options),
        results=results_html or "",
    )
    return HTMLResponse(content=html)

def _make_options() -> List[str]:
    opts = []
    for k in sorted(FUNCTION_KEYS):
        opts.append(f'<option value="{k}">{k}</option>')
    return opts

def _results_table(items: List[Dict[str, Any]]) -> str:
    if not items:
        return ""
    rows = []
    for it in items:
        rows.append(
            f"<tr><td><span class='copy'>{it.get('code','')}</span></td>"
            f"<td>{it.get('mode','')}</td>"
            f"<td>{it.get('function','')}</td>"
            f"<td>{it.get('expiresAt','')}</td></tr>"
        )
    return f"""
    <table aria-label="Created codes">
      <thead>
        <tr><th>Code</th><th>Mode</th><th>Function</th><th>Expires</th></tr>
      </thead>
      <tbody>
        {''.join(rows)}
      </tbody>
    </table>
    """

@router.get("/codes/form", response_class=HTMLResponse)
async def get_form():
    """Render the HTML form."""
    return _render(_make_options())

@router.post("/codes/form", response_class=HTMLResponse, status_code=status.HTTP_201_CREATED)
async def post_form(request: Request):
    """
    Handle HTML form submission.
    Converts form fields to CodeCreateIn and delegates to create_codes.
    """
    form = await request.form()
    mode = (form.get("mode") or "").strip()
    function = (form.get("function") or "").strip()
    expiresAt = (form.get("expiresAt") or "").strip()
    code = (form.get("code") or "").strip() or None
    count_raw = (form.get("count") or "").strip()
    try:
        count = int(count_raw) if count_raw else 1
    except ValueError:
        count = 1

    payload = CodeCreateIn(mode=mode, function=function, expiresAt=expiresAt, code=code, count=count)

    # Delegate to JSON creator to centralize validation + creation
    try:
        created = await create_codes(payload, request)  # may return single dict or list
        items = created if isinstance(created, list) else [created]
        results_html = _results_table(items)
        return _render(_make_options(), results_html)
    except Exception as e:
        # Render the error inline
        err = str(e)
        err_html = f"<p class='notice' style='color:#b91c1c'>Error: {err}</p>"
        return _render(_make_options(), err_html)
