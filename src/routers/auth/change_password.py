# ── src/routers/auth/change_password.py ───────────────────────────────────────
from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel
from typing import Any, Dict, Optional
from azure.cosmos import CosmosClient, exceptions
from azure.identity import DefaultAzureCredential
from passlib.hash import sha256_crypt
import os
import jwt

# ───────────────────────── Cosmos / env setup ─────────────────────────
_cosmos_endpoint = os.environ["COSMOS_ENDPOINT"]
_database_name   = os.getenv("COSMOS_DATABASE")
_users_container = os.getenv("USERS_CONTAINER", "users")
_jwt_secret      = os.getenv("JWT_SECRET", "change-me")

_client = CosmosClient(
    _cosmos_endpoint,
    credential=DefaultAzureCredential(),
)
_users = _client.get_database_client(_database_name).get_container_client(_users_container)

# ────────────────────────── Schemas ──────────────────────────────────
class ChangePasswordIn(BaseModel):
    current_password: str
    new_password: str  # no complexity policy for now (can be 1+ chars)

class ChangePasswordOut(BaseModel):
    status: str = "ok"

# ────────────────────────── Helpers ──────────────────────────────────
def _extract_bearer_token(req: Request) -> str:
    auth = req.headers.get("Authorization", "")
    if not auth.lower().startswith("bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing bearer token",
        )
    return auth.split(" ", 1)[1].strip()

def _decode_jwt(token: str) -> str:
    try:
        payload = jwt.decode(token, _jwt_secret, algorithms=["HS256"])
        sub = payload.get("sub")
        if not sub:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token (no subject)",
            )
        return sub
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token expired",
        )
    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
        )

def _get_user_by_username(username: str) -> Optional[Dict[str, Any]]:
    """Fast point-read via id == partition key (/username)."""
    try:
        return _users.read_item(item=username, partition_key=username)
    except exceptions.CosmosResourceNotFoundError:
        return None

def _verify_pwd(pwd: str, hashed: str) -> bool:
    return sha256_crypt.verify(pwd, hashed)

def _hash_pwd(pwd: str) -> str:
    return sha256_crypt.hash(pwd)

# ─────────────────────────── Router ──────────────────────────────────
router = APIRouter(
    prefix="/api/auth",
    tags=["auth"],
)

@router.post("/change-password", response_model=ChangePasswordOut)
def change_password(payload: ChangePasswordIn, request: Request):
    """
    Change the current user's password.
    Requirements:
      - Valid Bearer JWT (unchanged behavior: tokens remain valid until expiry)
      - Must supply current_password (verified)
      - new_password can be any non-empty string (no policy yet)
    """
    # Basic payload integrity (allow 1-char new passwords but not empty)
    if not payload.current_password:
        raise HTTPException(status_code=422, detail="current_password is required")
    if payload.new_password is None or payload.new_password == "":
        raise HTTPException(status_code=422, detail="new_password must not be empty")

    # Resolve current user from JWT
    token = _extract_bearer_token(request)
    username = _decode_jwt(token)

    # Load user document
    doc = _get_user_by_username(username)
    if not doc:
        # Valid token but user doc missing → treat as unauthorized (consistent with /me)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")

    # Verify current password
    if not _verify_pwd(payload.current_password, doc.get("password", "")):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid current password")

    # Update password (no token invalidation here by design)
    doc["password"] = _hash_pwd(payload.new_password)

    # Upsert to persist the change (avoid ETag headaches)
    _users.upsert_item(doc)

    return {"status": "ok"}
