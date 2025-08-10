# ── src/routers/auth/html_codegen.py ──────────────────────────────────────────
from __future__ import annotations

import datetime as _dt
import os
import re
import secrets
from typing import Optional, Literal

from fastapi import APIRouter, HTTPException, Form, status
from fastapi.responses import HTMLResponse
from azure.cosmos import CosmosClient, exceptions
from azure.identity import DefaultAzureCredential


# ───────────────────────── Cosmos setup ──────────────────────────
_cosmos_endpoint = os.environ["COSMOS_ENDPOINT"]
_database_name   = os.getenv("COSMOS_DATABASE")
_codes_container = os.getenv("CODES_CONTAINER", "codes")

_client = CosmosClient(
    _cosmos_endpoint,
    credential=DefaultAzureCredential()
)
_codes = _client.get_database_client(_database_name).get_container_client(_codes_container)

# ───────────────────────── constants / helpers ───────────────────
# Unambiguous uppercase + digits (omit 0/O and 1/I)
_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
_CODE_RE  = re.compile(r"^[A-Z0-9]{6,64}$")

Mode = Literal["oneoff", "reusable", "single"]
Func = Literal["is_admin", "is_premium"]


def _now_utc() -> _dt.datetime:
    return _dt.datetime.utcnow().replace(microsecond=0)


def _to_iso_z(dt: _dt.datetime) -> str:
    return dt.replace(microsecond=0).isoformat() + "Z"


def _gen_code(n: int = 20) -> str:
    return "".join(secrets.choice(_ALPHABET) for _ in range(n))


def _normalize_and_validate_code(s: Optional[str]) -> str:
    s = (s or "").strip().upper()
    if not s:
        raise HTTPException(status_code=422, detail="Code is required for this mode")
    if not _CODE_RE.fullmatch(s):
        raise HTTPException(status_code=422, detail="Code must be 6-64 chars [A–Z0–9]")
    return s


def _parse_expiry_utc(s: str) -> _dt.datetime:
    """
    Accepts common forms:
    - 'YYYY-MM-DDTHH:MM'                (from <input type="datetime-local">; treated as UTC)
    - 'YYYY-MM-DDTHH:MM:SS'
    - 'YYYY-MM-DDTHH:MM:SSZ' or with offset; converted to UTC
    Returns a naive UTC datetime (no tzinfo).
    """
    raw = (s or "").strip()
    if not raw:
        raise HTTPException(status_code=422, detail="expiry_utc is required")

    # Normalize trailing Z
    if raw.endswith("Z") or raw.endswith("z"):
        raw = raw[:-1]

    # Fill seconds if missing (common from datetime-local)
    if len(raw) == 16:  # YYYY-MM-DDTHH:MM
        raw = raw + ":00"

    try:
        dt = _dt.datetime.fromisoformat(raw)
    except ValueError:
        raise HTTPException(status_code=422, detail="expiry_utc must be ISO-8601")

    # If timezone-aware, convert to UTC then drop tzinfo
    if dt.tzinfo is not None:
        dt = dt.astimezone(_dt.timezone.utc).replace(tzinfo=None)

    return dt


def _ensure_future_and_ttl(expiry_utc_naive: _dt.datetime) -> int:
    now = _now_utc()
    ttl = int((expiry_utc_naive - now).total_seconds())
    if ttl <= 0:
        raise HTTPException(status_code=422, detail="expiry_utc must be in the future (UTC)")
    return ttl


def _code_exists(code: str) -> bool:
    try:
        _codes.read_item(item=code, partition_key=code)
        return True
    except exceptions.CosmosResourceNotFoundError:
        return False


def _page(title: str, body_html: str, status_code: int = 200) -> HTMLResponse:
    html = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>{title}</title>
<style>
  :root {{ color-scheme: light dark; }}
  body {{ font-family: system-ui, -apple-system, Segoe UI, Roboto, Helvetica, Arial, sans-serif;
          margin: 2rem; line-height: 1.5; }}
  .card {{ max-width: 720px; border: 1px solid #ccc; border-radius: 12px; padding: 1.25rem; }}
  label {{ display:block; margin-top: .75rem; font-weight: 600; }}
  input, select {{ padding: .5rem; width: 100%; max-width: 30rem; }}
  .row {{ margin: .5rem 0; }}
  .hint {{ font-size: .875rem; opacity: .75; }}
  .btn {{ display:inline-block; padding:.5rem .9rem; border-radius:8px; border:1px solid #888; cursor:pointer; }}
  .btn-primary {{ background:#2563eb; color:#fff; border-color:#2563eb; }}
  .muted {{ opacity: .8; }}
  .ok {{ color: #15803d; }}
  .err {{ color: #b91c1c; }}
  code {{ font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, "Liberation Mono", monospace; }}
</style>
<script>
  function onModeChange() {{
    const mode = document.getElementById('mode').value;
    const codeRow = document.getElementById('code-row');
    codeRow.style.display = (mode === 'reusable' || mode === 'single') ? 'block' : 'none';
  }}
  window.addEventListener('DOMContentLoaded', onModeChange);
</script>
</head>
<body>
  <div class="card">
    {body_html}
  </div>
</body>
</html>"""
    return HTMLResponse(content=html, status_code=status_code)


# ──────────────────────────── Router ────────────────────────────
router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.get("/codegen/ui", response_class=HTMLResponse)
def codegen_form():
    """Minimal HTML UI for code generation (no auth gate)."""
    default_expiry = (_now_utc() + _dt.timedelta(days=30)).strftime("%Y-%m-%dT%H:%M")
    body = f"""
    <h1>Code Generator</h1>
    <p class="muted">Utility form (independent of the SPA). Anyone who knows this URL can create codes.</p>

    <form method="post" action="/api/auth/codegen/ui">
      <div class="row">
        <label for="mode">Mode</label>
        <select id="mode" name="mode" onchange="onModeChange()">
          <option value="oneoff">oneoff (server-generated, single-use)</option>
          <option value="reusable">reusable (client code; one redemption per user)</option>
          <option value="single">single (client code; single-use)</option>
        </select>
        <div class="hint">Choose how the code behaves.</div>
      </div>

      <div class="row" id="code-row" style="display:none">
        <label for="code">Intended code (A–Z, 0–9; 6–64 chars)</label>
        <input id="code" name="code" placeholder="e.g. PREMIUM2025" />
        <div class="hint">Only required for reusable / single modes.</div>
      </div>

      <div class="row">
        <label for="function">Function</label>
        <select id="function" name="function">
          <option value="is_admin">is_admin → set user.is_admin = true</option>
          <option value="is_premium">is_premium → set user.is_premium = true</option>
        </select>
      </div>

      <div class="row">
        <label for="expiry_utc">Expiry (UTC)</label>
        <input id="expiry_utc" name="expiry_utc" type="datetime-local" value="{default_expiry}" />
        <div class="hint">Time is treated as UTC. TTL auto-purges expired codes.</div>
      </div>

      <div class="row" style="margin-top:1rem;">
        <button class="btn btn-primary" type="submit">Generate</button>
      </div>
    </form>
    """
    return _page("Code Generator", body)


@router.post("/codegen/ui", response_class=HTMLResponse)
def codegen_submit(
    mode: Mode = Form(...),
    function: Func = Form(...),
    expiry_utc: str = Form(...),
    code: Optional[str] = Form(None),
):
    """Process form submission and render result."""
    # 1) Parse & validate expiry → ttl
    expiry_dt = _parse_expiry_utc(expiry_utc)
    ttl = _ensure_future_and_ttl(expiry_dt)
    expiry_iso = _to_iso_z(expiry_dt)

    # 2) Resolve code
    if mode == "oneoff":
        resolved_code = _gen_code(20)
    else:
        resolved_code = _normalize_and_validate_code(code)

    # 3) Ensure uniqueness when client supplied
    if mode in ("reusable", "single") and _code_exists(resolved_code):
        return _page(
            "Code Generator – Error",
            f"<h1 class='err'>Conflict</h1><p>Code <code>{resolved_code}</code> already exists.</p>"
            "<p><a class='btn' href='/api/auth/codegen/ui'>Back</a></p>",
            status_code=status.HTTP_409_CONFLICT,
        )

    # 4) Build document
    created_iso = _to_iso_z(_now_utc())
    doc = {
        "id":           resolved_code,
        "mode":         mode,
        "function":     function,
        "created_utc":  created_iso,
        "expiry_utc":   expiry_iso,
        "ttl":          ttl,
        "redemptions":  [],
    }
    if mode in ("oneoff", "single"):
        doc.update({
            "consumed":     False,
            "consumed_by":  None,
            "consumed_utc": None,
        })

    # 5) Persist (create only; for oneoff regenerate once on rare collision)
    try:
        _codes.create_item(body=doc)
    except exceptions.CosmosResourceExistsError:
        if mode == "oneoff":
            # Try a second random code
            second = _gen_code(20)
            doc["id"] = second
            try:
                _codes.create_item(body=doc)
                resolved_code = second
            except exceptions.CosmosResourceExistsError:
                return _page(
                    "Code Generator – Error",
                    "<h1 class='err'>Service unavailable</h1><p>Please try again.</p>"
                    "<p><a class='btn' href='/api/auth/codegen/ui'>Back</a></p>",
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                )
        else:
            return _page(
                "Code Generator – Error",
                f"<h1 class='err'>Conflict</h1><p>Code <code>{resolved_code}</code> already exists.</p>"
                "<p><a class='btn' href='/api/auth/codegen/ui'>Back</a></p>",
                status_code=status.HTTP_409_CONFLICT,
            )

    # 6) Render success
    success = f"""
    <h1 class="ok">Code created</h1>
    <p><strong>Code:</strong> <code>{resolved_code}</code></p>
    <ul>
      <li><strong>Mode:</strong> {mode}</li>
      <li><strong>Function:</strong> {function}</li>
      <li><strong>Expiry (UTC):</strong> {expiry_iso}</li>
      <li><strong>Created:</strong> {created_iso}</li>
    </ul>
    <p><a class="btn" href="/api/auth/codegen/ui">Create another</a></p>
    """
    return _page("Code Generator – Success", success, status_code=status.HTTP_201_CREATED)
