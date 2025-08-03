# ── src/routers/auth/login.py ────────────────────────────────────────────────
from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel
from passlib.hash import sha256_crypt
from azure.cosmos import CosmosClient, exceptions
from azure.identity import DefaultAzureCredential
from user_agents import parse as parse_ua
import os, datetime, jwt

# ───────────────────────── Cosmos setup ──────────────────────────
_cosmos_endpoint = os.getenv("COSMOS_ENDPOINT")
_database_name   = os.getenv("COSMOS_DATABASE")
_users_container = os.getenv("USERS_CONTAINER", "users")
_jwt_secret      = os.getenv("JWT_SECRET", "change-me")

# Fail *early* with a clear message if the mandatory variables are missing
if not _cosmos_endpoint or not _database_name:
    raise RuntimeError("COSMOS_ENDPOINT and COSMOS_DATABASE must be set")

_client = CosmosClient(
    _cosmos_endpoint,
    credential=DefaultAzureCredential()
)
_users = _client.get_database_client(_database_name).get_container_client(_users_container)

# ────────────────────────── Pydantic models ─────────────────────
class LoginIn(BaseModel):
    username: str
    password: str


class TokenOut(BaseModel):
    access_token: str
    token_type:   str = "bearer"

# ───────────────────────── helper functions ────────────────────
def _verify_pwd(pwd: str, hashed: str) -> bool:
    return sha256_crypt.verify(pwd, hashed)


def _make_jwt(username: str) -> str:
    """Return a 24-hour HS256 JWT with `sub` and `username` claims."""
    exp = datetime.datetime.utcnow() + datetime.timedelta(hours=24)
    payload = {"sub": username, "username": username, "exp": exp}
    return jwt.encode(payload, _jwt_secret, algorithm="HS256")


def _build_last_login(request: Request) -> dict:
    """Extract IP + user-agent and return a structured dict."""
    ua_str  = request.headers.get("user-agent", "")
    ua      = parse_ua(ua_str)
    return {
        "ts":      datetime.datetime.utcnow().isoformat(),
        "ip":      request.client.host if request.client else None,
        "browser": ua.browser.family,
        "os":      ua.os.family,
        "device":  ua.device.family or "Other",
    }

# ──────────────────────────── Router ────────────────────────────
router = APIRouter(
    prefix="/api/auth",
    tags=["auth"],
)


@router.post("/login", response_model=TokenOut)
def login(creds: LoginIn, request: Request):
    """
    • Validates password  
    • Overwrites `last_login` field with current metadata  
    • Returns JWT that includes `"username"`
    """
    try:
        db_user = _users.read_item(item=creds.username, partition_key=creds.username)
    except exceptions.CosmosResourceNotFoundError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    if not _verify_pwd(creds.password, db_user.get("password", "")):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    # ── update last_login ───────────────────────────────────────
    db_user["last_login"] = _build_last_login(request)
    try:
        _users.replace_item(item=db_user["id"], body=db_user)
    except Exception as exc:          # Do not block login on analytics failure
        # In production, log to Application Insights / stdout instead
        print("[auth] warning: failed to update last_login:", exc)

    # ── build and return JWT ────────────────────────────────────
    token = _make_jwt(db_user["id"])
    return {"access_token": token, "token_type": "bearer"}
