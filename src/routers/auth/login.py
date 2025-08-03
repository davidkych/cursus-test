# src/routers/auth/login.py
# ──────────────────────────────────────────────────────────────────────────────
# POST /api/auth/login
# Validates username + password and returns a 24 h JWT access token.
# ──────────────────────────────────────────────────────────────────────────────
import os
from datetime import datetime, timedelta, timezone
from typing import Literal

import jwt
from azure.cosmos import CosmosClient
from azure.identity import DefaultAzureCredential
from fastapi import APIRouter, HTTPException, status
from passlib.context import CryptContext
from pydantic import BaseModel, constr

router = APIRouter(prefix="/api/auth", tags=["auth"])

# ── Request / Response models ────────────────────────────────────────────────
class LoginRequest(BaseModel):
    username: constr(strip_whitespace=True, min_length=3, max_length=40)
    password: str

class LoginResponse(BaseModel):
    access_token: str
    token_type:   Literal["bearer"]

# ── Runtime constants ────────────────────────────────────────────────────────
JWT_SECRET     = os.environ["JWT_SECRET"]
JWT_ALG        = "HS256"
JWT_EXPIRES_IN = timedelta(hours=24)

pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")

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

# ── Route --------------------------------------------------------------------
@router.post("/login",
             response_model=LoginResponse,
             status_code=status.HTTP_200_OK)
def login(payload: LoginRequest):
    """
    Authenticate a user and issue a JWT.
    """
    container = _get_container()

    # Fetch user (partition key = username)
    query = "SELECT * FROM c WHERE c.username = @u OFFSET 0 LIMIT 1"
    params = [{"name": "@u", "value": payload.username}]
    items = list(container.query_items(query, parameters=params,
                                       enable_cross_partition_query=True))
    if not items:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="Invalid credentials")

    user = items[0]

    # Verify password
    if not pwd_ctx.verify(payload.password, user.get("password_hash", "")):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="Invalid credentials")

    # Issue JWT
    now = datetime.now(timezone.utc)
    claims = {
        "sub": user["username"],
        "exp": now + JWT_EXPIRES_IN,
        "iat": now,
    }
    token = jwt.encode(claims, JWT_SECRET, algorithm=JWT_ALG)

    return LoginResponse(access_token=token, token_type="bearer")
