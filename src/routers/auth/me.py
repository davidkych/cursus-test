# ── src/routers/auth/me.py ───────────────────────────────────────────────────
from fastapi import APIRouter, HTTPException, status, Request
from pydantic import BaseModel, EmailStr
from typing import Optional, Literal, Any, Dict
from azure.cosmos import CosmosClient, exceptions
from azure.identity import DefaultAzureCredential
import os, datetime, jwt

# ⟨NEW⟩ storage for short-lived SAS
from azure.storage.blob import (
    BlobServiceClient,
    BlobSasPermissions,
    generate_blob_sas,
)

# ⟨NEW⟩ shared defaults for user flags
from .common import apply_default_user_flags

# ───────────────────────── Cosmos setup ──────────────────────────
_cosmos_endpoint = os.environ["COSMOS_ENDPOINT"]
_database_name   = os.getenv("COSMOS_DATABASE")
_users_container = os.getenv("USERS_CONTAINER", "users")
_jwt_secret      = os.getenv("JWT_SECRET", "change-me")

_client = CosmosClient(
    _cosmos_endpoint,
    credential=DefaultAzureCredential()
)
_users = _client.get_database_client(_database_name).get_container_client(_users_container)

# ⟨NEW⟩ Images storage (optional – only used when returning custom avatar SAS)
_images_account   = os.getenv("IMAGES_ACCOUNT")             # e.g., from web-app.yml
_images_container = os.getenv("IMAGES_CONTAINER", "avatars")

_blob_service: Optional[BlobServiceClient] = None
if _images_account:
    _blob_service = BlobServiceClient(
        account_url=f"https://{_images_account}.blob.core.windows.net",
        credential=DefaultAzureCredential(),
    )

# Simple in-memory cache for a user delegation key (avoid per-request fetch)
# We cache only for the current process lifetime and refresh proactively.
_udk_cache: Dict[str, Any] = {"key": None, "expires_at": None}

def _get_user_delegation_key() -> Optional[Any]:
    """
    Get or refresh a User Delegation Key for generating SAS.
    Returns None if images storage is not configured or MSI lacks permissions.
    """
    global _udk_cache
    if not _blob_service:
        return None

    now = datetime.datetime.utcnow()
    # Refresh if missing or expiring within 5 minutes
    exp_at: Optional[datetime.datetime] = _udk_cache.get("expires_at")
    if _udk_cache.get("key") is not None and exp_at and exp_at - now > datetime.timedelta(minutes=5):
        return _udk_cache["key"]

    try:
        start  = now - datetime.timedelta(minutes=5)
        expire = now + datetime.timedelta(hours=1)
        key = _blob_service.get_user_delegation_key(start, expire)
        _udk_cache["key"] = key
        _udk_cache["expires_at"] = expire
        return key
    except Exception:
        # RBAC not granted yet or storage not reachable
        return None

# ────────────────────────── Response models ───────────────────────
class LoginContext(BaseModel):
    # All optional; we only return what we have
    last_login_utc: Optional[datetime.datetime] = None
    ip: Optional[str] = None
    ua: Optional[Dict[str, Any]] = None          # parsed UA (browser/os/device flags)
    locale: Optional[Dict[str, Optional[str]]] = None  # client + accept_language
    timezone: Optional[str] = None
    geo: Optional[Dict[str, Any]] = None         # { country_iso2, source }

class UserMeOut(BaseModel):
    id: str
    username: str
    email: EmailStr
    created: datetime.datetime

    # Extended profile fields (optional for forward compatibility)
    gender: Optional[Literal["male", "female"]] = None
    dob: Optional[datetime.date] = None
    country: Optional[str] = None
    profile_pic_id: Optional[int] = 1
    profile_pic_type: Optional[Literal["default", "custom"]] = "default"

    # ⟨NEW⟩ account flags (default False for backward compatibility)
    is_admin: bool = False
    is_premium_member: bool = False

    # ⟨NEW⟩ latest login telemetry snapshot (optional)
    login_context: Optional[LoginContext] = None

    # ⟨NEW⟩ short-lived SAS URL for custom avatar (optional)
    avatar_url: Optional[str] = None

# ──────────────────────────── Helpers ────────────────────────────
def _extract_bearer_token(req: Request) -> str:
    auth = req.headers.get("Authorization", "")
    if not auth.lower().startswith("bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing bearer token")
    return auth.split(" ", 1)[1].strip()

def _decode_jwt(token: str) -> str:
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

def _get_user_by_username(username: str):
    """Fast point-read via id == partition key (/username)."""
    try:
        return _users.read_item(item=username, partition_key=username)
    except exceptions.CosmosResourceNotFoundError:
        return None

def _build_avatar_sas_url(blob_name: str) -> Optional[str]:
    """
    Return a read-only SAS URL valid for ~10 minutes for the given blob name.
    Requires IMAGES_ACCOUNT + MSI RBAC (Storage Blob Data Contributor).
    """
    if not _blob_service or not _images_account or not _images_container:
        return None

    # Acquire or refresh a user delegation key
    udk = _get_user_delegation_key()
    if not udk:
        return None

    # Mint SAS for this specific blob
    expiry = datetime.datetime.utcnow() + datetime.timedelta(minutes=10)
    try:
        sas = generate_blob_sas(
            account_name=_images_account,
            container_name=_images_container,
            blob_name=blob_name,
            user_delegation_key=udk,
            permission=BlobSasPermissions(read=True),
            expiry=expiry,
        )
        return f"https://{_images_account}.blob.core.windows.net/{_images_container}/{blob_name}?{sas}"
    except Exception:
        return None

# ──────────────────────────── Router ────────────────────────────
router = APIRouter(
    prefix="/api/auth",
    tags=["auth"]
)

@router.get("/me", response_model=UserMeOut)
def me(request: Request):
    """
    Current-user profile endpoint.
    Requires: Authorization: Bearer <JWT>  (HS256 signed with JWT_SECRET).
    Returns extended 'login_context' (latest snapshot) and the new
    'is_admin' / 'is_premium_member' flags. Missing flags default to False.
    Opportunistically persists defaults if flags were missing.
    If a custom avatar exists, returns a short-lived SAS URL (avatar_url).
    """
    token = _extract_bearer_token(request)
    username = _decode_jwt(token)

    doc = _get_user_by_username(username)
    if not doc:
        # token is valid but user doc is gone → treat as unauthorized
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")

    # ⟨NEW⟩ ensure flags exist (in-memory defaults for response)
    missing_flags = ("is_admin" not in doc) or ("is_premium_member" not in doc)
    apply_default_user_flags(doc)

    # Build a safe profile payload (omit hashed password, etc.)
    # Note: pydantic will coerce ISO strings (created/dob) into datetime/date.
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
        # ⟨NEW⟩ flags included in response (default False)
        "is_admin":          bool(doc.get("is_admin", False)),
        "is_premium_member": bool(doc.get("is_premium_member", False)),
    }

    # ⟨NEW⟩ latest login telemetry snapshot (optional)
    if "login_context" in doc and isinstance(doc["login_context"], dict):
        payload["login_context"] = doc["login_context"]

    # ⟨NEW⟩ Add a short-lived SAS for custom avatars (if configured & present)
    if payload.get("profile_pic_type") == "custom":
        meta = doc.get("custom_avatar")
        blob_name = meta.get("blob") if isinstance(meta, dict) else None
        if isinstance(blob_name, str) and blob_name:
            sas_url = _build_avatar_sas_url(blob_name)
            if sas_url:
                payload["avatar_url"] = sas_url

    # ⟨NEW⟩ Opportunistic backfill: persist defaults if flags were missing
    if missing_flags:
        try:
            _users.upsert_item(doc)
        except Exception:
            # Never fail the /me call because of persistence issues
            pass

    return payload
