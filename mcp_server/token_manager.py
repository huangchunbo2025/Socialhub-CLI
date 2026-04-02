"""mcp_server/token_manager.py

SocialHub Token Manager：
- 凭证来源（优先级）：1. PostgreSQL tenant_socialhub_credentials  2. MCP_TENANT_CREDS 环境变量
- Token 内存缓存（按 tenant_id），按 expiresTime TTL 自动续签
- 线程安全（_lock 保护缓存写入）

环境变量格式：
  MCP_TENANT_CREDS=uat:app_id1:secret1,tenant2:app_id2:secret2
  MCP_AUTH_URL=http://host/openapi-uat  （全局默认 auth_url，可被 DB 配置覆盖）
"""
from __future__ import annotations

import logging
import os
import threading
import time
from dataclasses import dataclass
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------- #
# 数据结构
# --------------------------------------------------------------------------- #

@dataclass
class _SocialHubCred:
    auth_url: str
    app_id: str
    app_secret: str


@dataclass
class _TokenEntry:
    token: str
    refresh_token: str
    expires_at: float  # Unix timestamp


# --------------------------------------------------------------------------- #
# 模块级状态
# --------------------------------------------------------------------------- #

_token_cache: dict[str, _TokenEntry] = {}
_lock = threading.Lock()
_REFRESH_BUFFER = 300  # 提前 5 分钟续签

# 环境变量 fallback（启动时解析一次）
_ENV_AUTH_URL: str = os.getenv("MCP_AUTH_URL", os.getenv("SOCIALHUB_AUTH_URL", ""))


def _load_env_creds() -> dict[str, _SocialHubCred]:
    raw = os.getenv("MCP_TENANT_CREDS", "").strip()
    if not raw:
        return {}
    result: dict[str, _SocialHubCred] = {}
    for entry in raw.split(","):
        parts = entry.strip().split(":")
        if len(parts) != 3:
            logger.warning("MCP_TENANT_CREDS 格式错误，跳过: %s", entry)
            continue
        tenant_id, app_id, app_secret = parts
        result[tenant_id.strip()] = _SocialHubCred(
            auth_url=_ENV_AUTH_URL,
            app_id=app_id.strip(),
            app_secret=app_secret.strip(),
        )
    logger.info("MCP_TENANT_CREDS 加载完成，共 %d 个租户", len(result))
    return result


_ENV_CREDS: dict[str, _SocialHubCred] = _load_env_creds()


# --------------------------------------------------------------------------- #
# 凭证查找（DB 优先，env var fallback）
# --------------------------------------------------------------------------- #

async def _load_cred_from_db(tenant_id: str) -> Optional[_SocialHubCred]:
    """从 PostgreSQL 查询租户 SocialHub 凭证。"""
    try:
        from mcp_server.db import get_session
        from mcp_server.models import TenantSocialHubCredential
        from mcp_server.services.crypto import decrypt
        from sqlalchemy import select

        session = await get_session()
        async with session:
            stmt = select(TenantSocialHubCredential).where(
                TenantSocialHubCredential.tenant_id == tenant_id
            )
            row = (await session.execute(stmt)).scalar_one_or_none()

        if row is None:
            return None
        return _SocialHubCred(
            auth_url=row.auth_url,
            app_id=row.app_id,
            app_secret=decrypt(row.app_secret),
        )
    except Exception as e:
        logger.warning("DB 查询 SocialHub 凭证失败 (fallback to env): %s", e)
        return None


async def get_cred(tenant_id: str) -> Optional[_SocialHubCred]:
    """DB 优先，fallback 到环境变量。"""
    cred = await _load_cred_from_db(tenant_id)
    if cred:
        return cred
    return _ENV_CREDS.get(tenant_id)


# --------------------------------------------------------------------------- #
# Token 获取与刷新（同步，在 executor 线程中调用）
# --------------------------------------------------------------------------- #

def _fetch_new_token(cred: _SocialHubCred, tenant_id: str) -> _TokenEntry:
    """用 app_id/app_secret 换新 token。Open API: POST /v1/auth/token"""
    url = f"{cred.auth_url.rstrip('/')}/v1/auth/token"
    body = {
        "appId": cred.app_id,
        "appSecret": cred.app_secret,
    }
    resp = httpx.post(url, json=body, headers={"Content-Type": "application/json"}, timeout=15)
    if resp.status_code >= 400:
        raise RuntimeError(f"SocialHub token 获取失败: HTTP {resp.status_code} {resp.text[:200]}")
    payload = resp.json()
    result_code = str(payload.get("resultCode") or payload.get("code") or "")
    if result_code != "200":
        raise RuntimeError(f"SocialHub token 获取失败: {payload.get('resultMessage') or payload.get('msg')} ({result_code}) {resp.text[:200]}")
    data = payload.get("data") or {}
    token = data.get("accessToken") or data.get("token") or ""
    refresh_token = data.get("refreshToken") or ""
    expires_time = int(data.get("expiresTime") or 0)
    if not token:
        raise RuntimeError(f"SocialHub token 响应缺少 accessToken 字段: {resp.text[:200]}")
    logger.info("SocialHub token 获取成功: tenant=%s expires_at=%s", tenant_id, expires_time)
    return _TokenEntry(token=token, refresh_token=refresh_token, expires_at=float(expires_time))


def _do_refresh_token(cred: _SocialHubCred, entry: _TokenEntry) -> _TokenEntry:
    """用 refreshToken 续签。失败时抛异常，调用方降级为重新获取。Open API: POST /v1/auth/refreshToken"""
    url = f"{cred.auth_url.rstrip('/')}/v1/auth/refreshToken"
    resp = httpx.post(
        url,
        json={"refreshToken": entry.refresh_token},
        headers={"Content-Type": "application/json", "Authorization": entry.token},
        timeout=15,
    )
    if resp.status_code >= 400:
        raise RuntimeError(f"token 续签失败: HTTP {resp.status_code}")
    payload = resp.json()
    result_code = str(payload.get("resultCode") or payload.get("code") or "")
    if result_code != "200":
        raise RuntimeError(f"token 续签失败: {payload.get('resultMessage') or payload.get('msg')} ({result_code})")
    data = payload.get("data") or {}
    token = data.get("accessToken") or data.get("token") or ""
    refresh_token = data.get("refreshToken") or ""
    expires_time = int(data.get("expiresTime") or 0)
    if not token:
        raise RuntimeError("续签响应缺少 accessToken 字段")
    logger.info("SocialHub token 续签成功: expires_at=%s", expires_time)
    return _TokenEntry(token=token, refresh_token=refresh_token, expires_at=float(expires_time))


def get_cached_token_sync(tenant_id: str, cred: _SocialHubCred) -> str:
    """同步获取 token（在 executor 线程中调用）。

    优先返回缓存，临期时尝试续签，无缓存时重新获取。
    """
    with _lock:
        entry = _token_cache.get(tenant_id)

    now = time.time()

    # 缓存有效
    if entry and entry.expires_at - now > _REFRESH_BUFFER:
        return entry.token

    # 尝试续签
    if entry and entry.refresh_token:
        try:
            new_entry = _do_refresh_token(cred, entry)
            with _lock:
                _token_cache[tenant_id] = new_entry
            return new_entry.token
        except Exception as e:
            logger.warning("token 续签失败，重新获取: %s", e)

    # 重新获取
    new_entry = _fetch_new_token(cred, tenant_id)
    with _lock:
        _token_cache[tenant_id] = new_entry
    return new_entry.token


def invalidate_token(tenant_id: str) -> None:
    """Portal 更新凭证后调用，清除缓存强制下次重新换 token。"""
    with _lock:
        _token_cache.pop(tenant_id, None)
    logger.info("SocialHub token 缓存已清除: tenant=%s", tenant_id)
