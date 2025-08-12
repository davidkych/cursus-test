# ── src/routers/auth/codes.py ────────────────────────────────────────────────
"""
Code generator + redemption endpoints.

Modes
-----
- oneoff     : server generates a 20-char random code; single-use, or expires.
               Supports batch generation via 'count'.
- reusable   : caller provides the intended code; multi-use until expiry,
               BUT the same user cannot redeem it more than once.
- single     : caller provides the intended code; single-use, or expires.

Notes
-----
- Generation endpoints are open (no auth required), per requirement.
- Redemption requires a valid bearer token (same JWT as /me, /login).
- Function application relies on common.FUNCTION_REGISTRY/apply_function
  as the single source of truth.
- Expired codes are not purged (no background cleanup).

Cosmos Layout (container: CODES_CONTAINER, default 'codes')
-----------------------------------------------------------
PK: /code (also used as document id)
{
  "id": "<code>",
  "code": "<code>",
  "type": "oneoff" | "reusable" | "single",
  "function": "<fn-key>",
  "created_at": "<ISO-utc>",
  "expires_at": "<ISO-utc>",
  // oneoff/single:
  "consumed": false|true,
  "consumed_by": "username" | null,
  "consumed_at": "<ISO-utc>" | null,
  // reusable:
  "redeemed_by": ["username", ...],   // for same-user-once rule
  "redeemed_count": 0
}
"""

from fastapi import APIRouter, HTTPException, status, Request, Body
from pydantic import BaseModel, Field, validator
from typing import Optional, List, Literal, Any, Dict
from azure.cosmos import CosmosClient, exceptions
from azure.identity import DefaultAzureCredential
import os, datetime, secrets, string, jwt

# Single source of truth for functions + UI metadata
from .common import FUNCTION_REGISTRY, FUNCTION_METADATA, apply_function, apply_default_user_flags

# ───────────────────────── Cosmos setup ──────────────────────────
_cosmos_endpoint = os.environ["COSMOS_ENDPOINT"]
_database_name   = os.getenv("COSMOS_DATABASE")
_users_container = os.getenv("USERS_CONTAINER", "users")
_codes_container = os.getenv("CODES_CONTAINER", "codes")
_jwt_secret      = os.getenv("JWT_SECRET", "change-me")

_client = CosmosClient(_cosmos_endpoint, credential=DefaultAzureCredential())
_db     = _client.get_database_client(_database_name)
_users  = _db.get_container_client(_users_container)
_codes  = _db.get_container_client(_codes_container)

# ───────────────────────── Utilities ─────────────────────────────
_MAX_BATCH = 500  # safety cap; not exposed as a hard requirement
_RANDOM_ALPHABET = string.ascii_uppercase + string.digits

def _now_utc() -> datetime.datetime:
    return datetime.datetime.now(tz=datetime.timezone.utc)

def _iso(dt: datetime.datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=datetime.timezone.utc)
    return dt.astimezone(datetime.timezone.utc).isoformat().replace("+00:00", "Z")

def _parse_expiry(value: str) -> datetime.datetime:
    """
    Accepts 'YYYY-MM-DD' or full ISO; returns a UTC *end-of-day* when only a date is given.
    Raises 422 on invalid formats.
    """
    if not value or not isinstance(value, str):
        raise HTTPException(status_code=422, detail="expires_at must be a string (YYYY-MM-DD or ISO)")
    try:
        # Try pure date first
        d = datetime.date.fromisoformat(value)
        # Interpret as end-of-day UTC
        return datetime.datetime(d.year, d.month, d.day, 23, 59, 59, tzinfo=datetime.timezone.utc)
    except ValueError:
        pass
    try:
        # Try full datetime
        dt = datetime.datetime.fromisoformat(value.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=datetime.timezone.utc)
        return dt.astimezone(datetime.timezone.utc)
    except ValueError:
        raise HTTPException(status_code=422, detail="expires_at must be ISO date or datetime")

def _require_future(dt: datetime.datetime) -> None:
    if dt <= _now_utc():
        raise HTTPException(status_code=422, detail="expires_at must be in the future")

def _gen_code(n: int = 20) -> str:
    return "".join(secrets.choice(_RANDOM_ALPHABET) for _ in range(n))

def _extract_bearer_token(req: Request) -> str:
    auth = req.headers.get("Authorization", "")
    if not auth.lower().startswith("bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing bearer token")
    return auth.split(" ", 1)[1].strip()

def _decode_jwt(token: str) -> str:
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

def _upsert_user(doc: Dict[str, Any]) -> None:
    _users.upsert_item(doc)

def _get_code_doc(code: str) -> Optional[Dict[str, Any]]:
    try:
        # id == /code for fast point-reads
        return _codes.read_item(item=code, partition_key=code)
    except exceptions.CosmosResourceNotFoundError:
        return None

def _create_code_doc(doc: Dict[str, Any]) -> None:
    _codes.create_item(doc)

def _upsert_code_doc(doc: Dict[str, Any]) -> None:
    _codes.upsert_item(doc)

def _is_expired(code_doc: Dict[str, Any]) -> bool:
    try:
        exp = datetime.datetime.fromisoformat(str(code_doc.get("expires_at", "")).replace("Z", "+00:00"))
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=datetime.timezone.utc)
        return exp <= _now_utc()
    except Exception:
        # Treat unknown/invalid as expired for safety
        return True

def _validate_function_key(fn_key: str) -> None:
    if fn_key not in FUNCTION_REGISTRY:
        raise HTTPException(status_code=422, detail=f"Unsupported function: {fn_key}")

def _build_user_payload(doc: Dict[str, Any]) -> Dict[str, Any]:
    """Mirror /api/auth/me payload shape (kept here to avoid cross-import)."""
    payload: Dict[str, Any] = {
        "id":               doc.get("id") or doc.get("username"),
        "username":         doc.get("username"),
        "email":            doc.get("email"),
        "created":          doc.get("created"),
        "gender":           doc.get("gender"),
        "dob":              doc.get("dob"),
        "country":          doc.get("country"),
        "profile_pic_id":   int(doc.get("profile_pic_id", 1)),
        "profile_pic_type": doc.get("profile_pic_type", "default"),
        "is_admin":          bool(doc.get("is_admin", False)),
        "is_premium_member": bool(doc.get("is_premium_member", False)),
    }
    if isinstance(doc.get("login_context"), dict):
        payload["login_context"] = doc["login_context"]
    return payload

# ───────────────────────── Pydantic models ───────────────────────
class OneOffGenerateIn(BaseModel):
    function: str = Field(..., description="Function key from registry, e.g. 'is_admin'")
    expires_at: str = Field(..., description="YYYY-MM-DD or ISO datetime (UTC assumed if naive)")
    count: int = Field(1, ge=1, le=_MAX_BATCH, description="How many codes to generate")

    @validator("function")
    def _fn_known(cls, v):
        if v not in FUNCTION_REGISTRY:
            raise ValueError(f"Unsupported function: {v}")
        return v

class ReusableGenerateIn(BaseModel):
    code: str = Field(..., min_length=4, max_length=128, description="Intended code (case-sensitive)")
    function: str
    expires_at: str

    @validator("function")
    def _fn_known(cls, v):
        if v not in FUNCTION_REGISTRY:
            raise ValueError(f"Unsupported function: {v}")
        return v

class SingleGenerateIn(ReusableGenerateIn):
    pass

class RedeemIn(BaseModel):
    code: str = Field(..., min_length=1)

# ─────────────────────────── Router ──────────────────────────────
router = APIRouter(
    prefix="/api/auth/codes",
    tags=["auth-codes"]
)

# ───────────────────────── NEW: Open function metadata endpoint ──
@router.get("/functions")
def list_functions():
    """
    Open endpoint returning UI-friendly function metadata, avoiding any
    frontend hardcoding. Only exposes functions that are actually registered.
    Response: [{ key, label, description }]
    """
    items = []
    for key in FUNCTION_REGISTRY.keys():
        meta = FUNCTION_METADATA.get(key, {})
        label = meta.get("label") or key.replace("_", " ").title()
        description = meta.get("description") or ""
        items.append({"key": key, "label": label, "description": description})
    return items

# ───────────────────────── Generation endpoints (OPEN) ───────────
@router.post("/generate/oneoff")
def generate_oneoff(payload: OneOffGenerateIn):
    exp = _parse_expiry(payload.expires_at)
    _require_future(exp)

    created: List[Dict[str, Any]] = []
    for _ in range(payload.count):
        # Retry on rare collision
        for _attempt in range(5):
            code = _gen_code(20)
            now_iso = _iso(_now_utc())
            doc = {
                "id":          code,
                "code":        code,
                "type":        "oneoff",
                "function":    payload.function,
                "created_at":  now_iso,
                "expires_at":  _iso(exp),
                "consumed":    False,
                "consumed_by": None,
                "consumed_at": None,
            }
            try:
                _create_code_doc(doc)
                created.append({
                    "code":        code,
                    "type":        "oneoff",
                    "function":    payload.function,
                    "expires_at":  doc["expires_at"],
                    "created_at":  doc["created_at"],
                })
                break
            except exceptions.CosmosResourceExistsError:
                # extremely unlikely; try a new code
                continue
        else:
            # could not create after retries
            raise HTTPException(status_code=500, detail="Failed to allocate unique code")
    return {"count": len(created), "codes": created}

@router.post("/generate/reusable")
def generate_reusable(payload: ReusableGenerateIn):
    exp = _parse_expiry(payload.expires_at)
    _require_future(exp)
    _validate_function_key(payload.function)

    code = payload.code
    now_iso = _iso(_now_utc())
    doc = {
        "id":             code,
        "code":           code,
        "type":           "reusable",
        "function":       payload.function,
        "created_at":     now_iso,
        "expires_at":     _iso(exp),
        "redeemed_by":    [],
        "redeemed_count": 0,
    }
    try:
        _create_code_doc(doc)
    except exceptions.CosmosResourceExistsError:
        raise HTTPException(status_code=409, detail="Code already exists")
    return {
        "code":        code,
        "type":        "reusable",
        "function":    payload.function,
        "expires_at":  doc["expires_at"],
        "created_at":  doc["created_at"],
    }

@router.post("/generate/single")
def generate_single(payload: SingleGenerateIn):
    exp = _parse_expiry(payload.expires_at)
    _require_future(exp)
    _validate_function_key(payload.function)

    code = payload.code
    now_iso = _iso(_now_utc())
    doc = {
        "id":          code,
        "code":        code,
        "type":        "single",
        "function":    payload.function,
        "created_at":  now_iso,
        "expires_at":  _iso(exp),
        "consumed":    False,
        "consumed_by": None,
        "consumed_at": None,
    }
    try:
        _create_code_doc(doc)
    except exceptions.CosmosResourceExistsError:
        raise HTTPException(status_code=409, detail="Code already exists")
    return {
        "code":        code,
        "type":        "single",
        "function":    payload.function,
        "expires_at":  doc["expires_at"],
        "created_at":  doc["created_at"],
    }

# ───────────────────────── Redemption endpoint (AUTH) ────────────
@router.post("/redeem")
def redeem(req: Request, payload: RedeemIn = Body(...)):
    """
    Redeem a code and return the updated /me payload.
    - Requires Authorization: Bearer <JWT>.
    - Applies the registered function to the user doc.
    - Enforces "same user cannot redeem the same reusable code multiple times".
    """
    token = _extract_bearer_token(req)
    username = _decode_jwt(token)

    # Load user
    user = _get_user_by_username(username)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")

    # Load code
    code_doc = _get_code_doc(payload.code)
    if not code_doc:
        raise HTTPException(status_code=404, detail="Invalid code")

    # Expiry check
    if _is_expired(code_doc):
        raise HTTPException(status_code=410, detail="Code expired")

    ctype = code_doc.get("type")
    fn_key = code_doc.get("function")
    if not ctype or not fn_key:
        raise HTTPException(status_code=400, detail="Malformed code document")
    _validate_function_key(fn_key)

    # Enforce redemption rules
    now = _iso(_now_utc())

    if ctype in ("oneoff", "single"):
        if bool(code_doc.get("consumed")):
            raise HTTPException(status_code=409, detail="Code already used")
        # Apply function, persist user
        try:
            apply_default_user_flags(user)
            apply_function(user, fn_key)
            _upsert_user(user)
        except ValueError as ve:
            # Unsupported function (should be caught earlier)
            raise HTTPException(status_code=422, detail=str(ve))
        # Mark consumed
        code_doc["consumed"] = True
        code_doc["consumed_by"] = username
        code_doc["consumed_at"] = now
        _upsert_code_doc(code_doc)

    elif ctype == "reusable":
        redeemed_by = code_doc.get("redeemed_by") or []
        if username in redeemed_by:
            # Same user cannot redeem reusable code more than once
            raise HTTPException(status_code=409, detail="Code already redeemed by this user")

        # Apply function, persist user
        try:
            apply_default_user_flags(user)
            apply_function(user, fn_key)
            _upsert_user(user)
        except ValueError as ve:
            raise HTTPException(status_code=422, detail=str(ve))

        # Append username to redeemed_by
        redeemed_by.append(username)
        code_doc["redeemed_by"] = redeemed_by
        code_doc["redeemed_count"] = int(code_doc.get("redeemed_count", 0)) + 1
        _upsert_code_doc(code_doc)

    else:
        raise HTTPException(status_code=400, detail=f"Unknown code type: {ctype}")

    # Return updated /me-style payload
    return _build_user_payload(user)
