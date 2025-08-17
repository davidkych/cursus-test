# ── src/routers/auth/avatar.py ───────────────────────────────────────────────
from fastapi import APIRouter, HTTPException, status, UploadFile, File, Request
from pydantic import BaseModel
from typing import Optional, Tuple, Dict, Any
from azure.cosmos import CosmosClient, exceptions as cosmos_ex
from azure.identity import DefaultAzureCredential
from azure.storage.blob import (
    BlobServiceClient,
    ContentSettings,
    BlobClient,
)
import os
import datetime as dt
import jwt
from .common import apply_default_user_flags  # reuse shared defaults

# ───────────────────────── Environment (fail-fast) ───────────────────────────
_COSMOS_ENDPOINT = os.environ["COSMOS_ENDPOINT"]
_DATABASE_NAME   = os.getenv("COSMOS_DATABASE")
_USERS_CONTAINER = os.getenv("USERS_CONTAINER", "users")
_JWT_SECRET      = os.getenv("JWT_SECRET", "change-me")

_IMAGES_ACCOUNT  = os.getenv("IMAGES_ACCOUNT")         # storage account *name*
_AVATAR_CONTAINER = os.getenv("AVATAR_CONTAINER", "avatars")
_AVATAR_BASE_PATH = os.getenv("AVATAR_BASE_PATH", "users")

if not _IMAGES_ACCOUNT:
    # Infrastructure should set this via Bicep
    raise RuntimeError("IMAGES_ACCOUNT app setting is missing")

# Blob endpoint is derived from the account *name*
_BLOB_ENDPOINT = f"https://{_IMAGES_ACCOUNT}.blob.core.windows.net"

# ───────────────────────── Clients (MSI) ─────────────────────────────────────
_cosmos_client = CosmosClient(_COSMOS_ENDPOINT, credential=DefaultAzureCredential())
_users = _cosmos_client.get_database_client(_DATABASE_NAME).get_container_client(_USERS_CONTAINER)

_blob_service: BlobServiceClient = BlobServiceClient(
    account_url=_BLOB_ENDPOINT,
    credential=DefaultAzureCredential()
)

# ───────────────────────── Helpers ───────────────────────────────────────────
def _extract_bearer_token(req: Request) -> str:
    auth = req.headers.get("Authorization", "")
    if not auth.lower().startswith("bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing bearer token")
    return auth.split(" ", 1)[1].strip()

def _decode_jwt_subject(token: str) -> str:
    try:
        payload = jwt.decode(token, _JWT_SECRET, algorithms=["HS256"])
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
    except cosmos_ex.CosmosResourceNotFoundError:
        return None

def _detect_type_and_ext(upload: UploadFile) -> Tuple[str, str]:
    """
    Returns (content_type, normalized_ext)
    Prefer HTTP content_type; fall back to filename extension.
    """
    ctype = (upload.content_type or "").lower().strip()
    name  = (upload.filename or "").lower().strip()

    ext = ""
    if "." in name:
        ext = name.rsplit(".", 1)[-1]

    # Normalize common types
    if ctype in ("image/jpeg", "image/jpg"):
        return "image/jpeg", "jpg"
    if ctype == "image/png":
        return "image/png", "png"
    if ctype.startswith("image/") and len(ctype.split("/", 1)[-1]) > 0:
        return ctype, (ext or ctype.split("/", 1)[-1])

    # If no/unknown content-type, try extension heuristics
    if ext in ("jpg", "jpeg"):
        return "image/jpeg", "jpg"
    if ext == "png":
        return "image/png", "png"
    if ext in ("gif", "webp", "bmp", "tif", "tiff", "svg"):
        return f"image/{'tiff' if ext in ('tif','tiff') else ext}", ("tiff" if ext in ('tif','tiff') else ext)

    # Fallback: treat as binary (admin path may still allow)
    return (ctype or "application/octet-stream"), (ext or "bin")

def _avatar_blob_path(username: str, file_ext: str) -> str:
    # Stable name for overwrite semantics, e.g. avatars/users/alice/avatar.jpg
    safe_user = username  # username is controlled on our side (id == pk)
    ext = (file_ext or "bin").lstrip(".")
    return f"{_AVATAR_CONTAINER}/{_AVATAR_BASE_PATH}/{safe_user}/avatar.{ext}"

def _blob_client_for_path(blob_path: str) -> BlobClient:
    # blob_path is "container/dir/dir/filename.ext"
    parts = blob_path.split("/", 1)
    container = parts[0]
    name = parts[1] if len(parts) > 1 else ""
    return _blob_service.get_blob_client(container=container, blob=name)

# ───────────────────────── API Router ────────────────────────────────────────
router = APIRouter(
    prefix="/api/auth",
    tags=["auth"]
)

class UploadResponse(BaseModel):
    ok: bool

@router.post("/avatar", response_model=UploadResponse, status_code=status.HTTP_200_OK)
async def upload_avatar(request: Request, file: UploadFile = File(...)):
    """
    Upload a new avatar for the current user.

    Eligibility:
      - is_premium_member == True  → allowed types: jpg/jpeg/png, size < 512 KiB
      - is_admin == True           → any image/* type, no size limit
      - otherwise                  → 403

    On success:
      - Uploads/overwrites blob: avatars/users/{username}/avatar.<ext>
      - Updates user doc: profile_pic_type='custom', avatar_blob, avatar_content_type, avatar_updated_utc
      - Returns { ok: true }  (client should call /me to get fresh SAS URL)
    """
    token = _extract_bearer_token(request)
    username = _decode_jwt_subject(token)

    user = _get_user(username)
    if not user:
      raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")

    apply_default_user_flags(user)  # ensure flags exist

    is_admin   = bool(user.get("is_admin", False))
    is_premium = bool(user.get("is_premium_member", False))

    if not (is_admin or is_premium):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Premium membership required to upload an avatar")

    content_type, ext = _detect_type_and_ext(file)

    # ── Validation rules
    if is_admin:
        # Any image type, no size limit — minimal guard: must be image/* or we accept if filename suggests image
        if not (content_type.startswith("image/") or ext in ("jpg","jpeg","png","gif","webp","bmp","tiff","svg")):
            raise HTTPException(status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail="Unsupported file type (expecting an image)")
        data_stream = file.file  # stream directly to Azure (no buffering)
    else:
        # Premium users: only jpeg/png, size < 512 KiB
        if content_type not in ("image/jpeg", "image/jpg", "image/png") and ext not in ("jpg", "jpeg", "png"):
            raise HTTPException(status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail="Only JPG/PNG allowed for premium users")
        raw = await file.read(512 * 1024 + 1)  # read up to 512 KiB + 1 byte
        if len(raw) > 512 * 1024:
            raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="Max file size is 512 KiB")
        # normalize content-type for jpg
        if ext in ("jpg", "jpeg"):
            content_type = "image/jpeg"
            ext = "jpg"
        elif ext == "png":
            content_type = "image/png"
        # Upload from memory buffer
        import io
        data_stream = io.BytesIO(raw)

    # ── Build stable blob path and upload (overwrite)
    blob_path = _avatar_blob_path(username, ext)
    blob = _blob_client_for_path(blob_path)

    try:
        # Ensure container exists (infra should create it; this is idempotent)
        # NOTE: We don't attempt to create here to keep infra-driven IaC truth.
        # Upload with overwrite=True
        blob.upload_blob(
            data=data_stream,
            overwrite=True,
            content_settings=ContentSettings(content_type=content_type)
        )
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to upload avatar: {e}")

    # ── Update user doc
    user["profile_pic_type"]  = "custom"
    user["avatar_blob"]       = blob_path  # includes container prefix
    user["avatar_content_type"] = content_type
    user["avatar_updated_utc"]  = dt.datetime.utcnow().isoformat() + "Z"

    try:
        _users.upsert_item(user)
    except Exception as e:
        # Roll forward: avatar on storage is fine; doc update should not block user
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Avatar uploaded but failed to update profile: {e}")

    return UploadResponse(ok=True)
