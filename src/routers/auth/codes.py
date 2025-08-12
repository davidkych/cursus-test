# ── src/routers/auth/codes.py ────────────────────────────────────────────────
from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, Union, Annotated, Literal, List
from azure.cosmos import CosmosClient, exceptions
from azure.identity import DefaultAzureCredential
import os, datetime, random, jwt

# Shared helpers / single source of truth for functions
from .common import apply_default_user_flags, apply_function, FUNCTION_REGISTRY
# Reuse the /me response model for a consistent payload
from .me import UserMeOut  # type: ignore

# ───────────────────────── Cosmos setup ──────────────────────────
_cosmos_endpoint = os.environ["COSMOS_ENDPOINT"]
_database_name   = os.getenv("COSMOS_DATABASE")
_users_container = os.getenv("USERS_CONTAINER", "users")
_codes_container = os.getenv("CODES_CONTAINER", "codes")
_jwt_secret      = os.getenv("JWT_SECRET", "change-me")

_client = CosmosClient(_cosmos_endpoint, credential=DefaultAzureCredential())
_users = _client.get_database_client(_database_name).get_container_client(_users_container)
_codes = _client.get_database_client(_database_name).get_container_client(_codes_container)

# ───────────────────────── Utilities ─────────────────────────────

ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # unambiguous, case-sensitive
CODE_LEN = 20

def _now_utc() -> datetime.datetime:
    return datetime.datetime.utcnow().replace(tzinfo=datetime.timezone.utc)

def _iso(dt: datetime.datetime | datetime.date | None) -> Optional[str]:
    if dt is None:
        return None
    if isinstance(dt, datetime.date) and not isinstance(dt, datetime.datetime):
        return datetime.datetime(dt.year, dt.month, dt.day, tzinfo=datetime.timezone.utc).isoformat()
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=datetime.timezone.utc)
    return dt.isoformat()

def _parse_expiry(dt: Optional[datetime.datetime]) -> Optional[datetime.datetime]:
    """Normalize expiry (allow None for reusable). Return aware UTC or None."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=datetime.timezone.utc)
    return dt.astimezone(datetime.timezone.utc)

def _expired(expiry: Optional[str]) -> bool:
    if not expiry:
        return False
    try:
        dt = datetime.datetime.fromisoformat(expiry)
    except Exception:
        return True
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=datetime.timezone.utc)
    return _now_utc() > dt

def _gen_code() -> str:
    return "".join(random.choice(ALPHABET) for _ in range(CODE_LEN))

def _client_ip(req: Request) -> str:
    xfwd = req.headers.get("x-forwarded-for")
    if xfwd:
        return xfwd.split(",")[0].strip()
    return (req.client.host if req.client else "") or ""

def _ua(req: Request) -> str:
    return req.headers.get("user-agent", "")

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

def _get_user_by_username(username: str) -> Optional[Dict[str, Any]]:
    try:
        return _users.read_item(item=username, partition_key=username)
    except exceptions.CosmosResourceNotFoundError:
        return None

# ───────────────────────── Pydantic models ───────────────────────

class GenerateBase(BaseModel):
    mode: Literal["one_off", "reusable", "single"]
    function: str = Field(..., description="Function key defined in FUNCTION_REGISTRY")

class GenerateOneOff(GenerateBase):
    mode: Literal["one_off"]
    expiry: datetime.datetime
    count: Optional[int] = Field(default=1, ge=1, description="Batch size for one-off codes")

class GenerateReusable(GenerateBase):
    mode: Literal["reusable"]
    code: str
    expiry: Optional[datetime.datetime] = None  # allowed to be open-ended

class GenerateSingle(GenerateBase):
    mode: Literal["single"]
    code: str
    expiry: datetime.datetime

GenerateIn = Annotated[Union[GenerateOneOff, GenerateReusable, GenerateSingle], Field(discriminator="mode")]

class CodeSummary(BaseModel):
    code: str
    mode: Literal["one_off", "reusable", "single"]
    function: str
    expiry: Optional[str] = None
    created: str

class RedeemIn(BaseModel):
    code: str

# ──────────────────────────── Router ────────────────────────────
router = APIRouter(
    prefix="/api/auth/codes",
    tags=["auth", "codes"]
)

# ─────────────────────────── Generate ────────────────────────────

@router.post("/generate", response_model=Union[CodeSummary, List[CodeSummary]])
def generate(payload: GenerateIn, request: Request):
    """
    Open code generator (no admin required).
    - one_off: server generates 20-char codes; supports 'count' batch
    - reusable: client supplies 'code'; expiry optional
    - single: client supplies 'code'; expires on consumption or expiry
    """
    # Validate function key
    if payload.function not in FUNCTION_REGISTRY:
        raise HTTPException(status_code=422, detail=f"Unsupported function: {payload.function}")

    created_at = _iso(_now_utc())
    provenance = {"ip": _client_ip(request), "ua": _ua(request)}

    if payload.mode == "one_off":
        exp = _parse_expiry(payload.expiry)
        if exp and exp <= _now_utc():
            raise HTTPException(status_code=422, detail="expiry must be in the future")

        count = payload.count or 1
        summaries: list[CodeSummary] = []

        for _ in range(count):
            # generate until unique (very low collision probability)
            for _attempt in range(10):
                code = _gen_code()
                doc = {
                    "id": code,
                    "code": code,
                    "mode": "one_off",
                    "function": payload.function,
                    "expiry": _iso(exp),
                    "created": created_at,
                    "created_by": provenance,
                    "consumed": False,
                    "consumed_by": None,
                    "consumed_at": None,
                    "redeemed_by": {},  # unused for one_off
                }
                try:
                    _codes.create_item(doc)
                    summaries.append(CodeSummary(code=code, mode="one_off", function=payload.function, expiry=_iso(exp), created=created_at))
                    break
                except exceptions.CosmosResourceExistsError:
                    # collision; try again
                    if _attempt == 9:
                        raise HTTPException(status_code=500, detail="Failed to allocate unique code")
        return summaries if len(summaries) > 1 else summaries[0]

    elif payload.mode == "reusable":
        exp = _parse_expiry(payload.expiry)
        code = payload.code
        doc = {
            "id": code,
            "code": code,
            "mode": "reusable",
            "function": payload.function,
            "expiry": _iso(exp),         # may be None
            "created": created_at,
            "created_by": provenance,
            "consumed": False,           # not used for reusable
            "consumed_by": None,
            "consumed_at": None,
            "redeemed_by": {},           # track per-user redemption
        }
        try:
            _codes.create_item(doc)
        except exceptions.CosmosResourceExistsError:
            raise HTTPException(status_code=409, detail="Code already exists")
        return CodeSummary(code=code, mode="reusable", function=payload.function, expiry=_iso(exp), created=created_at)

    else:  # single
        exp = _parse_expiry(payload.expiry)
        if exp and exp <= _now_utc():
            raise HTTPException(status_code=422, detail="expiry must be in the future")
        code = payload.code
        doc = {
            "id": code,
            "code": code,
            "mode": "single",
            "function": payload.function,
            "expiry": _iso(exp),
            "created": created_at,
            "created_by": provenance,
            "consumed": False,
            "consumed_by": None,
            "consumed_at": None,
            "redeemed_by": {},  # unused for single
        }
        try:
            _codes.create_item(doc)
        except exceptions.CosmosResourceExistsError:
            raise HTTPException(status_code=409, detail="Code already exists")
        return CodeSummary(code=code, mode="single", function=payload.function, expiry=_iso(exp), created=created_at)

# ──────────────────────────── Redeem ─────────────────────────────

@router.post("/redeem", response_model=UserMeOut)
def redeem(payload: RedeemIn, request: Request):
    """
    Redeem a code (requires Authorization: Bearer).
    - Applies the registered function to the user's account.
    - Enforces mode semantics:
        * one_off/single: expire on consumption or preset expiry
        * reusable: allow multiple users but block same-user repeat
    - Returns the updated /me payload.
    """
    # Authenticate
    token = _extract_bearer_token(request)
    username = _decode_jwt(token)

    # Load docs
    user_doc = _get_user_by_username(username)
    if not user_doc:
        raise HTTPException(status_code=401, detail="User not found")

    # Point-read the code (case-sensitive)
    try:
        code_doc = _codes.read_item(item=payload.code, partition_key=payload.code)
    except exceptions.CosmosResourceNotFoundError:
        raise HTTPException(status_code=404, detail="Code not found")

    # Check expiry if present
    if _expired(code_doc.get("expiry")):
        raise HTTPException(status_code=410, detail="Code expired")

    mode = code_doc.get("mode")
    fn_key = code_doc.get("function")

    if fn_key not in FUNCTION_REGISTRY:
        # Defensive: code refers to an unknown function; treat as invalid
        raise HTTPException(status_code=422, detail="Unsupported function attached to code")

    now_iso = _iso(_now_utc())

    if mode in ("one_off", "single"):
        if code_doc.get("consumed"):
            raise HTTPException(status_code=409, detail="Code already redeemed")

        # Apply and persist (best-effort; never fail user if code update fails after user write or vice versa)
        apply_function(user_doc, fn_key)
        apply_default_user_flags(user_doc)  # ensure all flags present
        try:
            _users.upsert_item(user_doc)
        except Exception:
            # If we cannot update the user, do not consume the code
            raise HTTPException(status_code=500, detail="Failed to update user")

        code_doc["consumed"] = True
        code_doc["consumed_by"] = username
        code_doc["consumed_at"] = now_iso

        try:
            _codes.upsert_item(code_doc)
        except Exception:
            # If code update fails, the function was already applied; we still return success
            pass

    elif mode == "reusable":
        redeemed_by: Dict[str, str] = code_doc.get("redeemed_by") or {}
        if username in redeemed_by:
            raise HTTPException(status_code=409, detail="Code already redeemed by this user")

        apply_function(user_doc, fn_key)
        apply_default_user_flags(user_doc)
        try:
            _users.upsert_item(user_doc)
        except Exception:
            raise HTTPException(status_code=500, detail="Failed to update user")

        redeemed_by[username] = now_iso
        code_doc["redeemed_by"] = redeemed_by

        try:
            _codes.upsert_item(code_doc)
        except Exception:
            # Same approach: if bookkeeping fails, the user is already updated
            pass
    else:
        raise HTTPException(status_code=422, detail="Unsupported code mode")

    # Build updated /me-style payload (mirror me.py behavior)
    payload_out: Dict[str, Any] = {
        "id":               user_doc.get("id") or username,
        "username":         user_doc.get("username") or username,
        "email":            user_doc.get("email"),
        "created":          user_doc.get("created"),
        "gender":           user_doc.get("gender"),
        "dob":              user_doc.get("dob"),
        "country":          user_doc.get("country"),
        "profile_pic_id":   int(user_doc.get("profile_pic_id", 1)),
        "profile_pic_type": user_doc.get("profile_pic_type", "default"),
        "is_admin":          bool(user_doc.get("is_admin", False)),
        "is_premium_member": bool(user_doc.get("is_premium_member", False)),
    }

    if "login_context" in user_doc and isinstance(user_doc["login_context"], dict):
        payload_out["login_context"] = user_doc["login_context"]

    return payload_out  # FastAPI will validate against UserMeOut
