# ── src/routers/auth/me.py ───────────────────────────────────────────────────
from fastapi import APIRouter, HTTPException, status, Request
from pydantic import BaseModel, EmailStr
from typing import Optional, Literal
from azure.cosmos import CosmosClient, exceptions
from azure.identity import DefaultAzureCredential
import os, datetime, jwt

# ───────────────────────── Cosmos setup ──────────────────────────
_cosmos_endpoint = os.environ["COSMOS_ENDPOINT"]
_database_name   = os.getenv("COSMOS_DATABASE")
_users_container = os.getenv("USERS_CONTAINER", "users")
_jwt_secret      = os.getenv("JWT_SECRET", "change-me")

_client = CosmosClient(
    _cosmos_endpoint,
    credential=DefaultAzureCredential()
)
_users = _client.get_database_client(_database_name).get_container_client(_users_container)

# ────────────────────────── Response model ───────────────────────
class UserMeOut(BaseModel):
    id: str
    username: str
    email: EmailStr
    created: datetime.datetime

    # Extended profile fields (optional for forward compatibility)
    gender: Optional[Literal["male", "female"]] = None
    dob: Optional[datetime.date] = None
    country: Optional[str] = None
    profile_pic_id: Optional[int] = 1
    profile_pic_type: Optional[Literal["default", "custom"]] = "default"

# ──────────────────────────── Helpers ────────────────────────────
def _extract_bearer_token(req: Request) -> str:
    auth = req.headers.get("Authorization", "")
    if not auth.lower().startswith("bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing bearer token")
    return auth.split(" ", 1)[1].strip()

def _decode_jwt(token: str) -> str:
    try:
        payload = jwt.decode(token, _jwt_secret, algorithms=["HS256"])
        sub = payload.get("sub")
        if not sub:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token (no subject)")
        return sub
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

def _get_user_by_username(username: str):
    """Fast point-read via id == partition key (/username)."""
    try:
        return _users.read_item(item=username, partition_key=username)
    except exceptions.CosmosResourceNotFoundError:
        return None

# ──────────────────────────── Router ────────────────────────────
router = APIRouter(
    prefix="/api/auth",
    tags=["auth"]
)

@router.get("/me", response_model=UserMeOut)
def me(request: Request):
    """
    Current-user profile endpoint.
    Requires: Authorization: Bearer <JWT>  (HS256 signed with JWT_SECRET).
    """
    token = _extract_bearer_token(request)
    username = _decode_jwt(token)

    doc = _get_user_by_username(username)
    if not doc:
        # token is valid but user doc is gone → treat as unauthorized
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")

    # Build a safe profile payload (omit hashed password, etc.)
    # Note: pydantic will coerce ISO strings (created/dob) into datetime/date.
    payload = {
        "id":              doc.get("id") or username,
        "username":        doc.get("username") or username,
        "email":           doc.get("email"),
        "created":         doc.get("created"),
        "gender":          doc.get("gender"),
        "dob":             doc.get("dob"),
        "country":         doc.get("country"),
        "profile_pic_id":  int(doc.get("profile_pic_id", 1)),
        "profile_pic_type": doc.get("profile_pic_type", "default"),
    }
    return payload
