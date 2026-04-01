"""OAuth2 token persistence.

Token file: ~/.socialhub/oauth_token.json
Permissions: 0600 (owner read/write only)

Stored fields mirror SocialHub API response:
- token (access token)
- refresh_token
- expires_at (ISO 8601, derived from expiresTime)
"""

import json
import stat
from datetime import datetime, timezone
from typing import Any, Optional

from ..config import CONFIG_DIR

_TOKEN_FILE = CONFIG_DIR / "oauth_token.json"


def load_oauth_token() -> Optional[dict[str, Any]]:
    """Load cached token from disk.

    Returns the full token dict if the access token is still valid,
    or None if missing, corrupted, or expired.
    """
    if not _TOKEN_FILE.exists():
        return None
    try:
        data = json.loads(_TOKEN_FILE.read_text(encoding="utf-8"))
        expires_at = data.get("expires_at")
        if not expires_at:
            return None
        exp = datetime.fromisoformat(expires_at)
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=timezone.utc)
        if datetime.now(timezone.utc) >= exp:
            return None
        return data
    except Exception:
        return None


def save_oauth_token(token_data: dict[str, Any]) -> None:
    """Save token to disk with restricted permissions (0600).

    Args:
        token_data: The ``data`` dict from SocialHub auth response.
                    Must contain ``token``, ``refreshToken``, ``expiresTime``.
    """
    _TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)

    # expiresTime is absolute Unix timestamp (seconds)
    expires_time = int(token_data.get("expiresTime", 0))
    expires_at = datetime.fromtimestamp(expires_time, tz=timezone.utc)

    store = {
        "token": token_data["token"],
        "refresh_token": token_data.get("refreshToken", ""),
        "expires_at": expires_at.isoformat(),
        "email": token_data.get("email", ""),
        "tenant_id": token_data.get("tenantId", ""),
    }
    _TOKEN_FILE.write_text(
        json.dumps(store, ensure_ascii=False),
        encoding="utf-8",
    )
    try:
        _TOKEN_FILE.chmod(stat.S_IRUSR | stat.S_IWUSR)
    except OSError:
        pass  # Windows best-effort


def delete_oauth_token() -> None:
    """Delete the cached token file (logout)."""
    if _TOKEN_FILE.exists():
        _TOKEN_FILE.unlink()


def get_stored_token() -> Optional[dict[str, Any]]:
    """Return stored token data even if access token is expired.

    Useful for getting the refresh_token and expired access token
    needed for the refresh request.
    Returns None only if the file is missing or corrupted.
    """
    if not _TOKEN_FILE.exists():
        return None
    try:
        return json.loads(_TOKEN_FILE.read_text(encoding="utf-8"))
    except Exception:
        return None
