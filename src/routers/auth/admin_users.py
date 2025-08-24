# ── src/routers/auth/admin_users.py ───────────────────────────────────────────
"""
Admin-only user listing (read-only).

GET /api/auth/admin/users
Query:
  - page (int, 1-based, default 1, min 1)
  - page_size (int, default 20; server-enforced cap at 20)
  - include_avatars (0|1, default 1) – include short-lived SAS avatar_url for custom avatars
  - include_total (0|1, default 1) – include exact total & total_pages (for 1..last pagination)

Sorting:
  - ORDER BY username ASC

Notes:
  - Uses MSI for Cosmos + Storage.
  - SAS minting limited to items on the current page (max 20).
"""

from fastapi import APIRouter, HTTPException, Request, status, Query
from pydantic import BaseModel, EmailStr
from typing import List, Optional, Dict, Any
from azure.identity import DefaultAzureCredential
from azure.cosmos import CosmosClient
from azure.cosmos import exceptions as cosmos_exceptions
from azure.storage.blob import (
    BlobServiceClient,
    BlobSasPermissions,
    generate_blob_sas,
)
import os
import jwt
import datetime
import math

# ─────────────────────────── Environment & clients ────────────────────────────
_cosmos_endpoint = os.environ["COSMOS_ENDPOINT"]
_database_name   = os.getenv("COSMOS_DATABASE")
_users_container = os.getenv("USERS_CONTAINER", "users")
_jwt_secret      = os.getenv("JWT_SECRET", "change-me")

_images_account   = os.getenv("IMAGES_ACCOUNT")              # optional
_images_container = os.getenv("IMAGES_CONTAINER", "avatars")

# Cosmos (MSI)
_cosmos_client = CosmosClient(_cosmos_endpoint, credential=DefaultAzureCredential())
_users = _cosmos_client.get_database_client(_database_name).get_container_client(_users_container)

# Blob service (MSI) – only if configured
_blob_service: Optional[BlobServiceClient] = None
if _images_account:
    _blob_service = BlobServiceClient(
        account_url=f"https://{_images_account}.blob.core.windows.net",
        credential=DefaultAzureCredential(),
    )

# In-memory cache for a User Delegation Key (process-lifetime only)
_udk_cache: Dict[str, Any] = {"key": None, "expires_at": None}


# ─────────────────────────── Helpers ──────────────────────────────────────────
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


def _get_user_by_username(username: str) -> Optional[Dict[str, Any]]:
    try:
        return _users.read_item(item=username, partition_key=username)
    except cosmos_exceptions.CosmosResourceNotFoundError:
        return None


def _get_user_delegation_key():
    """
    Acquire or refresh a User Delegation Key for SAS generation.
    Returns None if storage not configured or MSI lacks RBAC.
    """
    global _udk_cache
    if not _blob_service:
        return None

    now = datetime.datetime.utcnow()
    exp_at: Optional[datetime.datetime] = _udk_cache.get("expires_at")
    if _udk_cache.get("key") is not None and exp_at and (exp_at - now) > datetime.timedelta(minutes=5):
        return _udk_cache["key"]

    try:
        start  = now - datetime.timedelta(minutes=5)
        expire = now + datetime.timedelta(hours=1)
        key = _blob_service.get_user_delegation_key(start, expire)
        _udk_cache["key"] = key
        _udk_cache["expires_at"] = expire
        return key
    except Exception:
        return None


def _build_avatar_sas_url(blob_name: str) -> Optional[str]:
    """
    Mint a read-only SAS for a given blob valid for ~10 minutes.
    """
    if not (_images_account and _images_container):
        return None
    udk = _get_user_delegation_key()
    if not udk:
        return None

    try:
        expiry = datetime.datetime.utcnow() + datetime.timedelta(minutes=10)
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


# ─────────────────────────── Models ───────────────────────────────────────────
class AdminUserItem(BaseModel):
    id: str
    username: str
    email: Optional[EmailStr] = None
    gender: Optional[str] = None                     # "male" | "female" | None
    dob: Optional[datetime.date] = None
    country: Optional[str] = None
    profile_pic_id: Optional[int] = 1
    profile_pic_type: Optional[str] = "default"      # "default" | "custom"
    avatar_url: Optional[str] = None                 # only when custom & include_avatars=1


class AdminUserListResponse(BaseModel):
    page: int
    page_size: int
    total: int
    total_pages: int
    has_prev: bool
    has_next: bool
    items: List[AdminUserItem]


# ─────────────────────────── Router ───────────────────────────────────────────
router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.get("/admin/users", response_model=AdminUserListResponse)
def admin_list_users(
    request: Request,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1),
    include_avatars: int = Query(1, ge=0, le=1),
    include_total: int = Query(1, ge=0, le=1),
):
    """
    List users for admin panel with username ASC ordering and numeric pagination.
    """
    # AuthN
    token = _extract_bearer_token(request)
    caller = _decode_jwt_subject(token)
    caller_doc = _get_user_by_username(caller)
    if not caller_doc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")

    # AuthZ: require is_admin
    if not bool(caller_doc.get("is_admin", False)):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin only")

    # Enforce server-side page size cap (20)
    if page_size > 20:
        page_size = 20

    # Total count (for 1..last pager)
    total = 0
    total_pages = 1
    if include_total == 1:
        count_query = "SELECT VALUE COUNT(1) FROM c"
        try:
            total_items = list(
                _users.query_items(
                    query=count_query,
                    parameters=[],
                    enable_cross_partition_query=True,
                )
            )
            total = int(total_items[0]) if total_items else 0
        except Exception:
            # On failure, leave total at 0; UI will still get items below
            total = 0
        total_pages = max(1, math.ceil(total / page_size)) if page_size else 1

    # Clamp page to [1 .. total_pages] when we know total
    if include_total == 1 and total_pages > 0 and page > total_pages:
        page = total_pages

    # Page slice
    offset = (page - 1) * page_size
    # Cosmos SQL currently accepts OFFSET/LIMIT literals; inject sanitized ints
    fields = (
        "c.id, c.username, c.email, c.gender, c.dob, c.country, "
        "c.profile_pic_id, c.profile_pic_type, c.custom_avatar"
    )
    query = (
        f"SELECT {fields} FROM c "
        f"ORDER BY c.username ASC "
        f"OFFSET {int(offset)} LIMIT {int(page_size)}"
    )

    items: List[AdminUserItem] = []
    try:
        for it in _users.query_items(query=query, parameters=[], enable_cross_partition_query=True):
            # Prepare avatar_url if requested and custom
            avatar_url: Optional[str] = None
            if include_avatars == 1 and (it.get("profile_pic_type") == "custom"):
                meta = it.get("custom_avatar") if isinstance(it.get("custom_avatar"), dict) else None
                blob_name = meta.get("blob") if meta else None
                if isinstance(blob_name, str) and blob_name:
                    avatar_url = _build_avatar_sas_url(blob_name)

            # Build model with safe defaults
            item = AdminUserItem(
                id=str(it.get("id") or it.get("username") or ""),
                username=str(it.get("username") or ""),
                email=it.get("email"),
                gender=it.get("gender"),
                dob=it.get("dob"),
                country=it.get("country"),
                profile_pic_id=int(it.get("profile_pic_id", 1)) if it.get("profile_pic_id") is not None else 1,
                profile_pic_type=it.get("profile_pic_type", "default"),
                avatar_url=avatar_url,
            )
            items.append(item)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to query users: {e}")

    # Pager booleans
    if include_total == 1:
        has_prev = page > 1
        has_next = page < total_pages
    else:
        # Fallback when total is not provided
        has_prev = page > 1
        has_next = len(items) >= page_size  # heuristic

    return {
        "page": page,
        "page_size": page_size,
        "total": total if include_total == 1 else 0,
        "total_pages": total_pages if include_total == 1 else 1,
        "has_prev": has_prev,
        "has_next": has_next,
        "items": items,
    }
