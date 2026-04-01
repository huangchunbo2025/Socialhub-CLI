# API Key 管理 + 统一认证 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 用户通过 SocialHub 账号密码登录门户，在「API Key 管理」页面创建/吊销 API Key，MCP 客户端用这些 Key 认证；门户还提供「凭证管理」页面管理 BigQuery SA JSON。

**Architecture:**
- 新增 `tenant_api_keys` 表存储 API Key（SHA-256 哈希）。
- 登录认证采用 **JWT**（无状态，不建 session 表）：登录成功签发 JWT，前端存 localStorage，每次请求带 `X-Portal-Token` header，服务端验签。
- `APIKeyMiddleware` 改为优先查 DB（tenant_api_keys），找不到时 fallback 到 `MCP_API_KEYS` env var（保持向后兼容）。
- 门户 API（`/auth/*`、`/api-keys`）用 JWT 认证；MCP API（`/mcp`、`/credentials/bigquery`）继续用 API Key 认证，但也接受 JWT（UI 查看凭证状态用）。

**Tech Stack:** SQLAlchemy 2.0 async, asyncpg, Alembic, Starlette, httpx, secrets (stdlib), hashlib (stdlib), hmac + base64 + json (stdlib JWT，无额外依赖)

---

## File Map

| 动作 | 文件 | 职责 |
|------|------|------|
| 新建 | `mcp_server/services/jwt_service.py` | 签发/验证 JWT（stdlib 实现） |
| 新建 | `mcp_server/routers/auth_portal.py` | `POST /auth/login` |
| 新建 | `mcp_server/routers/api_keys.py` | POST/GET/DELETE `/api-keys` |
| 新建 | `alembic_mcp/versions/xxxx_add_tenant_api_keys.py` | DB migration |
| 修改 | `mcp_server/models.py` | 新增 `TenantApiKey` 模型 |
| 修改 | `mcp_server/auth.py` | DB API Key 查询 + `resolve_tenant_id()` 支持 JWT |
| 修改 | `mcp_server/routers/credentials.py` | 改用 `resolve_tenant_id()` 替代 `_get_tenant_id()` |
| 修改 | `mcp_server/http_app.py` | 注册新路由，`/auth/login` 加入免认证白名单 |
| 修改 | `mcp_server/static/ui.html` | 完全重写：SocialHub 登录 + 左侧导航 + API Key 页 + 凭证页 |
| 修改 | `alembic_mcp/env.py` | 注册新模型供 autogenerate 使用（Task 1 已完成）|
| 新建 | `tests/test_jwt_service.py` | JWT 服务单元测试 |
| 新建 | `tests/test_auth_portal.py` | 登录接口测试 |
| 新建 | `tests/test_api_keys_router.py` | API Key CRUD 测试 |

---

## Task 1: DB Model + Alembic Migration ✅ 已完成（commit 4b892f2）

**Files:**
- Modify: `mcp_server/models.py`
- Modify: `mcp_server/db.py`
- Create: `alembic_mcp/versions/<rev>_add_tenant_api_keys.py`

- [ ] **Step 1: Add `TenantApiKey` model to `mcp_server/models.py`**

在文件末尾追加（保留已有的 `TenantBigQueryCredential`）：

```python
class TenantApiKey(Base):
    """API Keys for MCP client authentication, managed per tenant via portal."""

    __tablename__ = "tenant_api_keys"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    key_prefix: Mapped[str] = mapped_column(String(10), nullable=False)   # first 8 chars, for display
    key_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)  # SHA-256 hex
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
```

- [ ] **Step 2: Register model in `mcp_server/db.py` `init_db()`**

```python
async def init_db() -> None:
    """Create all tables. Called at application startup."""
    from mcp_server.models import TenantBigQueryCredential, TenantApiKey  # noqa: F401
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database tables initialized")
```

- [ ] **Step 3: Generate Alembic migration**

```bash
cd /Users/wangyunlong/myproject/sap_Integration/src/Socialhub-CLI
conda run -n dev alembic -c alembic_mcp/alembic.ini revision --autogenerate \
  -m "add_tenant_api_keys"
```

Expected: new file in `alembic_mcp/versions/` named `xxxx_add_tenant_api_keys.py`

- [ ] **Step 4: Verify migration content**

Open the generated file. Confirm it contains `op.create_table('tenant_api_keys', ...)` with all columns: id, tenant_id, name, key_prefix, key_hash, created_at, last_used_at, revoked_at.

- [ ] **Step 5: Apply migration**

```bash
conda run -n dev alembic -c alembic_mcp/alembic.ini upgrade head
```

Expected output ends with: `Running upgrade ... -> <rev>, add_tenant_api_keys`

- [ ] **Step 6: Commit**

```bash
git add mcp_server/models.py mcp_server/db.py alembic_mcp/versions/
git commit -m "feat: add TenantApiKey model with migration"
```

---

## Task 2: JWT Service + Portal Login

**Files:**
- Create: `mcp_server/services/jwt_service.py`
- Create: `mcp_server/routers/auth_portal.py`
- Create: `tests/test_jwt_service.py`
- Create: `tests/test_auth_portal.py`

JWT 使用 stdlib 实现（`hmac` + `base64` + `json`），格式：`base64(header).base64(payload).hmac_sig`。
Secret 来自环境变量 `PORTAL_JWT_SECRET`（未设置时启动时 warning，用随机值兜底但每次重启失效）。
TTL：8 小时。

- [ ] **Step 1: Write failing tests for JWT service**

Create `tests/test_jwt_service.py`:

```python
"""Unit tests for jwt_service."""
import time
import pytest
from unittest.mock import patch

from mcp_server.services.jwt_service import create_token, verify_token


def test_create_and_verify_roundtrip():
    """create_token + verify_token returns original tenant_id."""
    token = create_token("tenant-abc")
    assert isinstance(token, str)
    assert token.count(".") == 2  # header.payload.sig

    tenant_id = verify_token(token)
    assert tenant_id == "tenant-abc"


def test_verify_expired_token():
    """verify_token returns None for expired token."""
    # Create token with TTL=0 by backdating exp
    token = create_token("tenant-abc")
    # Patch time so token appears expired
    with patch("mcp_server.services.jwt_service._now", return_value=int(time.time()) + 99999):
        result = verify_token(token)
    assert result is None


def test_verify_tampered_token():
    """verify_token returns None for tampered payload."""
    import base64, json
    token = create_token("tenant-abc")
    parts = token.split(".")
    # Replace payload with different tenant
    bad_payload = base64.urlsafe_b64encode(
        json.dumps({"sub": "hacker", "exp": int(time.time()) + 9999}).encode()
    ).rstrip(b"=").decode()
    tampered = f"{parts[0]}.{bad_payload}.{parts[2]}"
    assert verify_token(tampered) is None


def test_verify_invalid_format():
    """verify_token returns None for garbage input."""
    assert verify_token("not.a.token") is None
    assert verify_token("") is None
    assert verify_token("only-one-part") is None
```

- [ ] **Step 2: Run to confirm failure**

```bash
cd /Users/wangyunlong/myproject/sap_Integration/src/Socialhub-CLI
conda run -n dev pytest tests/test_jwt_service.py -v --tb=short 2>&1 | tail -15
```

Expected: `ImportError: No module named 'mcp_server.services.jwt_service'`

- [ ] **Step 3: Implement `mcp_server/services/jwt_service.py`**

```python
"""Minimal JWT implementation using Python stdlib only.

Format: base64url(header).base64url(payload).base64url(hmac_sig)
Algorithm: HMAC-SHA256
No external dependencies required.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import os
import secrets
import time

logger = logging.getLogger(__name__)

_JWT_TTL_SECONDS = 8 * 3600  # 8 hours

# Load secret from env; fallback to random (resets on restart — acceptable for dev)
_raw_secret = os.getenv("PORTAL_JWT_SECRET", "")
if not _raw_secret:
    _raw_secret = secrets.token_hex(32)
    logger.warning(
        "PORTAL_JWT_SECRET not set — using ephemeral random secret. "
        "All portal sessions will be invalidated on restart."
    )
_SECRET: bytes = _raw_secret.encode()


def _now() -> int:
    """Current UTC timestamp in seconds. Extracted for test patching."""
    return int(time.time())


def _b64encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _b64decode(s: str) -> bytes:
    # Re-add padding
    pad = 4 - len(s) % 4
    if pad != 4:
        s += "=" * pad
    return base64.urlsafe_b64decode(s)


def _sign(message: str) -> str:
    return _b64encode(hmac.new(_SECRET, message.encode(), hashlib.sha256).digest())


def create_token(tenant_id: str) -> str:
    """Create a signed JWT for the given tenant_id.

    Args:
        tenant_id: The authenticated tenant's ID.

    Returns:
        Signed JWT string: header.payload.signature
    """
    header = _b64encode(json.dumps({"alg": "HS256", "typ": "JWT"}).encode())
    payload = _b64encode(json.dumps({
        "sub": tenant_id,
        "exp": _now() + _JWT_TTL_SECONDS,
        "iat": _now(),
    }).encode())
    sig = _sign(f"{header}.{payload}")
    return f"{header}.{payload}.{sig}"


def verify_token(token: str) -> str | None:
    """Verify a JWT and return tenant_id if valid.

    Args:
        token: JWT string from X-Portal-Token header.

    Returns:
        tenant_id if token is valid and not expired, None otherwise.
    """
    try:
        parts = token.split(".")
        if len(parts) != 3:
            return None

        header, payload_b64, sig = parts

        # Verify signature
        expected_sig = _sign(f"{header}.{payload_b64}")
        if not hmac.compare_digest(sig, expected_sig):
            logger.debug("JWT signature verification failed")
            return None

        # Decode payload
        payload = json.loads(_b64decode(payload_b64))

        # Check expiry
        if payload.get("exp", 0) <= _now():
            logger.debug("JWT expired: exp=%s now=%s", payload.get("exp"), _now())
            return None

        return payload.get("sub")

    except Exception as e:
        logger.debug("JWT verification error: %s", e)
        return None
```

- [ ] **Step 4: Run JWT tests**

```bash
conda run -n dev pytest tests/test_jwt_service.py -v --tb=short
```

Expected: `4 passed`

- [ ] **Step 5: Write failing tests for auth portal**

Create `tests/test_auth_portal.py`:

```python
"""Tests for POST /auth/login endpoint."""
import pytest
from unittest.mock import MagicMock, patch
from starlette.testclient import TestClient

from mcp_server.http_app import app


@pytest.fixture
def client():
    return TestClient(app, raise_server_exceptions=False)


def test_login_missing_fields(client):
    """Login with missing fields returns 422."""
    resp = client.post("/auth/login", json={"tenantId": "democn"})
    assert resp.status_code == 422


def test_login_socialhub_error(client):
    """Login with wrong credentials returns 401."""
    with patch("mcp_server.routers.auth_portal.OAuthClient") as mock_cls:
        mock_client = MagicMock()
        mock_client.fetch_token.side_effect = Exception("invalid credentials")
        mock_cls.return_value = mock_client

        resp = client.post("/auth/login", json={
            "tenantId": "democn", "account": "bad", "pwd": "wrong"
        })

    assert resp.status_code == 401
    assert "error" in resp.json()


def test_login_success_returns_jwt(client):
    """Successful login returns a JWT token."""
    with patch("mcp_server.routers.auth_portal.OAuthClient") as mock_cls:
        mock_client = MagicMock()
        mock_client.fetch_token.return_value = {
            "token": "sh-token", "refreshToken": "r", "expiresTime": 9999
        }
        mock_cls.return_value = mock_client

        resp = client.post("/auth/login", json={
            "tenantId": "democn", "account": "admin", "pwd": "pass"
        })

    assert resp.status_code == 200
    data = resp.json()
    assert "token" in data
    assert data["token"].count(".") == 2  # valid JWT format
    assert data["tenant_id"] == "democn"


def test_login_no_auth_url(client):
    """Login returns 503 when SOCIALHUB_AUTH_URL is not configured."""
    with patch("mcp_server.routers.auth_portal._SOCIALHUB_AUTH_URL", ""):
        resp = client.post("/auth/login", json={
            "tenantId": "democn", "account": "admin", "pwd": "pass"
        })
    assert resp.status_code == 503
```

- [ ] **Step 6: Implement `mcp_server/routers/auth_portal.py`**

```python
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
    """POST /auth/login — authenticate with SocialHub credentials, return JWT."""
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
        return JSONResponse(status_code=500, content={"error": "登录服务异常，请稍后重试"})

    jwt_token = create_token(req.tenantId)
    logger.info("Portal login success: tenant=%s", req.tenantId)

    return JSONResponse(status_code=200, content={
        "token": jwt_token,
        "tenant_id": req.tenantId,
    })
```

- [ ] **Step 7: Register route in `mcp_server/http_app.py`**

Add import:
```python
from mcp_server.routers.auth_portal import login
```

Add `/auth/login` to `_AUTH_EXEMPT_PATHS` in `mcp_server/auth.py`:
```python
_AUTH_EXEMPT_PATHS: frozenset[str] = frozenset({
    "/health", "/health/", "/ui", "/ui/", "/auth/login", "/auth/login/"
})
```

Add route in `_app = Starlette(routes=[...])`:
```python
Route("/auth/login", login, methods=["POST"]),
```

- [ ] **Step 8: Run auth portal tests**

```bash
conda run -n dev pytest tests/test_auth_portal.py -v --tb=short
```

Expected: `4 passed`

- [ ] **Step 9: Commit**

```bash
git add mcp_server/services/jwt_service.py mcp_server/routers/auth_portal.py \
        mcp_server/auth.py mcp_server/http_app.py \
        tests/test_jwt_service.py tests/test_auth_portal.py
git commit -m "feat: add JWT service and portal login endpoint"
```

---

## Task 3: API Key Management Endpoints

**Files:**
- Create: `mcp_server/routers/api_keys.py`
- Create: `tests/test_api_keys_router.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_api_keys_router.py`:

```python
"""Tests for /api-keys endpoints."""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from starlette.testclient import TestClient

from mcp_server.http_app import app

VALID_JWT = "valid.jwt.token"
TENANT_ID = "democn"


@pytest.fixture
def client():
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture(autouse=True)
def mock_jwt_verification():
    """All tests use a valid JWT by default."""
    with patch(
        "mcp_server.routers.api_keys.verify_token",
        return_value=TENANT_ID,
    ):
        yield


def test_create_api_key_success(client):
    """POST /api-keys creates a new key and returns the full key once."""
    with patch("mcp_server.routers.api_keys.get_session") as mock_get:
        mock_db = AsyncMock()
        mock_db.__aenter__ = AsyncMock(return_value=mock_db)
        mock_db.__aexit__ = AsyncMock(return_value=False)
        mock_get.return_value = mock_db

        resp = client.post(
            "/api-keys",
            json={"name": "My MCP Key"},
            headers={"X-Portal-Token": VALID_JWT},
        )

    assert resp.status_code == 201
    data = resp.json()
    assert data["key"].startswith("sh_")
    assert data["name"] == "My MCP Key"
    assert "id" in data


def test_create_api_key_without_token(client):
    """POST /api-keys without JWT returns 401."""
    with patch("mcp_server.routers.api_keys.verify_token", return_value=None):
        resp = client.post("/api-keys", json={"name": "test"})
    assert resp.status_code == 401


def test_list_api_keys(client):
    """GET /api-keys returns list of active keys for the tenant."""
    from mcp_server.models import TenantApiKey
    from datetime import datetime, timezone

    fake_key = MagicMock(spec=TenantApiKey)
    fake_key.id = 1
    fake_key.name = "My MCP Key"
    fake_key.key_prefix = "sh_abc123"
    fake_key.created_at = datetime(2026, 4, 1, tzinfo=timezone.utc)
    fake_key.last_used_at = None
    fake_key.revoked_at = None

    with patch("mcp_server.routers.api_keys.get_session") as mock_get:
        mock_db = AsyncMock()
        mock_db.__aenter__ = AsyncMock(return_value=mock_db)
        mock_db.__aexit__ = AsyncMock(return_value=False)
        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = [fake_key]
        mock_db.execute = AsyncMock(return_value=result_mock)
        mock_get.return_value = mock_db

        resp = client.get("/api-keys", headers={"X-Portal-Token": VALID_JWT})

    assert resp.status_code == 200
    data = resp.json()
    assert len(data["keys"]) == 1
    assert data["keys"][0]["name"] == "My MCP Key"
    assert "key_hash" not in data["keys"][0]  # never expose hash


def test_revoke_api_key(client):
    """DELETE /api-keys/{key_id} sets revoked_at."""
    from mcp_server.models import TenantApiKey

    fake_key = MagicMock(spec=TenantApiKey)
    fake_key.tenant_id = TENANT_ID
    fake_key.revoked_at = None

    with patch("mcp_server.routers.api_keys.get_session") as mock_get:
        mock_db = AsyncMock()
        mock_db.__aenter__ = AsyncMock(return_value=mock_db)
        mock_db.__aexit__ = AsyncMock(return_value=False)
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = fake_key
        mock_db.execute = AsyncMock(return_value=result_mock)
        mock_get.return_value = mock_db

        resp = client.delete("/api-keys/1", headers={"X-Portal-Token": VALID_JWT})

    assert resp.status_code == 200
    assert fake_key.revoked_at is not None


def test_revoke_api_key_not_found(client):
    """DELETE /api-keys/{key_id} returns 404 if key not found."""
    with patch("mcp_server.routers.api_keys.get_session") as mock_get:
        mock_db = AsyncMock()
        mock_db.__aenter__ = AsyncMock(return_value=mock_db)
        mock_db.__aexit__ = AsyncMock(return_value=False)
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = None
        mock_db.execute = AsyncMock(return_value=result_mock)
        mock_get.return_value = mock_db

        resp = client.delete("/api-keys/999", headers={"X-Portal-Token": VALID_JWT})

    assert resp.status_code == 404
```

- [ ] **Step 2: Run to confirm failure**

```bash
conda run -n dev pytest tests/test_api_keys_router.py -v --tb=short 2>&1 | tail -15
```

Expected: `ImportError` or route not found errors.

- [ ] **Step 3: Implement `mcp_server/routers/api_keys.py`**

```python
"""API Key management endpoints.

Routes (all require X-Portal-Token JWT header):
    POST   /api-keys          — Create a new API key (returns raw key once)
    GET    /api-keys          — List active API keys for tenant
    DELETE /api-keys/{key_id} — Revoke an API key
"""

from __future__ import annotations

import hashlib
import logging
import secrets
from datetime import datetime, timezone

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

    Returns:
        tenant_id if valid, None otherwise.
    """
    token = request.headers.get("X-Portal-Token", "").strip()
    if not token:
        return None
    return verify_token(token)


def _hash_key(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


def _generate_api_key() -> str:
    return f"sh_{secrets.token_hex(16)}"


class CreateKeyRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100, description="Human-readable key name")


async def create_api_key(request: Request) -> JSONResponse:
    """POST /api-keys — create a new API key."""
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
        )
        session.add(row)
        await session.commit()
        await session.refresh(row)

    logger.info("API key created: tenant=%s name=%s prefix=%s", tenant_id, req.name, key_prefix)
    return JSONResponse(status_code=201, content={
        "id": row.id,
        "name": row.name,
        "key": raw_key,
        "key_prefix": key_prefix,
        "created_at": row.created_at.isoformat(),
    })


async def list_api_keys(request: Request) -> JSONResponse:
    """GET /api-keys — list active (non-revoked) API keys for tenant."""
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
                "created_at": row.created_at.isoformat(),
                "last_used_at": row.last_used_at.isoformat() if row.last_used_at else None,
            }
            for row in rows
        ]
    })


async def revoke_api_key(request: Request) -> JSONResponse:
    """DELETE /api-keys/{key_id} — revoke an API key."""
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
```

- [ ] **Step 4: Register routes in `mcp_server/http_app.py`**

Add imports:
```python
from mcp_server.routers.api_keys import create_api_key, list_api_keys, revoke_api_key
```

Add routes:
```python
Route("/api-keys", create_api_key, methods=["POST"]),
Route("/api-keys", list_api_keys, methods=["GET"]),
Route("/api-keys/{key_id}", revoke_api_key, methods=["DELETE"]),
```

- [ ] **Step 5: Run API key tests**

```bash
conda run -n dev pytest tests/test_api_keys_router.py -v --tb=short
```

Expected: `5 passed`

- [ ] **Step 6: Commit**

```bash
git add mcp_server/routers/api_keys.py mcp_server/http_app.py tests/test_api_keys_router.py
git commit -m "feat: add API key management endpoints (create/list/revoke)"
```

---

## Task 4: Update APIKeyMiddleware to Check DB + resolve_tenant_id

**Files:**
- Modify: `mcp_server/auth.py`
- Modify: `mcp_server/routers/credentials.py`

**Goal:** `APIKeyMiddleware` 先查 DB（tenant_api_keys），找不到再 fallback 到 `MCP_API_KEYS` env var。同时新增 `resolve_tenant_id()` 函数，让 `/credentials/bigquery` 也能接受 JWT（UI 查看凭证状态用）。

- [ ] **Step 1: Add `_lookup_api_key_in_db()` and update `dispatch()` in `mcp_server/auth.py`**

Add import at top:
```python
import hashlib
```

Add function before `APIKeyMiddleware` class:
```python
async def _lookup_api_key_in_db(api_key: str) -> str | None:
    """Look up API key in DB by SHA-256 hash. Returns tenant_id or None.

    Falls back gracefully if DB is unavailable.
    """
    try:
        from mcp_server.db import get_session
        from mcp_server.models import TenantApiKey
        from sqlalchemy import select

        key_hash = hashlib.sha256(api_key.encode()).hexdigest()
        session = await get_session()
        async with session:
            stmt = select(TenantApiKey).where(
                TenantApiKey.key_hash == key_hash,
                TenantApiKey.revoked_at.is_(None),
            )
            row = (await session.execute(stmt)).scalar_one_or_none()
        if row is not None:
            return row.tenant_id
    except Exception as e:
        logger.warning("DB API key lookup failed (fallback to env var): %s", e)
    return None
```

Update `dispatch()` in `APIKeyMiddleware` to check DB first:
```python
async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
    if request.url.path in _AUTH_EXEMPT_PATHS:
        return await call_next(request)

    api_key = _extract_api_key(request)
    tenant_id: str | None = None

    # DB lookup first (keys created via portal)
    if api_key:
        tenant_id = await _lookup_api_key_in_db(api_key)

    # Fallback: env var map (bootstrap / backward compat)
    if tenant_id is None:
        for stored_key, tid in self._key_map.items():
            if api_key and hmac.compare_digest(api_key, stored_key):
                tenant_id = tid
                break

    if tenant_id is None:
        ref_id = str(uuid.uuid4())
        logger.warning(
            "API Key 认证失败: path=%s ref_id=%s key_prefix=%s",
            request.url.path, ref_id, api_key[:8] if api_key else "<empty>",
        )
        return JSONResponse(
            status_code=401,
            content={"error": "unauthorized", "message": "Invalid or missing API Key",
                     "reference_id": ref_id},
        )

    request.state.tenant_id = tenant_id
    logger.info("API Key auth succeeded: path=%s tenant=%s prefix=%s",
                request.url.path, tenant_id, api_key[:8] if api_key else "<empty>")
    token = _tenant_id_var.set(tenant_id)
    try:
        response = await call_next(request)
    finally:
        _tenant_id_var.reset(token)
    return response
```

Add `resolve_tenant_id()` at end of `auth.py`:
```python
async def resolve_tenant_id(request: Request) -> str | None:
    """Resolve tenant_id from API Key (middleware) or JWT (portal UI).

    Precedence: API Key (set by middleware) > X-Portal-Token JWT header.

    Args:
        request: Incoming Starlette request.

    Returns:
        tenant_id or None if not authenticated.
    """
    # API Key path: already injected by APIKeyMiddleware
    tenant_id: str | None = getattr(request.state, "tenant_id", None)
    if tenant_id:
        return tenant_id

    # JWT path: portal UI access
    jwt_token = request.headers.get("X-Portal-Token", "").strip()
    if jwt_token:
        from mcp_server.services.jwt_service import verify_token
        return verify_token(jwt_token)

    return None
```

- [ ] **Step 2: Update `mcp_server/routers/credentials.py`**

Change import:
```python
# Remove:
from mcp_server.auth import _get_tenant_id
# Add:
from mcp_server.auth import resolve_tenant_id
```

In each of the three handlers (`upload_credentials`, `get_credentials`, `delete_credentials`), replace:
```python
tenant_id = _get_tenant_id()
```
with:
```python
tenant_id = await resolve_tenant_id(request)
if tenant_id is None:
    return JSONResponse(status_code=401, content={"status": "error", "message": "未认证"})
```

- [ ] **Step 3: Run full test suite**

```bash
conda run -n dev pytest tests/test_credentials_router.py tests/test_api_keys_router.py \
  tests/test_auth_portal.py tests/test_jwt_service.py -v --tb=short 2>&1 | tail -30
```

Expected: all pass. If `test_credentials_router.py` breaks, check: the existing fixtures set `request.state.tenant_id` via `APIKeyMiddleware` mock — `resolve_tenant_id()` reads `request.state.tenant_id` first, so it should still work.

- [ ] **Step 4: Commit**

```bash
git add mcp_server/auth.py mcp_server/routers/credentials.py
git commit -m "feat: APIKeyMiddleware checks DB first, add resolve_tenant_id for JWT support"
```

---

## Task 5: UI Complete Redesign

**Files:**
- Modify: `mcp_server/static/ui.html`

**Design:**
- Login page: SocialHub 账号密码（tenantId + account + password）
- 登录后进入主界面：左侧导航 + 右侧内容区
- 左侧导航：「API Key 管理」「凭证管理」两个菜单项
- API Key 管理页：表格列出 keys（name、prefix、创建时间）+ 「新建」按钮 + 「吊销」按钮
- 凭证管理页：BigQuery 凭证状态卡片 + 「新建凭证」按钮（拖拽上传 SA JSON）
- Token 存储：`localStorage.setItem('mcp_portal_token', jwt)`，header 用 `X-Portal-Token`

- [ ] **Step 1: Replace `mcp_server/static/ui.html` completely**

```html
<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>SocialHub MCP 管理门户</title>
<style>
  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
  :root {
    --primary: #0057b8; --primary-dark: #003f8a; --danger: #d93025;
    --success: #1e8e3e; --bg: #f5f7fa; --sidebar-bg: #1a1f36;
    --sidebar-text: #c8cde4; --card-bg: #ffffff; --border: #e1e4e8;
    --text: #24292e; --muted: #6a737d; --radius: 8px;
  }
  body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
         background: var(--bg); color: var(--text); height: 100vh; display: flex; }

  /* Login */
  #login-page { width:100%; display:flex; align-items:center; justify-content:center; }
  .login-card { background:var(--card-bg); border-radius:var(--radius);
    box-shadow:0 4px 24px rgba(0,0,0,.12); padding:48px 40px; width:400px; }
  .login-card h1 { font-size:22px; margin-bottom:8px; }
  .login-card p { color:var(--muted); font-size:14px; margin-bottom:32px; }
  .form-group { margin-bottom:18px; }
  .form-group label { display:block; font-size:13px; font-weight:600; margin-bottom:6px; }
  .form-group input { width:100%; padding:10px 12px; border:1px solid var(--border);
    border-radius:6px; font-size:14px; outline:none; transition:border .2s; }
  .form-group input:focus { border-color:var(--primary); }

  /* Buttons */
  .btn { display:inline-flex; align-items:center; gap:6px; padding:10px 18px;
    border:none; border-radius:6px; font-size:14px; font-weight:600;
    cursor:pointer; transition:background .2s, opacity .2s; }
  .btn:disabled { opacity:.5; cursor:not-allowed; }
  .btn-primary { background:var(--primary); color:#fff; }
  .btn-primary:hover:not(:disabled) { background:var(--primary-dark); }
  .btn-full { width:100%; justify-content:center; }
  .btn-sm { padding:6px 12px; font-size:13px; }
  .btn-outline { background:transparent; border:1px solid var(--border); color:var(--text); }
  .btn-outline:hover { background:var(--bg); }
  .btn-danger { background:var(--danger); color:#fff; }
  .btn-danger:hover:not(:disabled) { background:#b52b20; }
  .error-msg { color:var(--danger); font-size:13px; margin-top:12px; min-height:20px; }

  /* App shell */
  #app { display:none; width:100%; }
  .sidebar { width:220px; background:var(--sidebar-bg); display:flex;
    flex-direction:column; flex-shrink:0; padding:0 0 24px; }
  .sidebar-logo { padding:24px 20px 20px; font-size:15px; font-weight:700; color:#fff;
    border-bottom:1px solid rgba(255,255,255,.08); margin-bottom:12px; }
  .sidebar-logo span { opacity:.6; font-weight:400; font-size:12px; display:block; }
  .nav-item { display:flex; align-items:center; gap:10px; padding:10px 20px;
    color:var(--sidebar-text); font-size:14px; cursor:pointer; transition:background .15s; }
  .nav-item:hover { background:rgba(255,255,255,.06); color:#fff; }
  .nav-item.active { background:rgba(255,255,255,.12); color:#fff; }
  .nav-icon { font-size:16px; width:20px; text-align:center; }
  .sidebar-bottom { margin-top:auto; padding:0 16px; }
  .sidebar-tenant { padding:12px 20px; color:rgba(255,255,255,.4);
    font-size:12px; word-break:break-all; }

  .main { flex:1; overflow-y:auto; padding:32px 36px; }
  .page-header { display:flex; align-items:center; justify-content:space-between; margin-bottom:28px; }
  .page-header h2 { font-size:20px; font-weight:700; }

  /* Cards & Tables */
  .card { background:var(--card-bg); border:1px solid var(--border);
    border-radius:var(--radius); padding:24px; margin-bottom:20px; }
  table { width:100%; border-collapse:collapse; font-size:14px; }
  th { text-align:left; padding:10px 12px; font-size:12px; font-weight:600;
    text-transform:uppercase; letter-spacing:.5px; color:var(--muted);
    border-bottom:1px solid var(--border); }
  td { padding:12px; border-bottom:1px solid var(--border); vertical-align:middle; }
  tr:last-child td { border-bottom:none; }
  .badge { display:inline-block; padding:2px 8px; border-radius:12px; font-size:12px; font-weight:500; }
  .badge-ok { background:#e8f5e9; color:var(--success); }

  /* Modal */
  .modal-overlay { position:fixed; inset:0; background:rgba(0,0,0,.4);
    display:flex; align-items:center; justify-content:center; z-index:100; }
  .modal { background:#fff; border-radius:var(--radius); padding:32px;
    width:480px; box-shadow:0 8px 32px rgba(0,0,0,.18); }
  .modal h3 { font-size:17px; margin-bottom:20px; }
  .modal-actions { display:flex; gap:10px; justify-content:flex-end; margin-top:24px; }
  .key-reveal { background:#f6f8fa; border:1px solid var(--border); border-radius:6px;
    padding:12px; font-family:monospace; font-size:13px; word-break:break-all; margin:16px 0; }

  /* Dropzone */
  .dropzone { border:2px dashed var(--border); border-radius:var(--radius);
    padding:32px; text-align:center; cursor:pointer; transition:border .2s,background .2s;
    color:var(--muted); font-size:14px; }
  .dropzone.over { border-color:var(--primary); background:#f0f4ff; }
  .dropzone.has-file { border-color:var(--success); background:#f0faf3; color:var(--text); }

  .spinner { display:inline-block; width:14px; height:14px;
    border:2px solid rgba(255,255,255,.4); border-top-color:#fff;
    border-radius:50%; animation:spin .6s linear infinite; }
  @keyframes spin { to { transform:rotate(360deg); } }
  .hidden { display:none !important; }
  .text-muted { color:var(--muted); font-size:13px; }
  .mt-8 { margin-top:8px; }
</style>
</head>
<body>

<!-- LOGIN -->
<div id="login-page">
  <div class="login-card">
    <h1>SocialHub MCP 管理门户</h1>
    <p>使用 SocialHub 账号登录以管理 API Key 和数据凭证</p>
    <div class="form-group">
      <label>租户 ID</label>
      <input id="login-tenant" type="text" placeholder="例：democn" autocomplete="off">
    </div>
    <div class="form-group">
      <label>账号</label>
      <input id="login-account" type="text" placeholder="账号名" autocomplete="username">
    </div>
    <div class="form-group">
      <label>密码</label>
      <input id="login-pwd" type="password" placeholder="密码" autocomplete="current-password">
    </div>
    <button class="btn btn-primary btn-full" id="login-btn" onclick="doLogin()">登录</button>
    <div class="error-msg" id="login-error"></div>
  </div>
</div>

<!-- APP -->
<div id="app">
  <aside class="sidebar">
    <div class="sidebar-logo">MCP 管理门户<span>SocialHub</span></div>
    <div class="nav-item active" id="nav-apikeys" onclick="showPage('apikeys')">
      <span class="nav-icon">🔑</span> API Key 管理
    </div>
    <div class="nav-item" id="nav-credentials" onclick="showPage('credentials')">
      <span class="nav-icon">🗄️</span> 凭证管理
    </div>
    <div class="sidebar-bottom">
      <div class="sidebar-tenant" id="sidebar-tenant"></div>
      <button class="btn btn-sm btn-outline"
        style="width:100%;color:#c8cde4;border-color:rgba(255,255,255,.2);background:transparent"
        onclick="doLogout()">退出登录</button>
    </div>
  </aside>

  <main class="main">
    <!-- API Keys Page -->
    <div id="page-apikeys">
      <div class="page-header">
        <h2>API Key 管理</h2>
        <button class="btn btn-primary btn-sm" onclick="openCreateKeyModal()">＋ 新建 API Key</button>
      </div>
      <div class="card">
        <table><thead><tr>
          <th>名称</th><th>Key 前缀</th><th>创建时间</th><th>最后使用</th><th></th>
        </tr></thead>
        <tbody id="keys-tbody"></tbody></table>
        <p class="text-muted mt-8 hidden" id="keys-empty">暂无 API Key，点击「新建」创建第一个</p>
      </div>
    </div>

    <!-- Credentials Page -->
    <div id="page-credentials" class="hidden">
      <div class="page-header">
        <h2>凭证管理</h2>
        <button class="btn btn-primary btn-sm" onclick="openCredModal()">＋ 新建凭证</button>
      </div>
      <div id="cred-card" class="card"><p class="text-muted">加载中…</p></div>
    </div>
  </main>
</div>

<!-- MODAL: Create Key -->
<div class="modal-overlay hidden" id="modal-create-key">
  <div class="modal">
    <h3>新建 API Key</h3>
    <div class="form-group">
      <label>Key 名称</label>
      <input id="new-key-name" type="text" placeholder="例：Claude Desktop 生产环境">
    </div>
    <div class="error-msg" id="create-key-error"></div>
    <div class="modal-actions">
      <button class="btn btn-outline" onclick="closeModal('modal-create-key')">取消</button>
      <button class="btn btn-primary" id="create-key-btn" onclick="doCreateKey()">创建</button>
    </div>
  </div>
</div>

<!-- MODAL: Show Key -->
<div class="modal-overlay hidden" id="modal-show-key">
  <div class="modal">
    <h3>✅ API Key 已创建</h3>
    <p class="text-muted">请立即复制并保存，此 Key 只显示一次：</p>
    <div class="key-reveal" id="new-key-value"></div>
    <div class="modal-actions">
      <button class="btn btn-primary" onclick="copyKey()">复制 Key</button>
      <button class="btn btn-outline" onclick="closeModal('modal-show-key');loadApiKeys()">我已保存，关闭</button>
    </div>
  </div>
</div>

<!-- MODAL: New Credential -->
<div class="modal-overlay hidden" id="modal-cred">
  <div class="modal">
    <h3>新建 BigQuery 凭证</h3>
    <p class="text-muted" style="margin-bottom:16px">SAP Emarsys BigQuery 集成</p>
    <div class="form-group">
      <label>GCP Project ID</label>
      <input id="cred-project" type="text" placeholder="例：sap-emarsys-data-prod">
    </div>
    <div class="form-group">
      <label>Dataset ID <span class="text-muted">（可选，留空自动发现所有 emarsys_* 数据集）</span></label>
      <input id="cred-dataset" type="text" placeholder="留空自动发现">
    </div>
    <div class="form-group">
      <label>Service Account JSON</label>
      <div class="dropzone" id="sa-dropzone"
           onclick="document.getElementById('sa-file').click()"
           ondragover="event.preventDefault();this.classList.add('over')"
           ondragleave="this.classList.remove('over')"
           ondrop="handleDrop(event)">
        拖拽 SA JSON 文件到此处，或点击选择文件
      </div>
      <input type="file" id="sa-file" accept=".json" class="hidden" onchange="handleFileSelect(event)">
    </div>
    <div class="error-msg" id="cred-error"></div>
    <div class="modal-actions">
      <button class="btn btn-outline" onclick="closeModal('modal-cred')">取消</button>
      <button class="btn btn-primary" id="cred-submit-btn" onclick="doUploadCred()" disabled>上传并验证</button>
    </div>
  </div>
</div>

<script>
// ── State ──
let portalToken = localStorage.getItem('mcp_portal_token') || '';
let tenantId = localStorage.getItem('mcp_tenant') || '';
let saJsonData = null;
let pendingNewKey = '';

const $ = id => document.getElementById(id);
const show = id => $(id).classList.remove('hidden');
const hide = id => $(id).classList.add('hidden');
const closeModal = id => hide(id);

function portalHeaders() {
  return { 'Content-Type': 'application/json', 'X-Portal-Token': portalToken };
}

async function apiFetch(path, opts = {}) {
  const res = await fetch(path, opts);
  const data = await res.json().catch(() => ({}));
  return { ok: res.ok, status: res.status, data };
}

// ── Login ──
async function doLogin() {
  const tenant = $('login-tenant').value.trim();
  const account = $('login-account').value.trim();
  const pwd = $('login-pwd').value;
  $('login-error').textContent = '';
  if (!tenant || !account || !pwd) { $('login-error').textContent = '请填写所有字段'; return; }
  const btn = $('login-btn');
  btn.disabled = true; btn.innerHTML = '<span class="spinner"></span> 登录中…';
  const { ok, data } = await apiFetch('/auth/login', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ tenantId: tenant, account, pwd }),
  });
  btn.disabled = false; btn.textContent = '登录';
  if (!ok) { $('login-error').textContent = data.error || '登录失败'; return; }
  portalToken = data.token;
  tenantId = data.tenant_id;
  localStorage.setItem('mcp_portal_token', portalToken);
  localStorage.setItem('mcp_tenant', tenantId);
  enterApp();
}

$('login-pwd').addEventListener('keydown', e => { if (e.key === 'Enter') doLogin(); });

function enterApp() {
  hide('login-page'); show('app');
  $('sidebar-tenant').textContent = `租户：${tenantId}`;
  showPage('apikeys');
}

function checkAutoLogin() {
  if (portalToken && tenantId) enterApp();
}

function doLogout() {
  portalToken = ''; tenantId = '';
  localStorage.removeItem('mcp_portal_token');
  localStorage.removeItem('mcp_tenant');
  show('login-page'); hide('app');
}

// ── Navigation ──
function showPage(name) {
  ['apikeys','credentials'].forEach(p => {
    $('page-' + p)?.classList.toggle('hidden', p !== name);
    $('nav-' + p)?.classList.toggle('active', p === name);
  });
  if (name === 'apikeys') loadApiKeys();
  if (name === 'credentials') loadCredentials();
}

// ── API Keys ──
async function loadApiKeys() {
  const { ok, status, data } = await apiFetch('/api-keys', { headers: portalHeaders() });
  if (status === 401) { doLogout(); return; }
  if (!ok) return;
  const tbody = $('keys-tbody');
  tbody.innerHTML = '';
  if (!data.keys?.length) { show('keys-empty'); return; }
  hide('keys-empty');
  data.keys.forEach(k => {
    const tr = document.createElement('tr');
    tr.innerHTML = `
      <td>${esc(k.name)}</td>
      <td><code>${esc(k.key_prefix)}…</code></td>
      <td>${fmtDate(k.created_at)}</td>
      <td>${k.last_used_at ? fmtDate(k.last_used_at) : '<span class="text-muted">从未</span>'}</td>
      <td><button class="btn btn-danger btn-sm" onclick="revokeKey(${k.id},'${esc(k.name)}')">吊销</button></td>`;
    tbody.appendChild(tr);
  });
}

function openCreateKeyModal() {
  $('new-key-name').value = ''; $('create-key-error').textContent = '';
  show('modal-create-key'); setTimeout(() => $('new-key-name').focus(), 50);
}

async function doCreateKey() {
  const name = $('new-key-name').value.trim();
  $('create-key-error').textContent = '';
  if (!name) { $('create-key-error').textContent = '请输入 Key 名称'; return; }
  const btn = $('create-key-btn');
  btn.disabled = true; btn.innerHTML = '<span class="spinner"></span>';
  const { ok, data } = await apiFetch('/api-keys', {
    method: 'POST', headers: portalHeaders(), body: JSON.stringify({ name }),
  });
  btn.disabled = false; btn.textContent = '创建';
  if (!ok) { $('create-key-error').textContent = data.error || '创建失败'; return; }
  closeModal('modal-create-key');
  pendingNewKey = data.key;
  $('new-key-value').textContent = data.key;
  show('modal-show-key');
}

function copyKey() {
  navigator.clipboard.writeText(pendingNewKey).then(() => {
    event.target.textContent = '✓ 已复制';
    setTimeout(() => event.target.textContent = '复制 Key', 1500);
  });
}

async function revokeKey(id, name) {
  if (!confirm(`确定要吊销「${name}」吗？此操作不可恢复。`)) return;
  const { ok, data } = await apiFetch(`/api-keys/${id}`, {
    method: 'DELETE', headers: portalHeaders(),
  });
  if (!ok) { alert(data.error || '吊销失败'); return; }
  loadApiKeys();
}

// ── Credentials ──
async function loadCredentials() {
  const card = $('cred-card');
  card.innerHTML = '<p class="text-muted">加载中…</p>';
  const { ok, status, data } = await apiFetch('/credentials/bigquery', { headers: portalHeaders() });
  if (status === 401) { doLogout(); return; }
  if (!ok) { card.innerHTML = '<p class="text-muted">加载失败</p>'; return; }
  if (!data.configured) {
    card.innerHTML = `<div style="text-align:center;padding:40px 0">
      <div style="font-size:48px;margin-bottom:16px">🗄️</div>
      <p style="font-size:15px;font-weight:600;margin-bottom:8px">尚未配置 BigQuery 凭证</p>
      <p class="text-muted" style="margin-bottom:24px">配置后 MCP 工具可访问 Emarsys 数据</p>
      <button class="btn btn-primary" onclick="openCredModal()">＋ 新建凭证</button></div>`;
    return;
  }
  const datasets = (data.datasets_found || []).join('、') || '—';
  card.innerHTML = `
    <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:20px">
      <div><span class="badge badge-ok">✓ 已配置</span>
        <span class="text-muted" style="margin-left:8px;font-size:13px">上次验证：${fmtDate(data.validated_at)}</span>
      </div>
      <div style="display:flex;gap:8px">
        <button class="btn btn-outline btn-sm" onclick="openCredModal()">更新</button>
        <button class="btn btn-danger btn-sm" onclick="deleteCred()">删除</button>
      </div>
    </div>
    <table style="width:auto">
      <tr><td style="padding:6px 24px 6px 0;color:var(--muted);font-size:13px">GCP Project</td>
          <td><code>${esc(data.gcp_project_id)}</code></td></tr>
      <tr><td style="padding:6px 24px 6px 0;color:var(--muted);font-size:13px">发现的数据集</td>
          <td>${esc(datasets)}</td></tr>
      <tr><td style="padding:6px 24px 6px 0;color:var(--muted);font-size:13px">发现的表</td>
          <td>${(data.tables_found || []).length} 张</td></tr>
    </table>`;
}

function openCredModal() {
  $('cred-project').value = ''; $('cred-dataset').value = '';
  $('cred-error').textContent = ''; saJsonData = null;
  const dz = $('sa-dropzone');
  dz.textContent = '拖拽 SA JSON 文件到此处，或点击选择文件';
  dz.classList.remove('has-file','over');
  $('cred-submit-btn').disabled = true;
  show('modal-cred');
}

function handleDrop(e) {
  e.preventDefault(); $('sa-dropzone').classList.remove('over');
  if (e.dataTransfer.files[0]) loadSaFile(e.dataTransfer.files[0]);
}
function handleFileSelect(e) { if (e.target.files[0]) loadSaFile(e.target.files[0]); }
function loadSaFile(file) {
  const reader = new FileReader();
  reader.onload = ev => {
    try {
      saJsonData = JSON.parse(ev.target.result);
      const dz = $('sa-dropzone');
      dz.textContent = `✓ ${file.name}`;
      dz.classList.add('has-file');
      $('cred-submit-btn').disabled = false;
      if (saJsonData.project_id) $('cred-project').value = saJsonData.project_id;
    } catch { $('cred-error').textContent = '文件格式错误，请选择有效的 JSON 文件'; }
  };
  reader.readAsText(file);
}

async function doUploadCred() {
  $('cred-error').textContent = '';
  const project = $('cred-project').value.trim();
  const dataset = $('cred-dataset').value.trim() || null;
  if (!project) { $('cred-error').textContent = '请填写 GCP Project ID'; return; }
  if (!saJsonData) { $('cred-error').textContent = '请上传 Service Account JSON'; return; }
  const btn = $('cred-submit-btn');
  btn.disabled = true; btn.innerHTML = '<span class="spinner"></span> 验证中…';
  const { ok, data } = await apiFetch('/credentials/bigquery', {
    method: 'POST', headers: portalHeaders(),
    body: JSON.stringify({ gcp_project_id: project, dataset_id: dataset, service_account_json: saJsonData }),
  });
  btn.disabled = false; btn.textContent = '上传并验证';
  if (!ok) { $('cred-error').textContent = data.message || '上传失败'; return; }
  closeModal('modal-cred'); loadCredentials();
}

async function deleteCred() {
  if (!confirm('确定要删除 BigQuery 凭证吗？')) return;
  const { ok, data } = await apiFetch('/credentials/bigquery', {
    method: 'DELETE', headers: portalHeaders(),
  });
  if (!ok) { alert(data.message || '删除失败'); return; }
  loadCredentials();
}

// ── Utils ──
function esc(s) {
  return String(s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}
function fmtDate(iso) {
  if (!iso) return '—';
  return new Date(iso).toLocaleString('zh-CN', {
    year:'numeric', month:'2-digit', day:'2-digit', hour:'2-digit', minute:'2-digit'
  });
}

checkAutoLogin();
</script>
</body>
</html>
```

- [ ] **Step 2: Commit**

```bash
git add mcp_server/static/ui.html
git commit -m "feat: complete UI redesign — SocialHub login, API key management, credentials page"
```

---

## Task 6: Docker Rebuild + E2E Smoke Test

**Files:** None new.

- [ ] **Step 1: Run full relevant test suite**

```bash
cd /Users/wangyunlong/myproject/sap_Integration/src/Socialhub-CLI
conda run -n dev pytest tests/test_bigquery_validator.py tests/test_credentials_router.py \
  tests/test_crypto.py tests/test_db.py tests/test_models.py \
  tests/test_jwt_service.py tests/test_auth_portal.py tests/test_api_keys_router.py \
  -v --tb=short 2>&1 | tail -30
```

Expected: all pass.

- [ ] **Step 2: Apply migration to local DB**

```bash
conda run -n dev alembic -c alembic_mcp/alembic.ini upgrade head
```

- [ ] **Step 3: Rebuild Docker image**

```bash
docker build -t socialhub-mcp:local . 2>&1 | tail -15
```

Expected: `Successfully built` and `Successfully tagged socialhub-mcp:local`

- [ ] **Step 4: Run container**

```bash
docker stop socialhub-mcp-test 2>/dev/null; docker rm socialhub-mcp-test 2>/dev/null
docker run -d --name socialhub-mcp-test -p 8091:8090 \
  --env-file .env.local \
  -e SOCIALHUB_AUTH_URL="https://placeholder.socialhub.io" \
  -e PORTAL_JWT_SECRET="test-secret-for-local-dev" \
  socialhub-mcp:local
sleep 3
```

- [ ] **Step 5: Smoke tests**

```bash
# Health
curl -s http://localhost:8091/health | python3 -m json.tool

# Login returns 503 (placeholder URL) — expected
curl -s -X POST http://localhost:8091/auth/login \
  -H "Content-Type: application/json" \
  -d '{"tenantId":"democn","account":"test","pwd":"test"}' | python3 -m json.tool

# API keys requires JWT
curl -s http://localhost:8091/api-keys \
  -H "X-Portal-Token: invalid.jwt.token" | python3 -m json.tool
# Expected: {"error": "JWT 无效..."}

# Credentials still works with MCP_API_KEYS
curl -s http://localhost:8091/credentials/bigquery \
  -H "Authorization: Bearer sapbigquerytest" | python3 -m json.tool
# Expected: {"status":"ok","configured":...}
```

- [ ] **Step 6: Open UI in browser**

Open `http://localhost:8091/ui` — verify:
- Login form shows tenantId + account + password
- No API Key input field (old design removed)

- [ ] **Step 7: Commit**

```bash
git add -A
git commit -m "chore: all tasks complete — API key management with JWT auth"
```

---

## Environment Variables Summary

| 变量 | 用途 | 必填 |
|------|------|------|
| `DATABASE_URL` | PostgreSQL 连接串 | 是 |
| `MCP_API_KEYS` | Bootstrap API Key（向后兼容）| 可选 |
| `CREDENTIAL_ENCRYPT_KEY` | BigQuery SA JSON Fernet 加密 key | 是 |
| `SOCIALHUB_AUTH_URL` | SocialHub 认证 API 地址 | 是（门户登录用）|
| `PORTAL_JWT_SECRET` | JWT 签名密钥（未设置则随机，重启失效）| 建议设置 |

`.env.local` 新增：
```bash
SOCIALHUB_AUTH_URL=https://your-socialhub-api-host.com
PORTAL_JWT_SECRET=your-random-secret-here
```
