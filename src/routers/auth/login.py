# ── src/routers/auth/login.py ────────────────────────────────────────────────
from fastapi import APIRouter, HTTPException, status, Request
from pydantic import BaseModel
from passlib.hash import sha256_crypt
from azure.cosmos import CosmosClient, exceptions
from azure.identity import DefaultAzureCredential
import os, datetime, jwt, user_agents

# ───────────────────────── Cosmos setup ──────────────────────────
_cosmos_endpoint = os.environ["COSMOS_ENDPOINT"]
_database_name   = os.getenv("COSMOS_DATABASE")
_users_container = os.getenv("USERS_CONTAINER", "users")
_jwt_secret      = os.getenv("JWT_SECRET", "change-me")

_client = CosmosClient(_cosmos_endpoint, credential=DefaultAzureCredential())
_users  = _client.get_database_client(_database_name).get_container_client(_users_container)

# ────────────────────────── Pydantic models ─────────────────────
class LoginIn(BaseModel):
    username: str
    password: str

class TokenOut(BaseModel):
    access_token: str
    token_type:   str = "bearer"

# ───────────────────────── helper functions ────────────────────
def _verify_pwd(pwd: str, hashed: str) -> bool:
    """Return True if `pwd` matches argon2 / sha256_crypt hash."""
    return sha256_crypt.verify(pwd, hashed)

def _make_jwt(sub: str) -> str:
    """Generate a short-lived JWT (24 h) with `sub` = username."""
    now = datetime.datetime.utcnow()
    payload = {
        "sub": sub,
        "iat": now,
        "exp": now + datetime.timedelta(hours=24),
    }
    return jwt.encode(payload, _jwt_secret, algorithm="HS256")

# ──────────────────────────── Router ────────────────────────────
router = APIRouter(
    prefix="/api/auth",
    tags=["auth"],
)

@router.post("/login", response_model=TokenOut)
def login(creds: LoginIn, request: Request):
    """
    Verify credentials and return a Bearer token.
    The token contains the username in the `sub` claim.
    """
    try:
        db_user = _users.read_item(
            item=creds.username,
            partition_key=creds.username,
        )
    except exceptions.CosmosResourceNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )

    if not _verify_pwd(creds.password, db_user["password"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )

    # ✨ OPTIONAL: simple login analytics (UA string → Cosmos TTL 14 d)
    try:
        ua_header = request.headers.get("User-Agent", "")
        ua        = user_agents.parse(ua_header)
        _users.upsert_item({
            "id": f"{creds.username}#{int(datetime.datetime.utcnow().timestamp())}",
            "tag":        "login",          # partition key for TTL docs
            "username":   creds.username,
            "device":     ua.device.family,
            "os":         ua.os.family,
            "browser":    ua.browser.family,
            "timestamp":  datetime.datetime.utcnow().isoformat(),
            "ttl":        1_209_600,        # 14 days
        })
    except Exception:
        # Never block login if analytics fails
        pass

    return {
        "access_token": _make_jwt(db_user["id"]),
        "token_type":   "bearer",
    }
