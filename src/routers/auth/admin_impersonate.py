# ── src/routers/auth/admin_impersonate.py ─────────────────────────────────────
"""
Admin-only endpoint to impersonate another user.

POST /api/auth/admin/impersonate
Body:
  {
    "username": "<target-username>",
    "ttl_minutes": 120   // optional; server clamps to [min .. max]
  }

Response:
  {
    "access_token": "<JWT>",
    "token_type": "bearer",
    "for_username": "<target-username>",
    "actor": "<admin-username>",
    "expires_in": 7200                  // seconds
  }

Notes:
- Requires a valid admin JWT in Authorization: Bearer <token>.
- For security, self-impersonation is blocked.
- JWT carries explicit impersonation claims:
    sub = target username
    imp = true
    act = admin (actor)
- TTL is short-lived and server-capped via environment variables.
"""

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel
from typing import Optional, Dict, Any
from azure.identity import DefaultAzureCredential
from azure.cosmos import CosmosClient, exceptions as cosmos_exceptions
import os, datetime, jwt

# ─────────────────────────── Environment & clients ────────────────────────────
_cosmos_endpoint = os.environ["COSMOS_ENDPOINT"]
_database_name   = os.getenv("COSMOS_DATABASE")
_users_container = os.getenv("USERS_CONTAINER", "users")
_jwt_secret      = os.getenv("JWT_SECRET", "change-me")

# TTL policy (minutes) – overridable via environment; kept conservative by default
def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, "").strip() or default)
    except Exception:
        return default

_TTL_DEFAULT_MIN = _env_int("IMPERSONATE_TTL_DEFAULT_MINUTES", 120)  # 2h
_TTL_MIN_MIN     = _env_int("IMPERSONATE_TTL_MIN_MINUTES", 5)        # 5m
_TTL_MAX_MIN     = _env_int("IMPERSONATE_TTL_MAX_MINUTES", 240)      # 4h

# Cosmos (MSI)
_cosmos_client = CosmosClient(_cosmos_endpoint, credential=DefaultAzureCredential())
_users = _cosmos_client.get_database_client(_database_name).get_container_client(_users_container)

# ─────────────────────────── Models ───────────────────────────────────────────
class ImpersonateIn(BaseModel):
    username: str
    ttl_minutes: Optional[int] = None   # optional; server will clamp

class ImpersonateOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    for_username: str
    actor: str
    expires_in: int

# ─────────────────────────── Helpers ──────────────────────────────────────────
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
    except cosmos_exceptions.CosmosResourceNotFoundError:
        return None

def _is_admin(user_doc: Dict[str, Any]) -> bool:
    return bool(user_doc.get("is_admin", False))

def _clamp_ttl_minutes(requested: Optional[int]) -> int:
    ttl = requested if isinstance(requested, int) and requested > 0 else _TTL_DEFAULT_MIN
    if ttl < _TTL_MIN_MIN:
        ttl = _TTL_MIN_MIN
    if ttl > _TTL_MAX_MIN:
        ttl = _TTL_MAX_MIN
    return ttl

def _make_impersonation_jwt(target_username: str, actor_username: str, ttl_minutes: int) -> str:
    exp = datetime.datetime.utcnow() + datetime.timedelta(minutes=ttl_minutes)
    claims = {
        "sub": target_username,
        "exp": exp,
        # explicit impersonation markers (server & UI can detect if needed)
        "imp": True,
        "act": actor_username,
    }
    return jwt.encode(claims, _jwt_secret, algorithm="HS256")

# ─────────────────────────── Router ───────────────────────────────────────────
router = APIRouter(prefix="/api/auth", tags=["auth"])

@router.post("/admin/impersonate", response_model=ImpersonateOut, status_code=status.HTTP_200_OK)
def admin_impersonate(payload: ImpersonateIn, request: Request):
    """
    Issue a short-lived JWT that logs the admin in as the target user.
    """
    # AuthN
    token = _extract_bearer_token(request)
    actor = _decode_jwt_subject(token)

    # Load actor + authorize
    actor_doc = _get_user_by_username(actor)
    if not actor_doc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    if not _is_admin(actor_doc):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin only")

    # Validate target
    target = (payload.username or "").strip()
    if not target:
        raise HTTPException(status_code=422, detail="username is required")
    if target == actor:
        raise HTTPException(status_code=403, detail="Cannot impersonate your own account")

    target_doc = _get_user_by_username(target)
    if not target_doc:
        raise HTTPException(status_code=404, detail="Target user not found")

    # Build JWT
    ttl = _clamp_ttl_minutes(payload.ttl_minutes)
    access_token = _make_impersonation_jwt(
        target_username=str(target_doc.get("id") or target),
        actor_username=actor,
        ttl_minutes=ttl,
    )

    return ImpersonateOut(
        access_token=access_token,
        token_type="bearer",
        for_username=str(target_doc.get("username") or target),
        actor=actor,
        expires_in=ttl * 60,
    )
