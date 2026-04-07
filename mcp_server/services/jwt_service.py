"""Minimal JWT implementation using Python stdlib only.

Format: base64url(header).base64url(payload).base64url(hmac_sig)
Algorithm: HMAC-SHA256
No external dependencies required.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import os
import secrets
import time

logger = logging.getLogger(__name__)

_JWT_TTL_SECONDS = 8 * 3600  # 8 hours

_raw_secret = os.getenv("PORTAL_JWT_SECRET", "")
if not _raw_secret:
    _raw_secret = secrets.token_hex(32)
    logger.warning(
        "PORTAL_JWT_SECRET not set — using ephemeral random secret. "
        "All portal sessions will be invalidated on restart."
    )
_SECRET: bytes = _raw_secret.encode()


def _now() -> int:
    """Current UTC timestamp in seconds. Extracted for test patching."""
    return int(time.time())


def _b64encode(data: bytes) -> str:
    """URL-safe base64 encode without padding."""
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _b64decode(s: str) -> bytes:
    """URL-safe base64 decode with padding restoration."""
    pad = 4 - len(s) % 4
    if pad != 4:
        s += "=" * pad
    return base64.urlsafe_b64decode(s)


def _sign(message: str) -> str:
    """HMAC-SHA256 sign a message string, return base64url-encoded digest."""
    return _b64encode(hmac.new(_SECRET, message.encode(), hashlib.sha256).digest())


def create_token(tenant_id: str) -> str:
    """Create a signed JWT for the given tenant_id.

    Args:
        tenant_id: The authenticated tenant's ID.

    Returns:
        Signed JWT string: header.payload.signature
    """
    header = _b64encode(json.dumps({"alg": "HS256", "typ": "JWT"}).encode())
    payload = _b64encode(json.dumps({
        "sub": tenant_id,
        "exp": _now() + _JWT_TTL_SECONDS,
        "iat": _now(),
    }).encode())
    sig = _sign(f"{header}.{payload}")
    return f"{header}.{payload}.{sig}"


def verify_token(token: str) -> str | None:
    """Verify a JWT and return tenant_id if valid.

    Args:
        token: JWT string from X-Portal-Token header.

    Returns:
        tenant_id if token is valid and not expired, None otherwise.
    """
    try:
        parts = token.split(".")
        if len(parts) != 3:
            return None

        header, payload_b64, sig = parts

        expected_sig = _sign(f"{header}.{payload_b64}")
        if not hmac.compare_digest(sig, expected_sig):
            logger.debug("JWT signature verification failed")
            return None

        payload = json.loads(_b64decode(payload_b64))

        if payload.get("exp", 0) <= _now():
            logger.debug("JWT expired: exp=%s now=%s", payload.get("exp"), _now())
            return None

        return payload.get("sub")

    except Exception as e:
        logger.debug("JWT verification error: %s", e)
        return None
