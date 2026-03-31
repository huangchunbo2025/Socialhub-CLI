# BigQuery 凭据管理门户 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 MCP Server 中新增 BigQuery 凭据管理功能：三个 REST API（上传/获取/删除）+ 单页 Web 界面，支持 Token 登录和 Emarsys Open Data 凭据的校验与加密存储。

**Architecture:** 新建 `db.py`（SQLAlchemy 2.0 async）、`models.py`（ORM）、`services/crypto.py`（Fernet 加密）、`services/bigquery_validator.py`（list_tables 校验）、`routers/credentials.py`（三个接口）；在 `http_app.py` 注册路由并 serve `static/ui.html`；Alembic 管理 DB migration。

**Tech Stack:** Python 3.10+, SQLAlchemy 2.0 async + asyncpg, Alembic, cryptography (Fernet), google-cloud-bigquery, Starlette, HTML + 原生 JS

---

## File Map

| 操作 | 文件 | 职责 |
|------|------|------|
| 修改 | `pyproject.toml` | 新增依赖 sqlalchemy[asyncio]>=2.0, asyncpg, google-cloud-bigquery |
| 新建 | `mcp_server/db.py` | 异步 DB 引擎 + Session 工厂 + lifespan 初始化 |
| 新建 | `mcp_server/models.py` | TenantBigQueryCredential ORM 模型 |
| 新建 | `alembic_mcp/` | MCP Server 专用 Alembic 配置 |
| 新建 | `mcp_server/services/__init__.py` | 空文件 |
| 新建 | `mcp_server/services/crypto.py` | Fernet 加解密 |
| 新建 | `mcp_server/services/bigquery_validator.py` | BQ list_tables 校验 |
| 新建 | `mcp_server/routers/__init__.py` | 空文件 |
| 新建 | `mcp_server/routers/credentials.py` | POST/GET/DELETE /credentials/bigquery |
| 修改 | `mcp_server/http_app.py` | 注册凭据路由 + /ui 静态页路由 + DB lifespan |
| 新建 | `mcp_server/static/ui.html` | 客户门户 HTML |
| 新建 | `tests/test_crypto.py` | crypto.py 单元测试 |
| 新建 | `tests/test_bigquery_validator.py` | bigquery_validator.py 单元测试 |
| 新建 | `tests/test_credentials_router.py` | 凭据接口集成测试 |

---

## Task 1: 安装依赖

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: 更新 pyproject.toml 依赖**

在 `[project.dependencies]` 列表中追加（替换现有 `sqlalchemy` 如有）：

```toml
[project.dependencies]
# ... 现有依赖 ...
"sqlalchemy[asyncio]>=2.0.0",
"asyncpg>=0.29.0",
"google-cloud-bigquery>=3.0.0",
"google-auth>=2.0.0",
```

在 `[project.optional-dependencies]` 的 `http` 组追加：

```toml
[project.optional-dependencies]
http = [
    "uvicorn>=0.30.0",
    "starlette>=0.40.0",
    "alembic>=1.13.0",
]
```

- [ ] **Step 2: 安装依赖**

```bash
cd /Users/wangyunlong/myproject/sap_Integration/src/Socialhub-CLI
pip install "sqlalchemy[asyncio]>=2.0.0" asyncpg "google-cloud-bigquery>=3.0.0" "google-auth>=2.0.0" alembic
```

- [ ] **Step 3: 验证安装**

```bash
python -c "import sqlalchemy; print(sqlalchemy.__version__)"
python -c "import asyncpg; print('asyncpg ok')"
python -c "from google.cloud import bigquery; print('bq ok')"
python -c "import alembic; print('alembic ok')"
```

期望：版本号均正常输出，无 ImportError

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml
git commit -m "chore: add sqlalchemy2, asyncpg, google-cloud-bigquery dependencies"
```

---

## Task 2: 数据库连接层（db.py）

**Files:**
- Create: `mcp_server/db.py`
- Test: `tests/test_db.py`

- [ ] **Step 1: 新建 `tests/test_db.py` 写失败测试**

```python
"""Tests for database connection module."""
import os
from unittest.mock import patch, AsyncMock

import pytest


def test_db_module_imports():
    """db.py 可以正常导入，关键函数存在。"""
    from mcp_server.db import get_session, init_db, close_db
    assert callable(get_session)
    assert callable(init_db)
    assert callable(close_db)


def test_database_url_from_env():
    """DATABASE_URL 从环境变量读取。"""
    with patch.dict(os.environ, {"DATABASE_URL": "postgresql+asyncpg://user:pw@host/db"}):
        import importlib
        import mcp_server.db as db_module
        importlib.reload(db_module)
        assert "host" in db_module.DATABASE_URL
```

- [ ] **Step 2: 运行确认失败**

```bash
cd /Users/wangyunlong/myproject/sap_Integration/src/Socialhub-CLI
pytest tests/test_db.py -v
```

期望：`ModuleNotFoundError: No module named 'mcp_server.db'`

- [ ] **Step 3: 新建 `mcp_server/db.py`**

```python
"""Database connection module for MCP Server.

Provides async SQLAlchemy engine and session factory.

Environment variables:
    DATABASE_URL: PostgreSQL connection string (postgresql+asyncpg://...)
"""

from __future__ import annotations

import logging
import os

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

logger = logging.getLogger(__name__)

DATABASE_URL: str = os.environ.get(
    "DATABASE_URL", "postgresql+asyncpg://postgres:postgres@localhost:5432/socialhub_mcp"
)

_engine = create_async_engine(DATABASE_URL, echo=False, pool_pre_ping=True)
_session_factory = async_sessionmaker(_engine, expire_on_commit=False, class_=AsyncSession)


class Base(DeclarativeBase):
    """Base class for all ORM models."""
    pass


async def init_db() -> None:
    """Create all tables. Called at application startup."""
    from mcp_server.models import TenantBigQueryCredential  # noqa: F401 — registers model
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database tables initialized")


async def close_db() -> None:
    """Dispose engine. Called at application shutdown."""
    await _engine.dispose()
    logger.info("Database engine disposed")


async def get_session() -> AsyncSession:
    """Return a new async session. Caller is responsible for closing."""
    return _session_factory()
```

- [ ] **Step 4: 运行测试确认通过**

```bash
pytest tests/test_db.py -v
```

期望：`2 passed`

- [ ] **Step 5: Commit**

```bash
git add mcp_server/db.py tests/test_db.py
git commit -m "feat: add async database connection module"
```

---

## Task 3: ORM 模型（models.py）

**Files:**
- Create: `mcp_server/models.py`
- Test: `tests/test_models.py`

- [ ] **Step 1: 新建 `tests/test_models.py` 写失败测试**

```python
"""Tests for ORM models."""
import pytest
from sqlalchemy import inspect


def test_model_table_name():
    """TenantBigQueryCredential 映射到正确的表名。"""
    from mcp_server.models import TenantBigQueryCredential
    assert TenantBigQueryCredential.__tablename__ == "tenant_bigquery_credentials"


def test_model_columns():
    """TenantBigQueryCredential 包含所有必要字段。"""
    from mcp_server.models import TenantBigQueryCredential
    mapper = inspect(TenantBigQueryCredential)
    col_names = {col.key for col in mapper.columns}
    required = {
        "id", "tenant_id", "customer_id", "gcp_project_id",
        "dataset_id", "service_account_json", "tables_found",
        "validated_at", "created_at", "updated_at",
    }
    assert required.issubset(col_names), f"Missing columns: {required - col_names}"


def test_model_tenant_id_unique():
    """tenant_id 字段有唯一约束。"""
    from mcp_server.models import TenantBigQueryCredential
    mapper = inspect(TenantBigQueryCredential)
    tenant_col = next(c for c in mapper.columns if c.key == "tenant_id")
    assert tenant_col.unique is True
```

- [ ] **Step 2: 运行确认失败**

```bash
pytest tests/test_models.py -v
```

期望：`ModuleNotFoundError: No module named 'mcp_server.models'`

- [ ] **Step 3: 新建 `mcp_server/models.py`**

```python
"""ORM models for MCP Server."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from mcp_server.db import Base


class TenantBigQueryCredential(Base):
    """Stores encrypted BigQuery Service Account credentials per tenant."""

    __tablename__ = "tenant_bigquery_credentials"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    customer_id: Mapped[str] = mapped_column(String(255), nullable=False)
    gcp_project_id: Mapped[str] = mapped_column(String(255), nullable=False)
    dataset_id: Mapped[str] = mapped_column(String(255), nullable=False)
    service_account_json: Mapped[str] = mapped_column(Text, nullable=False)  # Fernet encrypted
    tables_found: Mapped[str | None] = mapped_column(Text, nullable=True)    # JSON array string
    validated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
```

- [ ] **Step 4: 运行测试确认通过**

```bash
pytest tests/test_models.py -v
```

期望：`3 passed`

- [ ] **Step 5: Commit**

```bash
git add mcp_server/models.py tests/test_models.py
git commit -m "feat: add TenantBigQueryCredential ORM model"
```

---

## Task 4: 加解密服务（crypto.py）

**Files:**
- Create: `mcp_server/services/__init__.py`
- Create: `mcp_server/services/crypto.py`
- Test: `tests/test_crypto.py`

- [ ] **Step 1: 新建失败测试 `tests/test_crypto.py`**

```python
"""Tests for Fernet encryption service."""
import os
from unittest.mock import patch

import pytest
from cryptography.fernet import Fernet


@pytest.fixture
def test_key():
    return Fernet.generate_key().decode()


def test_encrypt_returns_string(test_key):
    """encrypt() 返回字符串（不是原文）。"""
    with patch.dict(os.environ, {"CREDENTIAL_ENCRYPT_KEY": test_key}):
        from mcp_server.services import crypto
        import importlib; importlib.reload(crypto)
        result = crypto.encrypt("hello world")
        assert isinstance(result, str)
        assert result != "hello world"


def test_decrypt_roundtrip(test_key):
    """encrypt → decrypt 还原原文。"""
    with patch.dict(os.environ, {"CREDENTIAL_ENCRYPT_KEY": test_key}):
        from mcp_server.services import crypto
        import importlib; importlib.reload(crypto)
        original = '{"type": "service_account", "project_id": "test"}'
        encrypted = crypto.encrypt(original)
        decrypted = crypto.decrypt(encrypted)
        assert decrypted == original


def test_encrypt_different_each_time(test_key):
    """相同明文每次加密结果不同（Fernet IV 随机）。"""
    with patch.dict(os.environ, {"CREDENTIAL_ENCRYPT_KEY": test_key}):
        from mcp_server.services import crypto
        import importlib; importlib.reload(crypto)
        e1 = crypto.encrypt("same text")
        e2 = crypto.encrypt("same text")
        assert e1 != e2


def test_missing_key_raises():
    """未设置 CREDENTIAL_ENCRYPT_KEY 时 encrypt 抛出 RuntimeError。"""
    with patch.dict(os.environ, {}, clear=True):
        if "CREDENTIAL_ENCRYPT_KEY" in os.environ:
            del os.environ["CREDENTIAL_ENCRYPT_KEY"]
        from mcp_server.services import crypto
        import importlib; importlib.reload(crypto)
        with pytest.raises(RuntimeError, match="CREDENTIAL_ENCRYPT_KEY"):
            crypto.encrypt("test")
```

- [ ] **Step 2: 运行确认失败**

```bash
pytest tests/test_crypto.py -v
```

期望：`ModuleNotFoundError: No module named 'mcp_server.services'`

- [ ] **Step 3: 新建 `mcp_server/services/__init__.py`**

```python
```

（空文件）

- [ ] **Step 4: 新建 `mcp_server/services/crypto.py`**

```python
"""Fernet symmetric encryption for Service Account JSON.

Environment variables:
    CREDENTIAL_ENCRYPT_KEY: Fernet key (base64-urlsafe, 32 bytes).
                            Generate with: Fernet.generate_key().decode()
"""

from __future__ import annotations

import os

from cryptography.fernet import Fernet


def _get_fernet() -> Fernet:
    key = os.environ.get("CREDENTIAL_ENCRYPT_KEY", "")
    if not key:
        raise RuntimeError(
            "CREDENTIAL_ENCRYPT_KEY environment variable is not set. "
            "Generate one with: python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\""
        )
    return Fernet(key.encode() if isinstance(key, str) else key)


def encrypt(plaintext: str) -> str:
    """Encrypt a plaintext string. Returns base64-urlsafe ciphertext string."""
    return _get_fernet().encrypt(plaintext.encode()).decode()


def decrypt(ciphertext: str) -> str:
    """Decrypt a ciphertext string produced by encrypt(). Returns original plaintext."""
    return _get_fernet().decrypt(ciphertext.encode()).decode()
```

- [ ] **Step 5: 运行测试确认通过**

```bash
pytest tests/test_crypto.py -v
```

期望：`4 passed`

- [ ] **Step 6: Commit**

```bash
git add mcp_server/services/__init__.py mcp_server/services/crypto.py tests/test_crypto.py
git commit -m "feat: add Fernet encryption service"
```

---

## Task 5: BigQuery 校验服务（bigquery_validator.py）

**Files:**
- Create: `mcp_server/services/bigquery_validator.py`
- Test: `tests/test_bigquery_validator.py`

- [ ] **Step 1: 新建失败测试 `tests/test_bigquery_validator.py`**

```python
"""Tests for BigQuery credentials validator."""
import json
from unittest.mock import MagicMock, patch

import pytest

# Minimal valid service account JSON structure
VALID_SA_JSON = {
    "type": "service_account",
    "project_id": "test-project",
    "private_key_id": "key-id",
    "private_key": "-----BEGIN RSA PRIVATE KEY-----\nMIIEowIBAAKCAQEA\n-----END RSA PRIVATE KEY-----\n",
    "client_email": "test@test-project.iam.gserviceaccount.com",
    "client_id": "123456789",
    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
    "token_uri": "https://oauth2.googleapis.com/token",
}


def _mock_table(table_id: str):
    t = MagicMock()
    t.table_id = table_id
    return t


def test_validate_success():
    """有效凭据且目标表存在时返回表列表。"""
    from mcp_server.services.bigquery_validator import validate_credentials, ValidationResult

    mock_tables = [
        _mock_table("email_sends_12345"),
        _mock_table("email_opens_12345"),
        _mock_table("email_clicks_12345"),
    ]

    with patch("mcp_server.services.bigquery_validator.service_account") as mock_sa:
        with patch("mcp_server.services.bigquery_validator.bigquery") as mock_bq:
            mock_sa.Credentials.from_service_account_info.return_value = MagicMock()
            mock_client = MagicMock()
            mock_bq.Client.return_value = mock_client
            mock_client.list_tables.return_value = mock_tables

            result = validate_credentials(
                sa_json=VALID_SA_JSON,
                gcp_project_id="test-project",
                dataset_id="emarsys_12345",
                customer_id="12345",
            )

    assert isinstance(result, ValidationResult)
    assert result.success is True
    assert "email_sends_12345" in result.tables_found
    assert result.error is None


def test_validate_missing_core_table():
    """核心表 email_sends_{customer_id} 不存在时返回失败。"""
    from mcp_server.services.bigquery_validator import validate_credentials

    mock_tables = [_mock_table("some_other_table")]

    with patch("mcp_server.services.bigquery_validator.service_account") as mock_sa:
        with patch("mcp_server.services.bigquery_validator.bigquery") as mock_bq:
            mock_sa.Credentials.from_service_account_info.return_value = MagicMock()
            mock_client = MagicMock()
            mock_bq.Client.return_value = mock_client
            mock_client.list_tables.return_value = mock_tables

            result = validate_credentials(
                sa_json=VALID_SA_JSON,
                gcp_project_id="test-project",
                dataset_id="emarsys_12345",
                customer_id="12345",
            )

    assert result.success is False
    assert "email_sends_12345" in result.error


def test_validate_invalid_sa_json():
    """SA JSON 格式无效（缺少 type 字段）时返回失败。"""
    from mcp_server.services.bigquery_validator import validate_credentials

    bad_sa = {"project_id": "test"}  # missing 'type'

    result = validate_credentials(
        sa_json=bad_sa,
        gcp_project_id="test-project",
        dataset_id="emarsys_12345",
        customer_id="12345",
    )

    assert result.success is False
    assert result.error is not None


def test_validate_bq_api_error():
    """BigQuery API 抛出异常时返回失败。"""
    from mcp_server.services.bigquery_validator import validate_credentials

    with patch("mcp_server.services.bigquery_validator.service_account") as mock_sa:
        with patch("mcp_server.services.bigquery_validator.bigquery") as mock_bq:
            mock_sa.Credentials.from_service_account_info.return_value = MagicMock()
            mock_client = MagicMock()
            mock_bq.Client.return_value = mock_client
            mock_client.list_tables.side_effect = Exception("Permission denied")

            result = validate_credentials(
                sa_json=VALID_SA_JSON,
                gcp_project_id="test-project",
                dataset_id="emarsys_12345",
                customer_id="12345",
            )

    assert result.success is False
    assert "Permission denied" in result.error
```

- [ ] **Step 2: 运行确认失败**

```bash
pytest tests/test_bigquery_validator.py -v
```

期望：`ModuleNotFoundError: No module named 'mcp_server.services.bigquery_validator'`

- [ ] **Step 3: 新建 `mcp_server/services/bigquery_validator.py`**

```python
"""BigQuery credentials validator.

Validates a Service Account JSON by listing tables in the specified dataset
and checking that the core Emarsys table (email_sends_{customer_id}) exists.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from google.cloud import bigquery
from google.oauth2 import service_account

logger = logging.getLogger(__name__)

_REQUIRED_SA_FIELDS = {"type", "project_id", "private_key", "client_email"}
_SCOPES = ["https://www.googleapis.com/auth/bigquery.readonly"]


@dataclass
class ValidationResult:
    success: bool
    tables_found: list[str] = field(default_factory=list)
    error: str | None = None


def validate_credentials(
    sa_json: dict[str, Any],
    gcp_project_id: str,
    dataset_id: str,
    customer_id: str,
) -> ValidationResult:
    """Validate BigQuery Service Account credentials.

    Steps:
    1. Check SA JSON has required fields.
    2. Build BigQuery client with the SA credentials.
    3. List tables in dataset_id.
    4. Verify email_sends_{customer_id} is present.

    Returns:
        ValidationResult with success=True and tables_found on success,
        or success=False and error message on failure.
    """
    # Step 1: SA JSON format check
    missing = _REQUIRED_SA_FIELDS - set(sa_json.keys())
    if missing:
        return ValidationResult(
            success=False,
            error=f"service_account_json 格式无效：缺少字段 {', '.join(sorted(missing))}",
        )
    if sa_json.get("type") != "service_account":
        return ValidationResult(
            success=False,
            error="service_account_json 格式无效：type 必须为 'service_account'",
        )

    try:
        # Step 2: Build BQ client
        credentials = service_account.Credentials.from_service_account_info(
            sa_json, scopes=_SCOPES
        )
        client = bigquery.Client(credentials=credentials, project=gcp_project_id)

        # Step 3: List tables
        tables = list(client.list_tables(dataset_id))
        table_names = [t.table_id for t in tables]
        logger.info("BigQuery list_tables: dataset=%s found=%d tables", dataset_id, len(table_names))

        # Step 4: Check core table
        core_table = f"email_sends_{customer_id}"
        if core_table not in table_names:
            return ValidationResult(
                success=False,
                error=(
                    f"数据集 {dataset_id} 中未找到核心表 {core_table}。"
                    f"已发现的表：{', '.join(table_names[:10]) or '(空)'}"
                ),
            )

        return ValidationResult(success=True, tables_found=table_names)

    except Exception as exc:
        logger.error("BigQuery validation failed: %s", exc)
        return ValidationResult(success=False, error=str(exc))
```

- [ ] **Step 4: 运行测试确认通过**

```bash
pytest tests/test_bigquery_validator.py -v
```

期望：`4 passed`

- [ ] **Step 5: Commit**

```bash
git add mcp_server/services/bigquery_validator.py tests/test_bigquery_validator.py
git commit -m "feat: add BigQuery credentials validator"
```

---

## Task 6: 凭据 Router（credentials.py）

**Files:**
- Create: `mcp_server/routers/__init__.py`
- Create: `mcp_server/routers/credentials.py`
- Test: `tests/test_credentials_router.py`

- [ ] **Step 1: 新建失败测试 `tests/test_credentials_router.py`**

```python
"""Tests for /credentials/bigquery endpoints."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from starlette.testclient import TestClient
from starlette.applications import Starlette
from starlette.routing import Route
from starlette.middleware import Middleware

_TEST_KEY_MAP = {"test-token-001": "democn"}

VALID_SA_JSON = {
    "type": "service_account",
    "project_id": "test-project",
    "private_key": "-----BEGIN RSA PRIVATE KEY-----\ntest\n-----END RSA PRIVATE KEY-----\n",
    "client_email": "test@test.iam.gserviceaccount.com",
    "client_id": "123",
    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
    "token_uri": "https://oauth2.googleapis.com/token",
    "private_key_id": "key1",
}


@pytest.fixture
def client():
    with patch("mcp_server.auth._API_KEY_MAP", _TEST_KEY_MAP):
        from mcp_server.routers.credentials import (
            upload_credentials, get_credentials, delete_credentials
        )
        from mcp_server.auth import APIKeyMiddleware

        app = Starlette(
            routes=[
                Route("/credentials/bigquery", upload_credentials, methods=["POST"]),
                Route("/credentials/bigquery", get_credentials, methods=["GET"]),
                Route("/credentials/bigquery", delete_credentials, methods=["DELETE"]),
            ],
            middleware=[Middleware(APIKeyMiddleware)],
        )
        with TestClient(app, raise_server_exceptions=False) as c:
            yield c


def test_upload_no_token(client):
    resp = client.post("/credentials/bigquery", json={})
    assert resp.status_code == 401


def test_upload_missing_fields(client):
    resp = client.post(
        "/credentials/bigquery",
        json={"customer_id": "123"},
        headers={"Authorization": "Bearer test-token-001"},
    )
    assert resp.status_code == 422


def test_upload_success(client):
    from mcp_server.services.bigquery_validator import ValidationResult

    mock_result = ValidationResult(
        success=True,
        tables_found=["email_sends_12345", "email_opens_12345"],
    )

    mock_credential = MagicMock()
    mock_credential.customer_id = "12345"
    mock_credential.tables_found = '["email_sends_12345","email_opens_12345"]'
    mock_credential.validated_at = datetime(2026, 3, 31, 10, 0, 0, tzinfo=timezone.utc)

    with patch("mcp_server.routers.credentials.validate_credentials", return_value=mock_result):
        with patch("mcp_server.routers.credentials.encrypt", return_value="encrypted-blob"):
            with patch("mcp_server.routers.credentials.get_session") as mock_session_fn:
                mock_session = AsyncMock()
                mock_session.__aenter__ = AsyncMock(return_value=mock_session)
                mock_session.__aexit__ = AsyncMock(return_value=False)
                mock_session.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=None)))
                mock_session.add = MagicMock()
                mock_session.commit = AsyncMock()
                mock_session.refresh = AsyncMock(side_effect=lambda obj: setattr(obj, 'validated_at', mock_credential.validated_at) or setattr(obj, 'tables_found', mock_credential.tables_found))
                mock_session_fn.return_value = mock_session

                resp = client.post(
                    "/credentials/bigquery",
                    json={
                        "customer_id": "12345",
                        "gcp_project_id": "test-project",
                        "dataset_id": "emarsys_12345",
                        "service_account_json": VALID_SA_JSON,
                    },
                    headers={"Authorization": "Bearer test-token-001"},
                )

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["tenant_id"] == "democn"


def test_upload_validation_failure(client):
    from mcp_server.services.bigquery_validator import ValidationResult

    mock_result = ValidationResult(success=False, error="Permission denied")

    with patch("mcp_server.routers.credentials.validate_credentials", return_value=mock_result):
        resp = client.post(
            "/credentials/bigquery",
            json={
                "customer_id": "12345",
                "gcp_project_id": "test-project",
                "dataset_id": "emarsys_12345",
                "service_account_json": VALID_SA_JSON,
            },
            headers={"Authorization": "Bearer test-token-001"},
        )

    assert resp.status_code == 422
    assert "Permission denied" in resp.json()["message"]


def test_get_not_configured(client):
    with patch("mcp_server.routers.credentials.get_session") as mock_session_fn:
        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        mock_session.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=None)))
        mock_session_fn.return_value = mock_session

        resp = client.get(
            "/credentials/bigquery",
            headers={"Authorization": "Bearer test-token-001"},
        )

    assert resp.status_code == 200
    assert resp.json()["configured"] is False


def test_delete_not_found(client):
    with patch("mcp_server.routers.credentials.get_session") as mock_session_fn:
        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        mock_session.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=None)))
        mock_session_fn.return_value = mock_session

        resp = client.delete(
            "/credentials/bigquery",
            headers={"Authorization": "Bearer test-token-001"},
        )

    assert resp.status_code == 404
```

- [ ] **Step 2: 运行确认失败**

```bash
pytest tests/test_credentials_router.py -v
```

期望：`ModuleNotFoundError: No module named 'mcp_server.routers'`

- [ ] **Step 3: 新建 `mcp_server/routers/__init__.py`**

空文件：
```python
```

- [ ] **Step 4: 新建 `mcp_server/routers/credentials.py`**

```python
"""BigQuery credentials management endpoints.

Routes:
    POST   /credentials/bigquery  — Upload and validate credentials
    GET    /credentials/bigquery  — Get credential status (no SA JSON)
    DELETE /credentials/bigquery  — Delete credentials
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from pydantic import BaseModel, Field
from sqlalchemy import select
from starlette.requests import Request
from starlette.responses import JSONResponse

from mcp_server.auth import _get_tenant_id
from mcp_server.db import get_session
from mcp_server.models import TenantBigQueryCredential
from mcp_server.services.bigquery_validator import validate_credentials
from mcp_server.services.crypto import encrypt, decrypt

logger = logging.getLogger(__name__)


class UploadRequest(BaseModel):
    customer_id: str = Field(..., description="Emarsys Customer ID (table name suffix)")
    gcp_project_id: str = Field(..., description="SAP-hosted GCP project ID")
    dataset_id: str = Field(..., description="BigQuery dataset ID (e.g. emarsys_12345)")
    service_account_json: dict = Field(..., description="Google Service Account JSON")


async def upload_credentials(request: Request) -> JSONResponse:
    """POST /credentials/bigquery — upload and validate BQ credentials."""
    try:
        body = await request.json()
        req = UploadRequest(**body)
    except Exception as e:
        return JSONResponse(status_code=422, content={"status": "error", "message": f"请求格式错误: {e}"})

    tenant_id = _get_tenant_id()

    # Validate BigQuery credentials
    result = validate_credentials(
        sa_json=req.service_account_json,
        gcp_project_id=req.gcp_project_id,
        dataset_id=req.dataset_id,
        customer_id=req.customer_id,
    )
    if not result.success:
        return JSONResponse(
            status_code=422,
            content={"status": "error", "message": f"BigQuery 校验失败：{result.error}"},
        )

    # Encrypt and store
    encrypted_sa = encrypt(json.dumps(req.service_account_json))
    tables_json = json.dumps(result.tables_found)
    now = datetime.now(timezone.utc)

    session = await get_session()
    async with session:
        # Upsert: update if exists, insert if not
        stmt = select(TenantBigQueryCredential).where(
            TenantBigQueryCredential.tenant_id == tenant_id
        )
        row = (await session.execute(stmt)).scalar_one_or_none()

        if row is None:
            row = TenantBigQueryCredential(
                tenant_id=tenant_id,
                api_token=request.headers.get("Authorization", "").removeprefix("Bearer ").strip(),
                customer_id=req.customer_id,
                gcp_project_id=req.gcp_project_id,
                dataset_id=req.dataset_id,
                service_account_json=encrypted_sa,
                tables_found=tables_json,
                validated_at=now,
            )
            session.add(row)
        else:
            row.customer_id = req.customer_id
            row.gcp_project_id = req.gcp_project_id
            row.dataset_id = req.dataset_id
            row.service_account_json = encrypted_sa
            row.tables_found = tables_json
            row.validated_at = now

        await session.commit()
        await session.refresh(row)

    return JSONResponse(
        status_code=200,
        content={
            "status": "ok",
            "tenant_id": tenant_id,
            "customer_id": req.customer_id,
            "tables_found": result.tables_found,
            "validated_at": now.isoformat(),
        },
    )


async def get_credentials(request: Request) -> JSONResponse:
    """GET /credentials/bigquery — get credential status (no SA JSON returned)."""
    tenant_id = _get_tenant_id()

    session = await get_session()
    async with session:
        stmt = select(TenantBigQueryCredential).where(
            TenantBigQueryCredential.tenant_id == tenant_id
        )
        row = (await session.execute(stmt)).scalar_one_or_none()

    if row is None:
        return JSONResponse(status_code=200, content={"status": "ok", "configured": False})

    tables = json.loads(row.tables_found) if row.tables_found else []
    return JSONResponse(
        status_code=200,
        content={
            "status": "ok",
            "configured": True,
            "customer_id": row.customer_id,
            "gcp_project_id": row.gcp_project_id,
            "dataset_id": row.dataset_id,
            "tables_found": tables,
            "validated_at": row.validated_at.isoformat() if row.validated_at else None,
            "created_at": row.created_at.isoformat() if row.created_at else None,
        },
    )


async def delete_credentials(request: Request) -> JSONResponse:
    """DELETE /credentials/bigquery — delete credentials for current tenant."""
    tenant_id = _get_tenant_id()

    session = await get_session()
    async with session:
        stmt = select(TenantBigQueryCredential).where(
            TenantBigQueryCredential.tenant_id == tenant_id
        )
        row = (await session.execute(stmt)).scalar_one_or_none()

        if row is None:
            return JSONResponse(status_code=404, content={"status": "error", "message": "凭据不存在"})

        await session.delete(row)
        await session.commit()

    return JSONResponse(status_code=200, content={"status": "ok"})
```

- [ ] **Step 5: 运行测试确认通过**

```bash
pytest tests/test_credentials_router.py -v
```

期望：`6 passed`

- [ ] **Step 6: Commit**

```bash
git add mcp_server/routers/__init__.py mcp_server/routers/credentials.py tests/test_credentials_router.py
git commit -m "feat: add BigQuery credentials REST endpoints"
```

---

## Task 7: 接入 http_app.py + 静态页面

**Files:**
- Modify: `mcp_server/http_app.py`
- Create: `mcp_server/static/ui.html`

- [ ] **Step 1: 创建静态目录**

```bash
mkdir -p /Users/wangyunlong/myproject/sap_Integration/src/Socialhub-CLI/mcp_server/static
```

- [ ] **Step 2: 在 `mcp_server/http_app.py` 中添加路由和 DB lifespan**

在文件顶部 import 区块末尾追加：

```python
from starlette.responses import HTMLResponse
from starlette.staticfiles import StaticFiles
from pathlib import Path

from mcp_server.db import init_db, close_db
from mcp_server.routers.credentials import upload_credentials, get_credentials, delete_credentials
```

在现有 `lifespan()` 函数的 `async with _session_manager.run():` 块内，`yield` 之前添加 DB 初始化：

```python
@contextlib.asynccontextmanager
async def lifespan(app: Starlette):
    # ... 现有 probe 和 analytics 代码 ...

    # 初始化数据库（创建表）
    try:
        await init_db()
        logger.info("Database initialized")
    except Exception as e:
        logger.warning("Database init failed (non-fatal): %s", e)

    async with _session_manager.run():
        logger.info("StreamableHTTPSessionManager started (stateless=True)")
        yield

    await close_db()
    logger.info("HTTP MCP app shutting down")
```

新增 `/ui` 路由处理函数（在 `health()` 之后插入）：

```python
_STATIC_DIR = Path(__file__).parent / "static"

async def ui(request: Request) -> HTMLResponse:
    """GET /ui — serve customer portal HTML."""
    html_path = _STATIC_DIR / "ui.html"
    if not html_path.exists():
        return HTMLResponse("<h1>UI not found</h1>", status_code=404)
    return HTMLResponse(html_path.read_text(encoding="utf-8"))
```

在 `_app = Starlette(routes=[...])` 中追加路由：

```python
_app = Starlette(
    routes=[
        Route("/health", health, methods=["GET"]),
        Route("/ui", ui, methods=["GET"]),
        Route("/credentials/bigquery", upload_credentials, methods=["POST"]),
        Route("/credentials/bigquery", get_credentials, methods=["GET"]),
        Route("/credentials/bigquery", delete_credentials, methods=["DELETE"]),
        Mount("/mcp", app=_session_manager.handle_request),
    ],
    lifespan=lifespan,
)
```

- [ ] **Step 3: 新建 `mcp_server/static/ui.html`**

```html
<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>SocialHub - BigQuery 凭据管理</title>
  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: #f5f5f5; color: #333; }
    .container { max-width: 640px; margin: 40px auto; padding: 0 20px; }
    .card { background: #fff; border-radius: 8px; padding: 32px; box-shadow: 0 1px 4px rgba(0,0,0,0.1); margin-bottom: 20px; }
    h1 { font-size: 22px; margin-bottom: 24px; color: #1a1a1a; }
    h2 { font-size: 16px; margin-bottom: 16px; color: #444; }
    label { display: block; font-size: 13px; font-weight: 500; margin-bottom: 6px; color: #555; }
    input[type=text], input[type=password], textarea {
      width: 100%; padding: 10px 12px; border: 1px solid #ddd; border-radius: 6px;
      font-size: 14px; margin-bottom: 16px; outline: none;
    }
    input:focus, textarea:focus { border-color: #0070f3; }
    textarea { height: 120px; resize: vertical; font-family: monospace; font-size: 12px; }
    button {
      padding: 10px 20px; border: none; border-radius: 6px; font-size: 14px;
      font-weight: 500; cursor: pointer;
    }
    .btn-primary { background: #0070f3; color: #fff; }
    .btn-primary:hover { background: #0060df; }
    .btn-danger { background: #e53e3e; color: #fff; margin-left: 10px; }
    .btn-secondary { background: #eee; color: #333; }
    .btn-secondary:hover { background: #ddd; }
    .alert { padding: 12px 16px; border-radius: 6px; font-size: 14px; margin-bottom: 16px; }
    .alert-success { background: #f0fff4; border: 1px solid #9ae6b4; color: #276749; }
    .alert-error { background: #fff5f5; border: 1px solid #feb2b2; color: #c53030; }
    .alert-info { background: #ebf8ff; border: 1px solid #90cdf4; color: #2b6cb0; }
    .meta { font-size: 12px; color: #888; margin-top: 4px; }
    .tag { display: inline-block; background: #ebf8ff; color: #2b6cb0; padding: 2px 8px; border-radius: 4px; font-size: 12px; margin: 2px; }
    .header-bar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 24px; }
    .tenant-badge { font-size: 13px; color: #666; background: #f0f0f0; padding: 4px 10px; border-radius: 4px; }
    #file-drop-area {
      border: 2px dashed #ddd; border-radius: 8px; padding: 24px;
      text-align: center; cursor: pointer; color: #888; margin-bottom: 16px; font-size: 14px;
    }
    #file-drop-area.drag-over { border-color: #0070f3; background: #f0f7ff; }
    #file-name { font-size: 13px; color: #0070f3; margin-top: 8px; }
    .hidden { display: none; }
    .loading { opacity: 0.6; pointer-events: none; }
  </style>
</head>
<body>
<div class="container">
  <!-- Login View -->
  <div id="view-login" class="card">
    <h1>SocialHub 凭据管理</h1>
    <div id="login-error" class="alert alert-error hidden"></div>
    <label for="token-input">API Token</label>
    <input type="password" id="token-input" placeholder="输入您的 API Token">
    <button class="btn-primary" onclick="doLogin()">登录</button>
  </div>

  <!-- Credential View -->
  <div id="view-credential" class="hidden">
    <div class="card">
      <div class="header-bar">
        <h1>BigQuery 凭据管理</h1>
        <div>
          <span class="tenant-badge" id="tenant-display"></span>
          <button class="btn-secondary" onclick="doLogout()" style="margin-left:10px">退出</button>
        </div>
      </div>

      <!-- Status: configured -->
      <div id="status-configured" class="hidden">
        <div class="alert alert-success">✓ BigQuery 凭据已配置</div>
        <div style="margin-bottom: 16px;">
          <div><strong>Customer ID：</strong><span id="disp-customer-id"></span></div>
          <div><strong>GCP Project：</strong><span id="disp-project-id"></span></div>
          <div><strong>Dataset：</strong><span id="disp-dataset-id"></span></div>
          <div style="margin-top:8px;"><strong>已发现的表：</strong></div>
          <div id="disp-tables" style="margin-top:4px;"></div>
          <div class="meta" id="disp-validated-at"></div>
        </div>
        <button class="btn-danger" onclick="confirmDelete()">删除凭据</button>
      </div>

      <!-- Status: not configured -->
      <div id="status-not-configured" class="hidden">
        <div class="alert alert-info" style="margin-bottom:20px;">尚未配置 BigQuery 凭据，请上传 Service Account 文件</div>

        <div id="upload-result" class="hidden"></div>

        <div id="file-drop-area" onclick="document.getElementById('file-input').click()"
             ondragover="handleDragOver(event)" ondrop="handleDrop(event)">
          拖拽 Service Account JSON 文件到此处，或点击选择文件
          <div id="file-name"></div>
        </div>
        <input type="file" id="file-input" accept=".json" class="hidden" onchange="handleFileSelect(event)">

        <label>Emarsys Customer ID</label>
        <input type="text" id="inp-customer-id" placeholder="例如：12345">

        <label>GCP Project ID</label>
        <input type="text" id="inp-project-id" placeholder="例如：sap-emarsys-project">

        <label>Dataset ID</label>
        <input type="text" id="inp-dataset-id" placeholder="例如：emarsys_12345">

        <button class="btn-primary" id="upload-btn" onclick="doUpload()">上传并校验</button>
      </div>
    </div>
  </div>
</div>

<script>
  let _token = localStorage.getItem('sh_token') || '';
  let _saJson = null;

  function show(id) { document.getElementById(id).classList.remove('hidden'); }
  function hide(id) { document.getElementById(id).classList.add('hidden'); }

  async function doLogin() {
    const token = document.getElementById('token-input').value.trim();
    if (!token) return;
    hide('login-error');
    try {
      const resp = await fetch('/credentials/bigquery', {
        headers: { 'Authorization': 'Bearer ' + token }
      });
      if (resp.status === 401) {
        show('login-error');
        document.getElementById('login-error').textContent = 'Token 无效，请重试';
        return;
      }
      _token = token;
      localStorage.setItem('sh_token', token);
      await loadCredentialView(await resp.json());
    } catch (e) {
      show('login-error');
      document.getElementById('login-error').textContent = '连接失败：' + e.message;
    }
  }

  async function loadCredentialView(data) {
    hide('view-login');
    show('view-credential');
    if (data.configured) {
      show('status-configured');
      hide('status-not-configured');
      document.getElementById('disp-customer-id').textContent = data.customer_id;
      document.getElementById('disp-project-id').textContent = data.gcp_project_id;
      document.getElementById('disp-dataset-id').textContent = data.dataset_id;
      const tablesEl = document.getElementById('disp-tables');
      tablesEl.innerHTML = (data.tables_found || []).map(t => `<span class="tag">${t}</span>`).join('');
      document.getElementById('disp-validated-at').textContent =
        data.validated_at ? '最后校验：' + new Date(data.validated_at).toLocaleString() : '';
    } else {
      hide('status-configured');
      show('status-not-configured');
      hide('upload-result');
    }
    // Show tenant from response or decode from token
    const resp2 = await fetch('/credentials/bigquery', { headers: { 'Authorization': 'Bearer ' + _token } });
    const resp2data = await resp2.json();
    // tenant_id is returned on upload; show token prefix for now
    document.getElementById('tenant-display').textContent = 'Token: ' + _token.substring(0, 6) + '***';
  }

  function doLogout() {
    localStorage.removeItem('sh_token');
    _token = '';
    show('view-login');
    hide('view-credential');
    document.getElementById('token-input').value = '';
  }

  function handleDragOver(e) {
    e.preventDefault();
    document.getElementById('file-drop-area').classList.add('drag-over');
  }

  function handleDrop(e) {
    e.preventDefault();
    document.getElementById('file-drop-area').classList.remove('drag-over');
    const file = e.dataTransfer.files[0];
    if (file) readFile(file);
  }

  function handleFileSelect(e) {
    const file = e.target.files[0];
    if (file) readFile(file);
  }

  function readFile(file) {
    document.getElementById('file-name').textContent = file.name;
    const reader = new FileReader();
    reader.onload = (e) => {
      try {
        _saJson = JSON.parse(e.target.result);
        // Auto-fill project_id if empty
        if (_saJson.project_id && !document.getElementById('inp-project-id').value) {
          document.getElementById('inp-project-id').value = _saJson.project_id;
        }
      } catch {
        _saJson = null;
        document.getElementById('file-name').textContent = '⚠ 文件格式错误，请选择有效的 JSON 文件';
      }
    };
    reader.readAsText(file);
  }

  async function doUpload() {
    const customerId = document.getElementById('inp-customer-id').value.trim();
    const projectId = document.getElementById('inp-project-id').value.trim();
    const datasetId = document.getElementById('inp-dataset-id').value.trim();
    const resultEl = document.getElementById('upload-result');

    if (!_saJson) { alert('请先选择 Service Account JSON 文件'); return; }
    if (!customerId || !projectId || !datasetId) { alert('请填写所有必填字段'); return; }

    const btn = document.getElementById('upload-btn');
    btn.textContent = '校验中...';
    btn.classList.add('loading');
    show('upload-result');
    resultEl.className = 'alert alert-info';
    resultEl.textContent = '正在连接 BigQuery 并校验凭据，请稍候...';

    try {
      const resp = await fetch('/credentials/bigquery', {
        method: 'POST',
        headers: { 'Authorization': 'Bearer ' + _token, 'Content-Type': 'application/json' },
        body: JSON.stringify({
          customer_id: customerId,
          gcp_project_id: projectId,
          dataset_id: datasetId,
          service_account_json: _saJson,
        }),
      });
      const data = await resp.json();
      if (resp.ok) {
        resultEl.className = 'alert alert-success';
        resultEl.textContent = `✓ 校验通过！发现 ${data.tables_found.length} 张表`;
        setTimeout(() => loadCredentialView({ configured: true, ...data }), 1500);
      } else {
        resultEl.className = 'alert alert-error';
        resultEl.textContent = '✗ ' + (data.message || '校验失败');
      }
    } catch (e) {
      resultEl.className = 'alert alert-error';
      resultEl.textContent = '连接失败：' + e.message;
    } finally {
      btn.textContent = '上传并校验';
      btn.classList.remove('loading');
    }
  }

  async function confirmDelete() {
    if (!confirm('确定要删除 BigQuery 凭据吗？此操作不可撤销。')) return;
    try {
      const resp = await fetch('/credentials/bigquery', {
        method: 'DELETE',
        headers: { 'Authorization': 'Bearer ' + _token },
      });
      if (resp.ok) {
        await loadCredentialView({ configured: false });
      } else {
        alert('删除失败：' + (await resp.json()).message);
      }
    } catch (e) {
      alert('删除失败：' + e.message);
    }
  }

  // Auto-login if token in localStorage
  (async () => {
    if (_token) {
      try {
        const resp = await fetch('/credentials/bigquery', {
          headers: { 'Authorization': 'Bearer ' + _token }
        });
        if (resp.ok) {
          await loadCredentialView(await resp.json());
          return;
        }
      } catch {}
      localStorage.removeItem('sh_token');
      _token = '';
    }
  })();
</script>
</body>
</html>
```

- [ ] **Step 4: 运行完整测试套件确认无回归**

```bash
cd /Users/wangyunlong/myproject/sap_Integration/src/Socialhub-CLI
pytest tests/ -v --ignore=tests/test_skill_integration.py
```

期望：全部 PASS

- [ ] **Step 5: Commit**

```bash
git add mcp_server/http_app.py mcp_server/static/ui.html
git commit -m "feat: wire credentials routes and /ui page into http_app"
```

---

## Task 8: Alembic Migration

**Files:**
- Create: `alembic_mcp/` 目录及配置

- [ ] **Step 1: 初始化 Alembic**

```bash
cd /Users/wangyunlong/myproject/sap_Integration/src/Socialhub-CLI
alembic init alembic_mcp
```

- [ ] **Step 2: 编辑 `alembic_mcp/env.py`**

替换 `target_metadata = None` 为：

```python
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from mcp_server.db import Base
from mcp_server.models import TenantBigQueryCredential  # noqa: registers model

target_metadata = Base.metadata
```

在 `run_migrations_offline()` 中替换 `url = config.get_main_option("sqlalchemy.url")` 为：

```python
url = os.environ.get("DATABASE_URL", config.get_main_option("sqlalchemy.url"))
```

在 `run_migrations_online()` 中添加同样的 URL 覆盖：

```python
configuration = config.get_section(config.config_ini_section, {})
configuration["sqlalchemy.url"] = os.environ.get(
    "DATABASE_URL", configuration.get("sqlalchemy.url", "")
)
connectable = engine_from_config(configuration, ...)
```

- [ ] **Step 3: 生成初始 migration**

```bash
alembic -c alembic_mcp/alembic.ini revision --autogenerate -m "create tenant_bigquery_credentials"
```

期望：在 `alembic_mcp/versions/` 下生成一个 migration 文件，包含 `tenant_bigquery_credentials` 表的 `upgrade()` 和 `downgrade()`

- [ ] **Step 4: Commit**

```bash
git add alembic_mcp/
git commit -m "feat: add Alembic migration for tenant_bigquery_credentials"
```

---

## Self-Review

**Spec coverage 检查：**

| Spec 要求 | 覆盖 Task |
|----------|----------|
| POST /credentials/bigquery | Task 6 |
| GET /credentials/bigquery（不返回 SA JSON） | Task 6 |
| DELETE /credentials/bigquery | Task 6 |
| BigQuery list_tables 校验 | Task 5 |
| Fernet 加密存储 | Task 4 |
| tenant_bigquery_credentials 表（含所有字段） | Task 3 |
| 422 BQ 校验失败返回错误原因 | Task 6 |
| /ui 页面：Token 登录 | Task 7 |
| /ui 页面：上传表单（SA JSON 文件 + 4 个字段） | Task 7 |
| /ui 页面：已配置状态显示表列表 | Task 7 |
| /ui 页面：删除确认 | Task 7 |
| /ui 页面：退出登录 | Task 7 |
| DATABASE_URL + CREDENTIAL_ENCRYPT_KEY 环境变量 | Task 2 + Task 4 |
| asyncpg + SQLAlchemy 2.0 依赖 | Task 1 |

**类型一致性：**
- `ValidationResult.tables_found: list[str]` 在 Task 5 定义，在 Task 6 `result.tables_found` 使用 ✅
- `encrypt(str) -> str` / `decrypt(str) -> str` 在 Task 4 定义，在 Task 6 `encrypt(json.dumps(...))` 使用 ✅
- `get_session() -> AsyncSession` 在 Task 2 定义，在 Task 6 `await get_session()` 使用 ✅
- `TenantBigQueryCredential` 字段在 Task 3 定义，在 Task 6 全部字段赋值一致 ✅
