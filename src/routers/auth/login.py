# ── src/routers/auth/login.py ─────────────────────────────────────────────────
"""
User login endpoint.

POST /api/auth/login
Body (JSON):
{
  "username": "johndoe",
  "password": "s3cret!"
}

Success – 200 OK
{
  "access_token": "<JWT>",
  "token_type":   "bearer"
}

Errors
------
401 UNAUTHORIZED – bad credentials
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import jwt
from fastapi import APIRouter, HTTPException, status
from passlib.hash import bcrypt
from pydantic import BaseModel, constr

from azure.identity import DefaultAzureCredential
from azure.cosmos import CosmosClient, exceptions as cosmos_exc

# ─────────────────────────── Cosmos client ────────────────────────────
_COSMOS_ENDPOINT = os.getenv("COSMOS_ENDPOINT")
_COSMOS_DB_NAME  = os.getenv("COSMOS_DATABASE", "cursus-test1db")
_USERS_CONTAINER = os.getenv("USERS_CONTAINER", "users")
_COSMOS_KEY      = os.getenv("COSMOS_KEY")              # optional (local dev)

if not _COSMOS_ENDPOINT:
    raise RuntimeError("COSMOS_ENDPOINT env var is required")

_credential = _COSMOS_KEY or DefaultAzureCredential()
_cosmos      = CosmosClient(_COSMOS_ENDPOINT, _credential)  # type: ignore[arg-type]
_db          = _cosmos.get_database_client(_COSMOS_DB_NAME)
_container   = _db.get_container_client(_USERS_CONTAINER)

# ────────────────────────── JWT settings ──────────────────────────────
_JWT_SECRET = os.getenv("JWT_SECRET")
if not _JWT_SECRET:
    raise RuntimeError("JWT_SECRET env var is required")

_JWT_ALG    = "HS256"
_JWT_LIFETIME_HOURS = int(os.getenv("JWT_LIFETIME_HOURS", "24"))

# ────────────────────────────── models ─────────────────────────────────
class LoginRequest(BaseModel):
    username: constr(min_length=3, max_length=32)  # same regex as register (simplified)
    password: constr(min_length=8, max_length=256)

class LoginResponse(BaseModel):
    access_token: str
    token_type:   str = "bearer"

# ───────────────────────────── router ──────────────────────────────────
router = APIRouter(
    prefix="/api/auth",
    tags=["auth"],
    responses={401: {"description": "Invalid username or password"}},
)

@router.post("/login", response_model=LoginResponse)
def login(payload: LoginRequest) -> LoginResponse:  # noqa: D401
    """Authenticate user and return a JWT access token."""
    user_doc: Optional[dict[str, Any]] = None
    try:
        result = list(
            _container.query_items(
                query="SELECT * FROM c WHERE c.username = @u",
                parameters=[{"name": "@u", "value": payload.username}],
                partition_key=payload.username,       # single-partition query
                enable_cross_partition_query=False,
            )
        )
        if result:
            user_doc = result[0]
    except cosmos_exc.CosmosHttpResponseError:
        # Treat any Cosmos error as an auth failure to avoid information leakage
        pass

    if not user_doc or not bcrypt.verify(payload.password, user_doc["password_hash"]):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid username or password")

    now   = datetime.now(timezone.utc)
    token = jwt.encode(
        {
            "sub": user_doc["id"],
            "username": user_doc["username"],
            "iat": int(now.timestamp()),
            "exp": int((now + timedelta(hours=_JWT_LIFETIME_HOURS)).timestamp()),
        },
        _JWT_SECRET,
        algorithm=_JWT_ALG,
    )

    return LoginResponse(access_token=token)
