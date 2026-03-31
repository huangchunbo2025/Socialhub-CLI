"""OAuth2 Resource Owner Password Credentials (ROPC) HTTP client."""

from typing import Any, Optional

import httpx


class OAuthError(Exception):
    """OAuth2 authentication error."""

    def __init__(self, message: str, status_code: Optional[int] = None):
        self.message = message
        self.status_code = status_code
        super().__init__(message)


class OAuthClient:
    """HTTP client for OAuth2 ROPC token operations.

    Supports two grant types:
    - password: exchange username + password for tokens
    - refresh_token: exchange refresh_token for a new access_token
    """

    def __init__(self, token_url: str, client_id: str, scopes: str = ""):
        if not token_url:
            raise OAuthError("OAuth2 token_url is not configured.")
        if not client_id:
            raise OAuthError("OAuth2 client_id is not configured.")
        self.token_url = token_url
        self.client_id = client_id
        self.scopes = scopes

    def fetch_token_with_password(self, username: str, password: str) -> dict[str, Any]:
        """Exchange username + password for an access token (ROPC grant).

        Args:
            username: User's login name or email.
            password: User's password (never stored on disk).

        Returns:
            Token dict with keys: access_token, refresh_token, expires_in, token_type.

        Raises:
            OAuthError: On HTTP or authentication failure.
        """
        payload = {
            "grant_type": "password",
            "username": username,
            "password": password,
            "client_id": self.client_id,
        }
        if self.scopes:
            payload["scope"] = self.scopes
        return self._post_token_request(payload)

    def refresh_access_token(self, refresh_token: str) -> dict[str, Any]:
        """Exchange a refresh_token for a new access token.

        Args:
            refresh_token: The refresh token from a previous authentication.

        Returns:
            Token dict with keys: access_token, refresh_token, expires_in, token_type.

        Raises:
            OAuthError: On HTTP failure or if refresh_token is expired/invalid.
        """
        payload = {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": self.client_id,
        }
        return self._post_token_request(payload)

    def _post_token_request(self, payload: dict) -> dict[str, Any]:
        """Send a POST request to the token endpoint (form-encoded per OAuth2 spec)."""
        try:
            response = httpx.post(
                self.token_url,
                data=payload,  # form-encoded, NOT json
                headers={"Accept": "application/json"},
                timeout=15,
            )
        except (httpx.ConnectError, httpx.TimeoutException) as exc:
            raise OAuthError(f"Cannot reach OAuth2 server: {exc}") from exc

        if response.status_code >= 400:
            # Try to extract error description from OAuth2 error response
            try:
                err = response.json()
                desc = err.get("error_description", err.get("error", "Unknown error"))
            except Exception:
                desc = response.text or f"HTTP {response.status_code}"
            raise OAuthError(f"Authentication failed: {desc}", response.status_code)

        try:
            data = response.json()
        except Exception as exc:
            raise OAuthError(f"Invalid token response: {exc}") from exc

        if not data.get("access_token"):
            raise OAuthError("Token response missing access_token")

        return data
