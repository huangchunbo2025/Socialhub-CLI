# SocialHub.AI Skills Store 设计方案

## 1. 平台概述

SocialHub.AI Skills Store 是官方认证的技能市场平台，为 CLI 工具提供可扩展的技能插件系统。

### 核心特性
- **官方认证**: 所有技能必须通过官方审核认证
- **安全隔离**: CLI 仅允许安装来自官方 Store 的技能
- **版本管理**: 支持技能版本控制和更新
- **依赖管理**: 自动处理技能依赖关系

## 2. 系统架构

```
┌─────────────────────────────────────────────────────────────────┐
│                    SocialHub.AI Skills Store                     │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐             │
│  │   Web 控制台  │  │  开发者门户  │  │   审核系统   │             │
│  │  (用户浏览)   │  │  (提交技能)  │  │  (认证管理)  │             │
│  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘             │
│         │                │                │                      │
│         └────────────────┼────────────────┘                      │
│                          │                                       │
│                   ┌──────▼──────┐                               │
│                   │   API 网关   │                               │
│                   │  (认证/限流)  │                               │
│                   └──────┬──────┘                               │
│                          │                                       │
│         ┌────────────────┼────────────────┐                     │
│         │                │                │                      │
│  ┌──────▼──────┐  ┌──────▼──────┐  ┌──────▼──────┐             │
│  │  技能注册服务  │  │  技能存储服务  │  │  认证签名服务  │             │
│  │  (元数据)     │  │  (包存储)     │  │  (安全验证)   │             │
│  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘             │
│         │                │                │                      │
│         └────────────────┼────────────────┘                      │
│                          │                                       │
│                   ┌──────▼──────┐                               │
│                   │   数据存储    │                               │
│                   │ (PostgreSQL) │                               │
│                   └─────────────┘                               │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
                              │
                              │ HTTPS + 签名验证
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                     SocialHub CLI                                │
├─────────────────────────────────────────────────────────────────┤
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐             │
│  │ Skills 管理器 │  │  签名验证器  │  │  技能运行时   │             │
│  │  (安装/更新)  │  │  (安全检查)  │  │  (执行技能)   │             │
│  └─────────────┘  └─────────────┘  └─────────────┘             │
└─────────────────────────────────────────────────────────────────┘
```

## 3. 技能规范 (Skill Specification)

### 3.1 技能清单文件 (skill.yaml)

```yaml
# 技能元数据
name: "data-export-plus"
version: "1.2.0"
display_name: "高级数据导出"
description: "支持更多格式的数据导出，包括 Parquet、Feather 等"
author: "SocialHub Official"
license: "MIT"
homepage: "https://skills.socialhub.ai/data-export-plus"

# 分类和标签
category: "data"  # data, marketing, analytics, integration, utility
tags:
  - export
  - parquet
  - data-format

# 兼容性
compatibility:
  cli_version: ">=0.1.0"
  python_version: ">=3.10"

# 依赖
dependencies:
  python:
    - pyarrow>=14.0.0
    - fastparquet>=2023.0.0
  skills: []  # 依赖的其他技能

# 权限声明
permissions:
  - file:write      # 文件写入
  - network:none    # 无网络访问
  - data:read       # 读取客户数据

# 入口点
entrypoint: "main.py"
commands:
  - name: "export-parquet"
    description: "导出为 Parquet 格式"
    function: "export_parquet"
  - name: "export-feather"
    description: "导出为 Feather 格式"
    function: "export_feather"

# 认证信息 (由平台签名)
certification:
  certified_at: "2024-03-15T10:00:00Z"
  certified_by: "SocialHub.AI"
  signature: "base64_encoded_signature..."
  certificate_id: "CERT-2024-00123"
```

### 3.2 技能目录结构

```
skill-name/
├── skill.yaml          # 技能清单
├── main.py             # 入口文件
├── README.md           # 说明文档
├── LICENSE             # 许可证
├── requirements.txt    # Python 依赖
├── src/                # 源代码
│   ├── __init__.py
│   └── ...
├── tests/              # 测试文件
│   └── test_main.py
└── assets/             # 资源文件
    └── icon.png
```

## 4. API 设计

### 4.1 公开 API (CLI 使用)

```
Base URL: https://skills.socialhub.ai/api/v1

# 技能列表
GET /skills
  ?category=data
  ?search=export
  ?page=1&limit=20

# 技能详情
GET /skills/{skill_name}

# 技能版本列表
GET /skills/{skill_name}/versions

# 下载技能包
GET /skills/{skill_name}/download
  ?version=1.2.0

# 验证签名
POST /skills/verify
  Body: { "skill_name": "...", "signature": "...", "hash": "..." }

# 检查更新
POST /skills/check-updates
  Body: { "installed": [{"name": "...", "version": "..."}] }
```

### 4.2 开发者 API (需认证)

```
# 提交技能
POST /developer/skills
  Body: multipart/form-data (skill package)

# 更新技能
PUT /developer/skills/{skill_name}

# 查看审核状态
GET /developer/skills/{skill_name}/review-status

# 发布版本
POST /developer/skills/{skill_name}/publish
```

## 5. 安全机制

### 5.1 签名验证流程

```
1. 开发者提交技能包
2. 平台审核代码安全性
3. 审核通过后，平台使用私钥签名
4. CLI 下载技能时验证签名
5. 安装前校验文件哈希

签名算法: Ed25519
哈希算法: SHA-256
```

### 5.2 权限模型

```python
class SkillPermission(Enum):
    FILE_READ = "file:read"       # 读取文件
    FILE_WRITE = "file:write"     # 写入文件
    NETWORK_LOCAL = "network:local"   # 本地网络
    NETWORK_INTERNET = "network:internet"  # 互联网访问
    DATA_READ = "data:read"       # 读取客户数据
    DATA_WRITE = "data:write"     # 写入客户数据
    CONFIG_READ = "config:read"   # 读取配置
    CONFIG_WRITE = "config:write" # 写入配置
    EXECUTE = "execute"           # 执行外部命令
```

### 5.3 沙箱执行

- 技能在受限环境中执行
- 网络访问需要明确声明
- 文件操作限制在工作目录
- 敏感 API 调用需要用户确认

## 6. 审核流程

```
┌─────────┐     ┌─────────┐     ┌─────────┐     ┌─────────┐
│  提交   │ ──► │ 自动检测 │ ──► │ 人工审核 │ ──► │  签名   │
│  技能   │     │ (安全扫描)│     │ (代码审查)│     │  发布   │
└─────────┘     └─────────┘     └─────────┘     └─────────┘
                    │                │
                    ▼                ▼
              ┌─────────┐      ┌─────────┐
              │  拒绝   │      │  拒绝   │
              │ (安全问题)│      │ (质量问题)│
              └─────────┘      └─────────┘
```

### 审核标准

1. **安全性**
   - 无恶意代码
   - 无数据泄露风险
   - 权限声明准确

2. **质量**
   - 代码规范
   - 有测试覆盖
   - 文档完整

3. **合规性**
   - 许可证合规
   - 无侵权内容

## 7. 数据模型

### 7.1 技能表 (skills)

| 字段 | 类型 | 说明 |
|------|------|------|
| id | UUID | 主键 |
| name | VARCHAR(100) | 技能名称 (唯一) |
| display_name | VARCHAR(200) | 显示名称 |
| description | TEXT | 描述 |
| category | VARCHAR(50) | 分类 |
| author_id | UUID | 作者 ID |
| downloads | INTEGER | 下载次数 |
| rating | DECIMAL(2,1) | 评分 |
| status | ENUM | draft/review/published/suspended |
| created_at | TIMESTAMP | 创建时间 |
| updated_at | TIMESTAMP | 更新时间 |

### 7.2 版本表 (skill_versions)

| 字段 | 类型 | 说明 |
|------|------|------|
| id | UUID | 主键 |
| skill_id | UUID | 技能 ID |
| version | VARCHAR(20) | 版本号 |
| changelog | TEXT | 更新日志 |
| package_url | VARCHAR(500) | 包下载地址 |
| package_hash | VARCHAR(64) | SHA-256 哈希 |
| signature | TEXT | 数字签名 |
| cli_version_min | VARCHAR(20) | 最低 CLI 版本 |
| status | ENUM | review/published/deprecated |
| published_at | TIMESTAMP | 发布时间 |

### 7.3 认证表 (certifications)

| 字段 | 类型 | 说明 |
|------|------|------|
| id | UUID | 主键 |
| version_id | UUID | 版本 ID |
| certificate_id | VARCHAR(50) | 证书编号 |
| reviewer_id | UUID | 审核员 ID |
| review_notes | TEXT | 审核备注 |
| permissions | JSONB | 权限列表 |
| certified_at | TIMESTAMP | 认证时间 |
| expires_at | TIMESTAMP | 过期时间 |

## 8. CLI 集成

### 8.1 技能管理命令

```bash
# 浏览技能商店
sh skills browse
sh skills browse --category=data
sh skills search "export"

# 查看技能详情
sh skills info data-export-plus

# 安装技能
sh skills install data-export-plus
sh skills install data-export-plus@1.2.0

# 更新技能
sh skills update data-export-plus
sh skills update --all

# 卸载技能
sh skills uninstall data-export-plus

# 列出已安装技能
sh skills list

# 使用技能命令
sh export-parquet customers --output=data.parquet
```

### 8.2 本地技能存储

```
~/.socialhub/
├── config.json
└── skills/
    ├── registry.json       # 已安装技能注册表
    ├── cache/              # 下载缓存
    └── installed/          # 已安装技能
        ├── data-export-plus/
        │   ├── skill.yaml
        │   ├── main.py
        │   └── ...
        └── ...
```

## 9. 技术栈建议

### 后端服务
- **框架**: FastAPI (Python) 或 Gin (Go)
- **数据库**: PostgreSQL
- **缓存**: Redis
- **存储**: MinIO / S3
- **消息队列**: RabbitMQ (审核流程)

### 前端
- **Web 控制台**: Next.js + TypeScript
- **UI 组件**: Tailwind CSS + shadcn/ui

### 基础设施
- **容器**: Docker + Kubernetes
- **CI/CD**: GitHub Actions
- **监控**: Prometheus + Grafana

## 10. 里程碑计划

### Phase 1: MVP (4周)
- [ ] 技能规范定义
- [ ] CLI 技能管理器
- [ ] 基础 API 服务
- [ ] 签名验证机制

### Phase 2: 平台上线 (4周)
- [ ] Web 控制台
- [ ] 开发者门户
- [ ] 审核工作流
- [ ] 官方技能发布

### Phase 3: 生态建设 (持续)
- [ ] 开发者文档
- [ ] SDK 和模板
- [ ] 社区贡献指南
- [ ] 激励计划
