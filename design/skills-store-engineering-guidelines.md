# Skills Store MVP 工程规范

## 1. 文档目标

本文档定义 Skills Store MVP 在开发、测试、代码质量、技术选型和安全实现上的统一规范，用于约束后续所有实现工作。

本规范适用于：

- 后端服务实现
- 数据库模型与迁移
- API 开发
- 文件上传与扫描
- 签名、证书、CRL 能力
- 测试与交付

相关文档：

- [`CODEX.md`](C:\Users\86185\Socialhub-CLI\CODEX.md)
- [skills-store-api-spec.md](C:\Users\86185\Socialhub-CLI\docs\skills-store-api-spec.md)
- [skills-store-db-design.md](C:\Users\86185\Socialhub-CLI\docs\skills-store-db-design.md)
- [skills-store-technical-design.md](C:\Users\86185\Socialhub-CLI\docs\skills-store-technical-design.md)
- [skills-store-implementation-plan.md](C:\Users\86185\Socialhub-CLI\docs\skills-store-implementation-plan.md)

如文档冲突，优先级如下：

1. [`CODEX.md`](C:\Users\86185\Socialhub-CLI\CODEX.md)
2. API / DB / Technical Design
3. 本规范

## 2. 项目定位

当前项目是轻量级 MVP，规模预期如下：

- 技能总量 `<= 500`
- 用户总量 `<= 1000`
- 低并发，后台审核和 CLI 下载为主

因此工程目标是：

- 快速可交付
- 结构清晰
- 容易维护
- 与 CLI 契约稳定兼容

明确不允许的过度设计：

- 分库分表
- 多服务拆分
- 独立搜索引擎
- 消息队列平台
- 复杂缓存集群
- 与当前规模无关的抽象层堆叠

## 3. 技术栈规范

### 3.1 后端基础栈

固定技术栈如下：

- Python `3.11`
- FastAPI
- SQLAlchemy `2.x` Async
- PostgreSQL `15`
- Alembic
- `asyncpg`
- `pydantic-settings`
- `passlib` + `bcrypt`
- `python-jose`
- `cryptography` Ed25519
- `pytest`
- `httpx`
- Docker Compose

### 3.2 依赖约束

- 新增依赖必须有明确用途
- 优先选择成熟、主流、维护稳定的库
- 能用现有依赖解决的问题，不新增新库
- 不允许为了少量便利引入重量级框架

### 3.3 存储约束

- 数据库固定使用 PostgreSQL
- 包文件存储优先本地磁盘
- 后续如需切换对象存储，必须保持应用层接口不变

## 4. 代码结构规范

推荐结构：

```text
skills-store/
├── docker-compose.yml
├── Dockerfile
├── pyproject.toml
├── alembic.ini
├── alembic/
└── backend/
    └── app/
        ├── main.py
        ├── config.py
        ├── database.py
        ├── auth/
        ├── routers/
        ├── models/
        ├── schemas/
        ├── services/
        └── utils/
```

结构原则：

- 路由层只负责参数接收、鉴权和调用服务
- 业务逻辑集中在 `services/`
- ORM 模型只放数据结构和关系
- `schemas/` 只定义输入输出模型
- 公共工具放在 `utils/`
- 不允许把复杂业务逻辑直接写在 router 中

## 5. 编码规范

### 5.1 通用要求

- 代码必须清晰、直接、可维护
- 优先写可读代码，不写炫技代码
- 不为了未来可能需求做过度抽象
- 函数职责要单一
- 模块边界要清楚

### 5.2 命名规范

- 类名使用 `PascalCase`
- 函数、变量、文件名使用 `snake_case`
- 常量使用 `UPPER_SNAKE_CASE`
- API 路径使用短横线或稳定的 REST 风格命名，保持统一
- 数据库字段统一使用 `snake_case`

### 5.3 注释规范

- 注释只解释复杂原因，不解释显而易见的代码
- 避免无意义注释
- 复杂状态流转、签名载荷、兼容性约束可以写简短注释

### 5.4 异常处理

- 不允许裸 `except`
- 所有业务异常需要映射到明确的 HTTP 错误响应
- 不把内部 traceback 暴露给客户端
- 错误码必须稳定，不随实现细节变化

## 6. API 开发规范

### 6.1 基本原则

- 实现必须以 [skills-store-api-spec.md](C:\Users\86185\Socialhub-CLI\docs\skills-store-api-spec.md) 为准
- 任何偏离 CLI 契约的修改必须先更新文档并明确评估兼容性

### 6.2 响应格式

- 成功返回统一使用 `data`
- 列表返回带 `pagination`
- 错误返回统一使用 `error.code` 和 `error.message`

### 6.3 分页规范

- 当前统一使用 `page` + `limit`
- 不允许同一项目里混用 `page_size`

### 6.4 兼容性约束

以下点必须保持稳定：

- `search`
- `limit`
- `/skills/{name}/download`
- `/skills/{name}/download-info`
- `/skills/featured`
- `/categories`
- `verify` 的 `skill_name`
- `/crl`

## 7. 数据库与迁移规范

### 7.1 模型原则

- 模型字段必须与数据库设计文档一致
- 核心查询字段不能塞进 `JSONB`
- 状态字段必须使用 `ENUM`
- 轻量级规模下统一使用 `BIGSERIAL`

### 7.2 迁移原则

- 每次 schema 变更必须有 Alembic 迁移
- 不允许手工修改线上表结构而不补迁移
- 迁移脚本必须可重复执行
- 迁移必须考虑回滚能力

### 7.3 数据约束

- 邮箱唯一
- 技能名称唯一
- 同一技能下版本号唯一
- 每个版本最多一张证书
- 外键和唯一约束必须落实到数据库层

## 8. 文件上传与存储规范

### 8.1 上传限制

- 当前仅允许上传 zip 包
- 包大小必须有明确上限，建议初始值 `20MB`
- 文件名不能直接作为最终存储路径依据

### 8.2 存储原则

- 存储路径必须由服务端生成
- 存储前必须校验扩展名和 MIME 类型
- 存储后必须计算哈希值
- 下载前必须校验版本状态

### 8.3 清理要求

- 驳回或失败的临时文件应可清理
- 不允许长期堆积未引用文件

## 9. 安全规范

### 9.1 认证与授权

- 所有受保护接口必须走 JWT 鉴权
- 当前只允许 `developer` 和 `store_admin`
- 权限判断必须在服务端完成，不能依赖前端或客户端

### 9.2 密码安全

- 密码必须使用 `bcrypt` 哈希
- 不允许明文存储密码
- 日志中不得记录原始密码
- 密码最小长度建议 `8`

### 9.3 Token 安全

- access token 必须设置过期时间
- token secret 不允许硬编码
- secret 只能来自环境变量或安全配置

### 9.4 文件安全

- 上传包必须校验类型和大小
- 必须做 manifest 结构校验
- 必须做基础敏感文件检查
- 不允许直接信任客户端传入的 manifest 内容

### 9.5 签名与密钥安全

- 证书签名统一使用 Ed25519
- 私钥不能写进仓库
- 私钥路径通过环境变量配置
- 公钥标识 `public_key_id` 必须稳定
- 吊销记录必须可追溯

### 9.6 日志与脱敏

- 日志不得输出密码、token、私钥、完整签名原文
- 邮箱、哈希、签名等敏感字段如需记录，应做截断或脱敏
- 生产日志中不打印完整异常堆栈给客户端

## 10. 质量要求

### 10.1 测试要求

必须覆盖以下测试类型：

- 单元测试
- 集成测试
- CLI 兼容性测试
- 错误路径测试

核心链路必须有测试：

- 注册 / 登录
- 创建技能
- 上传版本
- 扫描
- 审核通过 / 驳回
- 签发证书
- 下载
- 验签
- 吊销
- CRL 查询

### 10.2 覆盖要求

当前 MVP 阶段建议：

- 核心服务层覆盖率不低于 `80%`
- 路由层覆盖关键接口
- 签名、扫描、状态流转必须重点覆盖

### 10.3 静态质量检查

建议至少执行：

- 格式化
- lint
- 基础类型检查
- 测试

推荐工具：

- `ruff`
- `pytest`
- `mypy` 或等价工具

## 11. 代码评审规范

每次 Code Review 至少检查以下内容：

- 是否符合 API 规格
- 是否破坏 CLI 契约
- 是否有权限绕过风险
- 是否有未处理异常路径
- 是否有无迁移的 schema 变更
- 是否有测试缺失
- 是否引入了不必要复杂度

重点高风险区域：

- 下载接口
- 验签接口
- CRL
- 上传与扫描
- 审核状态流转
- 签名载荷生成

## 12. 日志与可观测性规范

### 12.1 日志原则

- 日志以排障为目标，不做信息堆积
- 每个关键业务动作都应有结构化日志

建议记录：

- 注册
- 登录成功和失败
- 上传版本
- 扫描结果
- 审核通过和驳回
- 证书签发
- 证书吊销
- 下载请求

### 12.2 日志字段建议

- `request_id`
- `user_id`
- `role`
- `skill_name`
- `version`
- `action`
- `result`

## 13. 配置管理规范

- 所有环境差异通过环境变量控制
- 不允许把密钥、数据库密码写死在代码中
- `.env.example` 必须保持最新
- 新增配置项时必须同步更新文档

## 14. 文档维护规范

- 接口变更必须先更新 API 规格文档
- 表结构变更必须更新数据库设计文档
- 架构调整必须更新技术设计文档
- 实现顺序或阶段变化必须更新实现计划

## 15. 完成定义

一个功能被认为“完成”，至少满足以下条件：

1. 代码已实现
2. 测试已补齐或完成基础验证
3. 文档已同步
4. 没有破坏 CLI 契约
5. 没有明显安全缺口

## 16. 当前执行建议

基于当前规范，后续开发应按以下顺序进行：

1. 项目骨架
2. 模型与迁移
3. 认证
4. 公开接口
5. 开发者上传
6. 扫描
7. 审核
8. 签名与下载
9. 吊销与 CRL
10. 测试与收尾
