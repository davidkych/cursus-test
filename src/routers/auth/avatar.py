# ── src/routers/auth/avatar.py ────────────────────────────────────────────────
"""
Premium/custom avatar upload endpoint.

Rules:
- Only authenticated users (Bearer JWT).
- Non-admins must be premium members to upload.
- Non-admin uploads must be image/jpeg or image/png AND < 512 KiB.
- Admins have no size/type limits (still stored as-is; Content-Type is set accordingly).
- Upload overwrites the existing avatar blob deterministically at: avatars/<username>.
- On success, marks the user's profile as `profile_pic_type = "custom"` and records
  `avatar_updated_utc` (ISO-8601) for traceability.

`/api/auth/me` is responsible for returning a short-lived SAS URL (`avatar_url`)
when `profile_pic_type == "custom"`.
"""

from __future__ import annotations

import os
import datetime as dt
from typing import Any, Dict

from fastapi import APIRouter, UploadFile, File, HTTPException, Request, status
from pydantic import BaseModel
from azure.identity import DefaultAzureCredential
from azure.cosmos import CosmosClient, exceptions
import jwt

from ._blob import upload_overwrite  # same package (auth)
from .common import apply_default_user_flags  # ensure flags exist if missing

# ─────────────────────────── config / clients ───────────────────────────

_COSMOS_ENDPOINT = os.environ["COSMOS_ENDPOINT"]
_DB_NAME = os.getenv("COSMOS_DATABASE")
_USERS_CONTAINER = os.getenv("USERS_CONTAINER", "users")
_JWT_SECRET = os.getenv("JWT_SECRET", "change-me")

_cosmos = CosmosClient(_COSMOS_ENDPOINT, credential=DefaultAzureCredential())
_users = _cosmos.get_database_client(_DB_NAME).get_container_client(_USERS_CONTAINER)

# 512 KiB limit for premium members
_PREMIUM_MAX_BYTES = 512 * 1024
# Allowed MIME types for premium members
_PREMIUM_ALLOWED_TYPES = {"image/jpeg", "image/png"}


# ─────────────────────────── helpers ───────────────────────────

def _extract_bearer_token(req: Request) -> str:
    auth = req.headers.get("Authorization", "")
    if not auth.lower().startswith("bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing bearer token"
        )
    return auth.split(" ", 1)[1].strip()


def _decode_jwt_subject(token: str) -> str:
    try:
        payload = jwt.decode(token, _JWT_SECRET, algorithms=["HS256"])
        sub = payload.get("sub")
        if not sub:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token (no subject)",
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


def _get_user(username: str) -> Dict[str, Any] | None:
    try:
        return _users.read_item(item=username, partition_key=username)
    except exceptions.CosmosResourceNotFoundError:
        return None


def _persist_user(doc: Dict[str, Any]) -> None:
    # Upsert is idempotent; keep it simple
    _users.upsert_item(doc)


# ─────────────────────────── router ───────────────────────────

router = APIRouter(prefix="/api/auth", tags=["auth"])


class UploadResult(BaseModel):
    ok: bool = True
    # Optionally we could add: avatar_updated_utc: datetime, size: int, content_type: str


@router.post("/avatar", response_model=UploadResult, status_code=status.HTTP_200_OK)
async def upload_avatar(request: Request, file: UploadFile = File(...)) -> UploadResult:
    """
    Upload (and overwrite) the current user's avatar.

    Security / policy:
    - Admins: no limits.
    - Premium members: only JPEG/PNG, < 512 KiB.
    - Others: forbidden.
    """
    # Authenticate
    token = _extract_bearer_token(request)
    username = _decode_jwt_subject(token)

    # Load user doc
    doc = _get_user(username)
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found"
        )

    # Ensure default flags for consistent reads
    apply_default_user_flags(doc)
    is_admin = bool(doc.get("is_admin", False))
    is_premium = bool(doc.get("is_premium_member", False))

    # Authorization gate
    if not (is_admin or is_premium):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Premium membership required for custom avatar",
        )

    # Read the entire payload into memory (avatars are small)
    try:
        content = await file.read()
    finally:
        await file.close()

    content_type = (file.content_type or "").lower().strip()

    if not is_admin:
        # Enforce premium limits
        if content_type not in _PREMIUM_ALLOWED_TYPES:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Only JPEG/PNG are allowed for custom avatars",
            )
        if len(content) > _PREMIUM_MAX_BYTES:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail="Avatar exceeds 512 KiB limit",
            )
    # For admins, accept any content_type/size as-is.

    # Upload/overwrite to blob storage
    try:
        upload_overwrite(username=username, data=content, content_type=content_type or None)
    except Exception as e:
        # Avoid leaking storage details
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to store avatar",
        ) from e

    # Persist profile flag & timestamp (does not touch unrelated fields)
    doc["profile_pic_type"] = "custom"
    doc["avatar_updated_utc"] = dt.datetime.utcnow().isoformat()
    try:
        _persist_user(doc)
    except Exception:
        # Don’t fail the API if storage succeeded; the next /me will still
        # return a SAS (since type is already "custom" in-memory).
        pass

    return UploadResult(ok=True)
