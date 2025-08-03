# src/routers/auth/register.py
# ──────────────────────────────────────────────────────────────────────────────
# POST /api/auth/register
# Creates a new user document in the Cosmos DB *users* container.
# ──────────────────────────────────────────────────────────────────────────────
import os
from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4

from azure.cosmos import CosmosClient, exceptions
from azure.identity import DefaultAzureCredential
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, EmailStr, Field, constr
from passlib.context import CryptContext

router = APIRouter(prefix="/api/auth", tags=["auth"])

# ── Pydantic models ──────────────────────────────────────────────────────────
class RegisterRequest(BaseModel):
    username: constr(strip_whitespace=True,
                     min_length=3, max_length=40,
                     regex=r"^[A-Za-z0-9_\-\.]+$")
    email: EmailStr
    password: constr(min_length=8, max_length=100)
    profile_pic_id: int = Field(..., ge=1)
    profile_pic_type: str = Field("default",
                                  regex=r"^(default|custom)$")

class UserPublic(BaseModel):
    id: str
    username: str
    email: EmailStr
    profile_pic_id: Optional[int] = None
    profile_pic_type: Optional[str] = None
    created_at: datetime

# ── Crypto setup ─────────────────────────────────────────────────────────────
pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")

# ── Cosmos helpers (singleton) ───────────────────────────────────────────────
def _get_container():
    """Return a cached Cosmos container client for the *users* container."""
    if hasattr(_get_container, "_container"):
        return _get_container._container

    endpoint      = os.environ["COSMOS_ENDPOINT"]
    database_name = os.environ["COSMOS_DATABASE"]
    container_name = os.getenv("USERS_CONTAINER", "users")

    credential = DefaultAzureCredential()
    client     = CosmosClient(endpoint, credential=credential,
                              consistency_level="Session")

    database  = client.get_database_client(database_name)
    container = database.get_container_client(container_name)

    _get_container._container = container
    return container

# ── Route --------------------------------------------------------------------
@router.post("/register",
             response_model=UserPublic,
             status_code=status.HTTP_201_CREATED)
def register_user(payload: RegisterRequest):
    """
    Create a new user if **username** and **email** are unique.
    Passwords are stored as bcrypt hashes.
    """
    container = _get_container()

    # ‣ Check uniqueness
    dup_q = """
        SELECT VALUE COUNT(1) FROM c
        WHERE c.username = @u OR c.email = @e
    """
    params = [{"name": "@u", "value": payload.username},
              {"name": "@e", "value": payload.email}]
    dup = list(container.query_items(dup_q,
                                     parameters=params,
                                     enable_cross_partition_query=True))[0]
    if dup:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                            detail="Username or e-mail already exists")

    # ‣ Build document
    now = datetime.now(timezone.utc)
    doc = {
        "id":              str(uuid4()),
        "username":        payload.username,
        "email":           payload.email,
        "password_hash":   pwd_ctx.hash(payload.password),
        "profile_pic_id":  payload.profile_pic_id,
        "profile_pic_type": payload.profile_pic_type,
        "created_at":      now.isoformat().replace("+00:00", "Z"),
    }

    # ‣ Persist
    try:
        container.create_item(body=doc)
    except exceptions.CosmosHttpResponseError as exc:
        # Defensive: unique-key race, etc.
        if exc.status_code == 409:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                                detail="Username or e-mail already exists")
        raise

    return UserPublic(**{k: doc[k] for k in UserPublic.__fields__})
