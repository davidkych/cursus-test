from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, EmailStr
from azure.cosmos import CosmosClient, exceptions
from azure.identity import DefaultAzureCredential
from functools import lru_cache
import os, jwt, datetime, typing as _t

# ────────────────────────── ENV & Cosmos helpers ─────────────────────────────
_cosmos_endpoint   = os.getenv("COSMOS_ENDPOINT")
_database_name     = os.getenv("COSMOS_DATABASE")
_users_container   = os.getenv("USERS_CONTAINER", "users")
_jwt_secret        = os.getenv("JWT_SECRET", "change-me")

@lru_cache(maxsize=1)
def _get_users_container():
    client = CosmosClient(
        _cosmos_endpoint,
        credential=DefaultAzureCredential(),
    )
    return client.get_database_client(_database_name) \
                 .get_container_client(_users_container)

# ─────────────────────────── Pydantic model ──────────────────────────────────
class UserMe(BaseModel):
    id:               str
    username:         str
    email:            EmailStr
    created:          datetime.datetime
    profile_pic_id:   _t.Optional[int]  = None
    profile_pic_type: _t.Optional[str]  = None
    last_login:       _t.Optional[dict] = None   # { ts, ip, browser, os, device }

# ───────────────────────── security dependency ───────────────────────────────
security = HTTPBearer(auto_error=True)

def _get_username_from_token(
    creds: HTTPAuthorizationCredentials = Depends(security),
) -> str:
    try:
        payload = jwt.decode(creds.credentials, _jwt_secret, algorithms=["HS256"])
        return payload.get("username") or payload["sub"]
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except (jwt.InvalidTokenError, KeyError):
        raise HTTPException(status_code=401, detail="Invalid token")

# ───────────────────────────── Router ────────────────────────────────────────
router = APIRouter(prefix="/api/auth", tags=["auth"])

@router.get("/me", response_model=UserMe)
def me(current_username: str = Depends(_get_username_from_token)):
    container = _get_users_container()
    try:
        doc = container.read_item(item=current_username,
                                  partition_key=current_username)
    except exceptions.CosmosResourceNotFoundError:
        raise HTTPException(status_code=404, detail="User not found")

    doc.pop("password", None)          # never leak the hash
    return doc
