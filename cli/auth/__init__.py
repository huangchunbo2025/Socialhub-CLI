"""SocialHub authentication module."""

# Internal env var: set by executor.py when spawning sub-CLI processes
# so the auth gate does not prompt for credentials again.
SUBPROCESS_AUTH_SKIP_ENV = "_SOCIALHUB_INTERNAL_SUBPROCESS_SKIP_AUTH"

from .oauth_client import OAuthClient, OAuthError
from .token_store import (
    delete_oauth_token,
    get_stored_token,
    load_oauth_token,
    save_oauth_token,
)

__all__ = [
    "SUBPROCESS_AUTH_SKIP_ENV",
    "OAuthClient",
    "OAuthError",
    "delete_oauth_token",
    "get_stored_token",
    "load_oauth_token",
    "save_oauth_token",
]
