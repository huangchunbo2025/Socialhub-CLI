"""API Key management endpoints.

Routes (all require X-Portal-Token JWT header):
    POST   /api-keys          — Create a new API key (returns raw key once only)
    GET    /api-keys          — List active API keys for tenant
    DELETE /api-keys/{key_id} — Revoke an API key
"""

from __future__ import annotations

import hashlib
import logging
import secrets
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy import select
from starlette.requests import Request
from starlette.responses import JSONResponse

from mcp_server.db import get_session
from mcp_server.models import TenantApiKey
from mcp_server.services.jwt_service import verify_token

logger = logging.getLogger(__name__)


def _require_jwt(request: Request) -> str | None:
    """Extract and verify JWT from X-Portal-Token header.

    Args:
        request: Incoming Starlette request.

    Returns:
        tenant_id if JWT is valid, None otherwise.
    """
    token = request.headers.get("X-Portal-Token", "").strip()
    if not token:
        return None
    return verify_token(token)


def _hash_key(key: str) -> str:
    """SHA-256 hex digest of an API key.

    Args:
        key: Raw API key string.

    Returns:
        64-character lowercase hex string.
    """
    return hashlib.sha256(key.encode()).hexdigest()


def _generate_api_key() -> str:
    """Generate a new random API key.

    Returns:
        API key in format: sh_ + 32 hex chars (35 chars total).
    """
    return f"sh_{secrets.token_hex(16)}"


class CreateKeyRequest(BaseModel):
    """Request body for creating an API key."""

    name: str = Field(..., min_length=1, max_length=100, description="Human-readable key name")


async def create_api_key(request: Request) -> JSONResponse:
    """POST /api-keys — create a new API key for the authenticated tenant.

    Args:
        request: Starlette request with X-Portal-Token header and JSON body {name}.

    Returns:
        201 with {id, name, key, key_prefix, created_at} — key shown only once.
        401 if JWT is invalid or missing.
        422 if request body is malformed.
    """
    tenant_id = _require_jwt(request)
    if tenant_id is None:
        return JSONResponse(status_code=401, content={"error": "JWT 无效或已过期，请重新登录"})

    try:
        body = await request.json()
        req = CreateKeyRequest(**body)
    except Exception as e:
        return JSONResponse(status_code=422, content={"error": f"请求格式错误: {e}"})

    raw_key = _generate_api_key()
    key_hash = _hash_key(raw_key)
    key_prefix = raw_key[:8]

    session = await get_session()
    async with session:
        row = TenantApiKey(
            tenant_id=tenant_id,
            name=req.name,
            key_prefix=key_prefix,
            key_hash=key_hash,
            key_raw=raw_key,
        )
        session.add(row)
        await session.commit()
        await session.refresh(row)

    created_at = row.created_at or datetime.now(timezone.utc)
    logger.info("API key created: tenant=%s name=%s prefix=%s", tenant_id, req.name, key_prefix)
    return JSONResponse(status_code=201, content={
        "id": row.id,
        "name": row.name,
        "key": raw_key,
        "key_prefix": key_prefix,
        "created_at": created_at.isoformat(),
    })


async def list_api_keys(request: Request) -> JSONResponse:
    """GET /api-keys — list active (non-revoked) API keys for tenant.

    Args:
        request: Starlette request with X-Portal-Token header.

    Returns:
        200 with {keys: [{id, name, key_prefix, created_at, last_used_at}]}.
        401 if JWT is invalid or missing.
    """
    tenant_id = _require_jwt(request)
    if tenant_id is None:
        return JSONResponse(status_code=401, content={"error": "JWT 无效或已过期，请重新登录"})

    session = await get_session()
    async with session:
        stmt = (
            select(TenantApiKey)
            .where(
                TenantApiKey.tenant_id == tenant_id,
                TenantApiKey.revoked_at.is_(None),
            )
            .order_by(TenantApiKey.created_at.desc())
        )
        rows = (await session.execute(stmt)).scalars().all()

    return JSONResponse(status_code=200, content={
        "keys": [
            {
                "id": row.id,
                "name": row.name,
                "key_prefix": row.key_prefix,
                "key_raw": row.key_raw,
                "created_at": row.created_at.isoformat(),
                "last_used_at": row.last_used_at.isoformat() if row.last_used_at else None,
            }
            for row in rows
        ]
    })


async def revoke_api_key(request: Request) -> JSONResponse:
    """DELETE /api-keys/{key_id} — revoke an API key (soft delete via revoked_at).

    Args:
        request: Starlette request with X-Portal-Token header and key_id path param.

    Returns:
        200 {"status": "ok"} on success.
        401 if JWT is invalid or missing.
        404 if key not found or belongs to another tenant.
        422 if key_id is not an integer.
    """
    tenant_id = _require_jwt(request)
    if tenant_id is None:
        return JSONResponse(status_code=401, content={"error": "JWT 无效或已过期，请重新登录"})

    try:
        key_id = int(request.path_params.get("key_id", ""))
    except ValueError:
        return JSONResponse(status_code=422, content={"error": "key_id 必须为整数"})

    session = await get_session()
    async with session:
        stmt = select(TenantApiKey).where(
            TenantApiKey.id == key_id,
            TenantApiKey.tenant_id == tenant_id,
        )
        row = (await session.execute(stmt)).scalar_one_or_none()
        if row is None:
            return JSONResponse(status_code=404, content={"error": "API Key 不存在"})
        row.revoked_at = datetime.now(timezone.utc)
        await session.commit()

    logger.info("API key revoked: tenant=%s key_id=%d", tenant_id, key_id)
    return JSONResponse(status_code=200, content={"status": "ok"})
