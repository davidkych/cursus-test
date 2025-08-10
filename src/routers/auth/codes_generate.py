# ── src/routers/auth/codes_generate.py ───────────────────────────────────────
from __future__ import annotations

import datetime as _dt
import json as _json
import os
import re
import secrets
import string
from typing import List, Literal, Optional

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, Field, validator

from azure.cosmos import CosmosClient, exceptions
from azure.identity import DefaultAzureCredential

# ───────────────────────── Cosmos setup ──────────────────────────
_cosmos_endpoint   = os.environ["COSMOS_ENDPOINT"]
_database_name     = os.getenv("COSMOS_DATABASE")
_codes_container   = os.getenv("CODES_CONTAINER", "codes")

_client = CosmosClient(_cosmos_endpoint, credential=DefaultAzureCredential())
_codes  = _client.get_database_client(_database_name).get_container_client(_codes_container)

# ───────────────────────── Function map (server-allowlist) ──────
# Env var CODE_FUNCTION_MAP can override/extend defaults; keys are the external
# function names users request; values are the internal user-doc fields to set.
_DEFAULT_MAP = {"isAdmin": "is_admin", "IsPremiumMember": "is_premium_member"}
try:
    _env_map = _json.loads(os.getenv("CODE_FUNCTION_MAP", "") or "{}")
    if not isinstance(_env_map, dict):
        _env_map = {}
except Exception:
    _env_map = {}
CODE_FUNCTION_MAP = {**_DEFAULT_MAP, **_env_map}

# ───────────────────────── Helpers ──────────────────────────────
_ALNUM_UPPER = string.ascii_uppercase + string.digits
_CODE_RE = re.compile(r"^[A-Z0-9]+$")

def _now_utc() -> _dt.datetime:
    return _dt.datetime.utcnow().replace(microsecond=0)

def _parse_expiry_utc(iso: str) -> _dt.datetime:
    """
    Accepts ISO-8601 UTC with 'Z' suffix. Stores as aware UTC datetime.
    """
    if not isinstance(iso, str) or not iso.endswith("Z"):
        raise ValueError("expires_utc must be an ISO-8601 UTC string ending with 'Z'")
    try:
        # Python 3.9: support 'Z' by replacing with +00:00
        dt = _dt.datetime.fromisoformat(iso.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            raise ValueError
        # normalize to naive UTC for storage or keep ISO Z on output
        return dt.astimezone(_dt.timezone.utc).replace(tzinfo=None)
    except Exception:
        raise ValueError("expires_utc is not a valid ISO-8601 time")

def _rand_code(length: int = 20) -> str:
    return "".join(secrets.choice(_ALNUM_UPPER) for _ in range(length))

def _validate_functions(funcs: List[str]) -> List[str]:
    if not isinstance(funcs, list) or not funcs:
        raise HTTPException(status_code=422, detail="functions must be a non-empty array")
    invalid = [f for f in funcs if f not in CODE_FUNCTION_MAP]
    if invalid:
        raise HTTPException(
            status_code=422,
            detail=f"Unsupported functions: {', '.join(invalid)}"
        )
    # Keep original order, unique
    seen = set()
    out = []
    for f in funcs:
        if f not in seen:
            seen.add(f)
            out.append(f)
    return out

# ───────────────────────── Pydantic models ──────────────────────
Mode = Literal["one_off", "reusable", "single_use"]

class CodeGenIn(BaseModel):
    mode: Mode
    functions: List[str] = Field(..., description="Array of function names (e.g., ['isAdmin'])")
    expires_utc: str     = Field(..., description="ISO-8601 UTC timestamp with 'Z' suffix")
    code: Optional[str]  = Field(None, description="Required for reusable/single_use; ignored for one_off")

    @validator("code")
    def _upper_trim(cls, v, values):
        if v is None:
            return v
        v = v.strip().upper()
        if not _CODE_RE.match(v):
            raise ValueError("code must be A–Z, 0–9 only")
        return v

class CodeGenOut(BaseModel):
    code: str
    mode: Mode
    functions: List[str]
    expires_utc: str

# ───────────────────────── FastAPI router ───────────────────────
router = APIRouter(prefix="/api/auth", tags=["auth"])

@router.post("/code/generate", response_model=CodeGenOut, status_code=status.HTTP_201_CREATED)
def generate_code(payload: CodeGenIn, request: Request):
    """
    Public code generator (no admin gate).
    Modes:
      - one_off     : server generates a random 20-char code; single global consumption
      - reusable    : caller supplies the code; can be redeemed by many users once each
      - single_use  : caller supplies the code; single global consumption

    All modes require an expiry in the future and a non-empty functions[] array
    validated against the server-side allowlist (CODE_FUNCTION_MAP).
    """
    # Validate functions
    funcs = _validate_functions(payload.functions)

    # Validate expiry (must be in the future)
    try:
        expiry_dt_utc = _parse_expiry_utc(payload.expires_utc)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    if expiry_dt_utc <= _now_utc():
        raise HTTPException(status_code=422, detail="expires_utc must be in the future")

    mode = payload.mode

    # Decide code value
    if mode == "one_off":
        # Ignore any provided code; generate random and ensure uniqueness with bounded retries
        max_attempts = 5
        for attempt in range(1, max_attempts + 1):
            code = _rand_code(20)
            doc = _build_doc(
                code=code, mode=mode, functions=funcs, expiry_dt_utc=expiry_dt_utc, request=request
            )
            try:
                _codes.create_item(doc)
                break
            except exceptions.CosmosResourceExistsError:
                if attempt == max_attempts:
                    raise HTTPException(status_code=503, detail="Could not allocate a unique code, try again")
                continue
    else:
        # reusable / single_use require caller-provided code
        if not payload.code:
            raise HTTPException(status_code=422, detail="code is required for reusable/single_use modes")
        code = payload.code  # already uppercased + validated by the validator

        doc = _build_doc(
            code=code, mode=mode, functions=funcs, expiry_dt_utc=expiry_dt_utc, request=request
        )
        try:
            _codes.create_item(doc)
        except exceptions.CosmosResourceExistsError:
            raise HTTPException(status_code=409, detail="Code already exists")

    # Response mirrors inputs (functions as requested names; expiry as ISO Z)
    return CodeGenOut(
        code=code,
        mode=mode,
        functions=funcs,
        expires_utc=expiry_dt_utc.replace(microsecond=0).isoformat() + "Z",
    )

# ───────────────────────── doc builder ──────────────────────────
def _build_doc(
    *,
    code: str,
    mode: Mode,
    functions: List[str],
    expiry_dt_utc: _dt.datetime,
    request: Request,
) -> dict:
    """
    Build the Cosmos doc for 'codes' container. We set id == code and use /code as PK.
    """
    now = _now_utc()
    doc = {
        "id": code,
        "code": code,
        "mode": mode,
        "functions": list(functions),
        "expires_utc": expiry_dt_utc.replace(microsecond=0).isoformat() + "Z",
        "created_utc": now.isoformat() + "Z",
        "generated_by": "public",
    }

    # For single-consumption modes, initialize consumed flags
    if mode in ("one_off", "single_use"):
        doc.update({"consumed": False, "consumed_by": None, "consumed_utc": None})

    # Optionally capture a hint about origin (best-effort)
    try:
        xff = request.headers.get("X-Forwarded-For") or ""
        if xff:
            doc["generated_from"] = xff.split(",")[0].strip()
    except Exception:
        pass

    return doc
