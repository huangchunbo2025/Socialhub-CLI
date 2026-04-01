"""Portal authentication endpoint.

POST /auth/login — Login with SocialHub credentials, returns JWT
"""

from __future__ import annotations

import logging
import os

from pydantic import BaseModel, Field
from starlette.requests import Request
from starlette.responses import JSONResponse

from cli.auth.oauth_client import OAuthClient, OAuthError
from mcp_server.services.jwt_service import create_token

logger = logging.getLogger(__name__)

_SOCIALHUB_AUTH_URL = os.getenv("SOCIALHUB_AUTH_URL", "")


class LoginRequest(BaseModel):
    """Request body for portal login."""

    tenantId: str = Field(..., description="SocialHub tenant ID")
    account: str = Field(..., description="SocialHub account name")
    pwd: str = Field(..., description="SocialHub password")


async def login(request: Request) -> JSONResponse:
    """Authenticate with SocialHub credentials and return a signed JWT.

    Args:
        request: Starlette request with JSON body: {tenantId, account, pwd}.

    Returns:
        200 with {"token": "<jwt>", "tenant_id": "<id>"} on success.
        401 if credentials are invalid.
        422 if request body is malformed.
        503 if SOCIALHUB_AUTH_URL is not configured.
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
        client = OAuthClient(_SOCIALHUB_AUTH_URL)
        client.fetch_token(
            tenant_id=req.tenantId,
            account=req.account,
            password=req.pwd,
        )
    except OAuthError as e:
        logger.warning("Portal login failed: tenant=%s error=%s", req.tenantId, e.message)
        return JSONResponse(status_code=401, content={"error": f"登录失败：{e.message}"})
    except Exception as e:
        logger.error("Portal login unexpected error: %s", e)
        return JSONResponse(status_code=503, content={"error": "登录服务异常，请稍后重试"})

    jwt_token = create_token(req.tenantId)
    logger.info("Portal login success: tenant=%s", req.tenantId)

    return JSONResponse(status_code=200, content={
        "token": jwt_token,
        "tenant_id": req.tenantId,
    })
