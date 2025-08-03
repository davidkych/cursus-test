# ── src/routers/auth/register.py ─────────────────────────────────────────────
"""
User registration endpoint.

POST /api/auth/register
Body (JSON):
{
  "username":          "johndoe",
  "email":             "john@example.com",
  "password":          "s3cret!",
  "profile_pic_id":    5,                     # optional
  "profile_pic_type":  "default",             # optional: 'default' | 'custom'
  "gender":            "male",                # optional
  "dob":               "1990-01-31",          # optional (ISO - YYYY-MM-DD)
  "country":           "GB"                   # optional (ISO-3166-1 alpha-2)
}

Success - 201 CREATED
Returns the stored record (sans password hash).

Errors
------
409 CONFLICT   – username or e-mail already taken
400 BAD REQUEST – validation errors
"""
from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, EmailStr, Field, constr
from passlib.hash import bcrypt

from azure.identity import DefaultAzureCredential
from azure.cosmos import CosmosClient, exceptions as cosmos_exc

# ─────────────────────────── Cosmos client ────────────────────────────
_COSMOS_ENDPOINT = os.getenv("COSMOS_ENDPOINT")
_COSMOS_DB_NAME  = os.getenv("COSMOS_DATABASE", "cursus-test1db")
_USERS_CONTAINER = os.getenv("USERS_CONTAINER", "users")
_COSMOS_KEY      = os.getenv("COSMOS_KEY")             # optional (local dev)

if not _COSMOS_ENDPOINT:
    raise RuntimeError("COSMOS_ENDPOINT env var is required")

_credential = _COSMOS_KEY or DefaultAzureCredential()
_cosmos      = CosmosClient(_COSMOS_ENDPOINT, _credential)  # type: ignore[arg-type]
_db          = _cosmos.get_database_client(_COSMOS_DB_NAME)
_container   = _db.get_container_client(_USERS_CONTAINER)

# ────────────────────────────── models ─────────────────────────────────
UsernameStr = constr(regex=r"^[A-Za-z0-9_\-\.]{3,32}$")

class RegisterRequest(BaseModel):
    username:          UsernameStr
    email:             EmailStr
    password:          constr(min_length=8, max_length=256)
    # optional extras
    profile_pic_id:    Optional[int]   = Field(None, ge=1, le=999)
    profile_pic_type:  Optional[str]   = Field("default", regex="^(default|custom)$")
    gender:            Optional[str]   = Field(None, regex="^(male|female|other)?$")
    dob:               Optional[str]   = Field(None, regex=r"^\d{4}-\d{2}-\d{2}$")
    country:           Optional[str]   = Field(None, min_length=2, max_length=2)

class UserPublic(BaseModel):
    id:              str
    username:        str
    email:           EmailStr
    profile_pic_id:  Optional[int]  = None
    profile_pic_type: str = "default"
    gender:          Optional[str]  = None
    dob:             Optional[str]  = None
    country:         Optional[str]  = None
    created_at:      str
    updated_at:      str

# ───────────────────────────── router ──────────────────────────────────
router = APIRouter(
    prefix="/api/auth",
    tags=["auth"],
    responses={409: {"description": "Username or e-mail already taken"}},
)

@router.post("/register", response_model=UserPublic, status_code=status.HTTP_201_CREATED)
def register(payload: RegisterRequest) -> UserPublic:  # noqa: D401
    """Create a new user account."""
    now_iso = datetime.now(timezone.utc).isoformat()

    user_doc = {
        "id":             str(uuid.uuid4()),
        "username":       payload.username,
        "email":          payload.email.lower(),
        "password_hash":  bcrypt.hash(payload.password),
        "profile_pic_id": payload.profile_pic_id,
        "profile_pic_type": payload.profile_pic_type or "default",
        "gender":         payload.gender,
        "dob":            payload.dob,
        "country":        payload.country.upper() if payload.country else None,
        "created_at":     now_iso,
        "updated_at":     now_iso,
    }

    try:
        _container.create_item(user_doc, partition_key=user_doc["username"])
    except cosmos_exc.CosmosHttpResponseError as exc:
        # 409 from unique key constraint
        if exc.status_code == 409:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Username or e-mail already taken",
            ) from exc
        raise  # propagate other Cosmos errors

    # Strip sensitive fields before returning
    user_public = {k: v for k, v in user_doc.items() if k != "password_hash"}
    return UserPublic(**user_public)
