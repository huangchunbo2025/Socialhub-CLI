# Naming Conventions

开发规范文档。新增任何文件或目录时，按本文档规则命名。

---

## 目录命名

统一使用 `kebab-case`（小写 + 连字符）。

```
✓  skills-store/
✓  report-generator/
✓  sample-skill/
✗  SkillsStore/
✗  skills_store/
✗  skillsstore/
```

---

## 各模块命名规则

### CLI（`cli/`）

| 类型 | 规则 | 示例 |
|------|------|------|
| Python 模块文件 | `snake_case.py` | `store_client.py` |
| Python 子包目录 | `snake_case/` | `skills/`, `commands/`, `local/` |
| 命令文件（一个文件 = 一组命令） | `<noun>.py` | `skills.py`, `config.py` |
| 服务/管理类文件 | `<noun>_manager.py` / `<noun>_client.py` | `skill_manager.py`, `store_client.py` |
| 数据模型文件 | `models.py` 或 `<noun>.py` | `models.py` |
| 测试文件 | `test_<module>.py` | `test_skills.py`, `test_security.py` |

**类命名（Python）：**

| 类型 | 规则 | 示例 |
|------|------|------|
| 普通类 | `PascalCase` | `SkillManager`, `StoreClient` |
| 异常类 | `PascalCase` + `Error` 后缀 | `SkillManagerError`, `SecurityError` |
| Pydantic 模型 | `PascalCase` | `InstalledSkill`, `SkillManifest` |

**函数/变量命名（Python）：**

| 类型 | 规则 | 示例 |
|------|------|------|
| 函数 / 方法 | `snake_case` | `install_skill()`, `get_my_skills()` |
| 常量 | `UPPER_SNAKE_CASE` | `TOKEN_FILE`, `DEFAULT_TIMEOUT` |
| 私有方法 | `_snake_case` | `_load_token()`, `_auth_headers()` |
| 布尔变量 | `is_` / `has_` / `can_` 前缀 | `is_installed`, `has_permission` |

---

### 后端（`skills-store/backend/`）

| 类型 | 规则 | 示例 |
|------|------|------|
| Router 文件 | `<resource>.py`（名词复数） | `users.py`, `skills.py`, `user_skills.py` |
| Model 文件 | `<entity>.py`（名词单数） | `user.py`, `skill.py`, `user_skill.py` |
| Schema 文件 | `<resource>.py` | `user.py`, `skill.py` |
| Service 文件 | `<noun>.py` | `auth.py`, `scan.py`, `certificates.py` |
| Migration 文件 | Alembic 自动生成，保持不变 | `20240101_add_users_table.py` |

**数据库表命名：**

| 类型 | 规则 | 示例 |
|------|------|------|
| 表名 | `snake_case` 复数 | `users`, `skills`, `user_skills` |
| 外键字段 | `<table_singular>_id` | `user_id`, `skill_id` |
| 时间字段 | `<action>_at` | `created_at`, `installed_at` |
| 布尔字段 | `is_<state>` | `is_active`, `is_enabled` |
| JSONB 字段 | `snake_case` 名词 | `permissions`, `metadata` |

**API 路由命名：**

| 类型 | 规则 | 示例 |
|------|------|------|
| 资源路径 | `kebab-case` 复数名词 | `/api/v1/users`, `/api/v1/skills` |
| 子资源 | `/<id>/<sub-resource>` | `/users/me/skills` |
| 动作（非 CRUD） | `/<id>/<verb>` | `/skills/{name}/toggle` |
| 版本前缀 | `/api/v{n}` | `/api/v1` |

---

### 前端（`skills-store/frontend/`）

| 类型 | 规则 | 示例 |
|------|------|------|
| 页面组件 | `PascalCase` + `Page` 后缀 | `CatalogPage.jsx`, `UserPage.jsx` |
| 通用 UI 组件 | `PascalCase` | `SkillCard.jsx`, `Layout.jsx` |
| 工具 / 辅助模块 | `camelCase.js` | `api.js`, `session.js` |
| 样式文件 | `camelCase.css` 或与组件同名 | `styles.css` |
| 常量文件 | `camelCase.js` | `categoryMeta.js` |
| 目录（功能分组） | `kebab-case` 或约定俗成 | `components/`, `pages/`, `lib/` |

**组件内命名（React）：**

| 类型 | 规则 | 示例 |
|------|------|------|
| 组件函数 | `PascalCase` | `function SkillCard()` |
| Props | `camelCase` | `skillName`, `isInstalled` |
| 事件处理函数 | `handle` + `PascalCase` 动词 | `handleInstall`, `handleToggle` |
| 状态变量 | `camelCase` | `isLoading`, `skillList` |
| Context | `PascalCase` + `Context` 后缀 | `AuthContext`, `ToastContext` |

---

### 设计文档（`design/`）

| 类型 | 规则 | 示例 |
|------|------|------|
| 所有文档 | `kebab-case.md` | `prd-skills-store.md` |
| 任务追踪 | `tasks-<feature>.md` | `tasks-skills-store.md` |
| 技术规范 | `<feature>-spec.md` | `skills-technical-spec.md` |
| 部署相关 | `<service>-deploy.md` | `skills-store-render-deploy.md` |
| 安全指南 | `security-guide-<audience>.md` | `security-guide-developers.md` |

---

### 根目录文件

根目录只放项目级别的配置和入口文件，不放业务文件。

| 文件 | 用途 |
|------|------|
| `README.md` | 项目介绍（全大写，惯例） |
| `CODEX.md` | AI 协作任务文件（全大写，醒目） |
| `pyproject.toml` | CLI Python 包配置 |
| `.gitignore` | Git 忽略规则 |

---

## 新功能扩展示例

### 新增一个 CLI 命令模块

```
cli/commands/analytics.py     ← 命令定义
cli/services/analytics.py     ← 业务逻辑（如果复杂）
tests/test_analytics.py       ← 测试
```

### 新增一个后端资源（如 `teams`）

```
skills-store/backend/app/
├── models/team.py             ← 数据模型（单数）
├── routers/teams.py           ← 路由（复数）
├── schemas/team.py            ← 请求/响应结构
└── services/teams.py          ← 业务逻辑
alembic/versions/xxx_add_teams_table.py  ← 迁移
```

### 新增一个前端页面

```
skills-store/frontend/src/
├── pages/TeamPage.jsx         ← 页面（PascalCase + Page）
└── components/TeamCard.jsx    ← 组件（PascalCase）
```

### 新增一个 Skill 包（给开发者参考）

```
my-skill/                      ← kebab-case 目录名
├── skill.yaml                 ← manifest（固定名称）
├── main.py                    ← 入口（固定名称）
└── requirements.txt           ← 依赖（可选）
```

---

## 禁止的命名方式

| ✗ 错误 | ✓ 正确 | 原因 |
|--------|--------|------|
| `MyComponent.js` | `MyComponent.jsx` | React 组件用 `.jsx` 扩展名 |
| `get_Users()` | `get_users()` | Python 函数用 `snake_case` |
| `usersRouter.py` | `users.py` | Router 文件不加 `Router` 后缀 |
| `UserModel.py` | `user.py` | Model 文件不加 `Model` 后缀 |
| `helpers.py` / `utils.py` | 按功能命名 | 避免无意义的通用文件名 |
| `temp.py` / `test2.py` | 删掉或正式命名 | 临时文件不提交 |
| `NewFeature/` | `new-feature/` | 目录不用 PascalCase |
