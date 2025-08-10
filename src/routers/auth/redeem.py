# ── src/routers/auth/redeem.py ────────────────────────────────────────────────
from __future__ import annotations

import datetime as _dt
import os
from typing import Any, Dict, Optional, Literal

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, Field
from azure.cosmos import CosmosClient, exceptions
from azure.identity import DefaultAzureCredential
import jwt


# ───────────────────────── Cosmos & env setup ─────────────────────
_cosmos_endpoint = os.environ["COSMOS_ENDPOINT"]
_database_name   = os.getenv("COSMOS_DATABASE")
_users_container = os.getenv("USERS_CONTAINER", "users")
_codes_container = os.getenv("CODES_CONTAINER", "codes")
_jwt_secret      = os.getenv("JWT_SECRET", "change-me")

_client = CosmosClient(_cosmos_endpoint, credential=DefaultAzureCredential())
_users = _client.get_database_client(_database_name).get_container_client(_users_container)
_codes = _client.get_database_client(_database_name).get_container_client(_codes_container)

# Supported functions
Func = Literal["is_admin", "is_premium"]


# ───────────────────────── helpers ────────────────────────────────
def _now_utc() -> _dt.datetime:
    return _dt.datetime.utcnow().replace(microsecond=0)


def _parse_utc_z(s: str) -> Optional[_dt.datetime]:
    """Parse 'YYYY-MM-DDTHH:MM:SSZ' into naive UTC datetime."""
    if not s:
        return None
    s = s.strip()
    if s.endswith("Z") or s.endswith("z"):
        s = s[:-1]
    try:
        dt = _dt.datetime.fromisoformat(s)
    except ValueError:
        return None
    if dt.tzinfo is not None:
        dt = dt.astimezone(_dt.timezone.utc).replace(tzinfo=None)
    return dt


def _extract_bearer_token(req: Request) -> str:
    auth = req.headers.get("Authorization", "")
    if not auth.lower().startswith("bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing bearer token")
    return auth.split(" ", 1)[1].strip()


def _decode_jwt_subject(token: str) -> str:
    try:
        payload = jwt.decode(token, _jwt_secret, algorithms=["HS256"])
        sub = payload.get("sub")
        if not sub:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token (no subject)")
        return sub
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")


def _get_user_by_username(username: str) -> Optional[Dict[str, Any]]:
    try:
        return _users.read_item(item=username, partition_key=username)
    except exceptions.CosmosResourceNotFoundError:
        return None


def _apply_function_to_user(doc: Dict[str, Any], fn: Func) -> Dict[str, Any]:
    """Mutate the in-memory user document according to the function."""
    if fn == "is_admin":
        doc["is_admin"] = True
    elif fn == "is_premium":
        doc["is_premium"] = True
    return doc


# ───────────────────────── models ─────────────────────────────────
class RedeemIn(BaseModel):
    code: str = Field(..., min_length=6, max_length=64)


class RedeemOut(BaseModel):
    status: Literal["ok"]
    code: str
    mode: Literal["oneoff", "reusable", "single"]
    function: Func
    user: str
    applied: Dict[str, bool]  # e.g., {"is_admin": true} or {"is_premium": true}


# ───────────────────────── router ─────────────────────────────────
router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/redeem", response_model=RedeemOut)
def redeem(payload: RedeemIn, request: Request):
    """
    Redeem a code and apply its function to the current user.

    Rules:
    - 'oneoff' and 'single': expire on consumption (global single-use).
    - 'reusable': may be redeemed by many users until expiry, but only once per user.
    - All modes: respect expiry_utc; maintain 'redemptions' audit trail.
    """
    # Identify user from JWT
    token = _extract_bearer_token(request)
    username = _decode_jwt_subject(token)

    # Fetch user
    user_doc = _get_user_by_username(username)
    if not user_doc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")

    # Fetch code
    code_id = payload.code.strip().upper()
    try:
        code_doc = _codes.read_item(item=code_id, partition_key=code_id)
    except exceptions.CosmosResourceNotFoundError:
        raise HTTPException(status_code=404, detail="Invalid or expired code")

    mode = (code_doc.get("mode") or "").lower()
    fn: Func = code_doc.get("function")  # expected to be 'is_admin' | 'is_premium'
    expiry_iso = code_doc.get("expiry_utc") or ""
    expiry_dt = _parse_utc_z(expiry_iso)

    # Check expiry (even if TTL hasn't purged the item yet)
    if expiry_dt and _now_utc() >= expiry_dt:
        raise HTTPException(status_code=410, detail="Code expired")

    # Enforce per-user single redemption across all modes
    redemptions = code_doc.get("redemptions") or []
    if any(r.get("user") == username for r in redemptions):
        raise HTTPException(status_code=409, detail="You have already redeemed this code")

    # Enforce global single-use for oneoff/single
    if mode in ("oneoff", "single"):
        if code_doc.get("consumed"):
            raise HTTPException(status_code=409, detail="Code already consumed")

    # Apply function to user doc
    before_is_admin = bool(user_doc.get("is_admin", False))
    before_is_premium = bool(user_doc.get("is_premium", False))
    _apply_function_to_user(user_doc, fn)

    # Persist user change
    _users.upsert_item(user_doc)

    # Update code document: append redemption + possibly mark consumed
    redemption_entry = {
        "user": username,
        "at_utc": _now_utc().isoformat() + "Z",
    }
    code_doc.setdefault("redemptions", []).append(redemption_entry)

    if mode in ("oneoff", "single"):
        code_doc["consumed"] = True
        code_doc["consumed_by"] = username
        code_doc["consumed_utc"] = redemption_entry["at_utc"]

    _codes.upsert_item(code_doc)

    return RedeemOut(
        status="ok",
        code=code_id,
        mode=mode,            # type: ignore[arg-type]
        function=fn,          # type: ignore[arg-type]
        user=username,
        applied={
            "is_admin": bool(user_doc.get("is_admin", False)) and not before_is_admin or bool(user_doc.get("is_admin", False)),
            "is_premium": bool(user_doc.get("is_premium", False)) and not before_is_premium or bool(user_doc.get("is_premium", False)),
        },
    )
