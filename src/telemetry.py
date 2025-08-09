# src/telemetry.py
"""
Login telemetry helper utilities.

Collects:
- Client IP (from X-Forwarded-For with fallbacks) and filters out private/reserved IPs
- User-Agent parsing (browser/OS/device) using `user-agents`
- Client locale & timezone from explicit headers
- Optional Geo-IP (Azure Maps IP Geolocation) when enabled

Environment (all optional):
- LOGIN_TELEMETRY: "1" to enable (default "1"); "0" to disable
- GEOIP_PROVIDER:  "azmaps" to use Azure Maps; anything else disables Geo-IP
- AZURE_MAPS_KEY:  subscription key for Azure Maps (required if GEOIP_PROVIDER=azmaps)

Public API:
- telemetry_enabled() -> bool
- build_login_context(request: fastapi.Request) -> dict
"""

from __future__ import annotations

import datetime as _dt
import ipaddress as _ip
import os as _os
from typing import Any, Dict, Optional

import requests as _requests
from user_agents import parse as _parse_ua


# ───────────────────────── env helpers ─────────────────────────

def _env_bool(name: str, default: bool = True) -> bool:
    v = (_os.getenv(name) or "").strip().lower()
    if v in ("1", "true", "yes", "on"):  # enabled
        return True
    if v in ("0", "false", "no", "off"):  # disabled
        return False
    return default


def _env_str(name: str) -> str:
    return _os.getenv(name, "").strip()


def telemetry_enabled() -> bool:
    return _env_bool("LOGIN_TELEMETRY", True)


# ───────────────────────── IP helpers ─────────────────────────

def _is_public_ip(ip: str) -> bool:
    """Return True when IP is public (not private/reserved/loopback/link-local/multicast)."""
    try:
        obj = _ip.ip_address(ip)
    except ValueError:
        return False
    return not (obj.is_private or obj.is_loopback or obj.is_reserved or obj.is_link_local or obj.is_multicast)


def _first_public_ip_from_xff(xff: str) -> Optional[str]:
    """
    Extract the leftmost public IP from X-Forwarded-For.
    XFF format: "client, proxy1, proxy2"
    """
    for token in (p.strip() for p in xff.split(",") if p.strip()):
        if _is_public_ip(token):
            return token
    return None


def _extract_client_ip(request) -> Optional[str]:
    """
    Resolve client IP with precedence:
      1) X-Client-IP (if public)
      2) X-Forwarded-For (leftmost public)
      3) X-Original-For (leftmost public) — some proxies
      4) request.client.host (if public)
    """
    headers = request.headers
    candidates = [
        headers.get("X-Client-IP", ""),
        headers.get("X-Forwarded-For", ""),
        headers.get("X-Original-For", ""),
    ]
    # 1) Direct header with single IP
    if candidates[0]:
        ip = candidates[0].split(",")[0].strip()
        if _is_public_ip(ip):
            return ip

    # 2) XFF variants (find first public)
    for header_val in candidates[1:3]:
        if header_val:
            ip = _first_public_ip_from_xff(header_val)
            if ip:
                return ip

    # 3) Fallback to connection peer
    peer = getattr(getattr(request, "client", None), "host", None)
    if peer and _is_public_ip(peer):
        return peer

    return None


# ───────────────────────── UA / locale helpers ─────────────────────────

def _parse_user_agent(ua_raw: str) -> Dict[str, Any]:
    """
    Convert raw UA string to structured info using `user-agents`.
    """
    if not ua_raw:
        return {}

    ua = _parse_ua(ua_raw)

    browser_version = getattr(ua.browser, "version_string", None) or ""
    os_version = getattr(ua.os, "version_string", None) or ""

    return {
        "raw": ua_raw,
        "browser": {
            "name": getattr(ua.browser, "family", None) or "",
            "version": browser_version,
        },
        "os": {
            "name": getattr(ua.os, "family", None) or "",
            "version": os_version,
        },
        "is_mobile": bool(getattr(ua, "is_mobile", False)),
        "is_tablet": bool(getattr(ua, "is_tablet", False)),
        "is_pc": bool(getattr(ua, "is_pc", False)),
        "is_bot": bool(getattr(ua, "is_bot", False)),
    }


def _extract_client_timezone(request) -> Optional[str]:
    # Browser-provided IANA tz via custom header we set on the client
    tz = request.headers.get("X-Client-Timezone")
    return tz.strip() if tz else None


def _extract_locales(request) -> Dict[str, Optional[str]]:
    return {
        "client": (request.headers.get("X-Client-Locale") or "").strip() or None,
        "accept_language": (request.headers.get("Accept-Language") or "").strip() or None,
    }


# ───────────────────────── Azure Maps geolocation ─────────────────────────

def _geo_azmaps(ip: str) -> Dict[str, Any]:
    """
    Azure Maps IP Geolocation.

    API: GET https://atlas.microsoft.com/geolocation/ip/json?api-version=1.0&ip={ip}&subscription-key={KEY}
    Response (subset): { "ipAddress": "...", "countryRegion": { "isoCode": "GB" } }
    """
    key = _env_str("AZURE_MAPS_KEY")
    if not key or not ip:
        return {}

    try:
        resp = _requests.get(
            "https://atlas.microsoft.com/geolocation/ip/json",
            params={"api-version": "1.0", "ip": ip, "subscription-key": key},
            timeout=3.0,
        )
        if resp.status_code != 200:
            return {}
        data = resp.json() or {}
        iso2 = (data.get("countryRegion") or {}).get("isoCode")
        if iso2:
            return {"country_iso2": iso2.upper(), "source": "azmaps"}
        return {}
    except Exception:
        # Swallow provider errors; telemetry is best-effort
        return {}


def _geo_lookup(ip: Optional[str]) -> Dict[str, Any]:
    """
    Geo-IP dispatcher. Currently only 'azmaps' is supported per configuration.
    """
    if not ip or not _is_public_ip(ip):
        return {}

    provider = _env_str("GEOIP_PROVIDER").lower()
    if provider == "azmaps":
        return _geo_azmaps(ip)

    return {}  # unknown/disabled


# ───────────────────────── public builder ─────────────────────────

def build_login_context(request) -> Dict[str, Any]:
    """
    Build the login_context payload for a successful login.

    Note:
    - Does NOT raise; returns as much as it can.
    - Always sets last_login_utc (UTC ISO string).
    - Only performs Geo-IP when enabled by env (LOGIN_TELEMETRY=1) and provider configured.
    """
    # Base skeleton
    context: Dict[str, Any] = {
        "last_login_utc": _dt.datetime.utcnow().replace(microsecond=0).isoformat() + "Z",
    }

    # Headers & UA
    ua_raw = request.headers.get("User-Agent") or ""
    ua = _parse_user_agent(ua_raw)
    if ua:
        context["ua"] = ua

    # Locale & timezone
    locale = _extract_locales(request)
    if any(locale.values()):
        context["locale"] = locale

    tz = _extract_client_timezone(request)
    if tz:
        context["timezone"] = tz

    # IP & Geo (best-effort)
    ip = _extract_client_ip(request)
    if ip:
        context["ip"] = ip

    if telemetry_enabled():
        geo = _geo_lookup(ip)
        if geo:
            context["geo"] = geo

    return context
