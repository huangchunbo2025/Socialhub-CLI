"""OAuth2 token persistence.

Token file: ~/.socialhub/oauth_token.json
Permissions: 0600 (owner read/write only)
"""

import json
import stat
from datetime import datetime, timedelta, timezone
from typing import Optional

from ..config import CONFIG_DIR

_TOKEN_FILE = CONFIG_DIR / "oauth_token.json"

# Subtract 30 seconds from expires_in to avoid edge-case failures from clock drift.
_EXPIRY_BUFFER_SECONDS = 30


def load_oauth_token() -> Optional[dict]:
    """Load cached OAuth2 token from disk.

    Returns the full token dict if the access_token is still valid,
    or None if the file is missing, corrupted, or the access_token has expired.
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


def save_oauth_token(
    access_token: str,
    refresh_token: str,
    expires_in: int,
    token_type: str = "Bearer",
) -> None:
    """Save OAuth2 token to disk with restricted permissions (0600).

    Args:
        access_token: The access token string.
        refresh_token: The refresh token string.
        expires_in: Token lifetime in seconds (from server response).
        token_type: Token type, typically "Bearer".
    """
    _TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
    expires_at = datetime.now(timezone.utc) + timedelta(
        seconds=max(expires_in - _EXPIRY_BUFFER_SECONDS, 0)
    )
    _TOKEN_FILE.write_text(
        json.dumps(
            {
                "access_token": access_token,
                "refresh_token": refresh_token,
                "token_type": token_type,
                "expires_at": expires_at.isoformat(),
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    try:
        _TOKEN_FILE.chmod(stat.S_IRUSR | stat.S_IWUSR)
    except OSError:
        pass  # Windows best-effort


def delete_oauth_token() -> None:
    """Delete the cached OAuth2 token file (logout)."""
    if _TOKEN_FILE.exists():
        _TOKEN_FILE.unlink()


def get_refresh_token() -> Optional[str]:
    """Return the refresh_token even if the access_token is expired.

    This is used to attempt a token refresh before falling back to
    re-prompting for credentials.
    """
    if not _TOKEN_FILE.exists():
        return None
    try:
        data = json.loads(_TOKEN_FILE.read_text(encoding="utf-8"))
        return data.get("refresh_token") or None
    except Exception:
        return None
