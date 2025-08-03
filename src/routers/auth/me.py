# ── src/routers/auth/me.py ────────────────────────────────────────────────────
"""
Current-user endpoint.

GET /api/auth/me
Headers:
  Authorization: Bearer <JWT>

Success – 200 OK
{
  "id":              "…",
  "username":        "johndoe",
  "email":           "john@example.com",
  "profile_pic_id":  5,
  "profile_pic_type":"default",
  "gender":          "male",
  "dob":             "1990-01-31",
  "country":         "GB",
  "created_at":      "2025-08-03T12:34:56.789Z",
  "updated_at":      "2025-08-03T12:34:56.789Z"
}

Errors
------
401 UNAUTHORIZED – missing / invalid / expired token
"""
from __future__ import annotations

import os
from typing import Any, Optional

import jwt
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, EmailStr
from azure.cosmos import CosmosClient
from azure.identity import DefaultAzureCredential

# ───────────────────────────── settings ──────────────────────────────────────
_COSMOS_ENDPOINT = os.getenv("COSMOS_ENDPOINT")
_COSMOS_DB_NAME  = os.getenv("COSMOS_DATABASE", "cursus-test1db")
_USERS_CONTAINER = os.getenv("USERS_CONTAINER", "users")
_COSMOS_KEY      = os.getenv("COSMOS_KEY")             # optional (local dev)

if not _COSMOS_ENDPOINT:
    raise RuntimeError("COSMOS_ENDPOINT env var is required")

_JWT_SECRET = os.getenv("JWT_SECRET")
if not _JWT_SECRET:
    raise RuntimeError("JWT_SECRET env var is required")

_JWT_ALG = "HS256"

# ─────────────────────────── Cosmos client ───────────────────────────────────
_credential = _COSMOS_KEY or DefaultAzureCredential()
_cosmos      = CosmosClient(_COSMOS_ENDPOINT, _credential)  # type: ignore[arg-type]
_db          = _cosmos.get_database_client(_COSMOS_DB_NAME)
_container   = _db.get_container_client(_USERS_CONTAINER)

# ─────────────────────────── auth helpers ────────────────────────────────────
auth_scheme = HTTPBearer(auto_error=False)

def _get_current_user(
    creds: Optional[HTTPAuthorizationCredentials] = Depends(auth_scheme),
) -> dict[str, Any]:
    if not creds or creds.scheme.lower() != "bearer":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")

    token = creds.credentials
    try:
        payload = jwt.decode(token, _JWT_SECRET, algorithms=[_JWT_ALG])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

    username = payload.get("username")
    if not username:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload")

    # Single-partition point read (fast)
    try:
        user_doc = _container.read_item(item=username, partition_key=username)
    except Exception:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")

    return user_doc

# ───────────────────────────── models ────────────────────────────────────────
class UserPublic(BaseModel):
    id:              str
    username:        str
    email:           EmailStr
    profile_pic_id:  Optional[int] = None
    profile_pic_type:str = "default"
    gender:          Optional[str] = None
    dob:             Optional[str] = None
    country:         Optional[str] = None
    created_at:      str
    updated_at:      str

# ───────────────────────────── router ────────────────────────────────────────
router = APIRouter(prefix="/api/auth", tags=["auth"])

@router.get("/me", response_model=UserPublic)
def me(current_user: dict[str, Any] = Depends(_get_current_user)) -> UserPublic:  # noqa: D401
    """Return the authenticated user's public profile."""
    public = {k: v for k, v in current_user.items() if k != "password_hash"}
    return UserPublic(**public)
