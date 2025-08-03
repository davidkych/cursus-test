# ── src/routers/auth/me.py ────────────────────────────────────────────────────
"""
Authenticated profile endpoint
GET /api/auth/me           → returns the current user record

• Expects an `Authorization: Bearer <JWT>` header.
• JWT subject (`sub`) is the user’s **username** (matches the document id).
• Responds with username, e-mail and avatar selection.
"""

import os
import jwt
from typing import Optional

from fastapi import APIRouter, HTTPException, Header, status
from pydantic import BaseModel, EmailStr
from azure.cosmos import CosmosClient, exceptions
from azure.identity import DefaultAzureCredential

# ────────────────────────── Cosmos setup ────────────────────────────
_cosmos_endpoint = os.environ["COSMOS_ENDPOINT"]
_database_name   = os.getenv("COSMOS_DATABASE")
_users_container = os.getenv("USERS_CONTAINER", "users")
_jwt_secret      = os.getenv("JWT_SECRET", "change-me")

_client = CosmosClient(_cosmos_endpoint, credential=DefaultAzureCredential())
_users  = _client.get_database_client(_database_name).get_container_client(_users_container)

# ────────────────────────── Pydantic model ──────────────────────────
class UserMeOut(BaseModel):
    username:          str
    email:             EmailStr
    profile_pic_id:    Optional[int] = None
    profile_pic_type:  str = "default"

# ──────────────────────────── Router  ───────────────────────────────
router = APIRouter(
    prefix="/api/auth",
    tags=["auth"],
)

@router.get("/me", response_model=UserMeOut, status_code=status.HTTP_200_OK)
def get_me(authorization: str = Header(..., alias="Authorization")):
    """
    Decode the JWT, fetch the corresponding user document,
    and return public profile data.
    """
    if not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token header")

    token = authorization.split(" ", 1)[1]

    try:
        payload = jwt.decode(token, _jwt_secret, algorithms=["HS256"])
        username = payload.get("sub")
        if not username:
            raise ValueError("Missing subject")
    except (jwt.PyJWTError, ValueError):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token")

    try:
        doc = _users.read_item(item=username, partition_key=username)
    except exceptions.CosmosResourceNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    return {
        "username":         doc["username"],
        "email":            doc["email"],
        "profile_pic_id":   doc.get("profile_pic_id"),
        "profile_pic_type": doc.get("profile_pic_type", "default"),
    }
