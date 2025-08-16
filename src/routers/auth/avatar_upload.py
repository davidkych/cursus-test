# ── src/routers/auth/avatar_upload.py ─────────────────────────────────────────
"""
Upload a custom avatar for the current user.

Rules:
- Only allowed if the user is premium OR admin.
- For non-admins: only jpg/jpeg/png under 512 KB (client should pre-validate;
  backend enforces again).
- Admins: bypass both size and type restrictions (can upload GIF or others,
  no size cap here — still subject to App Service request limits).

Storage:
- Uses a **separate** Storage Account (RBAC via MSI) and a public-read container.
- App settings (set by GitHub Actions):
  AVATAR_STORAGE_ACCOUNT_NAME
  AVATAR_CONTAINER_NAME      (default: "avatars")
  AVATAR_PUBLIC_BASE         (optional, e.g. "https://<acct>.blob.core.windows.net/avatars")

Response:
- Returns the same shape as /api/auth/me plus:
  - profile_pic_type="custom"
  - profile_pic_url="<public url>"
  - (server keeps profile_pic_blob internally)
Note: /api/auth/me will be updated to include `profile_pic_url` as optional.
"""

import os
import datetime
from typing import Any, Dict, Optional

from fastapi import APIRouter, UploadFile, File, HTTPException, Request, status
from azure.identity import DefaultAzureCredential
from azure.cosmos import CosmosClient, exceptions
from azure.storage.blob import BlobServiceClient, ContentSettings
import jwt

from .common import apply_default_user_flags

# ─────────────────────────── env & clients ───────────────────────────
_cosmos_endpoint = os.environ["COSMOS_ENDPOINT"]
_database_name   = os.getenv("COSMOS_DATABASE")
_users_container = os.getenv("USERS_CONTAINER", "users")
_jwt_secret      = os.getenv("JWT_SECRET", "change-me")

_avatar_account  = os.getenv("AVATAR_STORAGE_ACCOUNT_NAME") or ""
_avatar_container = os.getenv("AVATAR_CONTAINER_NAME", "avatars")
_avatar_public_base = (os.getenv("AVATAR_PUBLIC_BASE") or "").rstrip("/")

if not _avatar_account:
    # We intentionally fail early: avatars feature needs its own account.
    raise RuntimeError("AVATAR_STORAGE_ACCOUNT_NAME app setting is required for avatar uploads")

# Cosmos (MSI)
_cosmos = CosmosClient(_cosmos_endpoint, credential=DefaultAzureCredential())
_users = _cosmos.get_database_client(_database_name).get_container_client(_users_container)

# Storage (MSI)
_blob_service = BlobServiceClient(
    account_url=f"https://{_avatar_account}.blob.core.windows.net",
    credential=DefaultAzureCredential(),
)
_container_client = _blob_service.get_container_client(_avatar_container)

# ─────────────────────────── helpers ────────────────────────────────
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

def _build_public_url(blob_path: str) -> str:
    if _avatar_public_base:
        return f"{_avatar_public_base}/{blob_path}"
    return f"https://{_avatar_account}.blob.core.windows.net/{_avatar_container}/{blob_path}"

_ALLOWED_NON_ADMIN_MIME = {"image/jpeg", "image/jpg", "image/png"}
_MAX_BYTES_NON_ADMIN = 512 * 1024  # 512 KiB

def _guess_ext(filename: str, content_type: str) -> str:
    fn = (filename or "").lower()
    if fn.endswith(".jpg") or fn.endswith(".jpeg"):
        return ".jpg" if fn.endswith(".jpg") else ".jpeg"
    if fn.endswith(".png"):
        return ".png"
    if fn.endswith(".gif"):
        return ".gif"
    # Fall back to content-type
    if content_type == "image/jpeg":
        return ".jpg"
    if content_type == "image/png":
        return ".png"
    if content_type == "image/gif":
        return ".gif"
    return ""  # unknown/other

# ─────────────────────────── router ─────────────────────────────────
router = APIRouter(prefix="/api/auth", tags=["auth"])

@router.post("/avatar")
async def upload_avatar(request: Request, file: UploadFile = File(...)):
    """
    Upload a custom avatar for the authenticated user.
    Enforces premium/admin gating and validation rules described above.
    """
    # AuthN
    token = _extract_bearer_token(request)
    username = _decode_jwt_subject(token)

    # User lookup
    doc = _get_user(username)
    if not doc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")

    # Flags (defaults if missing)
    apply_default_user_flags(doc)
    is_admin = bool(doc.get("is_admin", False))
    is_premium = bool(doc.get("is_premium_member", False))

    # Eligibility
    if not (is_admin or is_premium):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Premium membership required to upload an avatar")

    # Read file (into memory; avatars are small)
    try:
        content = await file.read()
    finally:
        await file.close()

    ctype = file.content_type or "application/octet-stream"
    size = len(content)

    # Non-admin constraints
    if not is_admin:
        if ctype.lower() not in _ALLOWED_NON_ADMIN_MIME:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Only JPG or PNG images are allowed for non-admin users",
            )
        if size > _MAX_BYTES_NON_ADMIN:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Avatar file exceeds 512 KB limit",
            )

    # Blob name (stable path; overwrite on re-upload)
    ext = _guess_ext(file.filename, ctype)
    blob_path = f"{username}/avatar{ext}"
    public_url = _build_public_url(blob_path)

    # Upload (idempotent overwrite)
    try:
        _container_client.upload_blob(
            name=blob_path,
            data=content,
            overwrite=True,
            content_settings=ContentSettings(
                content_type=ctype,
                cache_control="public, max-age=86400"
            ),
        )
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Upload failed: {e}")

    # Update user doc
    doc["profile_pic_type"] = "custom"
    doc["profile_pic_url"] = public_url
    doc["profile_pic_blob"] = blob_path
    # Maintain id/username consistency
    doc.setdefault("id", username)
    doc.setdefault("username", username)
    # Touch an 'updated' timestamp (optional; doesn't affect client)
    doc["updated"] = datetime.datetime.utcnow().isoformat() + "Z"

    try:
        _users.upsert_item(doc)
    except Exception as e:
        # Roll forward anyway; avatar is uploaded, but doc update failed
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Profile update failed: {e}")

    # Build response mirroring /api/auth/me (plus profile_pic_url)
    payload: Dict[str, Any] = {
        "id":               doc.get("id") or username,
        "username":         doc.get("username") or username,
        "email":            doc.get("email"),
        "created":          doc.get("created"),
        "gender":           doc.get("gender"),
        "dob":              doc.get("dob"),
        "country":          doc.get("country"),
        "profile_pic_id":   int(doc.get("profile_pic_id", 1)),
        "profile_pic_type": doc.get("profile_pic_type", "default"),
        "profile_pic_url":  doc.get("profile_pic_url"),
        "is_admin":          bool(doc.get("is_admin", False)),
        "is_premium_member": bool(doc.get("is_premium_member", False)),
    }
    if isinstance(doc.get("login_context"), dict):
        payload["login_context"] = doc["login_context"]

    return payload
