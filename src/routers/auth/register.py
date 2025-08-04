# ── src/routers/auth/register.py ─────────────────────────────────────────────
"""
User-registration endpoint.

• Stores every field coming from the <RegisterView.vue> form:
  username · email · password · profile_pic_id · profile_pic_type
  gender · dob · country · accepted_terms
• Username (== document id) remains the partition key for cheap point-reads.
• Passwords are hashed with passlib (sha256_crypt).
"""
from __future__ import annotations

import datetime as _dt
import os
import typing as _t
from enum import Enum

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, EmailStr, Field, validator
from passlib.hash import sha256_crypt
from azure.cosmos import CosmosClient, exceptions
from azure.identity import DefaultAzureCredential

# ───────────────────────── Cosmos setup ──────────────────────────
_cosmos_endpoint = os.environ["COSMOS_ENDPOINT"]
_database_name   = os.getenv("COSMOS_DATABASE")
_users_container = os.getenv("USERS_CONTAINER", "users")

_client = CosmosClient(_cosmos_endpoint, credential=DefaultAzureCredential())
_users  = _client.get_database_client(_database_name).get_container_client(_users_container)

# ────────────────────────── Pydantic models ─────────────────────
class _Gender(str, Enum):
    male   = "male"
    female = "female"


class UserCreate(BaseModel):
    # ── existing fields ─────────────────────────────────────────
    username: str      = Field(..., min_length=3, max_length=32)
    email:    EmailStr
    password: str      = Field(..., min_length=8)

    profile_pic_id:   _t.Optional[int]  = Field(None, ge=1,
        description="Numeric ID of built-in avatar (1, 2, …)")
    profile_pic_type: _t.Optional[str]  = Field(
        "default", regex=r"^(default|custom)$",
        description='"default" for built-ins, "custom" for future uploads',
    )

    # ── NEW fields from the UI ──────────────────────────────────
    gender:         _Gender
    dob:            _dt.date
    country:        str      = Field(..., min_length=2, max_length=64)
    accepted_terms: bool     = Field(...,
        description="Must be true – indicates ToS acceptance")

    # ── extra validations ───────────────────────────────────────
    @validator("dob")
    def _dob_in_past(cls, v: _dt.date) -> _dt.date:
        if v >= _dt.date.today():
            raise ValueError("Date of birth must be in the past")
        return v

    @validator("accepted_terms")
    def _terms_must_be_true(cls, v: bool) -> bool:
        if v is not True:
            raise ValueError("Terms & conditions must be accepted")
        return v


class UserRead(BaseModel):
    id:       str
    username: str
    email:    EmailStr
    created:  _dt.datetime

    # Echo optional / profile fields
    profile_pic_id:   _t.Optional[int]  = None
    profile_pic_type: _t.Optional[str]  = None
    gender:           _Gender
    dob:              _dt.date
    country:          str


# ───────────────────────── helper functions ─────────────────────
def _hash_pwd(pwd: str) -> str:
    return sha256_crypt.hash(pwd)


# ──────────────────────────── Router ────────────────────────────
router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/register", response_model=UserRead, status_code=status.HTTP_201_CREATED)
def register(user: UserCreate):
    """
    Create a new user document.

    ‣ Primary key (`id`) == username for inexpensive point-reads.  
    ‣ Unique-key policy (defined in Bicep) already prevents duplicate username/email.
    """
    doc = {
        # ── primary / security fields ───────────────────────────
        "id":       user.username,
        "username": user.username,
        "email":    user.email,
        "password": _hash_pwd(user.password),

        # ── timestamps ─────────────────────────────────────────
        "created":  _dt.datetime.utcnow().isoformat(),

        # ── profile & meta ­────────────────────────────────────
        "gender":         user.gender.value,
        "dob":            user.dob.isoformat(),
        "country":        user.country,
        "accepted_terms": user.accepted_terms,    # stored for audit/compliance
    }

    # Optional avatar
    if user.profile_pic_id is not None:
        doc["profile_pic_id"]   = user.profile_pic_id
        doc["profile_pic_type"] = user.profile_pic_type or "default"

    try:
        _users.create_item(doc)
    except exceptions.CosmosResourceExistsError:
        raise HTTPException(status_code=409, detail="Username or e-mail already exists")

    # Return a read-model (excludes hashed password)
    public_fields = (
        "id", "username", "email", "created",
        "profile_pic_id", "profile_pic_type",
        "gender", "dob", "country",
    )
    return {k: doc.get(k) for k in public_fields}
