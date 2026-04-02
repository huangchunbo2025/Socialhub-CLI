"""SocialHub authentication HTTP client.

Login:   POST {auth_url}/v1/user/auth/token
         Body: {"tenantId": "...", "account": "...", "pwd": "..."}

Refresh: GET  {auth_url}/v1/user/auth/refreshToken?refreshToken=...
         Header: Authorization: {current_token}
"""

from typing import Any, Optional

import httpx


class OAuthError(Exception):
    """Authentication error."""

    def __init__(self, message: str, status_code: Optional[int] = None):
        self.message = message
        self.status_code = status_code
        super().__init__(message)


class OAuthClient:
    """HTTP client for SocialHub user authentication."""

    def __init__(self, auth_url: str):
        if not auth_url:
            raise OAuthError("OAuth2 auth_url is not configured.")
        self.auth_url = auth_url.rstrip("/")

    def fetch_token(self, tenant_id: str, account: str, password: str) -> dict[str, Any]:
        """Login with tenant_id + account + password.

        POST /v1/user/auth/token
        Body: {"tenantId": "...", "account": "...", "pwd": "..."}

        Returns the full ``data`` dict from the response, including:
        token, refreshToken, expiresTime (absolute Unix seconds), etc.
        """
        url = f"{self.auth_url}/v1/user/auth/token"
        body = {
            "tenantId": tenant_id,
            "account": account,
            "pwd": password,
        }
        return self._request_token(
            lambda: httpx.post(
                url,
                json=body,
                headers={"Content-Type": "application/json"},
                timeout=15,
            )
        )

    def refresh_token(self, current_token: str, refresh_token: str) -> dict[str, Any]:
        """Refresh an expired access token.

        GET /v1/user/auth/refreshToken?refreshToken=...
        Header: Authorization: {current_token}

        Returns the full ``data`` dict from the response.
        """
        url = f"{self.auth_url}/v1/user/auth/refreshToken"
        return self._request_token(
            lambda: httpx.get(
                url,
                params={"refreshToken": refresh_token},
                headers={"Authorization": current_token},
                timeout=15,
            )
        )

    # ── Internal ────────────────────────────────────────────────────

    @staticmethod
    def _request_token(do_request) -> dict[str, Any]:
        """Execute an HTTP request and extract the token data."""
        try:
            response = do_request()
        except (httpx.ConnectError, httpx.TimeoutException) as exc:
            raise OAuthError(f"Cannot reach auth server: {exc}") from exc

        if response.status_code >= 400:
            raise OAuthError(
                f"Auth request failed: HTTP {response.status_code}",
                response.status_code,
            )

        try:
            body = response.json()
        except Exception as exc:
            raise OAuthError(f"Invalid auth response: {exc}") from exc

        if str(body.get("code")) != "200":
            raise OAuthError(
                f"Auth failed: {body.get('msg', 'unknown error')}"
            )

        data = body.get("data")
        if not data or not data.get("token"):
            raise OAuthError("Auth response missing token")

        return data
