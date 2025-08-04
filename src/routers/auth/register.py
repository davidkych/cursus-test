# ── src/routers/auth/register.py ─────────────────────────────────────────────
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, EmailStr, Field
from passlib.hash import sha256_crypt
from azure.cosmos import CosmosClient, exceptions
from azure.identity import DefaultAzureCredential
import os, datetime

# ───────────────────────── Cosmos setup ──────────────────────────
_cosmos_endpoint = os.environ["COSMOS_ENDPOINT"]
_database_name   = os.getenv("COSMOS_DATABASE")
_users_container = os.getenv("USERS_CONTAINER", "users")

_client = CosmosClient(
    _cosmos_endpoint,
    credential=DefaultAzureCredential()
)
_users = _client.get_database_client(_database_name).get_container_client(_users_container)

# ────────────────────────── Pydantic model ─────────────────────
class UserCreate(BaseModel):
    username: str     = Field(..., min_length=3, max_length=32)
    email:    EmailStr
    password: str     = Field(..., min_length=8)

class UserRead(BaseModel):
    id:       str
    username: str
    email:    EmailStr
    created:  datetime.datetime

# ───────────────────────── helper function ─────────────────────
def _hash_pwd(pwd: str) -> str:
    return sha256_crypt.hash(pwd)

# ──────────────────────────── Router ────────────────────────────
router = APIRouter(
    prefix="/api/auth",
    tags=["auth"]
)

@router.post("/register", response_model=UserRead, status_code=status.HTTP_201_CREATED)
def register(user: UserCreate):
    doc = {
        "id":       user.username,                 # id == PK for cheap point-reads
        "username": user.username,
        "email":    user.email,
        "password": _hash_pwd(user.password),
        "created":  datetime.datetime.utcnow().isoformat(),
    }
    try:
        _users.create_item(doc)
    except exceptions.CosmosResourceExistsError:
        raise HTTPException(status_code=409, detail="Username or e-mail already exists")

    return {k: doc[k] for k in ("id", "username", "email", "created")}
