"""Portal authentication endpoint.

POST /auth/login — Login with SocialHub credentials, returns JWT
"""

from __future__ import annotations

import logging
import os

import httpx
from pydantic import BaseModel, Field
from starlette.requests import Request
from starlette.responses import JSONResponse

from mcp_server.services.jwt_service import create_token

logger = logging.getLogger(__name__)

_SOCIALHUB_AUTH_URL = os.getenv("SOCIALHUB_AUTH_URL", "")


class LoginRequest(BaseModel):
    """Request body for portal login."""

    tenantId: str = Field(..., description="SocialHub tenant ID")
    account: str = Field(..., description="SocialHub account name")
    pwd: str = Field(..., description="SocialHub password")


def _verify_socialhub_credentials(auth_url: str, tenant_id: str, account: str, pwd: str) -> None:
    """Call SocialHub auth API to verify credentials.

    POST {auth_url}/v1/user/auth/token

    Raises:
        ValueError: if credentials are invalid or auth API returns an error.
        httpx.HTTPError: if the auth server is unreachable.
    """
    url = f"{auth_url.rstrip('/')}/v1/user/auth/token"
    try:
        resp = httpx.post(
            url,
            json={"tenantId": tenant_id, "account": account, "pwd": pwd},
            headers={"Content-Type": "application/json"},
            timeout=15,
        )
    except (httpx.ConnectError, httpx.TimeoutException) as exc:
        raise httpx.ConnectError(f"Cannot reach auth server: {exc}") from exc

    if resp.status_code >= 400:
        raise ValueError(f"Auth request failed: HTTP {resp.status_code}")

    body = resp.json()
    if str(body.get("code")) != "200":
        raise ValueError(body.get("msg", "unknown error"))

    data = body.get("data")
    if not data or not data.get("token"):
        raise ValueError("Auth response missing token")


async def login(request: Request) -> JSONResponse:
    """Authenticate with SocialHub credentials and return a signed JWT.

    Args:
        request: Starlette request with JSON body: {tenantId, account, pwd}.

    Returns:
        200 with {"token": "<jwt>", "tenant_id": "<id>"} on success.
        401 if credentials are invalid.
        422 if request body is malformed.
        503 if SOCIALHUB_AUTH_URL is not configured or auth server unreachable.
    """
    try:
        body = await request.json()
        req = LoginRequest(**body)
    except Exception as e:
        return JSONResponse(status_code=422, content={"error": f"请求格式错误: {e}"})

    if not _SOCIALHUB_AUTH_URL:
        return JSONResponse(
            status_code=503,
            content={"error": "SOCIALHUB_AUTH_URL 未配置，无法登录"},
        )

    try:
        _verify_socialhub_credentials(
            _SOCIALHUB_AUTH_URL,
            tenant_id=req.tenantId,
            account=req.account,
            pwd=req.pwd,
        )
    except ValueError as e:
        logger.warning("Portal login failed: tenant=%s error=%s", req.tenantId, e)
        return JSONResponse(status_code=401, content={"error": f"登录失败：{e}"})
    except Exception as e:
        logger.error("Portal login unexpected error: %s", e)
        return JSONResponse(status_code=503, content={"error": "登录服务异常，请稍后重试"})

    jwt_token = create_token(req.tenantId)
    logger.info("Portal login success: tenant=%s", req.tenantId)

    return JSONResponse(status_code=200, content={
        "token": jwt_token,
        "tenant_id": req.tenantId,
    })
