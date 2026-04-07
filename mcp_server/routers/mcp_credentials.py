"""mcp_server/routers/mcp_credentials.py

Routes:
    GET    /credentials/mcp  — 查询配置状态（不返回明文 secret）
    PUT    /credentials/mcp  — 新建或更新凭证
    DELETE /credentials/mcp  — 删除凭证
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from pydantic import BaseModel, Field
from sqlalchemy import select
from starlette.requests import Request
from starlette.responses import JSONResponse

from mcp_server.auth import resolve_tenant_id
from mcp_server.db import get_session
from mcp_server.models import TenantSocialHubCredential
from mcp_server.services.crypto import encrypt
from mcp_server.token_manager import invalidate_token

logger = logging.getLogger(__name__)


class McpCredRequest(BaseModel):
    auth_url: str = Field(..., description="SocialHub Auth URL，如 http://host/openapi-uat")
    app_id: str = Field(..., description="t_tenant_secret.app_id")
    app_secret: str = Field(..., description="t_tenant_secret.secret")


async def get_mcp_credentials(request: Request) -> JSONResponse:
    """GET /credentials/mcp — 查询凭证状态（不返回明文 secret）。"""
    tenant_id = await resolve_tenant_id(request)
    if not tenant_id:
        return JSONResponse(status_code=401, content={"status": "error", "message": "未认证"})

    session = await get_session()
    async with session:
        row = (await session.execute(
            select(TenantSocialHubCredential).where(
                TenantSocialHubCredential.tenant_id == tenant_id
            )
        )).scalar_one_or_none()

    if row is None:
        return JSONResponse(status_code=200, content={"status": "ok", "configured": False})

    return JSONResponse(status_code=200, content={
        "status": "ok",
        "configured": True,
        "auth_url": row.auth_url,
        "app_id": row.app_id,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    })


async def upsert_mcp_credentials(request: Request) -> JSONResponse:
    """PUT /credentials/mcp — 新建或更新 SocialHub 凭证。"""
    try:
        body = await request.json()
        req = McpCredRequest(**body)
    except Exception as e:
        return JSONResponse(status_code=422, content={"status": "error", "message": f"请求格式错误: {e}"})

    tenant_id = await resolve_tenant_id(request)
    if not tenant_id:
        return JSONResponse(status_code=401, content={"status": "error", "message": "未认证"})

    encrypted_secret = encrypt(req.app_secret)
    now = datetime.now(timezone.utc)

    session = await get_session()
    async with session:
        row = (await session.execute(
            select(TenantSocialHubCredential).where(
                TenantSocialHubCredential.tenant_id == tenant_id
            )
        )).scalar_one_or_none()

        if row is None:
            row = TenantSocialHubCredential(
                tenant_id=tenant_id,
                auth_url=req.auth_url,
                app_id=req.app_id,
                app_secret=encrypted_secret,
            )
            session.add(row)
        else:
            row.auth_url = req.auth_url
            row.app_id = req.app_id
            row.app_secret = encrypted_secret
            row.updated_at = now

        await session.commit()

    # 清除旧 token 缓存，下次工具调用时用新凭证重新换 token
    invalidate_token(tenant_id)

    return JSONResponse(status_code=200, content={
        "status": "ok",
        "tenant_id": tenant_id,
        "auth_url": req.auth_url,
        "app_id": req.app_id,
    })


async def delete_mcp_credentials(request: Request) -> JSONResponse:
    """DELETE /credentials/mcp — 删除凭证。"""
    tenant_id = await resolve_tenant_id(request)
    if not tenant_id:
        return JSONResponse(status_code=401, content={"status": "error", "message": "未认证"})

    session = await get_session()
    async with session:
        row = (await session.execute(
            select(TenantSocialHubCredential).where(
                TenantSocialHubCredential.tenant_id == tenant_id
            )
        )).scalar_one_or_none()

        if row is None:
            return JSONResponse(status_code=404, content={"status": "error", "message": "凭证不存在"})

        await session.delete(row)
        await session.commit()

    invalidate_token(tenant_id)
    return JSONResponse(status_code=200, content={"status": "ok"})
