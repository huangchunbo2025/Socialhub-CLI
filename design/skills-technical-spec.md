# Skills 系统技术文档

**项目：** SocialHub.AI CLI
**模块路径：** `socialhub/cli/skills/`
**文档版本：** 1.0
**更新日期：** 2026-03-21

---

## 目录

1. [系统概述](#1-系统概述)
2. [架构总览](#2-架构总览)
3. [数据模型](#3-数据模型)
4. [核心模块详解](#4-核心模块详解)
   - 4.1 [SkillRegistry — 本地注册表](#41-skillregistry--本地注册表)
   - 4.2 [SkillManager — 安装与生命周期管理](#42-skillmanager--安装与生命周期管理)
   - 4.3 [SkillLoader — 加载与执行引擎](#43-skillloader--加载与执行引擎)
   - 4.4 [SkillsStoreClient — 商店 API 客户端](#44-skillsstoreclient--商店-api-客户端)
   - 4.5 [VersionManager — 版本管理](#45-versionmanager--版本管理)
5. [安全子系统](#5-安全子系统)
   - 5.1 [安全模型概述](#51-安全模型概述)
   - 5.2 [KeyManager — 公钥管理](#52-keymanager--公钥管理)
   - 5.3 [HashVerifier — 包完整性校验](#53-hashverifier--包完整性校验)
   - 5.4 [SignatureVerifier — Ed25519 签名验证](#54-signatureverifier--ed25519-签名验证)
   - 5.5 [RevocationListManager — 吊销列表](#55-revocationlistmanager--吊销列表)
   - 5.6 [PermissionChecker — 权限检查](#56-permissionchecker--权限检查)
   - 5.7 [PermissionStore — 权限持久化存储](#57-permissionstore--权限持久化存储)
   - 5.8 [PermissionPrompter — 交互式权限请求](#58-permissionprompter--交互式权限请求)
   - 5.9 [PermissionContext — 运行时权限上下文](#59-permissioncontext--运行时权限上下文)
   - 5.10 [SecurityAuditLogger — 安全审计日志](#510-securityauditlogger--安全审计日志)
   - 5.11 [SecurityEventReporter — 事件上报](#511-securityeventreporter--事件上报)
   - 5.12 [SkillHealthChecker — 健康检查](#512-skillhealthchecker--健康检查)
6. [沙箱子系统](#6-沙箱子系统)
   - 6.1 [SandboxManager — 统一沙箱管理器](#61-sandboxmanager--统一沙箱管理器)
   - 6.2 [FileSystemSandbox — 文件系统隔离](#62-filesystemsandbox--文件系统隔离)
   - 6.3 [NetworkSandbox — 网络隔离](#63-networksandbox--网络隔离)
   - 6.4 [ExecuteSandbox — 命令执行隔离](#64-executesandbox--命令执行隔离)
7. [Skill 包格式规范](#7-skill-包格式规范)
8. [内置 Skill：report-generator](#8-内置-skill-report-generator)
9. [完整执行流程](#9-完整执行流程)
   - 9.1 [安装流程](#91-安装流程)
   - 9.2 [执行流程](#92-执行流程)
10. [文件系统布局](#10-文件系统布局)
11. [错误类型一览](#11-错误类型一览)
12. [设计局限与已知问题](#12-设计局限与已知问题)

---

## 1. 系统概述

Skills 是 SocialHub.AI CLI 的插件扩展机制，允许第三方（或官方）通过标准化的 `.zip` 包向 CLI 添加新命令。它是一个完整的插件生态系统，包含：

- **商店（Store）**：官方托管的 Skill 目录，提供搜索、下载、版本管理
- **安装管道**：带完整性校验、签名验证、吊销检查、权限申请的安装流程
- **运行时隔离**：基于 Python monkey-patching 的三层沙箱（文件系统 / 网络 / 命令执行）
- **权限系统**：声明式权限 + 用户交互授权 + 跨会话持久化

所有 Skill 只能从官方商店 `https://skills.socialhub.ai/api/v1` 安装，任何自定义来源 URL 都会被拒绝（`StoreError`）。

---

## 2. 架构总览

```
CLI 命令层 (commands/skills.py)
        │
        ▼
┌───────────────────────────────────────────────┐
│                SkillManager                   │  ← 安装 / 卸载 / 更新 / 启用 / 禁用
│  ┌──────────────┐   ┌─────────────────────┐   │
│  │SkillRegistry │   │ SkillsStoreClient   │   │
│  │ (registry.   │   │ (store_client.py)   │   │
│  │  json)       │   └─────────────────────┘   │
│  └──────────────┘                             │
│  ┌────────────────────────────────────────┐   │
│  │         Security Subsystem             │   │
│  │ SignatureVerifier / HashVerifier /     │   │
│  │ RevocationListManager / PermissionStore│   │
│  └────────────────────────────────────────┘   │
└───────────────────────────────────────────────┘
        │ 安装完成后
        ▼
┌───────────────────────────────────────────────┐
│                SkillLoader                    │  ← 加载模块 / 路由命令
│  ┌──────────────┐   ┌─────────────────────┐   │
│  │PermissionChecker   SandboxManager      │   │
│  │    (内存态)   │   │ FileSystem/Network/ │   │
│  └──────────────┘   │ Execute Sandbox     │   │
│                     └─────────────────────┘   │
└───────────────────────────────────────────────┘
        │ 执行时
        ▼
  Skill Python Module (main.py)
```

**模块职责划分：**

| 模块 | 文件 | 职责 |
|------|------|------|
| `models.py` | 数据模型 | Pydantic/dataclass 模型，枚举定义 |
| `registry.py` | 本地注册表 | 读写 `registry.json`，管理已安装记录 |
| `manager.py` | 安装管理器 | 完整安装管道，调度安全检查 |
| `loader.py` | 加载执行器 | `importlib` 动态加载，沙箱执行 |
| `store_client.py` | 商店客户端 | REST API 访问，降级 Demo 模式 |
| `security.py` | 安全子系统 | 签名/哈希/权限/审计/CRL |
| `version_manager.py` | 版本管理 | 语义版本比较，升级路径计算 |
| `sandbox/manager.py` | 沙箱协调器 | 统一管理三层沙箱 |
| `sandbox/filesystem.py` | 文件沙箱 | 拦截 `builtins.open` |
| `sandbox/network.py` | 网络沙箱 | 拦截 `socket.socket` |
| `sandbox/execute.py` | 执行沙箱 | 拦截 `subprocess.*` 和 `os.system` |

---

## 3. 数据模型

所有模型定义在 `models.py`，使用 Pydantic v2。

### 枚举

```python
class SkillCategory(str, Enum):
    DATA = "data"           # 数据处理
    MARKETING = "marketing" # 营销工具
    ANALYTICS = "analytics" # 数据分析
    INTEGRATION = "integration" # 系统集成
    UTILITY = "utility"     # 实用工具

class SkillPermission(str, Enum):
    FILE_READ   = "file:read"
    FILE_WRITE  = "file:write"
    NETWORK_LOCAL    = "network:local"
    NETWORK_INTERNET = "network:internet"
    DATA_READ   = "data:read"
    DATA_WRITE  = "data:write"
    CONFIG_READ = "config:read"
    CONFIG_WRITE = "config:write"
    EXECUTE     = "execute"

class SkillStatus(str, Enum):
    DRAFT      = "draft"
    REVIEW     = "review"
    PUBLISHED  = "published"
    SUSPENDED  = "suspended"
    DEPRECATED = "deprecated"
```

### SkillManifest（skill.yaml 的 Python 映射）

```python
class SkillManifest(BaseModel):
    name: str                          # 唯一标识符，也是目录名
    version: str                       # 语义版本，如 "1.2.3"
    display_name: str                  # 展示名称
    description: str
    author: str
    license: str                       # 默认 "MIT"
    homepage: str
    category: SkillCategory
    tags: list[str]
    compatibility: SkillCompatibility  # cli_version / python_version
    dependencies: SkillDependencies    # python 包列表 / skill 依赖
    permissions: list[SkillPermission] # 声明所需权限
    entrypoint: str                    # 默认 "main.py"
    commands: list[SkillCommand]       # 注册的命令列表
    certification: Optional[SkillCertification]  # 官方认证信息
```

### SkillCommand（单条命令定义）

```python
class SkillCommand(BaseModel):
    name: str        # 命令名，如 "generate"
    description: str
    function: str    # 对应 main.py 中的函数名
    arguments: list[dict[str, Any]]  # 参数元数据（文档用途）
```

### InstalledSkill（注册表中的记录）

```python
class InstalledSkill(BaseModel):
    name: str
    version: str
    display_name: str
    description: str
    category: SkillCategory
    installed_at: datetime
    path: str           # 绝对路径，指向安装目录
    enabled: bool       # 是否启用
    manifest: Optional[SkillManifest]
```

### SkillCertification（认证信息）

```python
class SkillCertification(BaseModel):
    certified_at: Optional[datetime]
    certified_by: str       # 必须为 "SocialHub.AI"
    signature: str          # Ed25519 签名，base64 编码
    certificate_id: str     # 证书 ID，如 "SKILL-RPT-003"
    expires_at: Optional[datetime]
```

---

## 4. 核心模块详解

### 4.1 SkillRegistry — 本地注册表

**文件：** `registry.py`

注册表是所有已安装 Skill 的权威来源，以 JSON 文件持久化在磁盘上。

**目录结构：**
```
~/.socialhub/skills/
├── registry.json           ← 注册表主文件
├── installed/
│   └── <skill-name>/       ← 解压后的 Skill 文件
└── cache/
    └── <name>-<version>.zip ← 下载缓存
```

**registry.json 格式：**
```json
{
  "skills": {
    "report-generator": {
      "name": "report-generator",
      "version": "3.1.0",
      "path": "/home/user/.socialhub/skills/installed/report-generator",
      "enabled": true,
      "installed_at": "2026-03-21T10:00:00",
      ...
    }
  },
  "updated_at": "2026-03-21T10:00:00"
}
```

**主要方法：**

| 方法 | 说明 |
|------|------|
| `list_installed() → list[InstalledSkill]` | 返回全部已安装 Skill |
| `get_installed(name) → Optional[InstalledSkill]` | 按名称查找 |
| `is_installed(name) → bool` | 快速判断是否安装 |
| `register_skill(skill)` | 写入注册表（安装后调用） |
| `unregister_skill(name) → bool` | 从注册表删除 |
| `enable_skill(name) / disable_skill(name)` | 启用/禁用 |
| `get_skill_path(name) → Path` | 返回安装目录路径 |
| `get_cache_path(name, version) → Path` | 返回 zip 缓存路径 |
| `clear_cache() → int` | 清理下载缓存，返回删除文件数 |
| `get_stats() → dict` | 统计信息（总数/启用/分类分布） |

---

### 4.2 SkillManager — 安装与生命周期管理

**文件：** `manager.py`

`SkillManager` 是安装管道的入口，协调商店客户端、安全子系统和注册表完成完整的安装流程。支持上下文管理器（`with SkillManager() as m:`）以自动释放 HTTP 客户端资源。

**安装管道（`install()` 方法，10 步）：**

```
Step 1  → 从 Store 获取 Skill 元信息
Step 2  → 获取下载信息（hash + signature）
Step 3  → 下载 .zip 包
Step 4  → 校验 SHA-256 哈希（强制，不可跳过）
Step 5  → 保存到本地缓存
Step 6  → 解压到安装目录
Step 7  → 加载并解析 skill.yaml
Step 8  → Ed25519 签名验证
Step 8.5→ 检查吊销列表（CRL）
Step 8.6→ （主循环外）交互式权限申请
Step 9  → pip 安装 Python 依赖
Step 10 → 写入注册表
```

> **注意：** 步骤 8.6 在 `Progress` 上下文之外执行，因为权限申请需要与用户交互。

**关键行为：**

- `force=False`（默认）时，若已安装同版本则抛出 `SkillManagerError`
- 若用户拒绝敏感权限且拒绝继续，则删除已解压的文件并抛出异常
- 卸载时同时清除内存中的权限记录（`permission_checker.revoke_all_permissions`）

**其他方法：**

| 方法 | 说明 |
|------|------|
| `uninstall(name) → bool` | 删除文件 + 注册表 + 权限 |
| `update(name=None, all_skills=False)` | 单个或全量更新 |
| `enable(name) / disable(name)` | 委托给 Registry |
| `search(query, category)` | 委托给 StoreClient |
| `get_skill_info(name)` | 从商店获取详情 |

---

### 4.3 SkillLoader — 加载与执行引擎

**文件：** `loader.py`

`SkillLoader` 负责在运行时动态加载 Skill Python 模块，并在沙箱中执行指定命令。

**加载机制：**

使用 `importlib.util.spec_from_file_location` 从磁盘加载模块，模块名格式为 `socialhub_skill_{name}`，并注册到 `sys.modules` 中防止重复加载：

```python
spec = importlib.util.spec_from_file_location(
    f"socialhub_skill_{name}",
    entrypoint_path,
)
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)
```

加载后的模块信息缓存在 `_loaded_skills` 字典中，避免重复加载磁盘文件。

**执行机制（`execute_command()`）：**

```
1. 从 PermissionStore 加载持久化权限
2. 创建 PermissionContext（运行时权限上下文）
3. 创建 SandboxManager（基于已授权权限配置各沙箱组件）
4. 在 PermissionContext 内 + SandboxManager 内执行目标函数
```

可通过 `use_sandbox=False` 跳过沙箱（仅用于测试/内部调用）。

**权限检查流程（加载时）：**

1. 从 `PermissionStore` 加载持久化授权
2. 将已授权权限注入 `PermissionChecker`
3. 检查 manifest 声明的权限是否均已授权
4. 过滤掉 `SAFE_PERMISSIONS`（`file:read`、`data:read`、`config:read`）
5. 若有未授权的敏感权限，抛出 `SecurityError`

**其他方法：**

| 方法 | 说明 |
|------|------|
| `load_skill(name) → dict` | 加载并返回 skill info（含 module、manifest、commands） |
| `get_command(skill_name, command_name) → Callable` | 返回可调用函数 |
| `list_commands(skill_name)` | 列出 Skill 所有命令 |
| `list_all_commands()` | 列出所有已启用 Skill 的命令 |
| `unload_skill(name)` | 从缓存和 sys.modules 中移除 |
| `reload_skill(name)` | 先卸载再重新加载 |

**动态 CLI 命令生成：**

`create_skill_typer_commands(loader)` 函数遍历所有已启用 Skill 的命令，动态创建 Typer 命令函数，命令名格式为 `skill_name:command_name`（若命令名不含 `:`）。

---

### 4.4 SkillsStoreClient — 商店 API 客户端

**文件：** `store_client.py`

官方商店地址固定为 `https://skills.socialhub.ai/api/v1`，任何自定义 `base_url` 都会触发 `StoreError`（安全约束）。

**Demo 模式：**

当商店 API 不可达（`httpx.ConnectError` / `httpx.TimeoutException`）时，自动切换至内置的 Demo 数据，避免离线状态下命令完全失败。可通过环境变量 `SOCIALHUB_DEMO_MODE=1` 强制启用。

Demo 内置 8 个模拟 Skill（均标记 `certified: True`）：
`data-export-plus`、`wechat-analytics`、`campaign-optimizer`、`customer-rfm`、`sms-batch-sender`、`data-sync-tool`、`report-generator`、`loyalty-calculator`

> **注意：** Demo 模式下 `download()` 方法直接抛出 `StoreError(503)`，无法实际下载包。

**API 端点映射：**

| 方法 | HTTP | 端点 |
|------|------|------|
| `search(query, category, page, limit)` | GET | `/skills?search=&category=&page=&limit=` |
| `get_skill(name)` | GET | `/skills/{name}` |
| `get_versions(name)` | GET | `/skills/{name}/versions` |
| `download(name, version)` | GET | `/skills/{name}/download` |
| `get_download_info(name, version)` | GET | `/skills/{name}/download-info` |
| `verify_signature(name, signature, hash)` | POST | `/skills/verify` |
| `check_updates(installed)` | POST | `/skills/check-updates` |
| `get_categories()` | GET | `/categories` |
| `get_featured()` | GET | `/skills/featured` |

---

### 4.5 VersionManager — 版本管理

**文件：** `version_manager.py`

实现完整的语义版本（SemVer）支持。

**VersionInfo** 支持全套比较运算符（`<`, `>`, `<=`, `>=`, `==`），并正确处理预发布版本（`1.0.0-beta.1 < 1.0.0`）。

**VersionManager 主要功能：**

| 方法 | 说明 |
|------|------|
| `get_latest_version(skill_name)` | 返回标记为 `is_latest` 的版本，无则取最大版本号 |
| `check_update_available(skill_name, current)` | 返回更新记录或 None |
| `get_upgrade_path(skill_name, from_v, to_v)` | 返回升级路径上所有版本记录（有序） |
| `has_breaking_changes(skill_name, from_v, to_v)` | 主版本号变化即视为破坏性更改 |
| `deprecate_version(skill_name, version, message)` | 标记版本为 deprecated |

版本索引存储于 `~/.socialhub/skills/version_index.json`。

---

## 5. 安全子系统

**文件：** `security.py`

### 5.1 安全模型概述

Skills 安全模型基于四道防线：

```
防线 1：来源控制 ── 只允许官方商店 URL（validate_skill_source）
防线 2：包完整性 ── SHA-256 哈希强制校验（HashVerifier）
防线 3：身份认证 ── Ed25519 数字签名验证（SignatureVerifier）
防线 4：吊销检查 ── CRL 实时查询（RevocationListManager）
           +
运行时防线：权限系统（PermissionContext）+ 沙箱（SandboxManager）
```

---

### 5.2 KeyManager — 公钥管理

管理用于签名验证的官方 Ed25519 公钥。

- 内置 base64 编码的官方公钥（`OFFICIAL_PUBLIC_KEY_B64`）
- 支持密钥轮换（`KEY_UPDATE_URL`）
- 本地缓存路径：`~/.socialhub/security/public_key.pem`
- 提供 `get_key_fingerprint()` 返回 `sha256:...` 格式的指纹

---

### 5.3 HashVerifier — 包完整性校验

支持算法：`sha256`、`sha384`、`sha512`（默认 `sha256`）

关键特性：
- `verify_hash()` 使用**常量时间比较**（`_constant_time_compare`）防止时序攻击
- `verify_multiple_hashes()` 支持多算法并行校验，返回失败的算法列表

---

### 5.4 SignatureVerifier — Ed25519 签名验证

验证 manifest 中 `certification.signature` 字段的 Ed25519 签名。

**签名数据规范（Canonical JSON）：**

```json
{"certificate_id":"...","certified_at":"...","certified_by":"SocialHub.AI","name":"skill-name","v":"1","version":"1.0.0"}
```
- 键名按字母排序，无空格（`sort_keys=True, separators=(",", ":")`）
- UTF-8 编码

**验证步骤：**
1. 检查 `certified_by == "SocialHub.AI"`
2. 检查证书未过期（`expires_at`）
3. 检查 `signature` 字段非空
4. 用官方公钥（Ed25519）验证 base64 解码后的签名

任何步骤失败均抛出 `SecurityError`，并通过 `SecurityAuditLogger` 记录。

---

### 5.5 RevocationListManager — 吊销列表

**CRL 来源：** `https://skills.socialhub.ai/api/v1/security/crl`
**本地缓存：** `~/.socialhub/security/crl.json`
**更新间隔：** 每小时（`timedelta(hours=1)`）

`is_revoked(skill_name, certificate_id)` 同时检查两个吊销集合（按名称 + 按证书 ID），支持离线降级到本地缓存。

---

### 5.6 PermissionChecker — 权限检查

内存态权限管理，跟踪每个 Skill 已被授权的权限集合。

**权限分类：**

| 分类 | 权限 | 风险等级 |
|------|------|------|
| 安全权限（自动放行） | `file:read`、`data:read`、`config:read` | low |
| 敏感权限（需用户确认） | `network:internet`、`data:write`、`config:write`、`execute` | high |
| 中等风险 | `file:write`、`network:local`、`config:write` | medium |

`check_permissions(skill_name, required)` 返回 `(all_granted: bool, missing: list[str])`，SAFE_PERMISSIONS 中的权限自动跳过检查。

---

### 5.7 PermissionStore — 权限持久化存储

**存储路径：** `~/.socialhub/security/permissions.json`

权限在安装时由用户授权后写入 `permissions.json`，跨 CLI 会话持久有效。

**文件格式：**
```json
{
  "version": "1.0",
  "updated_at": "2026-03-21T10:00:00",
  "skills": {
    "report-generator": {
      "permissions": ["file:write", "file:read"],
      "granted_at": "2026-03-21T10:00:00",
      "version": "3.1.0"
    }
  }
}
```

---

### 5.8 PermissionPrompter — 交互式权限请求

在安装时向用户展示权限请求面板，逐条获取敏感权限的授权。

**用户界面特性：**
- 富文本表格展示权限名称、描述、风险等级
- 风险等级用颜色和图标区分（绿色 ●/黄色 ▲/红色 ◆）
- 安全权限（`SAFE_PERMISSIONS`）自动授权，不打扰用户
- 支持 `auto_approve_safe=True`（默认）
- `KeyboardInterrupt` 取消整个授权流程

`request_single_permission()` 用于运行时动态申请单个权限（当 `PermissionContext` 配置了 `prompt_if_missing=True` 时触发）。

---

### 5.9 PermissionContext — 运行时权限上下文

作为上下文管理器在 `SkillLoader.execute_command()` 中包裹 Skill 执行：

```python
with perm_context:
    with sandbox:
        return func(*args, **kwargs)
```

`check_permission(permission, operation, prompt_if_missing)` 按以下顺序判断：
1. 是否在 `SAFE_PERMISSIONS` 中 → 直接放行
2. 是否在内存已授权集合中 → 放行
3. 是否在 `PermissionStore` 持久化记录中 → 放行并同步到内存
4. `prompt_if_missing=True` 时向用户实时申请
5. 全部不符合 → 记录安全违规，返回 `False`

`require_permission()` 在权限不足时抛出 `PermissionDeniedError`。

---

### 5.10 SecurityAuditLogger — 安全审计日志

**日志路径：** `~/.socialhub/logs/security_audit.log`

格式：`YYYY-MM-DD HH:MM:SS | LEVEL | EVENT_TYPE | skill=... | ...`

记录的事件类型：

| 方法 | 事件 | 级别 |
|------|------|------|
| `log_signature_verified` | `SIGNATURE_VERIFIED` | INFO |
| `log_signature_failed` | `SIGNATURE_FAILED` | WARNING |
| `log_permission_granted` | `PERMISSION_GRANTED` | INFO |
| `log_permission_denied` | `PERMISSION_DENIED` | WARNING |
| `log_security_violation` | `SECURITY_VIOLATION` | ERROR |
| `log_install_blocked` | `INSTALL_BLOCKED` | WARNING |

---

### 5.11 SecurityEventReporter — 事件上报

**上报地址：** `https://skills.socialhub.ai/api/v1/security/events`
**本地队列：** `~/.socialhub/security/event_queue.json`（最多 100 条）

事件会先写本地队列，再尝试立即上报；网络不可达时保留在队列中，下次触发时重试。

支持的事件类型：`signature_failure`、`permission_violation`、`sandbox_violation`、`revoked_skill_attempt`

---

### 5.12 SkillHealthChecker — 健康检查

对已安装的 Skill 执行 5 项检查并汇总为健康状态（`healthy` / `warning` / `critical`）：

| 检查项 | 说明 | 临界条件 |
|--------|------|----------|
| `certificate` | 证书有效期 | 已过期 = critical；30 天内到期 = warning |
| `revocation` | CRL 吊销状态 | 被吊销 = critical |
| `integrity` | 文件完整性 | manifest 或 entrypoint 缺失 = critical |
| `enabled` | 启用状态 | 禁用 = passed（不影响健康） |
| `updates` | 更新可用性 | 有更新 = info（不影响健康） |

---

## 6. 沙箱子系统

**目录：** `sandbox/`

沙箱采用 **Python monkey-patching** 技术，在执行期间替换标准库中的敏感函数，执行完毕后恢复原始函数。这是一种**进程级**隔离，而非操作系统级沙箱。

### 6.1 SandboxManager — 统一沙箱管理器

**文件：** `sandbox/manager.py`

权限到沙箱组件的映射：

```python
PERMISSION_MAP = {
    "file:read":        ("filesystem", "allow_read"),
    "file:write":       ("filesystem", "allow_write"),
    "network:local":    ("network",    "allow_local"),
    "network:internet": ("network",    "allow_internet"),
    "execute":          ("execute",    "allow_execute"),
}
```

**激活顺序（有意为之）：**
```
激活：execute → network → filesystem   （底层优先）
停用：filesystem → network → execute   （逆序）
```

`__exit__` 在捕获到 `FileAccessDeniedError`、`NetworkAccessDeniedError`、`CommandExecutionDeniedError` 时记录审计日志，但**不吞掉异常**（返回 `False`），确保违规行为向上传播。

---

### 6.2 FileSystemSandbox — 文件系统隔离

**文件：** `sandbox/filesystem.py`

**机制：** 替换 `builtins.open`，拦截所有文件打开操作。

**默认允许路径：**
- `~/.socialhub/skills/sandbox/<skill_name>/`（Skill 的专属沙箱目录，总是可写）
- `~/.socialhub/skills/installed/<skill_name>/`（安装目录，只读）
- `~/Documents/`、`~/Downloads/`（若存在）

**写入检测：** 检查 `mode` 中是否含有 `w`、`a`、`x`、`+`

**路径验证：** 使用 `Path.resolve()` 解析符号链接后再与允许路径比较，防止路径遍历攻击。

文件描述符（`int` 类型）直接放行，不做检查。

---

### 6.3 NetworkSandbox — 网络隔离

**文件：** `sandbox/network.py`

**机制：** 替换 `socket.socket` 为 `GuardedSocket` 子类，拦截 `connect()` 和 `connect_ex()`。

**本地地址识别：**
- 精确匹配：`localhost`、`127.0.0.1`、`::1`、`0.0.0.0`
- 前缀匹配：`192.168.*`、`10.*`、`172.16-31.*`
- IPv6 本地：`fe80:`、`fc00:`

**判断优先级：**
1. 端口白名单（若设置了 `allowed_ports`，不在其中的端口全部拒绝）
2. 精确主机白名单（`allowed_hosts`）
3. 是否本地地址 → 检查 `allow_local`
4. 否则 → 检查 `allow_internet`

---

### 6.4 ExecuteSandbox — 命令执行隔离

**文件：** `sandbox/execute.py`

**拦截范围：**
- `subprocess.run`
- `subprocess.Popen`
- `subprocess.call`
- `subprocess.check_call`
- `subprocess.check_output`
- `os.system`

**永久禁止命令（DANGEROUS_COMMANDS）：**
`rm`、`format`、`shutdown`、`sudo`、`iptables`、`apt` 等 30+ 个危险命令

**永久允许命令（SAFE_COMMANDS）：**
`echo`、`cat`、`ls`、`grep`、`find`、`awk` 等基础工具

**判断逻辑：**
```
if not allow_execute          → 拒绝（执行权限未授予）
if cmd in blocked_commands    → 拒绝（显式黑名单）
if cmd in DANGEROUS_COMMANDS  → 拒绝（系统黑名单）
if allowed_commands is set:
    if cmd in allowed_commands or cmd in SAFE_COMMANDS → 允许
    else                      → 拒绝（不在白名单）
else:
    → 允许（非危险命令均放行）
```

命令名从参数中提取（`Path(args[0]).stem.lower()`），忽略路径前缀。

---

## 7. Skill 包格式规范

Skill 包是标准 `.zip` 文件，解压后必须包含以下结构：

```
<skill-name>/
├── skill.yaml          ← 必须，Manifest 文件
├── main.py             ← 必须（或 entrypoint 指定的文件）
├── certification.json  ← 推荐，认证信息备份
└── ...                 ← 其他资源文件
```

### skill.yaml 最小示例

```yaml
name: "my-skill"
version: "1.0.0"
display_name: "My Skill"
description: "A sample skill"
author: "Your Name"
license: "MIT"
category: "utility"
compatibility:
  cli_version: ">=0.1.0"
  python_version: ">=3.10"
permissions:
  - file:read
  - file:write
dependencies:
  python:
    - requests>=2.28.0
entrypoint: "main.py"
commands:
  - name: "run"
    description: "Run the skill"
    function: "main_function"
    arguments:
      - name: "input"
        type: "string"
        required: true
        description: "Input parameter"
certification:
  certified_at: "2024-01-01T00:00:00"
  certified_by: "SocialHub.AI"
  signature: "<base64-encoded-ed25519-signature>"
  certificate_id: "SKILL-XXX-001"
  expires_at: "2025-01-01T00:00:00"
```

### main.py 最小示例

```python
def main_function(input: str, **kwargs) -> str:
    """Skill entry point."""
    return f"Processed: {input}"
```

函数签名中的参数名须与 `skill.yaml` 中 `commands[].arguments[].name` 一致。

---

## 8. 内置 Skill：report-generator

**路径：** `socialhub/cli/skills/store/report-generator/`
**版本：** 3.1.0
**证书 ID：** SKILL-RPT-003

这是唯一随代码仓库一同分发的内置 Skill，其他 Skill 需从商店下载。

**注意：** 该 Skill 的证书 `expires_at: "2025-03-20T00:00:00"` 已过期，`SignatureVerifier` 在验证时会抛出 `SecurityError`。在正式安装流程中，此 Skill 无法通过安全检查；`analytics report` 命令通过绕过安装流程（直接 `sys.path.insert` + `importlib`）来使用它。

**提供的命令：**

| 命令 | 函数 | 说明 |
|------|------|------|
| `generate` | `generate_consulting_report` | 通用咨询分析报告（支持多种框架） |
| `pestel` | `generate_pestel_report` | PESTEL 宏观环境分析 |
| `porter` | `generate_porter_report` | 波特五力分析 |
| `swot` | `generate_swot_report` | SWOT 竞争分析 |
| `valuechain` | `generate_valuechain_report` | 价值链分析 |
| `action` | `generate_action_report` | 5W2H 行动计划 |
| `data` | `generate_data_report` | 数据驱动报告（接受 JSON 数据） |
| `demo` | `generate_demo_report` | 展示所有框架的 Demo 报告 |
| `convert` | `convert_report` | 将已有 Markdown 转换为 HTML/PDF |

**所需权限：** `file:write`、`file:read`、`config:read`、`network:local`

---

## 9. 完整执行流程

### 9.1 安装流程

```
用户执行: sh skill install report-generator
        │
        ▼
SkillManager.install("report-generator")
  │
  ├─► [Step 1]  StoreClient.get_skill("report-generator")
  │              → 返回 SkillDetail（或 Demo 数据）
  │
  ├─► [Step 2]  StoreClient.get_download_info("report-generator", version)
  │              → 返回 { "hash": "sha256:...", "signature": "..." }
  │
  ├─► [Step 3]  StoreClient.download("report-generator", version)
  │              → 返回 bytes（.zip 内容）
  │
  ├─► [Step 4]  HashVerifier.verify_hash(content, expected_hash, "sha256")
  │              → 失败: SecurityError + 审计日志 INSTALL_BLOCKED
  │
  ├─► [Step 5]  写入 ~/.socialhub/skills/cache/report-generator-3.1.0.zip
  │
  ├─► [Step 6]  zipfile.ZipFile.extractall →
  │              ~/.socialhub/skills/installed/report-generator/
  │
  ├─► [Step 7]  加载并解析 skill.yaml → SkillManifest
  │
  ├─► [Step 8]  SignatureVerifier.verify_manifest_signature(manifest)
  │              → 检查 certified_by / expires_at / signature
  │              → Ed25519 公钥验证
  │              → 失败: 删除 install_path + 抛出 SkillManagerError
  │
  ├─► [Step 8.5] RevocationListManager.is_revoked(name, cert_id)
  │              → 失败: 删除 install_path + 抛出 SecurityError
  │
  ├─► [Step 8.6] PermissionPrompter.request_permissions(...)
  │              → 安全权限自动授权
  │              → 敏感权限逐条提示用户
  │              → 用户拒绝 + 无法继续: 删除 install_path + SkillManagerError
  │              → PermissionStore.grant_permissions(approved_perms)
  │
  ├─► [Step 9]  pip install <dependencies>
  │
  └─► [Step 10] SkillRegistry.register_skill(InstalledSkill(...))
                → 写入 registry.json
                → 返回 InstalledSkill
```

### 9.2 执行流程

```
用户执行: sh skill run report-generator generate --topic="分析" --output=out.md
        │
        ▼
commands/skills.py → SkillLoader.execute_command("report-generator", "generate", ...)
  │
  ├─► SkillLoader.load_skill("report-generator")
  │    ├─ SkillRegistry.get_installed("report-generator")
  │    ├─ 检查 enabled=True
  │    ├─ 加载 skill.yaml → SkillManifest
  │    ├─ PermissionStore.get_permissions() → 从磁盘加载已授权权限
  │    ├─ PermissionChecker.check_permissions() → 验证权限完备性
  │    └─ importlib 加载 main.py → Module
  │
  ├─► SkillLoader.get_command("report-generator", "generate")
  │    → manifest.commands 中查找 name="generate"
  │    → getattr(module, "generate_consulting_report")
  │
  ├─► 创建 PermissionContext(skill_name, granted_permissions, permission_store)
  │
  ├─► 创建 SandboxManager(skill_name, granted_permissions)
  │    ├─ FileSystemSandbox(allow_read=True, allow_write=True)
  │    ├─ NetworkSandbox(allow_local=True, allow_internet=False)
  │    └─ ExecuteSandbox(allow_execute=False)
  │
  └─► with perm_context:
        with sandbox:            ← 激活 execute/network/filesystem 拦截
          generate_consulting_report(topic="分析", output="out.md")
          │
          └─ [沙箱生效期间]
             ├─ open("out.md", "w")  → guarded_open → 路径检查 → 允许/拒绝
             ├─ socket.connect(...)  → GuardedSocket → 主机检查 → 允许/拒绝
             └─ subprocess.run(...)  → guarded_run  → 命令检查 → 允许/拒绝
        [沙箱停用，恢复原始函数]
```

---

## 10. 文件系统布局

```
~/.socialhub/
├── config.json                    ← CLI 主配置
├── skills/
│   ├── registry.json              ← 已安装 Skill 注册表
│   ├── version_index.json         ← 版本索引
│   ├── installed/
│   │   └── <skill-name>/
│   │       ├── skill.yaml
│   │       ├── main.py
│   │       └── certification.json
│   ├── cache/
│   │   └── <name>-<version>.zip   ← 下载缓存
│   └── sandbox/
│       └── <skill-name>/          ← Skill 的专属读写目录
├── security/
│   ├── public_key.pem             ← 官方公钥缓存（可选）
│   ├── crl.json                   ← 证书吊销列表缓存
│   ├── permissions.json           ← 权限授权记录
│   └── event_queue.json           ← 待上报安全事件队列
└── logs/
    └── security_audit.log         ← 安全审计日志
```

---

## 11. 错误类型一览

| 异常类 | 所在模块 | 触发场景 |
|--------|---------|---------|
| `SecurityError` | `security.py` | 签名验证失败、权限缺失、证书过期、Skill 已吊销 |
| `PermissionDeniedError` | `security.py` | 运行时 `require_permission()` 权限不足（`SecurityError` 子类） |
| `SkillManagerError` | `manager.py` | 安装/卸载/更新流程失败（非安全原因） |
| `SkillLoadError` | `loader.py` | Skill 未安装、已禁用、manifest 缺失、模块加载失败 |
| `StoreError` | `store_client.py` | 商店 API 错误、自定义 URL 拒绝、Demo 模式下载拒绝 |
| `SandboxViolationError` | `sandbox/manager.py` | 沙箱违规基类（`PermissionError` 子类） |
| `FileAccessDeniedError` | `sandbox/filesystem.py` | 访问未授权路径 |
| `NetworkAccessDeniedError` | `sandbox/network.py` | 连接未授权主机 |
| `CommandExecutionDeniedError` | `sandbox/execute.py` | 执行被拦截的命令 |

---

## 12. 设计局限与已知问题

### 沙箱局限性

1. **进程级隔离，非系统级隔离。** 沙箱通过 monkey-patching 实现，Skill 代码仍在同一 Python 进程中运行，理论上可以通过 ctypes、cffi 等绕过。

2. **文件系统沙箱仅覆盖 `open()`。** 通过 `os.rename`、`shutil.copy`、`pathlib.Path.write_text` 等 API 的文件操作不受保护。

3. **网络沙箱仅覆盖 `socket.socket`。** 使用 `urllib`、`httpx`、`requests` 等高层库会经过 `socket.socket`，通常可被拦截；但使用 C 扩展的底层网络调用可绕过。

4. **沙箱非线程安全。** `activate()` / `deactivate()` 直接替换全局函数，多线程并发加载 Skill 时可能产生竞争条件。

### 内置 Skill 认证过期

内置的 `report-generator` 证书 `expires_at` 为 `2025-03-20`，已过期。通过正式安装流程无法使用，`analytics report` 命令通过直接 `sys.path.insert` 绕过了安全检查。长期来看应更新证书或将内置 Skill 走豁免路径处理。

### Demo 模式安全性

`SOCIALHUB_DEMO_MODE=1` 可在离线状态下浏览 Skill 信息，但下载会被阻止。Demo 数据中所有 Skill 均标记 `certified: True`，这是模拟数据，不代表真实认证状态。

### 权限系统缺少运行时强制

`PermissionContext` 目前仅提供 `check_permission()` / `require_permission()` 供 Skill 主动调用；沙箱层（`SandboxManager`）提供被动拦截。两者是**独立**机制，未集成。Skill 代码若不主动调用 `require_permission()`，则运行时权限上下文不会产生任何约束（约束来自沙箱）。

---

*文档由 Claude Code 根据源码自动生成*
