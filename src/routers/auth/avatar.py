# ── src/routers/auth/avatar.py ────────────────────────────────────────────────
from fastapi import APIRouter, HTTPException, status, Request, UploadFile, File
from pydantic import BaseModel
from typing import Optional, Any, Dict, List
from azure.identity import DefaultAzureCredential
from azure.cosmos import CosmosClient, exceptions
from azure.storage.blob import (
    BlobServiceClient,
    ContentSettings,
    BlobSasPermissions,
    generate_blob_sas,
)
import os, io, datetime as dt, jwt

# ───────────────────────── Environment / config ─────────────────────────
_cosmos_endpoint   = os.environ["COSMOS_ENDPOINT"]
_database_name     = os.getenv("COSMOS_DATABASE")
_users_container   = os.getenv("USERS_CONTAINER", "users")

_images_account    = os.getenv("IMAGES_ACCOUNT_NAME")
_images_container  = os.getenv("IMAGES_CONTAINER", "avatars")
_images_blob_ep    = os.getenv("IMAGES_BLOB_ENDPOINT") or f"https://{_images_account}.blob.core.windows.net/"

_avatar_max_kib    = int(os.getenv("AVATAR_MAX_KIB", "512"))
_avatar_types_csv  = os.getenv("AVATAR_ALLOWED_TYPES", "image/jpeg,image/jpg,image/png")
_avatar_types      = [t.strip().lower() for t in _avatar_types_csv.split(",") if t.strip()]
_require_premium   = os.getenv("AVATAR_REQUIRE_PREMIUM", "1") == "1"

_jwt_secret        = os.getenv("JWT_SECRET", "change-me")

# Normalize blob base URL (ensure trailing slash)
if not _images_blob_ep.endswith("/"):
    _images_blob_ep += "/"

# ───────────────────────── Clients (MSI) ─────────────────────────────
_cred = DefaultAzureCredential()
_cosmos_client = CosmosClient(_cosmos_endpoint, credential=_cred)
_users = _cosmos_client.get_database_client(_database_name).get_container_client(_users_container)

_blob_service = BlobServiceClient(account_url=f"https://{_images_account}.blob.core.windows.net", credential=_cred)
_container_client = _blob_service.get_container_client(_images_container)

# ───────────────────────── Auth helpers ──────────────────────────────
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

# ───────────────────────── SAS helper ───────────────────────────────
def _make_read_sas_url(blob_name: str, minutes: int = 60) -> Dict[str, str]:
    """
    Create a user-delegation SAS URL (MSI-based) to read a single blob.
    """
    now = dt.datetime.utcnow()
    start = now - dt.timedelta(minutes=5)         # clock skew tolerance
    expiry = now + dt.timedelta(minutes=minutes)

    udk = _blob_service.get_user_delegation_key(key_start_time=start, key_expiry_time=expiry)

    sas = generate_blob_sas(
        account_name=_images_account,
        container_name=_images_container,
        blob_name=blob_name,
        user_delegation_key=udk,
        permission=BlobSasPermissions(read=True),
        expiry=expiry,
        start=start,
    )
    return {
        "url": f"{_images_blob_ep}{_images_container}/{blob_name}?{sas}",
        "expiresAt": expiry.replace(microsecond=0).isoformat() + "Z",
    }

# ───────────────────────── Router ────────────────────────────────────
router = APIRouter(
    prefix="/api/auth",
    tags=["auth"]
)

# Response model for SAS URL
class AvatarUrlOut(BaseModel):
    url: str
    expiresAt: str

# ───────────────────────── Upload endpoint ───────────────────────────
@router.post("/avatar", status_code=status.HTTP_204_NO_CONTENT)
async def upload_avatar(request: Request, file: UploadFile = File(...)):
    """
    Upload/replace the caller's avatar.

    Rules:
    - Admins: no type/size limit.
    - Otherwise (premium required): content-type must be in AVATAR_ALLOWED_TYPES; size < AVATAR_MAX_KIB.
    - Overwrites previous avatar.
    - Stores metadata on the user document: profile_pic_type='custom', avatar_blob='avatars/<username>'
    """
    if not file or not file.filename:
        raise HTTPException(status_code=400, detail="No file provided")

    # Identify caller
    token = _extract_bearer_token(request)
    username = _decode_jwt_subject(token)
    doc = _get_user(username)
    if not doc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")

    is_admin = bool(doc.get("is_admin", False))
    is_premium = bool(doc.get("is_premium_member", False))

    # Gate: premium or admin
    if _require_premium and (not is_admin) and (not is_premium):
        raise HTTPException(status_code=403, detail="Premium membership required to upload avatar")

    # Validate for non-admin
    content_type = (file.content_type or "").lower()
    if not is_admin:
        if content_type not in _avatar_types:
            raise HTTPException(status_code=415, detail=f"Unsupported media type: {content_type}")
        # Enforce size by reading into memory up to limit+1
        max_bytes = _avatar_max_kib * 1024
        data = await file.read()  # small (<512KiB) okay to buffer
        if len(data) > max_bytes:
            raise HTTPException(status_code=413, detail=f"File too large (max {_avatar_max_kib} KiB)")
        data_stream = io.BytesIO(data)
    else:
        # Admin: stream directly (no limits)
        data_stream = file.file

    # Blob name (no extension needed; content-type is preserved)
    blob_name = f"{username}"

    try:
        _container_client.upload_blob(
            name=blob_name,
            data=data_stream,
            overwrite=True,
            content_settings=ContentSettings(content_type=content_type or "application/octet-stream"),
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Upload failed: {e}")

    # Update user document to point to custom avatar
    doc["profile_pic_type"] = "custom"
    doc["avatar_blob"] = blob_name

    try:
        _users.upsert_item(doc)
    except Exception:
        # Do not fail the upload if metadata write has an issue
        pass

    return  # 204

# ───────────────────────── SAS URL endpoint ─────────────────────────
@router.get("/avatar/url", response_model=AvatarUrlOut)
def get_avatar_sas_url(request: Request):
    """
    Return a short-lived SAS URL for the caller's avatar.
    404 if the user has not uploaded a custom avatar yet.
    """
    token = _extract_bearer_token(request)
    username = _decode_jwt_subject(token)
    doc = _get_user(username)
    if not doc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")

    if doc.get("profile_pic_type") != "custom" or not doc.get("avatar_blob"):
        raise HTTPException(status_code=404, detail="No custom avatar")

    try:
        return _make_read_sas_url(doc["avatar_blob"], minutes=60)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create SAS URL: {e}")
