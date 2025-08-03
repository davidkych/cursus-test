from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, EmailStr, Field
from passlib.hash import sha256_crypt
from azure.cosmos import CosmosClient, exceptions
from azure.identity import DefaultAzureCredential
from functools import lru_cache
import os, datetime, typing as _t

# ───────────────────────── Cosmos helpers ──────────────────────────
_cosmos_endpoint   = os.getenv("COSMOS_ENDPOINT")
_database_name     = os.getenv("COSMOS_DATABASE")
_users_container   = os.getenv("USERS_CONTAINER", "users")

@lru_cache(maxsize=1)
def _get_users_container():
    """
    Lazily create the Cosmos client **after** FastAPI has started so that
    Managed Identity / AAD handshake doesn't block the container’s boot-up.
    """
    client = CosmosClient(
        _cosmos_endpoint,
        credential=DefaultAzureCredential(),
    )
    return client.get_database_client(_database_name) \
                 .get_container_client(_users_container)

# ────────────────────────── Pydantic models ─────────────────────
class UserCreate(BaseModel):
    username: str = Field(..., min_length=3, max_length=32)
    email:    EmailStr
    password: str = Field(..., min_length=8)

    # ── NEW profile-picture fields (future-proof for uploads) ──
    profile_pic_id:   _t.Optional[int] = Field(
        None, ge=1,
        description="Numeric ID of built-in avatar (1, 2, …)",
    )
    profile_pic_type: _t.Optional[str] = Field(
        'default',
        regex=r'^(default|custom)$',
        description='"default" for built-ins, "custom" for future uploads',
    )

class UserRead(BaseModel):
    id:       str
    username: str
    email:    EmailStr
    created:  datetime.datetime
    profile_pic_id:   _t.Optional[int] = None
    profile_pic_type: _t.Optional[str] = None

# ───────────────────────── helper function ─────────────────────
def _hash_pwd(pwd: str) -> str:
    return sha256_crypt.hash(pwd)

# ──────────────────────────── Router ────────────────────────────
router = APIRouter(prefix="/api/auth", tags=["auth"])

@router.post("/register", response_model=UserRead, status_code=status.HTTP_201_CREATED)
def register(user: UserCreate):
    """
    Create a new user document with optional avatar metadata.
    Primary key == username for inexpensive point-reads.
    """
    doc = {
        "id":       user.username,
        "username": user.username,
        "email":    user.email,
        "password": _hash_pwd(user.password),
        "created":  datetime.datetime.utcnow().isoformat(),
    }

    if user.profile_pic_id is not None:
        doc["profile_pic_id"]   = user.profile_pic_id
        doc["profile_pic_type"] = user.profile_pic_type or "default"

    container = _get_users_container()
    try:
        container.create_item(doc)
    except exceptions.CosmosResourceExistsError:
        raise HTTPException(
            status_code=409,
            detail="Username or e-mail already exists",
        )

    return {k: doc.get(k) for k in (
        "id", "username", "email", "created",
        "profile_pic_id", "profile_pic_type"
    )}
