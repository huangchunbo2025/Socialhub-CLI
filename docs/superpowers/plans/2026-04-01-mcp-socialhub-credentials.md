# MCP SocialHub 凭证管理 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为每个租户存储 SocialHub app_id/app_secret，MCP 工具调用时自动换取 token，以 `Authorization: Bearer <token>` 访问上游 APISIX MCP Gateway，支持 Portal UI 配置和环境变量两种方式。

**Architecture:** Portal 配置存 PostgreSQL（Fernet 加密），环境变量 `MCP_TENANT_CREDS` 作 fallback；TokenManager 在内存中按 tenant_id 缓存 token，按 `expiresTime` TTL 自动刷新；MCPClient 连接上游时自动带 `Authorization` header。

**Tech Stack:** Python asyncio, SQLAlchemy async, Fernet 加密, httpx, Starlette, threading.local

---

## 文件结构

| 文件 | 操作 | 说明 |
|------|------|------|
| `alembic_mcp/versions/b2c3d4e5f6a7_add_tenant_socialhub_credentials.py` | 新建 | DB 迁移：新建 `tenant_socialhub_credentials` 表 |
| `mcp_server/models.py` | 修改 | 新增 `TenantSocialHubCredential` ORM 模型 |
| `mcp_server/token_manager.py` | 新建 | 凭证加载（DB + env var fallback）、token 获取/缓存/刷新 |
| `mcp_server/routers/mcp_credentials.py` | 新建 | `/credentials/mcp` GET/PUT/DELETE 路由 |
| `mcp_server/http_app.py` | 修改 | 注册 `/credentials/mcp` 路由 |
| `cli/api/mcp_client.py` | 修改 | `MCPConfig` 加 `token` 字段，SSE/POST 请求带 `Authorization` header |
| `mcp_server/server.py` | 修改 | `_run()` 里从 TokenManager 取 token，注入 thread-local config |
| `mcp_server/static/ui.html` | 修改 | Portal 凭证管理：MCP 凭证类型排第一，必填标记，CRUD UI |

---

## Task 1: DB 迁移 — 新建 tenant_socialhub_credentials 表

**Files:**
- Create: `alembic_mcp/versions/b2c3d4e5f6a7_add_tenant_socialhub_credentials.py`
- Modify: `mcp_server/models.py`

- [ ] **Step 1: 新建 Alembic 迁移文件**

```python
# alembic_mcp/versions/b2c3d4e5f6a7_add_tenant_socialhub_credentials.py
"""add tenant_socialhub_credentials

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-04-01
"""
from alembic import op
import sqlalchemy as sa

revision = 'b2c3d4e5f6a7'
down_revision = 'a1b2c3d4e5f6'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'tenant_socialhub_credentials',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('tenant_id', sa.String(255), nullable=False),
        sa.Column('auth_url', sa.String(512), nullable=False),
        sa.Column('app_id', sa.String(128), nullable=False),
        sa.Column('app_secret', sa.Text(), nullable=False),  # Fernet encrypted
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('tenant_id'),
    )


def downgrade() -> None:
    op.drop_table('tenant_socialhub_credentials')
```

- [ ] **Step 2: 在 models.py 添加 ORM 模型**

在 `mcp_server/models.py` 末尾追加：

```python
class TenantSocialHubCredential(Base):
    """Stores encrypted SocialHub app_id/app_secret per tenant for upstream MCP auth."""

    __tablename__ = "tenant_socialhub_credentials"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    auth_url: Mapped[str] = mapped_column(String(512), nullable=False)
    app_id: Mapped[str] = mapped_column(String(128), nullable=False)
    app_secret: Mapped[str] = mapped_column(Text, nullable=False)  # Fernet encrypted
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
```

- [ ] **Step 3: 运行迁移**

```bash
cd /Users/wangyunlong/myproject/sap_Integration/src/Socialhub-CLI
conda run -n dev alembic -c alembic_mcp/alembic.ini upgrade head
```

Expected: `Running upgrade a1b2c3d4e5f6 -> b2c3d4e5f6a7, add tenant_socialhub_credentials`

- [ ] **Step 4: Commit**

```bash
git add alembic_mcp/versions/b2c3d4e5f6a7_add_tenant_socialhub_credentials.py mcp_server/models.py
git commit -m "feat: add tenant_socialhub_credentials table"
```

---

## Task 2: TokenManager — 凭证加载与 token 缓存

**Files:**
- Create: `mcp_server/token_manager.py`

- [ ] **Step 1: 新建 token_manager.py**

```python
"""mcp_server/token_manager.py

SocialHub Token Manager：
- 凭证来源（优先级）：1. PostgreSQL tenant_socialhub_credentials  2. MCP_TENANT_CREDS 环境变量
- Token 内存缓存（按 tenant_id），按 expiresTime TTL 自动刷新
- 线程安全（_lock 保护缓存写入）

环境变量格式：
  MCP_TENANT_CREDS=uat:app_id1:secret1,tenant2:app_id2:secret2
  MCP_AUTH_URL=http://192.168.1.16:30833/openapi-uat  （全局默认，可被 DB 配置覆盖）
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

# 环境变量 fallback（启动时解析一次）
_ENV_CREDS: dict[str, _SocialHubCred] = {}
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

_ENV_CREDS = _load_env_creds()


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


async def _get_cred(tenant_id: str) -> Optional[_SocialHubCred]:
    """DB 优先，fallback 到环境变量。"""
    cred = await _load_cred_from_db(tenant_id)
    if cred:
        return cred
    return _ENV_CREDS.get(tenant_id)


# --------------------------------------------------------------------------- #
# Token 获取与刷新
# --------------------------------------------------------------------------- #

def _fetch_new_token(cred: _SocialHubCred, tenant_id: str) -> _TokenEntry:
    """用 app_id/app_secret 换新 token（同步，在 run_in_executor 线程中调用）。"""
    url = f"{cred.auth_url.rstrip('/')}/v1/user/auth/token"
    body = {
        "tenantId": tenant_id,
        "appId": cred.app_id,
        "appSecret": cred.app_secret,
    }
    resp = httpx.post(url, json=body, headers={"Content-Type": "application/json"}, timeout=15)
    if resp.status_code >= 400:
        raise RuntimeError(f"SocialHub token 获取失败: HTTP {resp.status_code} {resp.text[:200]}")
    data = resp.json().get("data") or {}
    token = data.get("token") or ""
    refresh_token = data.get("refreshToken") or ""
    expires_time = int(data.get("expiresTime") or 0)
    if not token:
        raise RuntimeError(f"SocialHub token 响应缺少 token 字段: {resp.text[:200]}")
    logger.info("SocialHub token 获取成功: tenant=%s expires_at=%s", tenant_id, expires_time)
    return _TokenEntry(token=token, refresh_token=refresh_token, expires_at=float(expires_time))


def _refresh_token(cred: _SocialHubCred, entry: _TokenEntry) -> _TokenEntry:
    """用 refreshToken 续签（同步）。失败时抛异常，调用方重新用 app 凭证换。"""
    url = f"{cred.auth_url.rstrip('/')}/v1/user/auth/refreshToken"
    resp = httpx.get(
        url,
        params={"refreshToken": entry.refresh_token},
        headers={"Authorization": entry.token},
        timeout=15,
    )
    if resp.status_code >= 400:
        raise RuntimeError(f"refresh 失败: HTTP {resp.status_code}")
    data = resp.json().get("data") or {}
    token = data.get("token") or ""
    refresh_token = data.get("refreshToken") or ""
    expires_time = int(data.get("expiresTime") or 0)
    if not token:
        raise RuntimeError("refresh 响应缺少 token 字段")
    logger.info("SocialHub token 续签成功: expires_at=%s", expires_time)
    return _TokenEntry(token=token, refresh_token=refresh_token, expires_at=float(expires_time))


# --------------------------------------------------------------------------- #
# 公开接口
# --------------------------------------------------------------------------- #

_REFRESH_BUFFER = 300  # 提前 5 分钟续签


def get_cached_token_sync(tenant_id: str, cred: _SocialHubCred) -> str:
    """同步获取 token（在 executor 线程中调用）。缓存命中直接返回，否则刷新或重新获取。"""
    with _lock:
        entry = _token_cache.get(tenant_id)

    now = time.time()

    # 缓存有效
    if entry and entry.expires_at - now > _REFRESH_BUFFER:
        return entry.token

    # 尝试续签
    if entry and entry.refresh_token:
        try:
            new_entry = _refresh_token(cred, entry)
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


async def get_token(tenant_id: str) -> Optional[str]:
    """异步获取 token（供 async 上下文调用，内部用 to_thread 执行同步 HTTP）。"""
    import asyncio
    cred = await _get_cred(tenant_id)
    if not cred:
        logger.warning("未找到 tenant_id=%s 的 SocialHub 凭证", tenant_id)
        return None
    try:
        return await asyncio.get_running_loop().run_in_executor(
            None, get_cached_token_sync, tenant_id, cred
        )
    except Exception as e:
        logger.error("获取 SocialHub token 失败: tenant=%s error=%s", tenant_id, e)
        return None


def invalidate_token(tenant_id: str) -> None:
    """Portal 更新凭证后调用，清除缓存强制下次重新获取。"""
    with _lock:
        _token_cache.pop(tenant_id, None)
    logger.info("token 缓存已清除: tenant=%s", tenant_id)
```

- [ ] **Step 2: Commit**

```bash
git add mcp_server/token_manager.py
git commit -m "feat: add SocialHub token manager with DB+env fallback"
```

---

## Task 3: /credentials/mcp 路由

**Files:**
- Create: `mcp_server/routers/mcp_credentials.py`
- Modify: `mcp_server/http_app.py`

- [ ] **Step 1: 新建 mcp_credentials.py**

```python
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
    """GET /credentials/mcp"""
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
    """PUT /credentials/mcp"""
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

    # 清除旧 token 缓存，下次调用工具时用新凭证换
    invalidate_token(tenant_id)

    return JSONResponse(status_code=200, content={
        "status": "ok",
        "tenant_id": tenant_id,
        "auth_url": req.auth_url,
        "app_id": req.app_id,
    })


async def delete_mcp_credentials(request: Request) -> JSONResponse:
    """DELETE /credentials/mcp"""
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
```

- [ ] **Step 2: 在 http_app.py 注册路由**

在 `mcp_server/http_app.py` 的 import 区域加：

```python
from mcp_server.routers.mcp_credentials import (
    get_mcp_credentials, upsert_mcp_credentials, delete_mcp_credentials
)
```

在 `_app = Starlette(routes=[...])` 的 `/credentials/bigquery` 路由**之前**插入（排第一）：

```python
Route("/credentials/mcp", get_mcp_credentials, methods=["GET"]),
Route("/credentials/mcp", upsert_mcp_credentials, methods=["PUT"]),
Route("/credentials/mcp", delete_mcp_credentials, methods=["DELETE"]),
```

- [ ] **Step 3: Commit**

```bash
git add mcp_server/routers/mcp_credentials.py mcp_server/http_app.py
git commit -m "feat: add /credentials/mcp CRUD endpoints"
```

---

## Task 4: MCPClient 加 Authorization header

**Files:**
- Modify: `cli/api/mcp_client.py`

- [ ] **Step 1: 在 MCPConfig dataclass 加 token 字段**

在 `cli/api/mcp_client.py` 的 `MCPConfig` dataclass 里追加：

```python
@dataclass
class MCPConfig:
    sse_url: str = ""
    post_url: str = ""
    tenant_id: str = ""
    timeout: int = 120
    token: str = ""  # SocialHub Bearer token，由 TokenManager 注入
```

- [ ] **Step 2: SSE 连接加 Authorization header**

在 `_sse_listener` 方法的 `headers=` 里加 token（[mcp_client.py:126](cli/api/mcp_client.py#L126)）：

```python
headers = {"tenant_id": self.config.tenant_id}
if self.config.token:
    headers["Authorization"] = f"Bearer {self.config.token}"

with httpx.stream(
    "GET",
    self.config.sse_url,
    headers=headers,
    timeout=httpx.Timeout(...),
) as response:
```

- [ ] **Step 3: POST 消息加 Authorization header**

在 `_send_request` 方法的 POST headers 里加 token（[mcp_client.py:233](cli/api/mcp_client.py#L233)）：

```python
headers = {"tenant_id": self.config.tenant_id, "Content-Type": "application/json"}
if self.config.token:
    headers["Authorization"] = f"Bearer {self.config.token}"

response = httpx.post(url, headers=headers, json=message, timeout=self._post_timeout)
```

- [ ] **Step 4: Commit**

```bash
git add cli/api/mcp_client.py
git commit -m "feat: MCPClient supports Authorization Bearer token"
```

---

## Task 5: server.py 注入 token 到 config

**Files:**
- Modify: `mcp_server/server.py`

- [ ] **Step 1: 在 _get_config() patcher 里加 token 字段**

在 `mcp_server/server.py` 的 `_get_config()` 函数，thread-local patch 部分追加 token：

```python
tid = getattr(_thread_local, "tenant_id", None)
if not tid:
    return _config_cache

import copy
patched = copy.copy(_config_cache)
mcp = copy.copy(_config_cache.mcp)
mcp.tenant_id = tid
if not mcp.database:
    mcp.database = f"das_{tid}"
# token 由 _run() 在线程中同步注入，此处占位
mcp.token = getattr(_thread_local, "mcp_token", "")
patched.mcp = mcp
return patched
```

- [ ] **Step 2: 在 _run() 里获取 token**

在 `mcp_server/server.py` 的 `_run()` 函数，`_thread_local.tenant_id = tid` 之后加 token 获取：

```python
def _run():
    if not _analytics_ready.wait(timeout=120):
        return _err("Analytics failed to load within 120s")

    _thread_local.tenant_id = tid
    # 从 TokenManager 同步获取 token（DB 优先，env fallback，带缓存）
    try:
        from mcp_server.token_manager import get_cached_token_sync, _get_cred
        import asyncio
        # 在线程里同步运行异步的 _get_cred
        loop = asyncio.new_event_loop()
        cred = loop.run_until_complete(_get_cred(tid))
        loop.close()
        if cred:
            _thread_local.mcp_token = get_cached_token_sync(tid, cred)
        else:
            _thread_local.mcp_token = ""
            logger.warning("未找到 tenant=%s 的 SocialHub 凭证，工具调用将无法访问上游", tid)
    except Exception as e:
        logger.error("获取 SocialHub token 失败: %s", e)
        _thread_local.mcp_token = ""

    try:
        safe_args = {k: v for k, v in args.items() if k != "tenant_id"}
        return _run_with_cache(name, safe_args, tid, lambda: handler(safe_args))
    finally:
        _thread_local.tenant_id = None
        _thread_local.mcp_token = None
```

- [ ] **Step 3: 在 MCPConfig pydantic 模型加 token 字段**

在 `cli/config.py` 的 `MCPConfig` 里加：

```python
token: str = Field(
    default_factory=lambda: os.environ.get("MCP_TOKEN", ""),
    description="SocialHub Bearer token (managed by TokenManager)"
)
```

- [ ] **Step 4: 在 analytics 函数里透传 token**

所有 analytics 文件创建 `MCPClientConfig` 时需透传 token，但有 40+ 处。

**最小改动方案**：修改 `MCPClient.__init__` 从 `_thread_local` 读取 token fallback（无需改 analytics 文件）：

在 `cli/api/mcp_client.py` 的 `MCPClient.__init__` 中加：

```python
def __init__(self, config: Optional[MCPConfig] = None):
    self.config = config or MCPConfig()
    # 如果 config 未传 token，从 thread-local 取（server.py 注入）
    if not self.config.token:
        import threading
        tl = threading.current_thread().__dict__
        # server.py 的 _thread_local 是模块级的，在同一线程中可以访问
        from mcp_server import server as _srv  # noqa: PLC0415
        self.config.token = getattr(_srv._thread_local, "mcp_token", "") or ""
    ...
```

**注意**：这个方案依赖 import，如果 analytics 函数在 CLI 模式运行（没有 mcp_server），import 会失败。改用 os.environ fallback：

```python
def __init__(self, config: Optional[MCPConfig] = None):
    self.config = config or MCPConfig()
    if not self.config.token:
        try:
            from mcp_server import server as _srv
            self.config.token = getattr(_srv._thread_local, "mcp_token", "") or ""
        except ImportError:
            pass  # CLI 模式，不需要 server token
    ...
```

- [ ] **Step 5: Commit**

```bash
git add mcp_server/server.py cli/config.py cli/api/mcp_client.py
git commit -m "feat: inject SocialHub token into MCPClient via thread-local"
```

---

## Task 6: Portal UI — MCP 凭证类型

**Files:**
- Modify: `mcp_server/static/ui.html`

- [ ] **Step 1: 在凭证类型选择 modal 里加 MCP 类型（排第一，标注必填）**

在 `modal-cred-type` div 里，`bigquery_emarsys` 卡片**之前**插入：

```html
<div class="cred-type-card" onclick="selectCredType('socialhub_mcp')" style="border:2px solid var(--primary)">
  <div style="font-size:1.4rem">🔗</div>
  <div class="cred-type-name">MCP 凭证 <span style="color:var(--danger);font-size:0.75rem">必填</span></div>
  <div class="cred-type-desc">SocialHub 数据分析接入凭证</div>
</div>
```

- [ ] **Step 2: 在 credTypeLabel 映射里加 socialhub_mcp**

```javascript
const CRED_TYPE_LABELS = {
  'bigquery_emarsys': 'SAP BigQuery · Emarsys Open Data',
  'socialhub_mcp': 'MCP · SocialHub 数据分析',
};
```

- [ ] **Step 3: 在 selectCredType 里加 socialhub_mcp 的表单配置**

```javascript
const CRED_FORMS = {
  bigquery_emarsys: { title: '配置 BigQuery 凭证', subtitle: 'SAP Emarsys Open Data 集成' },
  socialhub_mcp: { title: '配置 MCP 凭证', subtitle: 'SocialHub 数据分析接入' },
};
```

- [ ] **Step 4: 新建 renderSocialHubForm() 和 saveSocialHubCred()**

```javascript
function renderSocialHubForm(existing) {
  document.getElementById('modal-cred-title').textContent = 'MCP 凭证';
  document.getElementById('modal-cred-subtitle').textContent = 'SocialHub 数据分析接入凭证（必填）';
  document.getElementById('modal-cred-body').innerHTML = `
    <div class="form-group">
      <label>Auth URL <span style="color:var(--danger)">*</span></label>
      <input id="sh-auth-url" class="form-control" placeholder="http://host/openapi-uat"
             value="${esc(existing?.auth_url || '')}">
    </div>
    <div class="form-group">
      <label>App ID <span style="color:var(--danger)">*</span></label>
      <input id="sh-app-id" class="form-control" placeholder="3e5bced1-..."
             value="${esc(existing?.app_id || '')}">
    </div>
    <div class="form-group">
      <label>App Secret <span style="color:var(--danger)">*</span></label>
      <input id="sh-app-secret" class="form-control" type="password" placeholder="输入 app_secret">
    </div>
    <button class="btn btn-primary" style="width:100%;margin-top:8px" onclick="saveSocialHubCred()">保存</button>
  `;
}

async function saveSocialHubCred() {
  const auth_url = document.getElementById('sh-auth-url').value.trim();
  const app_id = document.getElementById('sh-app-id').value.trim();
  const app_secret = document.getElementById('sh-app-secret').value.trim();
  if (!auth_url || !app_id || !app_secret) {
    showToast('Auth URL、App ID 和 App Secret 均为必填', 'error'); return;
  }
  const resp = await apiFetch('/credentials/mcp', {
    method: 'PUT',
    body: JSON.stringify({ auth_url, app_id, app_secret }),
  });
  if (!resp.ok) { showToast('保存失败', 'error'); return; }
  showToast('MCP 凭证保存成功');
  closeModal('modal-cred');
  loadCredentials();
}
```

- [ ] **Step 5: 修改 loadCredentials() 同时展示两类凭证**

`loadCredentials()` 需同时 `GET /credentials/mcp` 和 `GET /credentials/bigquery`，在凭证区域分别显示状态：MCP 凭证放第一位，未配置时显示红色警告。

- [ ] **Step 6: Commit**

```bash
git add mcp_server/static/ui.html
git commit -m "feat: portal UI adds MCP credential type (first, required)"
```

---

## Task 7: 集成测试 & Docker 验证

**Files:**
- Modify: `.env.local`
- Modify: `tests/test_integration_mcp_http.py`

- [ ] **Step 1: .env.local 加 MCP_TENANT_CREDS 和 MCP_AUTH_URL**

```bash
MCP_AUTH_URL=http://192.168.1.16:30833/openapi-uat
MCP_TENANT_CREDS=uat:3e5bced1-0370-11ee-b837-00163e030c1a:451c425c-0370-11ee-b837-00163e030c1e
```

- [ ] **Step 2: 重建 Docker 镜像并重启**

```bash
cd /Users/wangyunlong/myproject/sap_Integration/src/Socialhub-CLI
docker build -t socialhub-mcp:local . && \
docker stop socialhub-mcp-test && docker rm socialhub-mcp-test && \
docker run -d --name socialhub-mcp-test -p 8091:8090 --env-file .env.local socialhub-mcp:local && \
sleep 4 && docker logs socialhub-mcp-test --tail 10
```

Expected: 无 401 错误，启动日志显示 token 获取成功。

- [ ] **Step 3: curl 验证 analytics_overview 返回真实数据**

```bash
curl -s -X POST http://localhost:8091/mcp/ \
  -H "Authorization: Bearer sh_a2d8db3b7011a3e4a4dbf56b49203abf" \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"analytics_overview","arguments":{}}}' \
  | python3 -m json.tool
```

Expected: `result.content[0].text` 包含真实 GMV/订单数据，而非 `"error"` 字段。

- [ ] **Step 4: 运行集成测试**

```bash
conda run -n dev pytest tests/test_integration_mcp_http.py -v
```

Expected: 14/14 passed.

- [ ] **Step 5: Commit**

```bash
git add .env.local tests/test_integration_mcp_http.py
git commit -m "feat: verify end-to-end MCP tool call with real SocialHub token"
```
