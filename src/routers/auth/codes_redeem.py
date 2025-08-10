# ── src/routers/auth/codes_redeem.py ─────────────────────────────────────────
from __future__ import annotations

import datetime as _dt
import json as _json
import os
import re
from typing import Dict, List, Optional

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, Field, validator

from azure.cosmos import CosmosClient, exceptions
from azure.identity import DefaultAzureCredential
import jwt

# ───────────────────────── Env & Cosmos setup ─────────────────────────
_cosmos_endpoint      = os.environ["COSMOS_ENDPOINT"]
_database_name        = os.getenv("COSMOS_DATABASE")
_users_container_name = os.getenv("USERS_CONTAINER", "users")
_codes_container_name = os.getenv("CODES_CONTAINER", "codes")
_redeem_container_name = os.getenv("REDEMPTIONS_CONTAINER", "codeRedemptions")
_jwt_secret           = os.getenv("JWT_SECRET", "change-me")

_client       = CosmosClient(_cosmos_endpoint, credential=DefaultAzureCredential())
_db           = _client.get_database_client(_database_name)
_users        = _db.get_container_client(_users_container_name)
_codes        = _db.get_container_client(_codes_container_name)
_redemptions  = _db.get_container_client(_redeem_container_name)

# ───────────────────────── Function map (server-allowlist) ──────
_DEFAULT_MAP = {"isAdmin": "is_admin", "IsPremiumMember": "is_premium_member"}
try:
    _env_map = _json.loads(os.getenv("CODE_FUNCTION_MAP", "") or "{}")
    if not isinstance(_env_map, dict):
        _env_map = {}
except Exception:
    _env_map = {}
CODE_FUNCTION_MAP: Dict[str, str] = {**_DEFAULT_MAP, **_env_map}

# ───────────────────────── Helpers ──────────────────────────────
_CODE_RE = re.compile(r"^[A-Z0-9]+$")

def _now_utc() -> _dt.datetime:
    return _dt.datetime.utcnow().replace(microsecond=0)

def _iso_z(dt: _dt.datetime) -> str:
    return dt.replace(microsecond=0).isoformat() + "Z"

def _parse_iso_utc_z(s: str) -> _dt.datetime:
    # Accept '...Z' and convert to naive UTC for comparison
    if not isinstance(s, str) or not s.endswith("Z"):
        raise ValueError("timestamp must be ISO-8601 UTC with 'Z'")
    return _dt.datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(_dt.timezone.utc).replace(tzinfo=None)

def _extract_bearer_username(req: Request) -> str:
    auth = req.headers.get("Authorization", "")
    if not auth.lower().startswith("bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing bearer token")
    token = auth.split(" ", 1)[1].strip()
    try:
        payload = jwt.decode(token, _jwt_secret, algorithms=["HS256"])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

    sub = payload.get("sub")
    if not sub:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token (no subject)")
    return sub

def _get_user(username: str) -> Optional[dict]:
    try:
        return _users.read_item(item=username, partition_key=username)
    except exceptions.CosmosResourceNotFoundError:
        return None

def _apply_functions_to_user(user_doc: dict, requested_functions: List[str]) -> List[str]:
    """
    Map requested function names to internal fields and set them to True.
    Returns the list of internal field names that were granted.
    """
    granted_fields: List[str] = []
    changed = False
    for fn in requested_functions:
        field = CODE_FUNCTION_MAP.get(fn)
        if not field:
            continue  # defensive; generator already validated
        if user_doc.get(field) is not True:
            user_doc[field] = True
            changed = True
        granted_fields.append(field)

    if changed:
        _users.upsert_item(user_doc)
    return granted_fields

def _write_audit(code: str, username: str, result: str, mode: str, functions: List[str]) -> None:
    """
    Best-effort write to codeRedemptions (one per username per code).
    For reusable codes, duplicate attempts by the same user will conflict on uniqueKey and
    will simply be ignored here.
    """
    doc = {
        "id": f"{code}:{username}:{_iso_z(_now_utc())}",
        "code": code,
        "username": username,
        "redeemed_utc": _iso_z(_now_utc()),
        "result": result,
        "mode": mode,
        "functions": list(functions or []),
    }
    try:
        _redemptions.create_item(doc)
    except (exceptions.CosmosResourceExistsError, exceptions.CosmosHttpResponseError):
        # On uniqueKey conflict or other 409-ish errors, do not raise.
        pass

def _consume_code_once(code_doc: dict, username: str) -> bool:
    """
    Attempt to atomically consume a one_off/single_use code using ETag match.
    Returns True if we successfully marked it consumed; False if already consumed.
    """
    if code_doc.get("consumed") is True:
        return False

    etag = code_doc.get("_etag")
    code = code_doc["code"]
    updated = {**code_doc, "consumed": True, "consumed_by": username, "consumed_utc": _iso_z(_now_utc())}

    try:
        # Conditional replace on ETag to serialize concurrent consumers
        _codes.replace_item(
            item=code,
            body=updated,
            access_condition={"type": "IfMatch", "condition": etag},
        )
        return True
    except exceptions.CosmosHttpResponseError as e:
        # 412 Precondition Failed or 409 Conflict indicates ETag mismatch / already consumed
        if getattr(e, "status_code", None) in (409, 412):
            return False
        raise

# ───────────────────────── Models ───────────────────────────────
class RedeemIn(BaseModel):
    code: str = Field(..., description="Code to redeem (A–Z/0–9)")

    @validator("code")
    def _upper_alnum(cls, v):
        v = (v or "").strip().upper()
        if not _CODE_RE.match(v):
            raise ValueError("code must be A–Z, 0–9 only")
        return v

class RedeemOut(BaseModel):
    status: str                 # "ok"
    granted: List[str] = []     # list of internal field names set on the user

# ───────────────────────── Router ───────────────────────────────
router = APIRouter(prefix="/api/auth", tags=["auth"])

@router.post("/code/redeem", response_model=RedeemOut)
def redeem_code(payload: RedeemIn, request: Request):
    """
    Redeem a code for the authenticated user.

    Behavior:
      - Validates code exists and is not expired
      - Mode=reusable: one redemption per user (enforced by codeRedemptions uniqueKey)
      - Mode=one_off/single_use: first user to consume wins (atomic ETag replace)
      - Applies mapped functions onto the user document (idempotent set True)
      - Writes an audit record (best-effort)
    """
    username = _extract_bearer_username(request)
    code = payload.code

    # 1) Load code doc
    try:
        code_doc = _codes.read_item(item=code, partition_key=code)
    except exceptions.CosmosResourceNotFoundError:
        _write_audit(code, username, "unknown_code", "unknown", [])
        raise HTTPException(status_code=404, detail="Unknown code")

    mode = code_doc.get("mode") or "reusable"
    functions_requested = code_doc.get("functions") or []

    # 2) Expiry check
    try:
        expires_dt = _parse_iso_utc_z(code_doc.get("expires_utc", ""))
    except Exception:
        _write_audit(code, username, "expired", mode, functions_requested)
        raise HTTPException(status_code=410, detail="Code expired or invalid expiry")
    if expires_dt <= _now_utc():
        _write_audit(code, username, "expired", mode, functions_requested)
        raise HTTPException(status_code=410, detail="Code expired")

    # 3) User existence
    user_doc = _get_user(username)
    if not user_doc:
        # Should not happen with valid JWT, but keep a safe error
        _write_audit(code, username, "user_not_found", mode, functions_requested)
        raise HTTPException(status_code=401, detail="User not found")

    # 4) Mode-specific checks & auditing
    if mode == "reusable":
        # Enforce "one redemption per user" via uniqueKey on /username inside /code partition
        audit_doc = {
            "id": f"{code}:{username}:{_iso_z(_now_utc())}",
            "code": code,
            "username": username,
            "redeemed_utc": _iso_z(_now_utc()),
            "result": "ok",                      # updated later on error
            "mode": mode,
            "functions": list(functions_requested),
        }
        try:
            _redemptions.create_item(audit_doc)  # if duplicate user, this will 409
        except (exceptions.CosmosResourceExistsError, exceptions.CosmosHttpResponseError):
            # Already redeemed by this user
            _write_audit(code, username, "already_redeemed", mode, functions_requested)  # best-effort extra trace
            raise HTTPException(status_code=409, detail="You have already redeemed this code")

        # Apply functions (idempotent)
        granted = _apply_functions_to_user(user_doc, functions_requested)

        # success path (audit already inserted as 'ok')
        return RedeemOut(status="ok", granted=granted)

    elif mode in ("one_off", "single_use"):
        # Attempt atomic consume
        consumed_now = _consume_code_once(code_doc, username)
        if not consumed_now:
            _write_audit(code, username, "consumed", mode, functions_requested)
            raise HTTPException(status_code=409, detail="This code has already been consumed")

        # Apply functions (idempotent)
        granted = _apply_functions_to_user(user_doc, functions_requested)

        # Audit success
        _write_audit(code, username, "ok", mode, functions_requested)
        return RedeemOut(status="ok", granted=granted)

    else:
        # Unknown mode present in DB (defensive)
        _write_audit(code, username, "invalid_mode", str(mode), functions_requested)
        raise HTTPException(status_code=422, detail="Invalid code mode")
