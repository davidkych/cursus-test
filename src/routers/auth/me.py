# src/routers/auth/me.py
# ──────────────────────────────────────────────────────────────────────────────
# GET /api/auth/me
# Returns the current user record based on the JWT in the Authorization header.
# ──────────────────────────────────────────────────────────────────────────────
import os
from datetime import datetime, timezone
from typing import Optional

import jwt
from azure.cosmos import CosmosClient
from azure.identity import DefaultAzureCredential
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, EmailStr

router = APIRouter(prefix="/api/auth", tags=["auth"])
security = HTTPBearer(auto_error=False)

# ── Response model ───────────────────────────────────────────────────────────
class UserPublic(BaseModel):
    id: str
    username: str
    email: EmailStr
    profile_pic_id: Optional[int] = None
    profile_pic_type: Optional[str] = None
    created_at: datetime

# ── JWT settings ─────────────────────────────────────────────────────────────
JWT_SECRET = os.environ["JWT_SECRET"]
JWT_ALG    = "HS256"

# ── Cosmos helpers (singleton) ───────────────────────────────────────────────
def _get_container():
    if hasattr(_get_container, "_container"):
        return _get_container._container

    endpoint       = os.environ["COSMOS_ENDPOINT"]
    database_name  = os.environ["COSMOS_DATABASE"]
    container_name = os.getenv("USERS_CONTAINER", "users")

    cred      = DefaultAzureCredential()
    client    = CosmosClient(endpoint, credential=cred,
                             consistency_level="Session")
    database  = client.get_database_client(database_name)
    container = database.get_container_client(container_name)

    _get_container._container = container
    return container

# ── Dependency ---------------------------------------------------------------
def _authenticate(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> str:
    if not credentials or credentials.scheme.lower() != "bearer":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="Missing credentials")
    token = credentials.credentials
    try:
        payload   = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALG])
        username: str | None = payload.get("sub")
        if not username:
            raise ValueError("sub missing")
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="Token expired")
    except (jwt.InvalidTokenError, ValueError):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="Invalid token")
    return username

# ── Route --------------------------------------------------------------------
@router.get("/me",
            response_model=UserPublic,
            status_code=status.HTTP_200_OK)
def get_me(username: str = Depends(_authenticate)):
    """
    Return the public profile of the authenticated user.
    """
    container = _get_container()

    query   = "SELECT * FROM c WHERE c.username = @u OFFSET 0 LIMIT 1"
    params  = [{"name": "@u", "value": username}]
    records = list(container.query_items(query, parameters=params,
                                         enable_cross_partition_query=True))
    if not records:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail="User not found")

    doc = records[0]
    # Convert ISO string to datetime for pydantic
    created_at = doc.get("created_at", "")
    if isinstance(created_at, str):
        created_at = datetime.fromisoformat(created_at.replace("Z", "+00:00"))

    return UserPublic(
        id=doc["id"],
        username=doc["username"],
        email=doc["email"],
        profile_pic_id=doc.get("profile_pic_id"),
        profile_pic_type=doc.get("profile_pic_type"),
        created_at=created_at,
    )
