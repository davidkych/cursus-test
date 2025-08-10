# ── src/routers/auth/change_email.py ──────────────────────────────────────────
from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, EmailStr
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
class ChangeEmailIn(BaseModel):
    current_password: str
    new_email: EmailStr

class ChangeEmailOut(BaseModel):
    status: str = "ok"
    email: EmailStr

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

# ─────────────────────────── Router ──────────────────────────────────
router = APIRouter(
    prefix="/api/auth",
    tags=["auth"],
)

@router.post("/change-email", response_model=ChangeEmailOut)
def change_email(payload: ChangeEmailIn, request: Request):
    """
    Change the current user's e-mail.
    Requirements:
      - Valid Bearer JWT (existing tokens remain valid until expiry)
      - Must supply current_password (verified)
      - new_email must be valid format (EmailStr)
    Behavior:
      - If new_email equals current e-mail, operation is idempotent (200).
      - Unique e-mail is enforced by Cosmos uniqueKeyPolicy on /email.
    """
    # Basic payload integrity
    if not payload.current_password:
        raise HTTPException(status_code=422, detail="current_password is required")

    new_email = str(payload.new_email).strip()

    # Resolve current user from JWT
    token = _extract_bearer_token(request)
    username = _decode_jwt(token)

    # Load user document
    doc = _get_user_by_username(username)
    if not doc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")

    # Verify current password
    if not _verify_pwd(payload.current_password, doc.get("password", "")):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid current password")

    # Idempotency: no change needed
    if (doc.get("email") or "").strip() == new_email:
        return {"status": "ok", "email": new_email}

    # Update e-mail; rely on uniqueKeyPolicy(/email) for uniqueness
    doc["email"] = new_email
    try:
        _users.upsert_item(doc)
    except exceptions.CosmosHttpResponseError as e:
        # Map unique-key conflicts to 409
        if getattr(e, "status_code", None) == 409:
            raise HTTPException(status_code=409, detail="E-mail already exists")
        raise
    except exceptions.CosmosResourceExistsError:
        # Some SDK versions may raise this for unique key violation
        raise HTTPException(status_code=409, detail="E-mail already exists")

    return {"status": "ok", "email": new_email}
