# BigQuery 凭据门户 - 剩余任务 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 完成 BigQuery 凭据管理门户的剩余两块工作：① 后端修正（命名修正 + dataset_id 可选）；② UI 完全重设计（左侧导航 + 凭证列表 + 新建凭证流程）。

**Architecture:** 后端只改 `bigquery_validator.py` 和 `routers/credentials.py`（无 DB 结构变更，models.py 已包含 datasets_found / dataset_id nullable）；UI 完全重写 `mcp_server/static/ui.html`，保持所有 JS 逻辑在同一文件内，使用原生 HTML/CSS/JS，无外部依赖。

**Tech Stack:** Python 3.11, Starlette, HTML + 原生 CSS + 原生 JS (ES2020)

---

## 背景与现状

### 已完成
- `models.py`：`dataset_id` 已为 nullable，已有 `datasets_found` 字段
- `bigquery_validator.py`：支持 `dataset_id=None` 自动发现 `emarsys_*` datasets
- `routers/credentials.py`：基本逻辑完整，但 `dataset_id` 仍为必填

### 官方文档确认的命名规范（SAP Emarsys Open Data）
- GCP Project：`sap-od-<customer>`（2021年后）或 `ems-od-<customer>`（之前）
- Dataset：**`emarsys_<customer>_<suite_account_id>`**（例如 `emarsys_mycompany_123456`）
- 表名后缀是 **suite account ID**，不是 customer_id

### 需修正的问题
1. `ValidationResult.customer_ids_found` → 应改名为 `account_ids_found`（后缀是 suite account ID）
2. `routers/credentials.py` 中 `dataset_id` 仍为必填 `str` → 改为 `str | None = None`
3. UI 需要完全重设计

---

## File Map

| 操作 | 文件 | 变更内容 |
|------|------|---------|
| 修改 | `mcp_server/services/bigquery_validator.py` | `customer_ids_found` → `account_ids_found` |
| 修改 | `mcp_server/routers/credentials.py` | `dataset_id` 改可选；`customer_ids_found` → `account_ids_found`；保存 `datasets_found` |
| 修改 | `tests/test_bigquery_validator.py` | 更新字段名 |
| 修改 | `tests/test_credentials_router.py` | 更新字段名 + 测试 dataset_id 可选 |
| 重写 | `mcp_server/static/ui.html` | 全新 UI：左侧导航 + 凭证列表 + 新建凭证流程 |

---

## Task 1: 后端修正 — 命名修正 + dataset_id 可选

**Files:**
- Modify: `mcp_server/services/bigquery_validator.py`
- Modify: `mcp_server/routers/credentials.py`
- Modify: `tests/test_bigquery_validator.py`
- Modify: `tests/test_credentials_router.py`

- [ ] **Step 1: 更新 ValidationResult 字段名**

在 `mcp_server/services/bigquery_validator.py` 中，将 `customer_ids_found` 改为 `account_ids_found`：

```python
@dataclass
class ValidationResult:
    success: bool
    datasets_found: list[str] = field(default_factory=list)
    tables_found: list[str] = field(default_factory=list)
    account_ids_found: list[str] = field(default_factory=list)  # suite account IDs from email_sends_* tables
    error: str | None = None
```

同时更新文件内所有引用该字段的地方（共出现在两处 `return ValidationResult(...)` 中）：

```python
# 在 dataset_id is None 的分支（约第93-103行）
customer_ids = list({
    t.table_id.removeprefix("email_sends_")
    for t in all_tables
    if t.table_id.startswith("email_sends_")
})

return ValidationResult(
    success=True,
    datasets_found=dataset_ids,
    tables_found=[t.table_id for t in all_tables],
    account_ids_found=customer_ids,   # 改名
)
```

```python
# 在单 dataset 分支（约第118-143行）
account_ids_found = [                  # 改名
    t.removeprefix("email_sends_")
    for t in table_names
    if t.startswith("email_sends_")
]
# ...
return ValidationResult(
    success=True,
    tables_found=table_names,
    account_ids_found=account_ids_found,  # 改名
)
```

- [ ] **Step 2: 更新 routers/credentials.py**

修改 `UploadRequest`，让 `dataset_id` 变可选：

```python
class UploadRequest(BaseModel):
    """Request body for uploading BigQuery credentials."""

    customer_id: str | None = Field(None, description="Emarsys Customer ID (optional, auto-detected if omitted)")
    gcp_project_id: str = Field(..., description="SAP-hosted GCP project ID (e.g. sap-od-mycompany)")
    dataset_id: str | None = Field(None, description="BigQuery dataset ID (optional, auto-discovers emarsys_* if omitted)")
    service_account_json: dict = Field(..., description="Google Service Account JSON")
```

在 `upload_credentials` 函数中，更新字段名引用并保存 `datasets_found`：

```python
# 第77行附近：
resolved_customer_id = req.customer_id or (result.account_ids_found[0] if result.account_ids_found else None)

# 第80-98行 row 写入，增加 datasets_found：
datasets_found_str = ",".join(result.datasets_found) if result.datasets_found else None

if row is None:
    row = TenantBigQueryCredential(
        tenant_id=tenant_id,
        credential_type="bigquery_emarsys",
        customer_id=resolved_customer_id,
        gcp_project_id=req.gcp_project_id,
        dataset_id=req.dataset_id,
        service_account_json=encrypted_sa,
        tables_found=tables_json,
        datasets_found=datasets_found_str,
        validated_at=now,
    )
    session.add(row)
else:
    row.credential_type = "bigquery_emarsys"
    row.customer_id = resolved_customer_id
    row.gcp_project_id = req.gcp_project_id
    row.dataset_id = req.dataset_id
    row.service_account_json = encrypted_sa
    row.tables_found = tables_json
    row.datasets_found = datasets_found_str
    row.validated_at = now
```

更新返回 JSON（`upload_credentials` 函数末尾）：

```python
return JSONResponse(
    status_code=200,
    content={
        "status": "ok",
        "tenant_id": tenant_id,
        "customer_id": resolved_customer_id,
        "datasets_found": result.datasets_found,
        "account_ids_found": result.account_ids_found,
        "tables_found": result.tables_found,
        "validated_at": now.isoformat(),
    },
)
```

更新 `get_credentials` 函数，返回 `datasets_found`：

```python
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
    datasets = row.datasets_found.split(",") if row.datasets_found else []
    return JSONResponse(
        status_code=200,
        content={
            "status": "ok",
            "configured": True,
            "customer_id": row.customer_id,
            "gcp_project_id": row.gcp_project_id,
            "dataset_id": row.dataset_id,
            "datasets_found": datasets,
            "tables_found": tables,
            "validated_at": row.validated_at.isoformat() if row.validated_at else None,
            "created_at": row.created_at.isoformat() if row.created_at else None,
        },
    )
```

- [ ] **Step 3: 更新测试文件**

在 `tests/test_bigquery_validator.py` 中，将所有 `customer_ids_found` 替换为 `account_ids_found`：

```bash
grep -n "customer_ids_found" tests/test_bigquery_validator.py
```

对每处出现，把 `result.customer_ids_found` 改为 `result.account_ids_found`，断言中的键名也同步更新。

在 `tests/test_credentials_router.py` 中：
1. 把所有 `customer_ids_found` 替换为 `account_ids_found`
2. 新增一个测试，验证 `dataset_id` 可省略：

```python
def test_upload_without_dataset_id(client, mock_validator_success):
    """dataset_id is optional — validator auto-discovers emarsys_* datasets."""
    resp = client.post(
        "/credentials/bigquery",
        json={
            "gcp_project_id": "sap-od-test",
            # dataset_id 省略
            "service_account_json": {"type": "service_account", "project_id": "x",
                                      "private_key": "k", "client_email": "e@e.com"},
        },
        headers={"Authorization": "Bearer sapbigquerytest"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
```

- [ ] **Step 4: 运行测试**

```bash
cd /Users/wangyunlong/myproject/sap_Integration/src/Socialhub-CLI
conda run -n dev pytest tests/ -v --tb=short 2>&1 | tail -40
```

预期：所有测试通过，无 `AttributeError: customer_ids_found`

- [ ] **Step 5: 提交**

```bash
cd /Users/wangyunlong/myproject/sap_Integration/src/Socialhub-CLI
git add mcp_server/services/bigquery_validator.py mcp_server/routers/credentials.py tests/test_bigquery_validator.py tests/test_credentials_router.py
git commit -m "fix: rename customer_ids_found to account_ids_found, make dataset_id optional"
```

---

## Task 2: UI 重设计

**Files:**
- Rewrite: `mcp_server/static/ui.html`

### 设计说明

新 UI 为左右两栏布局：
- **左侧导航栏**（200px 固定宽）：Logo + 菜单项"凭证管理"（可扩展）+ 底部退出按钮
- **右侧主内容区**：根据状态显示不同视图

### 视图流程

```
[登录页]
    ↓ 输入 Token，点登录
[凭证管理主页]
    ├── 有凭证 → 显示凭证卡片（配置信息 + 删除按钮）
    └── 无凭证 → 显示空状态 + "新建凭证"按钮
                    ↓ 点击
               [类型选择页]
                    └── 选择"SAP Emarsys BigQuery 集成"
                            ↓
                       [上传表单页]（SA JSON 拖拽 + GCP Project + 可选 Dataset ID）
                            ↓ 提交成功
                       [回到凭证主页，显示凭证卡片]
```

- [ ] **Step 1: 写失败测试（UI 路由可访问）**

```bash
# 确认 /ui 可访问（已有路由，测试确保 HTML 内容中有新关键词）
conda run -n dev python -c "
import httpx, asyncio
async def t():
    async with httpx.AsyncClient(base_url='http://localhost:8091') as c:
        r = await c.get('/ui')
        print(r.status_code, 'SocialHub' in r.text)
asyncio.run(t())
"
```

期望：200 True（当前 UI 有 SocialHub 字样，确认路由正常）

- [ ] **Step 2: 重写 ui.html**

完全替换 `mcp_server/static/ui.html` 为以下内容：

```html
<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>SocialHub - 凭证管理</title>
  <style>
    *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
    body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: #f0f2f5; color: #1a1a1a; min-height: 100vh; }

    /* ─── Login ─── */
    #view-login {
      min-height: 100vh; display: flex; align-items: center; justify-content: center;
    }
    .login-card {
      background: #fff; border-radius: 12px; padding: 40px 36px; width: 380px;
      box-shadow: 0 4px 24px rgba(0,0,0,0.08);
    }
    .login-card h1 { font-size: 20px; font-weight: 600; margin-bottom: 8px; }
    .login-card p { font-size: 14px; color: #666; margin-bottom: 28px; }

    /* ─── App Shell ─── */
    #view-app { display: flex; min-height: 100vh; }

    /* Sidebar */
    .sidebar {
      width: 220px; background: #1e2a3a; color: #c8d3e0; flex-shrink: 0;
      display: flex; flex-direction: column;
    }
    .sidebar-logo {
      padding: 24px 20px 20px; font-size: 16px; font-weight: 700;
      color: #fff; border-bottom: 1px solid rgba(255,255,255,0.07);
      letter-spacing: 0.3px;
    }
    .sidebar-logo span { color: #4f9eff; }
    .sidebar-nav { flex: 1; padding: 12px 0; }
    .nav-item {
      display: flex; align-items: center; gap: 10px;
      padding: 10px 20px; font-size: 14px; cursor: pointer;
      border-radius: 0; transition: background 0.15s;
      color: #c8d3e0;
    }
    .nav-item:hover { background: rgba(255,255,255,0.06); }
    .nav-item.active { background: rgba(79,158,255,0.15); color: #4f9eff; font-weight: 500; }
    .nav-icon { font-size: 16px; width: 20px; text-align: center; }
    .sidebar-footer { padding: 16px 20px; border-top: 1px solid rgba(255,255,255,0.07); }
    .tenant-info { font-size: 12px; color: #8a9ab5; margin-bottom: 10px; }

    /* Main content */
    .main { flex: 1; padding: 32px 36px; overflow-y: auto; }
    .page-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 28px; }
    .page-title { font-size: 20px; font-weight: 600; }

    /* Cards */
    .card { background: #fff; border-radius: 10px; padding: 24px; box-shadow: 0 1px 4px rgba(0,0,0,0.06); margin-bottom: 16px; }

    /* Credential card */
    .cred-card { border: 1px solid #e8ecf0; }
    .cred-card-header { display: flex; align-items: flex-start; justify-content: space-between; margin-bottom: 16px; }
    .cred-type-badge {
      display: inline-flex; align-items: center; gap: 6px;
      background: #eef6ff; color: #1a6fbb; padding: 4px 10px;
      border-radius: 20px; font-size: 12px; font-weight: 500;
    }
    .cred-status-dot { width: 7px; height: 7px; border-radius: 50%; background: #22c55e; }
    .cred-fields { display: grid; grid-template-columns: 1fr 1fr; gap: 12px 24px; }
    .cred-field label { font-size: 11px; color: #888; text-transform: uppercase; letter-spacing: 0.5px; display: block; margin-bottom: 3px; }
    .cred-field span { font-size: 14px; color: #1a1a1a; word-break: break-all; }
    .cred-field.full { grid-column: 1 / -1; }
    .tag-list { display: flex; flex-wrap: wrap; gap: 4px; margin-top: 4px; }
    .tag { background: #f0f4ff; color: #3563c9; padding: 2px 8px; border-radius: 4px; font-size: 12px; font-family: monospace; }
    .cred-footer { display: flex; align-items: center; justify-content: space-between; margin-top: 20px; padding-top: 16px; border-top: 1px solid #f0f0f0; }
    .cred-meta { font-size: 12px; color: #aaa; }

    /* Empty state */
    .empty-state { text-align: center; padding: 60px 20px; }
    .empty-icon { font-size: 48px; margin-bottom: 16px; }
    .empty-state h3 { font-size: 16px; font-weight: 600; margin-bottom: 8px; }
    .empty-state p { font-size: 14px; color: #888; margin-bottom: 24px; }

    /* Type picker */
    .type-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap: 16px; }
    .type-card {
      border: 2px solid #e8ecf0; border-radius: 10px; padding: 20px;
      cursor: pointer; transition: border-color 0.15s, box-shadow 0.15s;
    }
    .type-card:hover { border-color: #4f9eff; box-shadow: 0 0 0 3px rgba(79,158,255,0.1); }
    .type-card-icon { font-size: 28px; margin-bottom: 10px; }
    .type-card h3 { font-size: 14px; font-weight: 600; margin-bottom: 4px; }
    .type-card p { font-size: 12px; color: #888; line-height: 1.5; }

    /* Form */
    .form-group { margin-bottom: 20px; }
    .form-group label { display: block; font-size: 13px; font-weight: 500; margin-bottom: 6px; color: #444; }
    .form-group .hint { font-size: 12px; color: #888; margin-top: 4px; }
    input[type=text], input[type=password] {
      width: 100%; padding: 10px 12px; border: 1px solid #ddd; border-radius: 7px;
      font-size: 14px; outline: none; transition: border-color 0.15s;
    }
    input:focus { border-color: #4f9eff; box-shadow: 0 0 0 3px rgba(79,158,255,0.12); }
    .optional-badge { font-size: 11px; color: #aaa; font-weight: 400; margin-left: 6px; }

    /* File drop */
    .file-drop {
      border: 2px dashed #d0d7e0; border-radius: 8px; padding: 28px 20px;
      text-align: center; cursor: pointer; color: #888; font-size: 14px;
      transition: border-color 0.15s, background 0.15s; margin-bottom: 4px;
    }
    .file-drop:hover, .file-drop.drag-over { border-color: #4f9eff; background: #f4f9ff; color: #4f9eff; }
    .file-drop-icon { font-size: 28px; margin-bottom: 8px; }
    .file-name { font-size: 13px; color: #4f9eff; margin-top: 8px; font-weight: 500; }

    /* Buttons */
    button { cursor: pointer; border: none; border-radius: 7px; font-size: 14px; font-weight: 500; padding: 10px 20px; transition: opacity 0.15s; }
    .btn-primary { background: #4f9eff; color: #fff; }
    .btn-primary:hover { background: #3a8ef0; }
    .btn-danger { background: #fee2e2; color: #dc2626; }
    .btn-danger:hover { background: #fecaca; }
    .btn-secondary { background: #f0f2f5; color: #444; }
    .btn-secondary:hover { background: #e4e7eb; }
    .btn-sm { padding: 7px 14px; font-size: 13px; }
    button:disabled { opacity: 0.5; cursor: not-allowed; }

    /* Alert */
    .alert { padding: 12px 16px; border-radius: 7px; font-size: 14px; margin-bottom: 16px; }
    .alert-success { background: #f0fdf4; border: 1px solid #86efac; color: #166534; }
    .alert-error { background: #fef2f2; border: 1px solid #fca5a5; color: #991b1b; }
    .alert-info { background: #eff6ff; border: 1px solid #93c5fd; color: #1e40af; }

    /* Breadcrumb */
    .breadcrumb { font-size: 13px; color: #888; margin-bottom: 20px; }
    .breadcrumb a { color: #4f9eff; text-decoration: none; cursor: pointer; }
    .breadcrumb a:hover { text-decoration: underline; }

    .hidden { display: none !important; }
    .loading { opacity: 0.6; pointer-events: none; }
    .spinner { display: inline-block; width: 14px; height: 14px; border: 2px solid currentColor; border-top-color: transparent; border-radius: 50%; animation: spin 0.6s linear infinite; margin-right: 6px; vertical-align: middle; }
    @keyframes spin { to { transform: rotate(360deg); } }
  </style>
</head>
<body>

<!-- ═══ LOGIN VIEW ═══ -->
<div id="view-login">
  <div class="login-card">
    <h1>SocialHub</h1>
    <p>请输入 API Token 以继续</p>
    <div id="login-error" class="alert alert-error hidden"></div>
    <div class="form-group">
      <label for="token-input">API Token</label>
      <input type="password" id="token-input" placeholder="输入您的 API Token" onkeydown="if(event.key==='Enter')doLogin()">
    </div>
    <button class="btn-primary" id="login-btn" onclick="doLogin()" style="width:100%">登录</button>
  </div>
</div>

<!-- ═══ APP SHELL ═══ -->
<div id="view-app" class="hidden">
  <!-- Sidebar -->
  <div class="sidebar">
    <div class="sidebar-logo">Social<span>Hub</span></div>
    <nav class="sidebar-nav">
      <div class="nav-item active" onclick="showPage('credentials')">
        <span class="nav-icon">🔑</span> 凭证管理
      </div>
    </nav>
    <div class="sidebar-footer">
      <div class="tenant-info" id="tenant-info"></div>
      <button class="btn-secondary btn-sm" onclick="doLogout()" style="width:100%">退出登录</button>
    </div>
  </div>

  <!-- Main -->
  <div class="main">

    <!-- PAGE: Credential List -->
    <div id="page-credentials">
      <div class="page-header">
        <div class="page-title">凭证管理</div>
        <button class="btn-primary btn-sm" onclick="showPage('type-picker')">+ 新建凭证</button>
      </div>

      <!-- Has credential -->
      <div id="cred-list" class="hidden">
        <div class="card cred-card" id="cred-card">
          <div class="cred-card-header">
            <div class="cred-type-badge">
              <span class="cred-status-dot"></span>
              SAP Emarsys BigQuery 集成
            </div>
            <button class="btn-danger btn-sm" onclick="confirmDelete()">删除</button>
          </div>
          <div class="cred-fields">
            <div class="cred-field">
              <label>GCP Project</label>
              <span id="disp-project-id"></span>
            </div>
            <div class="cred-field">
              <label>Dataset</label>
              <span id="disp-dataset-id"></span>
            </div>
            <div class="cred-field">
              <label>Suite Account ID</label>
              <span id="disp-account-id"></span>
            </div>
            <div class="cred-field full" id="disp-datasets-row">
              <label>已发现的数据集</label>
              <div class="tag-list" id="disp-datasets"></div>
            </div>
            <div class="cred-field full">
              <label>已发现的视图 / 表</label>
              <div class="tag-list" id="disp-tables"></div>
            </div>
          </div>
          <div class="cred-footer">
            <div class="cred-meta" id="disp-validated-at"></div>
            <div class="cred-meta" id="disp-created-at"></div>
          </div>
        </div>
      </div>

      <!-- No credential -->
      <div id="cred-empty" class="card hidden">
        <div class="empty-state">
          <div class="empty-icon">🔒</div>
          <h3>尚未配置任何凭证</h3>
          <p>添加您的第一个数据源凭证，开始使用 SocialHub 分析功能</p>
          <button class="btn-primary" onclick="showPage('type-picker')">+ 新建凭证</button>
        </div>
      </div>
    </div>

    <!-- PAGE: Type Picker -->
    <div id="page-type-picker" class="hidden">
      <div class="breadcrumb">
        <a onclick="showPage('credentials')">凭证管理</a> / 选择凭证类型
      </div>
      <div class="page-header">
        <div class="page-title">选择凭证类型</div>
      </div>
      <div class="type-grid">
        <div class="type-card" onclick="showPage('upload-form')">
          <div class="type-card-icon">📊</div>
          <h3>SAP Emarsys BigQuery 集成</h3>
          <p>通过 Service Account 连接 Emarsys Open Data，自动发现所有 emarsys_* 数据集</p>
        </div>
      </div>
    </div>

    <!-- PAGE: Upload Form -->
    <div id="page-upload-form" class="hidden">
      <div class="breadcrumb">
        <a onclick="showPage('credentials')">凭证管理</a> /
        <a onclick="showPage('type-picker')">选择类型</a> /
        SAP Emarsys BigQuery 集成
      </div>
      <div class="page-header">
        <div class="page-title">SAP Emarsys BigQuery 集成</div>
      </div>

      <div class="card">
        <div id="upload-result" class="hidden"></div>

        <!-- SA JSON upload -->
        <div class="form-group">
          <label>Service Account JSON</label>
          <div class="file-drop" id="file-drop-area"
               onclick="document.getElementById('file-input').click()"
               ondragover="handleDragOver(event)" ondrop="handleDrop(event)">
            <div class="file-drop-icon">📄</div>
            <div>拖拽 Service Account JSON 文件到此处，或点击选择</div>
            <div class="file-name" id="file-name"></div>
          </div>
          <input type="file" id="file-input" accept=".json" class="hidden" onchange="handleFileSelect(event)">
          <div class="hint">从 Google Cloud Console 下载的 Service Account JSON 文件</div>
        </div>

        <!-- GCP Project ID -->
        <div class="form-group">
          <label for="inp-project-id">GCP Project ID</label>
          <input type="text" id="inp-project-id" placeholder="例如：sap-od-mycompany">
          <div class="hint">Emarsys Open Data 项目 ID，通常格式为 sap-od-&lt;customer&gt;</div>
        </div>

        <!-- Dataset ID (optional) -->
        <div class="form-group">
          <label for="inp-dataset-id">Dataset ID <span class="optional-badge">可选</span></label>
          <input type="text" id="inp-dataset-id" placeholder="例如：emarsys_mycompany_123456（留空自动发现）">
          <div class="hint">留空时自动发现所有 emarsys_* 数据集；填写则只验证指定数据集</div>
        </div>

        <div style="display:flex; gap:12px;">
          <button class="btn-primary" id="upload-btn" onclick="doUpload()">上传并校验</button>
          <button class="btn-secondary" onclick="showPage('type-picker')">取消</button>
        </div>
      </div>
    </div>

  </div><!-- /main -->
</div><!-- /view-app -->

<script>
  'use strict';
  let _token = localStorage.getItem('sh_token') || '';
  let _saJson = null;
  let _currentPage = 'credentials';

  // ─── Utilities ───────────────────────────────────────────────
  function show(id) { document.getElementById(id).classList.remove('hidden'); }
  function hide(id) { document.getElementById(id).classList.add('hidden'); }
  function showPage(name) {
    _currentPage = name;
    ['page-credentials', 'page-type-picker', 'page-upload-form'].forEach(p => hide(p));
    show('page-' + name);
    if (name === 'upload-form') {
      // Reset form
      _saJson = null;
      document.getElementById('file-name').textContent = '';
      document.getElementById('inp-project-id').value = '';
      document.getElementById('inp-dataset-id').value = '';
      hide('upload-result');
    }
  }

  async function apiFetch(path, opts = {}) {
    const headers = { 'Authorization': 'Bearer ' + _token, ...(opts.headers || {}) };
    return fetch(path, { ...opts, headers });
  }

  // ─── Auth ─────────────────────────────────────────────────────
  async function doLogin() {
    const token = document.getElementById('token-input').value.trim();
    if (!token) return;
    hide('login-error');
    const btn = document.getElementById('login-btn');
    btn.disabled = true;
    btn.innerHTML = '<span class="spinner"></span>验证中...';
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
      enterApp(await resp.json());
    } catch (e) {
      show('login-error');
      document.getElementById('login-error').textContent = '连接失败：' + e.message;
    } finally {
      btn.disabled = false;
      btn.textContent = '登录';
    }
  }

  function doLogout() {
    localStorage.removeItem('sh_token');
    _token = '';
    hide('view-app');
    show('view-login');
    document.getElementById('token-input').value = '';
  }

  function enterApp(data) {
    hide('view-login');
    show('view-app');
    document.getElementById('tenant-info').textContent = 'Token: ' + _token.substring(0, 6) + '***';
    renderCredentials(data);
    showPage('credentials');
  }

  // ─── Credentials ──────────────────────────────────────────────
  function renderCredentials(data) {
    if (data.configured) {
      show('cred-list');
      hide('cred-empty');
      document.getElementById('disp-project-id').textContent = data.gcp_project_id || '—';
      document.getElementById('disp-dataset-id').textContent = data.dataset_id || '（自动发现）';
      // account id from customer_id field (first suite account ID)
      document.getElementById('disp-account-id').textContent = data.customer_id || '—';

      // datasets
      const datasets = data.datasets_found || [];
      const datasetsRow = document.getElementById('disp-datasets-row');
      if (datasets.length > 0) {
        show('disp-datasets-row');
        document.getElementById('disp-datasets').innerHTML =
          datasets.map(d => `<span class="tag">${d}</span>`).join('');
      } else {
        hide('disp-datasets-row');
      }

      // tables
      const tables = data.tables_found || [];
      document.getElementById('disp-tables').innerHTML =
        tables.slice(0, 20).map(t => `<span class="tag">${t}</span>`).join('') +
        (tables.length > 20 ? `<span class="tag">+${tables.length - 20} 更多</span>` : '');

      document.getElementById('disp-validated-at').textContent =
        data.validated_at ? '校验时间：' + new Date(data.validated_at).toLocaleString('zh-CN') : '';
      document.getElementById('disp-created-at').textContent =
        data.created_at ? '创建时间：' + new Date(data.created_at).toLocaleString('zh-CN') : '';
    } else {
      hide('cred-list');
      show('cred-empty');
    }
  }

  async function confirmDelete() {
    if (!confirm('确定要删除此凭证吗？此操作不可撤销。')) return;
    try {
      const resp = await apiFetch('/credentials/bigquery', { method: 'DELETE' });
      if (resp.ok) {
        renderCredentials({ configured: false });
      } else {
        alert('删除失败：' + (await resp.json()).message);
      }
    } catch (e) {
      alert('删除失败：' + e.message);
    }
  }

  // ─── File handling ────────────────────────────────────────────
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
    document.getElementById('file-name').textContent = '📎 ' + file.name;
    const reader = new FileReader();
    reader.onload = (e) => {
      try {
        _saJson = JSON.parse(e.target.result);
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

  // ─── Upload ───────────────────────────────────────────────────
  async function doUpload() {
    const projectId = document.getElementById('inp-project-id').value.trim();
    const datasetId = document.getElementById('inp-dataset-id').value.trim();
    const resultEl = document.getElementById('upload-result');

    if (!_saJson) { alert('请先选择 Service Account JSON 文件'); return; }
    if (!projectId) { alert('请填写 GCP Project ID'); return; }

    const btn = document.getElementById('upload-btn');
    btn.disabled = true;
    btn.innerHTML = '<span class="spinner"></span>校验中...';
    show('upload-result');
    resultEl.className = 'alert alert-info';
    resultEl.textContent = '正在连接 BigQuery 并校验凭据，请稍候...';

    try {
      const body = {
        gcp_project_id: projectId,
        service_account_json: _saJson,
      };
      if (datasetId) body.dataset_id = datasetId;

      const resp = await apiFetch('/credentials/bigquery', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      const data = await resp.json();
      if (resp.ok) {
        const dsCount = (data.datasets_found || []).length;
        const tCount = (data.tables_found || []).length;
        resultEl.className = 'alert alert-success';
        resultEl.textContent = `✓ 校验通过！发现 ${dsCount} 个数据集，共 ${tCount} 张视图/表`;
        setTimeout(async () => {
          const r = await apiFetch('/credentials/bigquery');
          const fresh = await r.json();
          enterApp(fresh);
        }, 1500);
      } else {
        resultEl.className = 'alert alert-error';
        resultEl.textContent = '✗ ' + (data.message || '校验失败');
      }
    } catch (e) {
      resultEl.className = 'alert alert-error';
      resultEl.textContent = '连接失败：' + e.message;
    } finally {
      btn.disabled = false;
      btn.textContent = '上传并校验';
    }
  }

  // ─── Auto-login ───────────────────────────────────────────────
  (async () => {
    if (_token) {
      try {
        const resp = await fetch('/credentials/bigquery', {
          headers: { 'Authorization': 'Bearer ' + _token }
        });
        if (resp.ok) { enterApp(await resp.json()); return; }
      } catch {}
      localStorage.removeItem('sh_token');
      _token = '';
    }
  })();
</script>
</body>
</html>
```

- [ ] **Step 3: 验证新 UI 可访问**

Docker 容器 (`socialhub-mcp:local`) 使用的是 build 时 COPY 进去的静态文件，需要重新 build。但先在本地 Python 测试路由：

```bash
# 确认文件写入正确
wc -l /Users/wangyunlong/myproject/sap_Integration/src/Socialhub-CLI/mcp_server/static/ui.html
# 期望：行数 > 200
```

- [ ] **Step 4: 运行全量测试**

```bash
cd /Users/wangyunlong/myproject/sap_Integration/src/Socialhub-CLI
conda run -n dev pytest tests/ -v --tb=short 2>&1 | tail -20
```

期望：所有测试通过

- [ ] **Step 5: 提交**

```bash
cd /Users/wangyunlong/myproject/sap_Integration/src/Socialhub-CLI
git add mcp_server/static/ui.html
git commit -m "feat: redesign UI with sidebar layout, credential cards, and new credential flow"
```

---

## Task 3: 重新构建 Docker 镜像并验证

**Files:** 无代码变更，仅 Docker build + smoke test

- [ ] **Step 1: 停止并删除旧容器**

```bash
docker stop socialhub-mcp-local 2>/dev/null || true
docker rm socialhub-mcp-local 2>/dev/null || true
```

- [ ] **Step 2: 重新构建镜像**

```bash
cd /Users/wangyunlong/myproject/sap_Integration/src/Socialhub-CLI
docker build -t socialhub-mcp:local .
```

期望：Successfully built ...

- [ ] **Step 3: 启动容器**

```bash
docker run -d --name socialhub-mcp-local \
  --env-file .env.local \
  -p 8091:8090 \
  socialhub-mcp:local
```

- [ ] **Step 4: Smoke test**

```bash
# Health check
curl -s http://localhost:8091/health

# Auth check
curl -s http://localhost:8091/credentials/bigquery \
  -H "Authorization: Bearer sapbigquerytest"

# UI check
curl -s http://localhost:8091/ui | grep -c "SocialHub"
```

期望：
- `/health` 返回 `{"status":"ok"}`
- `/credentials/bigquery` 返回 `{"status":"ok","configured":...}`
- `/ui` 返回的 HTML 包含 "SocialHub"

- [ ] **Step 5: 在浏览器中打开验证**

打开 `http://localhost:8091/ui`，确认：
- 显示登录页
- 输入 `sapbigquerytest`，登录后进入左侧导航布局
- 显示凭证管理页（有凭证则显示卡片，无凭证则显示空状态）
- 点击"新建凭证"→ 类型选择页 → 上传表单页

- [ ] **Step 6: 提交（可选）**

如有必要的小修复：

```bash
cd /Users/wangyunlong/myproject/sap_Integration/src/Socialhub-CLI
git add -A
git commit -m "chore: rebuild docker with new UI and backend fixes"
```

---

## 自检

### Spec 覆盖
- [x] `customer_ids_found` → `account_ids_found` 命名修正（Task 1）
- [x] `dataset_id` 改可选（Task 1）
- [x] `datasets_found` 写入 DB 并在 GET 返回（Task 1）
- [x] UI 左侧导航（Task 2）
- [x] 凭证列表卡片（Task 2）
- [x] 新建凭证流程：类型选择 → 上传表单（Task 2）
- [x] Dataset ID 可选（UI 层面已体现，Task 2）
- [x] Docker 重新 build 验证（Task 3）

### 无占位符
已检查，所有步骤包含完整代码。

### 类型一致性
- `ValidationResult.account_ids_found: list[str]` — Task 1 Step 1 定义，Task 1 Step 2 引用 ✓
- `datasets_found: str | None`（DB 字段）— 已存在于 models.py，Task 1 写入，Task 1 读取 ✓
