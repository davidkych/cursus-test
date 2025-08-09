# ── src/routers/auth/login.py ────────────────────────────────────────────────
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from passlib.hash import sha256_crypt
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

# ────────────────────────── Pydantic model ─────────────────────
class LoginIn(BaseModel):
    # NOTE: This field may now carry either the username *or* the e-mail.
    username: str
    password: str

class TokenOut(BaseModel):
    access_token: str
    token_type:   str = "bearer"

# ───────────────────────── helper functions ────────────────────
def _verify_pwd(pwd: str, hashed: str) -> bool:
    return sha256_crypt.verify(pwd, hashed)

def _make_jwt(sub: str) -> str:
    exp = datetime.datetime.utcnow() + datetime.timedelta(hours=24)
    return jwt.encode({"sub": sub, "exp": exp}, _jwt_secret, algorithm="HS256")

def _looks_like_email(s: str) -> bool:
    # Lightweight heuristic; we still fall back to the other path if not found
    return "@" in s and "." in s

def _get_user_by_username(username: str):
    """Fast point-read via id == partition key (/username)."""
    try:
      return _users.read_item(item=username, partition_key=username)
    except exceptions.CosmosResourceNotFoundError:
      return None

def _get_user_by_email(email: str):
    """
    Cross-partition query by unique e-mail.
    Container enforces uniqueKeyPolicy on /email, so at most one hit.
    """
    query = "SELECT * FROM c WHERE c.email = @e"
    params = [{"name": "@e", "value": email}]
    items = list(_users.query_items(
        query=query,
        parameters=params,
        enable_cross_partition_query=True
    ))
    return items[0] if items else None

def _find_user(identifier: str):
    """
    Accepts username or e-mail. Prefer the most likely path first,
    then fall back to the other to avoid false negatives.
    """
    if _looks_like_email(identifier):
        u = _get_user_by_email(identifier) or _get_user_by_username(identifier)
    else:
        u = _get_user_by_username(identifier) or _get_user_by_email(identifier)
    return u

# ──────────────────────────── Router ────────────────────────────
router = APIRouter(
    prefix="/api/auth",
    tags=["auth"]
)

@router.post("/login", response_model=TokenOut)
def login(creds: LoginIn):
    # Treat creds.username as a generic "identifier" (username or e-mail)
    identifier = creds.username.strip()

    db_user = _find_user(identifier)
    if not db_user:
        raise HTTPException(status_code=401, detail="Invalid username/email or password")

    if not _verify_pwd(creds.password, db_user["password"]):
        raise HTTPException(status_code=401, detail="Invalid username/email or password")

    # For JWT sub, continue to use the stable username/id key
    return {"access_token": _make_jwt(db_user["id"])}
