# src/routers/auth/codes.py
# ─────────────────────────────────────────────────────────────────────────────
# Code generator & redeemer APIs (no generator auth per your policy)
#
# Endpoints:
#   POST /api/auth/codes/generate   → create a code (oneoff | reusable | single)
#   POST /api/auth/codes/redeem     → redeem a code (requires user JWT)
#
# Cosmos:
#   - Container: CODES_CONTAINER (default "codes"), PK: /code, unique on /code
#   - Users    : USERS_CONTAINER  (default "users"), PK: /username
#
# Behavior:
#   - oneoff  : server generates 20-char code, max_uses = 1
#   - single  : client supplies code,         max_uses = 1
#   - reusable: client supplies code,         max_uses = null or provided int>0
#   - Expiry  : rejects when now >= expires_at (UTC)
#   - Per-user: a user can redeem a given code only once (409 on repeat)
#   - Concurrency: code consumption uses Cosmos ETag (If-Match) to prevent double-spend
# ─────────────────────────────────────────────────────────────────────────────

from __future__ import annotations

import datetime as _dt
import os
import re
import secrets
from typing import Any, Dict, List, Literal, Optional, Tuple, Union

import jwt
from azure.cosmos import CosmosClient, exceptions
from azure.identity import DefaultAzureCredential
from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, Field, validator

from .grants import ALLOWED_GRANTS, apply_grants, validate_grants

# ───────────────────────── Cosmos & env wiring ─────────────────────────

_cosmos_endpoint = os.environ["COSMOS_ENDPOINT"]
_database_name = os.getenv("COSMOS_DATABASE")
_codes_container_name = os.getenv("CODES_CONTAINER", "codes")
_users_container_name = os.getenv("USERS_CONTAINER", "users")
_jwt_secret = os.getenv("JWT_SECRET", "change-me")

_client = CosmosClient(_cosmos_endpoint, credential=DefaultAzureCredential())
_db = _client.get_database_client(_database_name)
_codes = _db.get_container_client(_codes_container_name)
_users = _db.get_container_client(_users_container_name)

# ───────────────────────── Router ─────────────────────────────────────

router = APIRouter(prefix="/api/auth", tags=["auth"])

# ───────────────────────── Utilities ──────────────────────────────────


def _now_utc() -> _dt.datetime:
    return _dt.datetime.utcnow().replace(tzinfo=_dt.timezone.utc, microsecond=0)


def _to_utc_iso(dt: _dt.datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=_dt.timezone.utc)
    else:
        dt = dt.astimezone(_dt.timezone.utc)
    return dt.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _parse_expires_at(value: Union[str, _dt.date, _dt.datetime]) -> _dt.datetime:
    """
    Accepts:
      - 'YYYY-MM-DD' (treated as end-of-day 23:59:59Z)
      - RFC3339/ISO datetime (with or without 'Z'); naive treated as UTC
      - datetime/date objects
    Returns timezone-aware UTC datetime.
    """
    if isinstance(value, _dt.datetime):
        dt = value
    elif isinstance(value, _dt.date):
        dt = _dt.datetime(value.year, value.month, value.day, 23, 59, 59)
    elif isinstance(value, str):
        s = value.strip()
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", s):
            y, m, d = map(int, s.split("-"))
            dt = _dt.datetime(y, m, d, 23, 59, 59)
        else:
            # Support 'Z'
            if s.endswith("Z"):
                s = s[:-1] + "+00:00"
            try:
                dt = _dt.datetime.fromisoformat(s)
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="expires_at must be a valid ISO date or datetime",
                )
    else:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="expires_at is required",
        )

    # Normalize to UTC
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=_dt.timezone.utc)
    else:
        dt = dt.astimezone(_dt.timezone.utc)
    return dt


def _gen_random_code(length: int = 20) -> str:
    # URL-safe, mixed chars, trimmed to exact length
    return secrets.token_urlsafe(16)[:length]


def _code_exists(code: str) -> bool:
    try:
        _codes.read_item(item=code, partition_key=code)
        return True
    except exceptions.CosmosResourceNotFoundError:
        return False


def _extract_bearer_token(req: Request) -> str:
    auth = req.headers.get("Authorization", "")
    if not auth.lower().startswith("bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing bearer token"
        )
    return auth.split(" ", 1)[1].strip()


def _decode_jwt_subject(token: str) -> str:
    try:
        payload = jwt.decode(token, _jwt_secret, algorithms=["HS256"])
        sub = payload.get("sub")
        if not sub:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token (no subject)"
            )
        return sub
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Token expired"
        )
    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token"
        )


def _load_user(username: str) -> Dict[str, Any]:
    try:
        return _users.read_item(item=username, partition_key=username)
    except exceptions.CosmosResourceNotFoundError:
        raise HTTPException(status_code=401, detail="User not found")


# ───────────────────────── Pydantic models ────────────────────────────


class GenerateIn(BaseModel):
    mode: Literal["oneoff", "reusable", "single"]
    code: Optional[str] = Field(
        None, description="Required for reusable/single; ignored for oneoff"
    )
    expires_at: Union[_dt.datetime, _dt.date, str]
    grants: List[str] = Field(..., description=f"Subset of {sorted(ALLOWED_GRANTS)}")
    max_uses: Optional[int] = Field(
        None,
        description="Optional for reusable; null means unlimited; ignored for oneoff/single",
        gt=0,
    )

    @validator("grants")
    def _validate_grants(cls, v: List[str]) -> List[str]:
        unknown = validate_grants(v)
        if unknown:
            raise ValueError(f"Unknown grants: {', '.join(unknown)}; allowed: {sorted(ALLOWED_GRANTS)}")
        return v

    @validator("code")
    def _trim_code(cls, v: Optional[str], values: Dict[str, Any]) -> Optional[str]:
        if v is None:
            return v
        s = v.strip()
        if not s:
            return None
        # Keep it flexible — no strict pattern as requested; prevent overly long payloads
        if len(s) > 128:
            raise ValueError("code must be <= 128 characters")
        return s


class CodeOut(BaseModel):
    code: str
    mode: Literal["oneoff", "reusable", "single"]
    expires_at: str
    grants: List[str]
    max_uses: Optional[int] = None
    uses_count: int = 0


class RedeemIn(BaseModel):
    code: str = Field(..., min_length=1)


class RedeemOut(BaseModel):
    applied: List[str]
    remaining_uses: Optional[int] = None


# ───────────────────────── Endpoint: generate ─────────────────────────


@router.post("/codes/generate", response_model=CodeOut)
def generate_code(payload: GenerateIn):
    # Normalize/validate expiry
    expires = _parse_expires_at(payload.expires_at)
    if expires <= _now_utc():
        raise HTTPException(status_code=422, detail="expires_at must be in the future")

    # Resolve code + max_uses by mode
    mode = payload.mode
    if mode == "oneoff":
        # server-generated, single-use
        code = None
        # attempt a few times to avoid collisions
        for _ in range(6):
            c = _gen_random_code(20)
            if not _code_exists(c):
                code = c
                break
        if not code:
            raise HTTPException(status_code=500, detail="Failed to generate a unique code")
        max_uses = 1
    elif mode == "single":
        if not payload.code:
            raise HTTPException(status_code=422, detail="code is required for mode=single")
        if _code_exists(payload.code):
            raise HTTPException(status_code=409, detail="code already exists")
        code = payload.code
        max_uses = 1
    elif mode == "reusable":
        if not payload.code:
            raise HTTPException(status_code=422, detail="code is required for mode=reusable")
        if _code_exists(payload.code):
            raise HTTPException(status_code=409, detail="code already exists")
        code = payload.code
        # optional cap; None => unlimited
        max_uses = payload.max_uses if payload.max_uses and payload.max_uses > 0 else None
    else:
        raise HTTPException(status_code=422, detail="Unsupported mode")

    doc = {
        "id": code,  # convenience
        "code": code,
        "mode": mode,
        "grants": list(dict.fromkeys(payload.grants or [])),  # normalized, unique
        "expires_at": _to_utc_iso(expires),
        "max_uses": max_uses,
        "uses_count": 0,
        "applied_to": [],
        "created_at": _to_utc_iso(_now_utc()),
    }

    try:
        _codes.create_item(doc)
    except exceptions.CosmosHttpResponseError as e:
        # unique key violation or other Cosmos error
        if getattr(e, "status_code", None) == 409:
            raise HTTPException(status_code=409, detail="code already exists")
        raise

    return CodeOut(**{k: doc[k] for k in ("code", "mode", "expires_at", "grants", "max_uses")}, uses_count=0)


# ───────────────────────── Endpoint: redeem ──────────────────────────


@router.post("/codes/redeem", response_model=RedeemOut)
def redeem_code(payload: RedeemIn, request: Request):
    # Identify user
    token = _extract_bearer_token(request)
    username = _decode_jwt_subject(token)

    # Load code doc
    code = payload.code.strip()
    try:
        doc = _codes.read_item(item=code, partition_key=code)
    except exceptions.CosmosResourceNotFoundError:
        raise HTTPException(status_code=404, detail="Code not found")

    # Check expiry
    exp = _parse_expires_at(doc.get("expires_at"))
    if _now_utc() >= exp:
        raise HTTPException(status_code=410, detail="Code expired")

    # Check usage caps
    uses_count = int(doc.get("uses_count", 0) or 0)
    max_uses = doc.get("max_uses", None)
    if isinstance(max_uses, int) and uses_count >= max_uses:
        raise HTTPException(status_code=409, detail="Code usage exhausted")

    # Check if same user already redeemed (block repeat)
    applied = doc.get("applied_to") or []
    if any((a or {}).get("username") == username for a in applied):
        raise HTTPException(status_code=409, detail="Code already redeemed by this user")

    # Load user
    user_doc = _load_user(username)

    # Apply grants (idempotent)
    grants = doc.get("grants") or []
    # (If registry changed since creation, ignore unknown silently)
    applied_grants = [g for g in grants if g in ALLOWED_GRANTS]
    apply_grants(user_doc, applied_grants)

    # Consume code (ETag-based optimistic concurrency)
    etag = doc.get("_etag")
    doc["uses_count"] = uses_count + 1
    (doc.setdefault("applied_to", [])).append(
        {"username": username, "at": _to_utc_iso(_now_utc())}
    )

    try:
        _codes.replace_item(
            item=doc,
            body=doc,
            access_condition={"type": "IfMatch", "condition": etag},
            partition_key=code,
        )
    except exceptions.CosmosHttpResponseError as e:
        # Precondition failed or other concurrency issue → treat as exhausted/conflict
        raise HTTPException(status_code=409, detail="Code was just redeemed or exhausted") from e

    # Persist user doc (best-effort; expected to succeed with MSI role)
    _users.upsert_item(user_doc)

    # Compute remaining uses
    remaining: Optional[int]
    if isinstance(max_uses, int):
        remaining = max(0, int(max_uses) - int(doc["uses_count"]))
    else:
        remaining = None

    return RedeemOut(applied=applied_grants, remaining_uses=remaining)
