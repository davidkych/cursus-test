# ── src/routers/auth/codes.py ────────────────────────────────────────────────
"""
Redemption code generator + redemption endpoints (under /api/auth).

Requirements implemented:
- Three code modes:
  * oneoff   : system-generated 20-char code, single use, expires on use or at given expiry
  * single   : caller-provided code, single use, expires on use or at given expiry
  * reusable : caller-provided code, multi-user reusable until expiry; a given user can redeem at most once
- Functions supported are centrally registered in routers.auth.common (no hard-coding here).
- Code generation endpoints are OPEN (no admin/auth required).
- Prompt-based creation endpoint (text/plain) independent of frontend.
- HTML form endpoint is implemented in a separate file (html_codegen.py).
- Redemption endpoint requires login (Bearer JWT), applies function to user, and records usage.

Notes:
- No TTL/purging (per requirements).
- Basic collision handling for generated codes.
- Minimal race-protection (best effort). If you want strict single-consume guarantees
  under high concurrency, we can add ETag-based conditional writes later.
"""

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, Field
from typing import Optional, Literal, Dict, Any, List, Tuple
from azure.cosmos import CosmosClient, exceptions
from azure.identity import DefaultAzureCredential
import os, datetime, random, string, jwt

# Shared function/flag helpers
from .common import FUNCTION_KEYS, apply_user_function, apply_default_user_flags

# ───────────────────────── Cosmos setup ──────────────────────────
_cosmos_endpoint   = os.environ["COSMOS_ENDPOINT"]
_database_name     = os.getenv("COSMOS_DATABASE")
_users_container   = os.getenv("USERS_CONTAINER", "users")
_codes_container   = os.getenv("CODES_CONTAINER", "codes")
_jwt_secret        = os.getenv("JWT_SECRET", "change-me")

_client = CosmosClient(_cosmos_endpoint, credential=DefaultAzureCredential())
_db     = _client.get_database_client(_database_name)
_users  = _db.get_container_client(_users_container)
_codes  = _db.get_container_client(_codes_container)

# ──────────────────────────── Router ────────────────────────────
router = APIRouter(
    prefix="/api/auth",
    tags=["auth"]
)

# ────────────────────────── Utilities ───────────────────────────
_BASE62 = string.ascii_letters + string.digits

def _now_utc() -> datetime.datetime:
    return datetime.datetime.utcnow().replace(tzinfo=datetime.timezone.utc)

def _to_utc_iso(dt: datetime.datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=datetime.timezone.utc)
    else:
        dt = dt.astimezone(datetime.timezone.utc)
    return dt.isoformat()

def _parse_expires_at(s: str) -> datetime.datetime:
    """
    Accepts ISO-8601 or 'YYYY-MM-DD'. Dates are treated as end-of-day (23:59:59Z).
    Raises ValueError on invalid input.
    """
    s = (s or "").strip()
    if not s:
        raise ValueError("expiresAt is required")
    try:
        # Try full ISO first
        dt = datetime.datetime.fromisoformat(s.replace("Z", "+00:00"))
        return dt.astimezone(datetime.timezone.utc)
    except Exception:
        pass
    try:
        # Try plain date → end-of-day UTC
        d = datetime.date.fromisoformat(s)
        dt = datetime.datetime.combine(d, datetime.time(23, 59, 59, tzinfo=datetime.timezone.utc))
        return dt
    except Exception:
        raise ValueError("expiresAt must be ISO-8601 or YYYY-MM-DD")

def _gen_code(n: int = 20) -> str:
    return "".join(random.SystemRandom().choice(_BASE62) for _ in range(n))

def _looks_expired(expires_at_iso: str) -> bool:
    try:
        dt = datetime.datetime.fromisoformat(expires_at_iso.replace("Z", "+00:00"))
    except Exception:
        return True
    return _now_utc() > dt.astimezone(datetime.timezone.utc)

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

def _read_code(code: str) -> Optional[Dict[str, Any]]:
    try:
        return _codes.read_item(item=code, partition_key=code)
    except exceptions.CosmosResourceNotFoundError:
        return None

def _create_code_doc(
    mode: str,
    function: str,
    code: str,
    expires_at: datetime.datetime,
    request: Request,
    generated_by_user: Optional[str],
) -> Dict[str, Any]:
    ip = getattr(request.client, "host", None)
    doc: Dict[str, Any] = {
        "id": code,
        "code": code,
        "mode": mode,
        "function": function,
        "expiresAt": _to_utc_iso(expires_at),
        "generatedAt": _to_utc_iso(_now_utc()),
        "generatedByUser": generated_by_user,
        "generatedByIp": ip,
        # usage policy & state
        "maxUses": 1 if mode in ("oneoff", "single") else None,
        "usedCount": 0,
        "usedBy": [],
        "consumed": False,
        "notes": "",
    }
    return doc

# ────────────────────────── Pydantic models ─────────────────────
class CodeCreateIn(BaseModel):
    mode: Literal["oneoff", "single", "reusable"]
    function: str = Field(..., description="One of the registered function keys")
    expiresAt: str = Field(..., description="ISO-8601 or YYYY-MM-DD (UTC end-of-day if date)")
    code: Optional[str] = Field(None, description="Required for 'single' and 'reusable'. Must be omitted for 'oneoff'.")
    count: Optional[int] = Field(1, ge=1, le=1000, description="For batch generation of oneoff codes")

class CodeCreateOut(BaseModel):
    code: str
    mode: str
    function: str
    expiresAt: str

class RedeemIn(BaseModel):
    code: str

class RedeemOut(BaseModel):
    is_admin: bool
    is_premium_member: bool
    applied: bool = Field(..., description="Whether the user document changed as a result of redemption")

# ────────────────────────── Creation helpers ─────────────────────
def _validate_and_normalize_payload(p: CodeCreateIn) -> Tuple[str, str, datetime.datetime, Optional[str], int]:
    if p.function not in FUNCTION_KEYS:
        raise HTTPException(status_code=422, detail=f"Unsupported function '{p.function}'")

    # Parse expiry and ensure it is in the future
    try:
        expires_at = _parse_expires_at(p.expiresAt)
    except ValueError as ve:
        raise HTTPException(status_code=422, detail=str(ve))
    if _now_utc() >= expires_at:
        raise HTTPException(status_code=422, detail="expiresAt must be in the future")

    mode = p.mode
    if mode == "oneoff":
        if p.code:
            raise HTTPException(status_code=422, detail="code must be omitted for mode=oneoff")
        count = int(p.count or 1)
    else:
        # single | reusable
        if not p.code or not p.code.strip():
            raise HTTPException(status_code=422, detail="code is required for mode=single/reusable")
        count = 1
    return mode, p.function, expires_at, (p.code.strip() if p.code else None), count

def _safe_create_code(doc: Dict[str, Any]) -> Dict[str, Any]:
    """
    Try to create the code document; on conflict raise HTTP 409.
    """
    try:
        _codes.create_item(doc)
        return doc
    except exceptions.CosmosResourceExistsError:
        raise HTTPException(status_code=409, detail="Code already exists")

def _safe_create_generated_code(mode: str, function: str, expires_at: datetime.datetime, request: Request, generated_by_user: Optional[str]) -> Dict[str, Any]:
    # Attempt a few times in case of rare collision
    for _ in range(6):
        code = _gen_code(20)
        doc = _create_code_doc(mode, function, code, expires_at, request, generated_by_user)
        try:
            _codes.create_item(doc)
            return doc
        except exceptions.CosmosResourceExistsError:
            continue
    raise HTTPException(status_code=500, detail="Failed to generate a unique code; please retry")

# ────────────────────────── Endpoints: create ────────────────────
@router.post("/codes", response_model=List[CodeCreateOut] | CodeCreateOut, status_code=status.HTTP_201_CREATED)
async def create_codes(payload: CodeCreateIn, request: Request):
    """
    OPEN endpoint. Create one or more codes.
    - mode=oneoff: generate 20-char codes; supports `count` up to 1000
    - mode=single|reusable: use provided `code`; single create only
    """
    mode, function, expires_at, intended_code, count = _validate_and_normalize_payload(payload)

    # If a bearer was present, we record creator username; otherwise None (open endpoint)
    generated_by_user = None
    auth = request.headers.get("Authorization", "")
    if auth.lower().startswith("bearer "):
        try:
            generated_by_user = _decode_jwt_subject(_extract_bearer_token(request))
        except Exception:
            # Ignore JWT errors for open endpoint
            generated_by_user = None

    created: List[Dict[str, Any]] = []
    if mode == "oneoff":
        for _ in range(count):
            doc = _safe_create_generated_code(mode, function, expires_at, request, generated_by_user)
            created.append(doc)
    else:
        doc = _create_code_doc(mode, function, intended_code, expires_at, request, generated_by_user)
        created.append(_safe_create_code(doc))

    # Shape response(s)
    items = [
        {"code": d["code"], "mode": d["mode"], "function": d["function"], "expiresAt": d["expiresAt"]}
        for d in created
    ]
    return items if len(items) > 1 else items[0]

@router.post("/codes/prompt", response_model=List[CodeCreateOut] | CodeCreateOut, status_code=status.HTTP_201_CREATED)
async def create_codes_prompt(request: Request):
    """
    OPEN endpoint. Accepts text/plain "prompt" with key=value per line.
    Example:
        mode=oneoff
        function=is_premium_member
        expiresAt=2025-12-31
        count=50
    """
    try:
        body = (await request.body()).decode("utf-8", errors="ignore")
    except Exception:
        raise HTTPException(status_code=400, detail="Failed to read request body as text/plain")

    kv: Dict[str, str] = {}
    for line in body.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        k, v = line.split("=", 1)
        kv[k.strip()] = v.strip()

    # Build payload
    payload = CodeCreateIn(
        mode=kv.get("mode", ""),
        function=kv.get("function", ""),
        expiresAt=kv.get("expiresAt", kv.get("expiry", "")),
        code=kv.get("code", None),
        count=int(kv["count"]) if "count" in kv and kv["count"].strip().isdigit() else 1,
    )
    return await create_codes(payload, request)

# ────────────────────────── Endpoint: redeem ─────────────────────
@router.post("/codes/redeem", response_model=RedeemOut)
def redeem_code(data: RedeemIn, request: Request):
    """
    AUTH endpoint. Redeem a code:
    - Applies the mapped function to the user (idempotent).
    - For reusable codes, the same user cannot redeem twice.
    - For oneoff/single, consumes the code on first successful redemption.
    """
    # Identify current user (JWT)
    token = _extract_bearer_token(request)
    username = _decode_jwt_subject(token)

    # Load code
    code = (data.code or "").strip()
    if not code:
        raise HTTPException(status_code=422, detail="code is required")
    doc = _read_code(code)
    if not doc:
        raise HTTPException(status_code=404, detail="Invalid code")

    # Validate expiry / consumed
    if _looks_expired(doc.get("expiresAt", "")):
        raise HTTPException(status_code=410, detail="Code expired")

    mode = doc.get("mode")
    function = doc.get("function")
    if function not in FUNCTION_KEYS:
        # Defensive: unknown function in stored doc
        raise HTTPException(status_code=422, detail="Unsupported function in code")

    used_by: List[str] = list(doc.get("usedBy") or [])
    used_count: int = int(doc.get("usedCount") or 0)
    max_uses = doc.get("maxUses", 1 if mode in ("oneoff", "single") else None)
    consumed = bool(doc.get("consumed", False))

    if mode in ("oneoff", "single"):
        if consumed or (max_uses is not None and used_count >= max_uses):
            raise HTTPException(status_code=410, detail="Code already consumed")
    elif mode == "reusable":
        if username in used_by:
            # same user cannot redeem the same reusable code multiple times
            raise HTTPException(status_code=409, detail="Code already redeemed by this user")
    else:
        raise HTTPException(status_code=422, detail="Unknown code mode")

    # Load user
    user_doc = _get_user_by_username(username)
    if not user_doc:
        # token valid but user doc missing → treat as unauthorized
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")

    # Ensure flags exist; then apply function
    apply_default_user_flags(user_doc)
    changed = apply_user_function(user_doc, function)

    # Update code usage
    if username not in used_by:
        used_by.append(username)
    used_count += 1
    if mode in ("oneoff", "single"):
        consumed = True  # single-use

    # Persist changes (best-effort; order not critical)
    doc["usedBy"] = used_by
    doc["usedCount"] = used_count
    doc["consumed"] = consumed
    try:
        _codes.upsert_item(doc)
    except Exception:
        # We still try to persist user update even if code update failed;
        # failing the request would invite client retries that could double-apply.
        pass

    try:
        _users.upsert_item(user_doc)
    except Exception:
        # Roll back code state is non-trivial; report failure
        raise HTTPException(status_code=500, detail="Failed to update user")

    return RedeemOut(
        is_admin=bool(user_doc.get("is_admin", False)),
        is_premium_member=bool(user_doc.get("is_premium_member", False)),
        applied=bool(changed),
    )
