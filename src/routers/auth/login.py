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

# ──────────────────────────── Router ────────────────────────────
router = APIRouter(
    prefix="/api/auth",
    tags=["auth"]
)

@router.post("/login", response_model=TokenOut)
def login(creds: LoginIn):
    try:
        db_user = _users.read_item(item=creds.username, partition_key=creds.username)
    except exceptions.CosmosResourceNotFoundError:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    if not _verify_pwd(creds.password, db_user["password"]):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    return {"access_token": _make_jwt(db_user["id"])}
