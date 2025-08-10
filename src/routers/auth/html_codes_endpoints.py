# ── src/routers/auth/html_codes_endpoints.py ─────────────────────────────────
from __future__ import annotations

import datetime as _dt
import json as _json
import os
import secrets
import string
from typing import List

from fastapi import APIRouter, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, PlainTextResponse, RedirectResponse

from azure.cosmos import CosmosClient, exceptions
from azure.identity import DefaultAzureCredential

# Reuse the same function allowlist used by the JSON generator/redeemer
try:
    from .codes_generate import CODE_FUNCTION_MAP  # type: ignore
except Exception:
    # Fallback to defaults if import fails for any reason
    CODE_FUNCTION_MAP = {"isAdmin": "is_admin", "IsPremiumMember": "is_premium_member"}

# ───────────────────────── Cosmos setup ──────────────────────────
_cosmos_endpoint   = os.environ["COSMOS_ENDPOINT"]
_database_name     = os.getenv("COSMOS_DATABASE")
_codes_container   = os.getenv("CODES_CONTAINER", "codes")

_client = CosmosClient(_cosmos_endpoint, credential=DefaultAzureCredential())
_codes  = _client.get_database_client(_database_name).get_container_client(_codes_container)

# ───────────────────────── helpers ───────────────────────────────
def _now_utc():
    return _dt.datetime.utcnow().replace(microsecond=0)

def _iso_z(dt: _dt.datetime) -> str:
    return dt.replace(microsecond=0).isoformat() + "Z"

def _parse_expiry_utc(iso: str) -> _dt.datetime:
    if not isinstance(iso, str) or not iso.endswith("Z"):
        raise ValueError("expires_utc must end with 'Z' (UTC)")
    return _dt.datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone(_dt.timezone.utc).replace(tzinfo=None)

_ALNUM_UPPER = string.ascii_uppercase + string.digits
def _rand_code(n: int = 20) -> str:
    return "".join(secrets.choice(_ALNUM_UPPER) for _ in range(n))

# ───────────────────────── router ────────────────────────────────
router = APIRouter(prefix="/api/auth", tags=["auth"], include_in_schema=False)

# Shared minimal CSS
_BASE_CSS = """
<style>
 body{font-family:system-ui,-apple-system,Segoe UI,Roboto,Arial,sans-serif;margin:2rem;color:#111}
 .wrap{max-width:820px;margin:0 auto}
 h1{font-size:1.4rem;margin-bottom:.75rem}
 form{border:1px solid #ddd;padding:1rem;border-radius:.5rem;background:#fafafa}
 label{display:block;margin:.5rem 0 .25rem;font-weight:600}
 input[type=text],select{width:100%;padding:.5rem;border:1px solid #ccc;border-radius:.375rem}
 .row{display:grid;grid-template-columns:1fr 1fr;gap:1rem}
 .hint{font-size:.85rem;color:#555}
 .btn{display:inline-block;margin-top:1rem;background:#2563eb;color:#fff;border:none;padding:.5rem .9rem;border-radius:.375rem;cursor:pointer}
 .ok{padding:.75rem;border:1px solid #16a34a;background:#ecfdf5;color:#065f46;border-radius:.375rem;margin:.75rem 0}
 .err{padding:.75rem;border:1px solid #dc2626;background:#fef2f2;color:#7f1d1d;border-radius:.375rem;margin:.75rem 0}
 .small{font-size:.85rem;color:#444}
 .fn-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:.5rem}
 .checkbox{display:flex;align-items:center;gap:.5rem;border:1px solid #ddd;padding:.5rem;border-radius:.375rem;background:#fff}
 .footer{margin-top:1rem;color:#666;font-size:.85rem}
 .code{font-family:ui-monospace,SFMono-Regular,Menlo,monospace}
</style>
"""

# ───────────────────────── GET: render generate form ─────────────
@router.get("/code/generate-form", response_class=HTMLResponse)
def get_code_form():
    fn_options = "".join(
        f'<div class="checkbox"><input type="checkbox" name="functions" value="{k}" id="fn_{k}">'
        f'<label for="fn_{k}">{k} <span class="small">→ {v}</span></label></div>'
        for k, v in CODE_FUNCTION_MAP.items()
    )
    html = f"""
{_BASE_CSS}
<div class="wrap">
  <h1>Public Code Generator</h1>
  <p class="small">No auth required. Generates codes directly into the backend. Functions are allow-listed on the server.</p>

  <form method="post" action="./generate-form">
    <label for="mode">Mode</label>
    <select name="mode" id="mode" required>
      <option value="one_off">one_off (server random; single global use)</option>
      <option value="reusable">reusable (caller code; multiple users, once per user)</option>
      <option value="single_use">single_use (caller code; single global use)</option>
    </select>

    <div class="row">
      <div>
        <label for="expires_utc">Expiry (UTC, ISO-8601 with Z)</label>
        <input type="text" id="expires_utc" name="expires_utc" placeholder="2025-12-31T23:59:59Z" required />
        <div class="hint">Must be in the future. Example: <span class="code">{_iso_z(_now_utc() + _dt.timedelta(days=30))}</span></div>
      </div>
      <div>
        <label for="code">Code (uppercase A-Z 0-9)</label>
        <input type="text" id="code" name="code" placeholder="(leave blank for one_off)" />
        <div class="hint">Required for reusable / single_use; ignored for one_off.</div>
      </div>
    </div>

    <label>Functions to grant on redemption</label>
    <div class="fn-grid">
      {fn_options}
    </div>

    <button class="btn" type="submit">Generate</button>
  </form>

  <p class="footer">Redemption endpoint (JSON): <span class="code">POST /api/auth/code/redeem</span></p>
</div>
    """
    return HTMLResponse(content=html)

# ───────────────────────── POST: handle generation ───────────────
@router.post("/code/generate-form", response_class=HTMLResponse)
def post_code_form(
    mode: str = Form(...),
    expires_utc: str = Form(...),
    code: str = Form(""),
    functions: List[str] = Form(default=[]),
):
    # Basic validation mirroring JSON API (kept minimal here)
    mode = (mode or "").strip()
    if mode not in ("one_off", "reusable", "single_use"):
        return _render_error("Invalid mode")

    try:
        expiry_dt = _parse_expiry_utc(expires_utc)
        if expiry_dt <= _now_utc():
            return _render_error("Expiry must be in the future")
    except Exception as e:
        return _render_error(f"Invalid expiry: {e}")

    funcs = [f for f in (functions or []) if f in CODE_FUNCTION_MAP]
    if not funcs:
        return _render_error("Pick at least one supported function")

    if mode == "one_off":
        # allocate random, retry on rare collision
        final_code = None
        for _ in range(5):
            try_code = _rand_code(20)
            doc = _build_doc(try_code, mode, funcs, expiry_dt)
            try:
                _codes.create_item(doc)
                final_code = try_code
                break
            except exceptions.CosmosResourceExistsError:
                continue
        if not final_code:
            return _render_error("Could not allocate a unique code; please try again.")
    else:
        code = (code or "").strip().upper()
        if not code or any(ch not in _ALNUM_UPPER for ch in code):
            return _render_error("Provided code must be uppercase letters/digits only")
        doc = _build_doc(code, mode, funcs, expiry_dt)
        try:
            _codes.create_item(doc)
        except exceptions.CosmosResourceExistsError:
            return _render_error("This code already exists. Pick another.")
        final_code = code

    return _render_ok(final_code, mode, funcs, expiry_dt)

# ───────────────────────── small render helpers ──────────────────
def _render_ok(code: str, mode: str, funcs: List[str], expiry_dt: _dt.datetime) -> HTMLResponse:
    fns = ", ".join(funcs)
    html = f"""
{_BASE_CSS}
<div class="wrap">
  <h1>Code generated ✅</h1>
  <div class="ok">
    <div><strong>Code:</strong> <span class="code">{code}</span></div>
    <div><strong>Mode:</strong> {mode}</div>
    <div><strong>Functions:</strong> {fns}</div>
    <div><strong>Expires:</strong> {_iso_z(expiry_dt)}</div>
  </div>
  <p><a class="btn" href="./generate-form">Generate another</a></p>
  <p class="footer">Users can redeem at <span class="code">POST /api/auth/code/redeem</span> with their bearer token.</p>
</div>
    """
    return HTMLResponse(content=html)

def _render_error(msg: str) -> HTMLResponse:
    html = f"""
{_BASE_CSS}
<div class="wrap">
  <h1>Code generator</h1>
  <div class="err">{msg}</div>
  <p><a class="btn" href="./generate-form">Back</a></p>
</div>
    """
    return HTMLResponse(content=html)

# ───────────────────────── doc builder ───────────────────────────
def _build_doc(code: str, mode: str, functions: List[str], expiry_dt: _dt.datetime) -> dict:
    doc = {
        "id": code,
        "code": code,
        "mode": mode,
        "functions": list(functions),
        "expires_utc": _iso_z(expiry_dt),
        "created_utc": _iso_z(_now_utc()),
        "generated_by": "html",
    }
    if mode in ("one_off", "single_use"):
        doc.update({"consumed": False, "consumed_by": None, "consumed_utc": None})
    return doc
