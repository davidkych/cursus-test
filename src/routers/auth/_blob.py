# ── src/routers/auth/_blob.py ─────────────────────────────────────────────────
"""
Tiny helper layer for image blob storage.

Design goals:
- No hardcoding: reads account/container from env (IMAGES_ACCOUNT / IMAGES_CONTAINER).
- Uses Managed Identity / DefaultAzureCredential (no keys in settings).
- Single deterministic blob name per user (the username) → easy overwrite.
- Exposes only the primitives needed by auth endpoints:
    - get_container_client()
    - upload_overwrite(username, data, content_type)
    - mint_read_sas_url(username, minutes=5)
"""

from __future__ import annotations

import os
import io
import typing as T
import datetime as dt

from azure.identity import DefaultAzureCredential
from azure.storage.blob import (
    BlobServiceClient,
    ContentSettings,
    generate_blob_sas,
    BlobSasPermissions,
    UserDelegationKey,
)

# ─────────────────────────── configuration ───────────────────────────

_IMAGES_ACCOUNT = os.getenv("IMAGES_ACCOUNT")  # required (set in Bicep)
_IMAGES_CONTAINER = os.getenv("IMAGES_CONTAINER", "avatars")  # defaulted in Bicep

if not _IMAGES_ACCOUNT:
    # Keep import-time failure explicit so misconfig is obvious
    raise RuntimeError(
        "IMAGES_ACCOUNT is not configured. "
        "Set app settings IMAGES_ACCOUNT/IMAGES_CONTAINER or disable avatar uploads."
    )

_BLOB_BASE = f"https://{_IMAGES_ACCOUNT}.blob.core.windows.net"

# Managed Identity / Azure CLI / POD Identity (DefaultAzureCredential covers them)
_CRED = DefaultAzureCredential()

# Lazily created singletons
_SERVICE_CLIENT: BlobServiceClient | None = None


def _svc() -> BlobServiceClient:
    global _SERVICE_CLIENT
    if _SERVICE_CLIENT is None:
        _SERVICE_CLIENT = BlobServiceClient(account_url=_BLOB_BASE, credential=_CRED)
    return _SERVICE_CLIENT


# ─────────────────────────── public helpers ───────────────────────────

def get_container_client():
    """
    Return a ContainerClient for the configured container.
    Container is expected to exist (provisioned by Bicep). We do not attempt to create it here.
    """
    return _svc().get_container_client(_IMAGES_CONTAINER)


def _blob_name_for_user(username: str) -> str:
    """
    Deterministic blob name for a user's avatar.
    We deliberately do not include a file extension; Content-Type is authoritative.
    """
    # Username is already used as PK/id in Users container; reuse as-is.
    # If you want stricter naming, normalize here (e.g., lower/strip). Keep 1:1 for now.
    return username


def blob_url_for_user(username: str) -> str:
    """Compute the HTTPS URL to the user's avatar blob (without SAS)."""
    return f"{_BLOB_BASE}/{_IMAGES_CONTAINER}/{_blob_name_for_user(username)}"


def upload_overwrite(
    username: str,
    data: T.Union[bytes, bytearray, io.BufferedIOBase, io.BytesIO, io.RawIOBase],
    content_type: T.Optional[str] = None,
) -> None:
    """
    Overwrite the user's avatar blob with the provided bytes/file-like.
    - Sets Content-Type for correct delivery & downstream caching.
    - Does not enforce policy (type/size) here; caller (endpoint) owns validation.

    Raises azure.core.exceptions.HttpResponseError on storage failures.
    """
    if hasattr(data, "read"):
        # Read all into memory; avatars are small. Endpoint should enforce size limits.
        payload = T.cast(T.Any, data).read()
    else:
        payload = data  # bytes/bytearray

    settings = ContentSettings(content_type=content_type or "application/octet-stream")
    cc = get_container_client()
    cc.upload_blob(
        name=_blob_name_for_user(username),
        data=payload,
        overwrite=True,
        content_settings=settings,
    )


def _get_user_delegation_key(
    minutes_valid: int = 5,
) -> UserDelegationKey:
    """
    Request a short-lived user delegation key. Requires the Web App MSI to have:
    - Storage Blob Data Delegator (on the storage account scope).
    """
    now = dt.datetime.utcnow()
    # Start a little earlier to avoid clock skew issues
    start = now - dt.timedelta(minutes=1)
    expiry = now + dt.timedelta(minutes=max(1, minutes_valid))
    return _svc().get_user_delegation_key(starts_on=start, expires_on=expiry)


def mint_read_sas_url(username: str, minutes: int = 5) -> str:
    """
    Generate a short-lived HTTPS read SAS URL for the user's avatar blob using a user-delegation SAS.
    """
    udk = _get_user_delegation_key(minutes_valid=minutes)
    sas = generate_blob_sas(
        account_name=_IMAGES_ACCOUNT,
        container_name=_IMAGES_CONTAINER,
        blob_name=_blob_name_for_user(username),
        user_delegation_key=udk,
        permission=BlobSasPermissions(read=True),
        expiry=dt.datetime.utcnow() + dt.timedelta(minutes=max(1, minutes)),
        # Enforce HTTPS-only use of the SAS
        protocol="https",
    )
    return f"{blob_url_for_user(username)}?{sas}"
