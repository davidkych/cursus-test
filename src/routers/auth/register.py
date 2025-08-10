# ── src/routers/auth/register.py ─────────────────────────────────────────────
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, EmailStr, Field
from typing import Literal
from azure.cosmos import CosmosClient, exceptions
from azure.identity import DefaultAzureCredential
import os, datetime, re

# ───────────────────────── Cosmos setup ──────────────────────────
_cosmos_endpoint = os.environ["COSMOS_ENDPOINT"]
_database_name   = os.getenv("COSMOS_DATABASE")
_users_container = os.getenv("USERS_CONTAINER", "users")

_client = CosmosClient(
    _cosmos_endpoint,
    credential=DefaultAzureCredential()
)
_users = _client.get_database_client(_database_name).get_container_client(_users_container)

# ────────────────────────── Pydantic models ─────────────────────
class UserCreate(BaseModel):
    username:          str                                = Field(..., min_length=3, max_length=32)
    email:             EmailStr
    password:          str                                = Field(..., min_length=8)

    # ⟨NEW⟩ extended fields
    gender:            Literal['male', 'female']
    dob:               datetime.date                      # expects 'YYYY-MM-DD'
    country:           str                                = Field(..., min_length=3, max_length=3)  # ISO-3166-1 alpha-3
    profile_pic_id:    int                                = Field(..., ge=1)
    profile_pic_type:  Literal['default', 'custom']
    accepted_terms:    bool

class UserRead(BaseModel):
    id:       str
    username: str
    email:    EmailStr
    created:  datetime.datetime

# ───────────────────────── helper function ─────────────────────
def _hash_pwd(pwd: str) -> str:
    # passlib is pure-python; see requirements.txt
    from passlib.hash import sha256_crypt
    return sha256_crypt.hash(pwd)

# ──────────────────────────── Router ────────────────────────────
router = APIRouter(
    prefix="/api/auth",
    tags=["auth"]
)

@router.post("/register", response_model=UserRead, status_code=status.HTTP_201_CREATED)
def register(user: UserCreate):
    # ── server-side validation for new fields (minimal & explicit) ───────────
    # country must be ISO-3166-1 alpha-3 (AAA)
    country = user.country.upper()
    if not re.fullmatch(r'[A-Z]{3}', country):
        raise HTTPException(status_code=422, detail="country must be ISO-3166-1 alpha-3 code")

    # dob must be in the past (YYYY-MM-DD already parsed by Pydantic)
    if user.dob > datetime.date.today():
        raise HTTPException(status_code=422, detail="dob must be in the past")

    # ── build the document to persist (username as id & partition key) ───────
    doc = {
        "id":               user.username,                 # id == PK for cheap point-reads
        "username":         user.username,
        "email":            user.email,
        "password":         _hash_pwd(user.password),
        "created":          datetime.datetime.utcnow().isoformat(),

        # ⟨NEW⟩ persist all extended fields
        "gender":           user.gender,                   # 'male' | 'female'
        "dob":              user.dob.isoformat(),          # 'YYYY-MM-DD'
        "country":          country,                       # ISO-3166-1 alpha-3 (e.g. 'USA')
        "profile_pic_id":   user.profile_pic_id,
        "profile_pic_type": user.profile_pic_type,         # 'default' | 'custom'
        "accepted_terms":   bool(user.accepted_terms),

        # ⟨NEW⟩ canonical grant flags defaulted OFF; toggled by code redemption later
        "isAdmin":          False,
        "isPremiumMember":  False,
    }

    try:
        _users.create_item(doc)
    except exceptions.CosmosResourceExistsError:
        # uniqueKeyPolicy enforces uniqueness for /username and /email
        raise HTTPException(status_code=409, detail="Username or e-mail already exists")

    return {k: doc[k] for k in ("id", "username", "email", "created")}
