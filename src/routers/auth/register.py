# ── src/routers/auth/register.py ─────────────────────────────────────────────
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, EmailStr, Field
from passlib.hash import sha256_crypt
from azure.cosmos import CosmosClient, exceptions
from azure.identity import DefaultAzureCredential
from typing import Optional, Literal
import os, datetime

# ───────────────────────── Cosmos setup ──────────────────────────
_cosmos_endpoint = os.environ["COSMOS_ENDPOINT"]
_database_name   = os.getenv("COSMOS_DATABASE")
_users_container = os.getenv("USERS_CONTAINER", "users")

_client = CosmosClient(_cosmos_endpoint, credential=DefaultAzureCredential())
_users  = _client.get_database_client(_database_name).get_container_client(_users_container)

# ────────────────────────── Pydantic models ─────────────────────
class UserCreate(BaseModel):
    username: str = Field(..., min_length=3, max_length=32)
    email:    EmailStr
    password: str = Field(..., min_length=8)

    # ✨ NEW – optional avatar selection
    profile_pic_id:   Optional[int] = Field(None, ge=1, le=23)
    profile_pic_type: Optional[Literal["default", "custom"]] = "default"

class UserRead(BaseModel):
    id:              str
    username:        str
    email:           EmailStr
    created:         datetime.datetime
    # ✨ NEW – echo avatar fields back
    profile_pic_id:  Optional[int] = None
    profile_pic_type: str = "default"

# ───────────────────────── helper function ─────────────────────
def _hash_pwd(pwd: str) -> str:
    return sha256_crypt.hash(pwd)

# ──────────────────────────── Router ────────────────────────────
router = APIRouter(
    prefix="/api/auth",
    tags=["auth"],
)

@router.post("/register", response_model=UserRead, status_code=status.HTTP_201_CREATED)
def register(user: UserCreate):
    """Create a new user record in the **users** Cosmos container."""
    doc = {
        "id":       user.username,             # id == PK for fast point-reads
        "username": user.username,
        "email":    user.email,
        "password": _hash_pwd(user.password),
        "created":  datetime.datetime.utcnow().isoformat(),
        # Optional avatar fields (frontend defaults: id=1, type="default")
        "profile_pic_id":   user.profile_pic_id,
        "profile_pic_type": user.profile_pic_type or "default",
    }

    try:
        _users.create_item(doc)
    except exceptions.CosmosResourceExistsError:
        # Unique-key policy on username / e-mail triggers this
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Username or e-mail already exists",
        )

    # Strip password before returning
    return {k: doc[k] for k in (
        "id", "username", "email", "created", "profile_pic_id", "profile_pic_type"
    )}
