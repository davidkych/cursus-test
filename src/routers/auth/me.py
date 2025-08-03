# ── src/routers/auth/me.py ────────────────────────────────────────────────────
"""
GET /api/auth/me
Returns the current user document (minus sensitive fields).

• Auth:   Bearer <JWT>
• JWT:    HS256, signed with JWT_SECRET, contains at least {"sub": "<username>"}.
• Reads:  Cosmos DB  (container = env USERS_CONTAINER, default "users")
"""

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, EmailStr
from azure.cosmos import CosmosClient, exceptions
from azure.identity import DefaultAzureCredential
import os, jwt, datetime, typing as _t

# ────────────────────────── ENV & Cosmos client ──────────────────────────────
_cosmos_endpoint = os.environ["COSMOS_ENDPOINT"]
_database_name   = os.getenv("COSMOS_DATABASE")
_users_container = os.getenv("USERS_CONTAINER", "users")
_jwt_secret      = os.getenv("JWT_SECRET", "change-me")

_client = CosmosClient(
    _cosmos_endpoint,
    credential=DefaultAzureCredential()
)
_users = _client.get_database_client(_database_name).get_container_client(_users_container)

# ─────────────────────────── Pydantic model ──────────────────────────────────
class UserMe(BaseModel):
    id:              str
    username:        str
    email:           EmailStr
    created:         datetime.datetime
    profile_pic_id:  _t.Optional[int]  = None
    profile_pic_type:_t.Optional[str]  = None
    last_login:      _t.Optional[dict] = None   # { ts, ip, browser, os, device }

# ───────────────────────── security dependency ───────────────────────────────
security = HTTPBearer(auto_error=True)

def _get_username_from_token(
    creds: HTTPAuthorizationCredentials = Depends(security),
) -> str:
    token = creds.credentials
    try:
        payload = jwt.decode(token, _jwt_secret, algorithms=["HS256"])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

    username = payload.get("username") or payload.get("sub")
    if not username:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload")
    return username

# ───────────────────────────── Router ────────────────────────────────────────
router = APIRouter(
    prefix="/api/auth",
    tags=["auth"],
)

@router.get("/me", response_model=UserMe)
def me(current_username: str = Depends(_get_username_from_token)):
    """
    Return the user document for the caller (fields are schemaless in Cosmos).
    Sensitive fields (password) are stripped automatically.
    """
    try:
        doc = _users.read_item(item=current_username, partition_key=current_username)
    except exceptions.CosmosResourceNotFoundError:
        raise HTTPException(status_code=404, detail="User not found")

    # Remove password hash if present
    doc.pop("password", None)

    return doc
