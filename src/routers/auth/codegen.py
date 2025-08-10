# ── src/routers/auth/codegen.py ───────────────────────────────────────────────
from __future__ import annotations

import datetime as _dt
import os
import re
import secrets
from typing import Literal, Optional

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
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
_CODE_MIN = 6
_CODE_MAX = 64

def _now_utc() -> _dt.datetime:
    return _dt.datetime.utcnow().replace(microsecond=0)

def _to_iso_z(dt: _dt.datetime) -> str:
    # return ISO string with trailing 'Z'
    return dt.replace(microsecond=0).isoformat() + "Z"

def _gen_code(n: int = 20) -> str:
    return "".join(secrets.choice(_ALPHABET) for _ in range(n))

_CODE_RE = re.compile(r"^[A-Z0-9]{6,64}$")

def _normalize_and_validate_code(s: str) -> str:
    if not s:
        raise HTTPException(status_code=422, detail="code is required for this mode")
    s_up = s.upper().strip()
    if not _CODE_RE.fullmatch(s_up):
        raise HTTPException(
            status_code=422,
            detail=f"code must be {_CODE_MIN}-{_CODE_MAX} characters [A–Z0–9]",
        )
    return s_up

def _ensure_future_expiry(expiry_utc: _dt.datetime) -> int:
    now = _now_utc()
    if expiry_utc.tzinfo is not None:
        # Normalize timezone-aware inputs to naive UTC for consistency
        expiry_utc = expiry_utc.astimezone(_dt.timezone.utc).replace(tzinfo=None)
    ttl = int((expiry_utc - now).total_seconds())
    if ttl <= 0:
        raise HTTPException(status_code=422, detail="expiry_utc must be in the future (UTC)")
    return ttl

def _code_exists(code: str) -> bool:
    try:
        _codes.read_item(item=code, partition_key=code)
        return True
    except exceptions.CosmosResourceNotFoundError:
        return False


# ───────────────────────── Pydantic models ───────────────────────
Mode = Literal["oneoff", "reusable", "single"]
Func = Literal["is_admin", "is_premium"]

class CodeGenIn(BaseModel):
    mode: Mode = Field(..., description="oneoff | reusable | single")
    function: Func = Field(..., description="is_admin | is_premium")
    expiry_utc: _dt.datetime = Field(..., description="UTC ISO-8601, e.g. 2025-12-31T23:59:59Z")
    code: Optional[str] = Field(None, description="Required for reusable/single; ignored for oneoff")

class CodeGenOut(BaseModel):
    code: str
    mode: Mode
    function: Func
    expiry_utc: str


# ──────────────────────────── Router ────────────────────────────
router = APIRouter(
    prefix="/api/auth",
    tags=["auth"]
)

@router.post("/codegen", response_model=CodeGenOut, status_code=status.HTTP_201_CREATED)
def generate_code(payload: CodeGenIn):
    """
    Create a code document in the 'codes' container.

    Modes:
      - oneoff  : server generates a 20-char code; global single-use
      - reusable: client provides code; one redemption per user; multi-user until expiry
      - single  : client provides code; global single-use

    Anyone can call this endpoint (no admin gate), per requirements.
    """
    # Validate expiry and compute TTL (for Cosmos auto-purge)
    ttl_seconds = _ensure_future_expiry(payload.expiry_utc)
    expiry_iso  = _to_iso_z(
        payload.expiry_utc.astimezone(_dt.timezone.utc).replace(tzinfo=None)
        if payload.expiry_utc.tzinfo is not None else payload.expiry_utc
    )
    created_iso = _to_iso_z(_now_utc())

    # Resolve code string
    if payload.mode == "oneoff":
        code = _gen_code(20)
    else:
        code = _normalize_and_validate_code(payload.code or "")

    # For provided codes, ensure uniqueness
    if payload.mode in ("reusable", "single") and _code_exists(code):
        raise HTTPException(status_code=409, detail="code already exists")

    # Build document
    doc = {
        "id":           code,
        "mode":         payload.mode,
        "function":     payload.function,
        "created_utc":  created_iso,
        "expiry_utc":   expiry_iso,
        "ttl":          ttl_seconds,         # item-level TTL (seconds from now)
        "redemptions":  [],                  # audit trail for ALL modes
    }

    if payload.mode in ("oneoff", "single"):
        # global single-use flags
        doc.update({
            "consumed":     False,
            "consumed_by":  None,
            "consumed_utc": None,
        })

    # Persist (create only)
    try:
        _codes.create_item(body=doc)
    except exceptions.CosmosResourceExistsError:
        # Defensive: should not happen for oneoff, but in case of rare collision regenerate once
        if payload.mode == "oneoff":
            code2 = _gen_code(20)
            doc["id"] = code2
            try:
                _codes.create_item(body=doc)
                code = code2
            except exceptions.CosmosResourceExistsError:
                # Give up cleanly
