# ── src/routers/auth/me.py ───────────────────────────────────────────────────
from fastapi import APIRouter, HTTPException, status, Request
from pydantic import BaseModel, EmailStr
from typing import Optional, Literal, Any, Dict
from azure.cosmos import CosmosClient, exceptions
from azure.identity import DefaultAzureCredential
import os, datetime, jwt

# ⟨NEW⟩ blob SAS helpers
from azure.storage.blob import (
    BlobServiceClient,
    generate_blob_sas,
    BlobSasPermissions,
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

# ───────────────────────── Blob config (optional) ─────────────────
# If these are missing, we simply won't return avatar_sas_url (backward compatible).
_IMAGES_ACCOUNT           = os.getenv("IMAGES_ACCOUNT")            # storage account *name*
_AVATAR_SAS_TTL_MINUTES   = int(os.getenv("AVATAR_SAS_TTL_MINUTES", "5"))

_BLOB_ENDPOINT: Optional[str] = None
_blob_service: Optional[BlobServiceClient] = None
if _IMAGES_ACCOUNT:
    _BLOB_ENDPOINT = f"https://{_IMAGES_ACCOUNT}.blob.core.windows.net"
    _blob_service  = BlobServiceClient(account_url=_BLOB_ENDPOINT, credential=DefaultAzureCredential())

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

    # ⟨NEW⟩ short-lived read URL for the custom avatar (only when available)
    avatar_sas_url: Optional[str] = None

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

def _mint_avatar_read_sas(avatar_blob_path: str) -> Optional[str]:
    """
    Build a user-delegation SAS URL for the given blob path.
    avatar_blob_path is expected to include the container prefix, e.g.:
      'avatars/users/alice/avatar.jpg'
    Returns an absolute URL or None on any issue.
    """
    try:
        if not (_blob_service and _IMAGES_ACCOUNT and _BLOB_ENDPOINT and avatar_blob_path):
            return None

        # Split "container/dir/file" into container + blob name
        if "/" not in avatar_blob_path:
            return None
        container, blob_name = avatar_blob_path.split("/", 1)

        # Build time window (start slightly in the past to avoid clock skew)
        now = datetime.datetime.utcnow().replace(tzinfo=datetime.timezone.utc)
        start  = now - datetime.timedelta(minutes=1)
        expiry = now + datetime.timedelta(minutes=_AVATAR_SAS_TTL_MINUTES or 5)

        # User delegation key + SAS (read-only)
        udk = _blob_service.get_user_delegation_key(start, expiry)
        sas = generate_blob_sas(
            account_name=_IMAGES_ACCOUNT,
            container_name=container,
            blob_name=blob_name,
            user_delegation_key=udk,
            permission=BlobSasPermissions(read=True),
            expiry=expiry,
            start=start,
        )

        return f"{_BLOB_ENDPOINT}/{container}/{blob_name}?{sas}"
    except Exception:
        # Never fail /me because SAS minting had an issue
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
    If a custom avatar exists, returns a short-lived 'avatar_sas_url'.
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

    # ⟨NEW⟩ Mint a short-lived read SAS URL if custom avatar exists
    if doc.get("profile_pic_type") == "custom":
        avatar_blob_path = doc.get("avatar_blob")  # e.g. 'avatars/users/alice/avatar.jpg'
        sas_url = _mint_avatar_read_sas(avatar_blob_path) if avatar_blob_path else None
        if sas_url:
            payload["avatar_sas_url"] = sas_url

    # ⟨NEW⟩ Opportunistic backfill: persist defaults if flags were missing
    if missing_flags:
        try:
            _users.upsert_item(doc)
        except Exception:
            # Never fail the /me call because of persistence issues
            pass

    return payload
