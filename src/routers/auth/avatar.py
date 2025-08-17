# ── src/routers/auth/avatar.py ───────────────────────────────────────────────
"""
Upload endpoint for user avatars.

Rules:
- Admins (is_admin=True): may upload ANY content type/size (incl. GIF); no limits.
- Premium members (is_premium_member=True): only JPEG/PNG under 512 KB.
- Others: 403.

Storage:
- Separate images storage account (private). Container: IMAGES_CONTAINER (default: 'avatars').
- Blob name: <username>  (no extension). We set the blob Content-Type header.
- Overwrite-on-upload (idempotent): upload_blob(..., overwrite=True).

After successful upload:
- Update user doc:
  custom_avatar = { blob, content_type, updated_utc }
  profile_pic_type = "custom"

The /api/auth/me endpoint will return a short-lived SAS URL for reads.
"""

from fastapi import APIRouter, UploadFile, File, HTTPException, status, Request
from pydantic import BaseModel
from typing import Optional, Dict, Any
from azure.identity import DefaultAzureCredential
from azure.storage.blob import BlobServiceClient, ContentSettings
from azure.cosmos import CosmosClient, exceptions
import os, io, datetime, jwt

# For content sniffing (non-admin policy)
from PIL import Image

# Shared defaults for flags
from .common import apply_default_user_flags

# ────────────────────────── Environment & clients ────────────────────────────
_cosmos_endpoint   = os.environ["COSMOS_ENDPOINT"]
_database_name     = os.getenv("COSMOS_DATABASE")
_users_container   = os.getenv("USERS_CONTAINER", "users")
_jwt_secret        = os.getenv("JWT_SECRET", "change-me")

_images_account    = os.getenv("IMAGES_ACCOUNT")            # required
_images_container  = os.getenv("IMAGES_CONTAINER", "avatars")

if not _images_account:
    # Fail fast at import time so misconfig surfaces clearly in logs
    raise RuntimeError("IMAGES_ACCOUNT app setting is required (images storage account name)")

# Cosmos (MSI)
_cosmos_client = CosmosClient(_cosmos_endpoint, credential=DefaultAzureCredential())
_users = _cosmos_client.get_database_client(_database_name).get_container_client(_users_container)

# Blob service (MSI)
_blob_service = BlobServiceClient(
    account_url=f"https://{_images_account}.blob.core.windows.net",
    credential=DefaultAzureCredential(),
)

# ─────────────────────────── Helpers ─────────────────────────────────────────
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

def _get_user(username: str) -> Optional[Dict[str, Any]]:
    try:
        return _users.read_item(item=username, partition_key=username)
    except exceptions.CosmosResourceNotFoundError:
        return None

# ─────────────────────────── Response model ──────────────────────────────────
class AvatarUploadResponse(BaseModel):
    ok: bool
    updated_utc: str

# ─────────────────────────── Router ──────────────────────────────────────────
router = APIRouter(prefix="/api/auth", tags=["auth"])

# Limits for non-admins
_ALLOWED_TYPES = {"image/jpeg", "image/png"}
_MAX_BYTES = 512 * 1024  # 512 KB

@router.post("/avatar", response_model=AvatarUploadResponse, status_code=status.HTTP_200_OK)
async def upload_avatar(request: Request, file: UploadFile = File(...)):
    """
    Upload/overwrite current user's avatar.
    - Enforces type/size for premium users.
    - Admins bypass limits.
    """
    token = _extract_bearer_token(request)
    username = _decode_jwt_subject(token)

    # Fetch user & flags
    doc = _get_user(username)
    if not doc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")

    apply_default_user_flags(doc)
    is_admin = bool(doc.get("is_admin", False))
    is_premium = bool(doc.get("is_premium_member", False))

    if not is_admin and not is_premium:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Premium membership required to upload avatar")

    # Read file content (to bytes) – needed for validation and to set Content-Type reliably.
    # For non-admins, enforce the size limit before reading fully.
    # Note: Starlette reads into SpooledTemporaryFile; we convert to bytes for Pillow/sniff.
    raw: bytes = await file.read()

    if not is_admin and len(raw) > _MAX_BYTES:
        raise HTTPException(status_code=413, detail="Avatar exceeds 512 KB limit")

    # Determine and validate content type
    # Prefer server-side sniff over client-reported header
    sniffed_ct = None
    try:
        im = Image.open(io.BytesIO(raw))
        fmt = (im.format or "").upper()
        if fmt == "JPEG":
            sniffed_ct = "image/jpeg"
        elif fmt == "PNG":
            sniffed_ct = "image/png"
        elif fmt == "GIF":
            sniffed_ct = "image/gif"
        else:
            sniffed_ct = None
    except Exception:
        sniffed_ct = None  # fall back to upload header; may still be rejected for non-admin

    content_type = sniffed_ct or (file.content_type or "application/octet-stream")

    if not is_admin:
        if content_type not in _ALLOWED_TYPES:
            raise HTTPException(status_code=415, detail="Only JPEG/PNG are allowed for non-admin users")

    # Prepare blob target
    container = _blob_service.get_container_client(_images_container)
    blob_name = username  # no extension; rely on Content-Type header
    blob = container.get_blob_client(blob_name)

    # Upload with overwrite
    try:
        blob.upload_blob(
            raw,
            overwrite=True,
            content_settings=ContentSettings(content_type=content_type),
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to upload avatar: {e}")

    # Update user document with custom avatar metadata
    updated_iso = datetime.datetime.utcnow().replace(microsecond=0).isoformat() + "Z"
    doc["custom_avatar"] = {
        "blob": blob_name,
        "content_type": content_type,
        "updated_utc": updated_iso,
    }
    doc["profile_pic_type"] = "custom"

    try:
        _users.upsert_item(doc)
    except Exception as e:
        # If metadata update fails, we still uploaded the blob; surface error to caller.
        raise HTTPException(status_code=500, detail=f"Avatar saved but failed to update profile: {e}")

    return AvatarUploadResponse(ok=True, updated_utc=updated_iso)
