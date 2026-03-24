# Skills Store 任务清单

> **审查说明**：Claude Code 直接读取代码审查，无需粘贴代码。
> 告诉我「任务 X 完成了」，我去读代码，给出通过/具体修改意见。
>
> **分工**：
> - `skills-store/`、`frontend/`、`docs/` → **Codex 负责**
> - `socialhub/` → **Claude Code 负责，Codex 不得修改**

---

## 总体进度

```
阶段一：后端 MVP（基础链路）
  M-001 脚手架 + DB       ██████████  ✅ 已验收
  M-002 认证              ████████░░  需补测试 + 小修复
  M-003 安全扫描 + 上传    █████░░░░░  扫描逻辑不完整
  M-004 审核 + 证书        ████████░░  需补测试
  M-005 公开 API + CRL    ███████░░░  CRL 格式错误

阶段二：安全修复（上线前必须完成）
  SEC-001 后端安全加固     ░░░░░░░░░░  未开始

阶段三：Web ↔ CLI 同步
  B-006 用户技能库 API    ░░░░░░░░░░  未开始
  W-001 技能详情页更新     ░░░░░░░░░░  未开始（依赖 B-006）
  W-002 用户工作台更新     ░░░░░░░░░░  未开始（依赖 B-006）

阶段四：质量门禁
  Q-001 全量测试 + 覆盖率  ░░░░░░░░░░  未开始（依赖阶段一完成）
```

---

## 依赖关系图

```
M-001 ──→ M-002 ──→ M-003 ──→ M-004 ──→ M-005
                                              │
                              SEC-001 ────────┤（可与 M-005 修复并行）
                                              │
                              B-006  ─────────┤（依赖 M-005 部署完成）
                                              │
                              W-001 ──────────┤（依赖 B-006）
                              W-002 ──────────┘（依赖 B-006）

Q-001 依赖：M-002、M-003、M-004、M-005、SEC-001 全部通过
```

---

## 阶段一：后端 MVP

---

### ✅ M-001：脚手架 + 数据库模型

**状态**：已验收通过

**已实现**：
- FastAPI 项目结构 `skills-store/backend/`
- Docker-compose（FastAPI + PostgreSQL 15）
- SQLAlchemy 2.0 async + Alembic 迁移
- 5 张核心表：`developers`、`skills`、`skill_versions`、`skill_certifications`、`skill_reviews`
- `GET /health` 返回 `{"status": "ok"}`
- `.env.example` 提供
- Render 部署配置（`render.yaml`、`start.sh`）
- 迁移文件：`0001_initial_schema.py`、`0002_skill_detail_content.py`

**验收记录**：2026-03-22 Claude Code 审查通过

---

### ⚠️ M-002：基础认证

**状态**：功能基本完成，需补测试文件

**已实现**：
- `POST /api/v1/auth/register`（邮箱+密码+姓名）
- `POST /api/v1/auth/login`（JWT，24小时有效期）
- `GET /api/v1/auth/me`、`PATCH /api/v1/auth/me`
- `get_current_user` / `require_store_admin` FastAPI 依赖
- Admin 账号启动时自动创建（`ADMIN_EMAIL` / `ADMIN_PASSWORD` 环境变量）
- PBKDF2 密码哈希（等价于 bcrypt 安全强度）
- 迁移文件：`0003_developer_saved_skills.py`（已加 `saved_skills` JSONB）

**待补充**：
- [ ] `tests/test_auth.py` — 覆盖以下场景，全部通过：
  - 注册成功后可登录
  - 重复邮箱注册返回 409
  - 无 token 访问受保护接口返回 401
  - admin 账号随服务启动自动创建
  - 登录响应格式必须是：`{"data": {"access_token": "...", "expires_in": 86400, "user": {...}}}`

> ⚠️ **login 响应格式约束**：CLI 依赖 `data.access_token` 和 `data.expires_in` 字段（见 `socialhub/cli/skills/store_client.py`），格式不对 CLI login 会失败。

---

### ❌ M-003：安全扫描 + 开发者提交技能

**状态**：上传流程完整，但扫描逻辑不完整（关键缺陷）

**已实现**：
- `POST /api/v1/developer/skills`（创建技能元数据）
- `POST /api/v1/developer/skills/{name}/versions`（上传 ZIP 包）
- ZIP 格式校验、manifest 解析（YAML/JSON）
- SHA-256 `package_hash` 计算存储
- 自动创建 SkillReview 记录（status=reviewing）
- 文件扩展名黑名单（.exe/.dll/.bat 等）
- 文件大小限制（20MB）

**必须修复**：

- [ ] **`services/scan.py` 补充危险代码正则检测**（当前完全缺失）：
  ```python
  # 必须检测以下模式，发现任意一个即返回 422，不写数据库
  DANGEROUS_PATTERNS = [
      r'eval\s*\(',
      r'exec\s*\(',
      r'__import__\s*\(',
      r'pickle\.loads\s*\(',
      r'shell\s*=\s*True',
      r'os\.system\s*\(',
  ]
  # 硬编码密钥检测
  HARDCODED_SECRET_PATTERN = r'(password|secret|api_key|token)\s*=\s*[\'"][^\'"]{8,}[\'"]'
  ```
  扫描所有 `.py` 文件内容，发现匹配时返回 422 并在响应中说明原因。

- [ ] **`tests/test_scan_service.py`** — 必须包含 8 个恶意样本测试（每种危险模式至少 1 个）+ 合法包通过测试

- [ ] **`tests/test_developer_api.py`** — 覆盖：
  - 含 `eval()` 包返回 422，数据库无记录
  - 非 .zip 格式返回 400
  - 合法包上传后创建三条记录（Skill + SkillVersion + SkillReview）

---

### ⚠️ M-004：审核队列 + 证书颁发

**状态**：功能完整，需补测试

**已实现**：
- `GET /api/v1/admin/reviews`（分页，支持 status 过滤）
- `POST /api/v1/admin/reviews/{id}/start`（标记为 in_review）
- `POST /api/v1/admin/reviews/{id}/approve`（颁发证书，更新 status=published）
- `POST /api/v1/admin/reviews/{id}/reject`（更新 status=rejected）
- `POST /api/v1/admin/certificates/{cert_serial}/revoke`
- Ed25519 签名实现正确（cryptography 库）
- 证书 serial 格式：`cert-{YYYYMMDD}-{16位hex}`
- 私钥不存在时自动生成

**待补充**：

- [ ] **`tests/test_admin_api.py`** — 覆盖：
  - 非 admin 调用审核接口返回 403
  - approve 后 SkillVersion.status = "published"，SkillCertification 记录存在
  - reject 后 SkillVersion.status = "rejected"
  - 吊销后 `revoked_at` 不为空

- [ ] **`tests/test_cert_service.py`** — 覆盖：
  - 证书 signature 由 Ed25519 私钥生成，用公钥可验证通过

---

### ❌ M-005：公开 API + 下载 + CRL

**状态**：大部分完整，CRL 格式错误（阻断 CLI 集成）

**已实现**：
- `GET /api/v1/skills`（search、category、page、limit）
- `GET /api/v1/skills/featured`（12 条）
- `GET /api/v1/skills/{name}`
- `GET /api/v1/skills/{name}/versions`
- `GET /api/v1/skills/{name}/download`（FileResponse，异步 +1 计数）
- `GET /api/v1/skills/{name}/download-info`
- `POST /api/v1/skills/verify`（Ed25519 签名验证）
- `GET /api/v1/crl`（有内容，但格式错误）
- `GET /api/v1/categories`

**必须修复**：

- [ ] **CRL 响应格式错误**（当前字段名与 CLI `security.py` 不匹配，会导致 CLI 吊销检查静默失败）

  当前返回（错误）：
  ```json
  {"issued_at": null, "revoked_certificates": [{"certificate_serial": "..."}]}
  ```

  必须改为（严格按此格式）：
  ```json
  {
    "version": 1,
    "updated_at": "2026-03-22T10:00:00Z",
    "revoked": [
      {"certificate_id": "cert-20260322-abc123", "revoked_at": "...", "reason": "..."}
    ]
  }
  ```
  字段映射：`certificate_serial` → `certificate_id`，`revoked_certificates` → `revoked`，补充 `version: 1` 和 `updated_at`

- [ ] **CRL 响应头缺失**：加 `Cache-Control: max-age=3600`

- [ ] **`tests/test_public_api.py`** — 覆盖：
  - 搜索/分类/分页正常
  - 下载返回可解压 zip
  - 非 published 版本返回 404
  - CRL 格式完全正确（字段名、嵌套结构）
  - verify 返回正确的 valid/invalid

---

## 阶段二：安全修复（必须在首次上线前完成）

---

### ❌ SEC-001：后端安全加固

**状态**：未开始

**依赖**：无（可与 M-002～M-005 并行修复）

**必须修复（按优先级排序）**：

**Fix 1：删除 CORS `"null"` origin**（`skills-store/backend/app/main.py`）

```python
# 删除这行 ——「null」允许本地 HTML 文件以用户身份发请求（高危）
"null",
```

**Fix 2：JWT secret 无默认值，启动时强制校验**（`skills-store/backend/app/config.py`）

```python
# 改为（无默认值，未设置时 pydantic-settings 会在启动时报错）：
jwt_secret: str
```

同步更新 `.env.example`，添加：
```
JWT_SECRET=<请生成32位以上随机字符串，例如：openssl rand -hex 32>
```

**Fix 3：登录接口加速率限制**（`skills-store/backend/app/routers/auth.py`）

安装 `slowapi`，对 `POST /api/v1/auth/login` 限制：**同一 IP 每分钟最多 10 次**，超出返回 429。

```python
# pyproject.toml dependencies 加：
# "slowapi>=0.1.9",
```

**验收标准**：
- [ ] `"null"` 不在 allow_origins 列表中
- [ ] 未设置 `JWT_SECRET` 环境变量时，服务启动报错退出（不使用默认值）
- [ ] 连续 11 次登录同一 IP 返回 429
- [ ] `.env.example` 有 `JWT_SECRET` 说明

---

## 阶段三：Web ↔ CLI 同步

---

### ❌ B-006：用户技能库 API

**状态**：未开始

**依赖**：M-005 已部署到 Render（需要 published skills 才能添加到用户库）

**需要新建的数据库表**（Alembic 迁移文件：`0004_user_skills.py`）：

```sql
CREATE TABLE user_skills (
    id               BIGSERIAL PRIMARY KEY,
    developer_id     BIGINT NOT NULL REFERENCES developers(id) ON DELETE CASCADE,
    skill_id         BIGINT NOT NULL REFERENCES skills(id) ON DELETE RESTRICT,
    skill_version_id BIGINT NOT NULL REFERENCES skill_versions(id) ON DELETE RESTRICT,
    is_enabled       BOOLEAN NOT NULL DEFAULT TRUE,
    downloaded_at    TIMESTAMPTZ DEFAULT NOW(),
    updated_at       TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(developer_id, skill_id)
);
CREATE INDEX idx_user_skills_developer ON user_skills(developer_id);
```

> ⚠️ 不要删除 `developers.saved_skills` JSONB 字段，`user_skills` 是独立的新概念。

**需要新建的路由**（`skills-store/backend/app/routers/me.py`）：

所有端点需要有效 JWT（`get_current_user` 依赖）。

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/api/v1/me/skills` | 返回用户技能库列表 |
| `POST` | `/api/v1/me/skills/{skill_name}` | 添加 skill 到用户库 |
| `DELETE` | `/api/v1/me/skills/{skill_name}` | 从用户库移除 |
| `PATCH` | `/api/v1/me/skills/{skill_name}/toggle` | 切换启用/禁用 |

**`GET /api/v1/me/skills` 响应格式**（CLI 依赖此格式，不得改变字段名）：
```json
{
  "data": {
    "items": [
      {
        "skill_name": "report-generator",
        "display_name": "报表生成器",
        "version": "1.1.0",
        "category": "utility",
        "is_enabled": true,
        "downloaded_at": "2026-03-22T10:00:00Z",
        "description": "..."
      }
    ],
    "total": 3
  }
}
```

**`POST /api/v1/me/skills/{skill_name}` 请求体**：
```json
{ "version": "1.1.0" }
```
- `version` 可选，缺省取最新 published 版本
- 技能已在库中返回 409

**`PATCH /api/v1/me/skills/{skill_name}/toggle` 请求体**：
```json
{ "enabled": true }
```

**错误场景**：
- 技能不存在或非 published 状态 → 404
- 技能已在用户库（POST）→ 409
- 技能不在用户库（DELETE/PATCH）→ 404

**验收标准**：
- [ ] `POST /me/skills/report-generator` → 出现在 `GET /me/skills` 列表
- [ ] `DELETE /me/skills/report-generator` → 从列表消失
- [ ] `PATCH /me/skills/report-generator/toggle {"enabled": false}` → `is_enabled = false`
- [ ] 不同用户的库相互独立
- [ ] `tests/test_me_api.py` 全部通过

---

### ❌ W-001：技能详情页 Install/Uninstall 按钮

**状态**：未开始

**依赖**：B-006 已部署

**改动文件**：`frontend/src/pages/SkillDetailPage.jsx`

**需求**：
- 登录状态下，检查该 skill 是否在用户库（调用 `GET /me/skills` 比对）
- 不在库中：显示 **"Install"** 按钮 → 点击调用 `POST /api/v1/me/skills/{name}`
- 已在库中：显示 **"Uninstall"** 按钮 → 点击调用 `DELETE /api/v1/me/skills/{name}`
- 未登录：显示 **"Login to Install"** → 跳转 `/login`
- 说明文案：`Install adds this skill to your library. Use the CLI to run it.`（说明实际执行仍在 CLI）

**验收标准**：
- [ ] 未登录用户看到 "Login to Install"
- [ ] 登录后点 Install → 按钮变为 Uninstall
- [ ] 点 Uninstall → 按钮变回 Install
- [ ] `GET /me/skills` 反映最新状态

---

### ❌ W-002：用户工作台 My Skills

**状态**：未开始

**依赖**：B-006 已部署

**改动文件**：`frontend/src/pages/UserPage.jsx`

**需求**：
- 把现有 "Saved Skills"（localStorage）替换为 **"My Skills"**（从 `GET /api/v1/me/skills` 读取）
- 每行展示：技能名、版本、分类、**Enable/Disable 开关**、Remove 按钮
- Enable/Disable 开关 → 调用 `PATCH /api/v1/me/skills/{name}/toggle`
- Remove → 调用 `DELETE /api/v1/me/skills/{name}` + 刷新列表
- 空状态文案：`Your library is empty. Browse the store to install skills.`（附跳转 `/` 链接）

> ⚠️ `session.js` 中 `toggleSkillEnabledState` / `getSkillEnabledState` 是旧的 localStorage 实现，W-002 完成后这两个函数可以废弃，但不要删除——等确认无其他引用后再清理。

**验收标准**：
- [ ] 页面加载调用 `GET /me/skills`，展示用户库
- [ ] Enable/Disable 开关调用 toggle API，刷新后状态保持
- [ ] Remove 按钮调用 DELETE API，列表立即更新
- [ ] 空库时显示引导文案

---

## 阶段四：质量门禁

---

### ❌ Q-001：全量测试 + 质量检查

**状态**：未开始

**依赖**：M-002、M-003、M-004、M-005、SEC-001、B-006 全部通过

**检查项**：

| 检查 | 命令 | 标准 |
|------|------|------|
| 单元/集成测试 | `pytest --cov=app --cov-report=term` | 全部通过，覆盖率 ≥ 70% |
| 类型检查 | `mypy app/` | 无错误（不要求 strict） |
| 代码风格 | `ruff check .` | 无 error |
| 安全扫描 | `grep -r "shell=True" app/` | 无输出 |
| 硬编码密钥 | `grep -rE "(password|secret|api_key)\s*=\s*['\"][^'\"]{8,}" app/` | 无输出 |
| CRL 兼容性 | 对照 `socialhub/cli/skills/security.py` 手动测试 | CRL 格式完全匹配 |

---

## 审查流程

```
Codex 说「M-003 修完了」
        ↓
Claude Code 读 skills-store/ 代码
        ↓
通过 → 更新本文档状态 → 告知继续下一个任务
不通过 → 给出具体修改意见（文件名 + 行号）
```

**当前推荐执行顺序**：
1. **M-003**（修复扫描 + 写测试）— 阻断安全问题
2. **M-005**（修复 CRL 格式）— 阻断 CLI 集成
3. **SEC-001**（安全修复）— 上线前必须
4. **M-002 + M-004**（补测试）— 质量要求
5. **B-006**（用户库 API）— 新功能
6. **W-001 + W-002**（Web 更新）— 新功能
7. **Q-001**（质量门禁）— 最终检查
