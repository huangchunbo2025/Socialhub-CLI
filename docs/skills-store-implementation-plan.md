# Skills Store MVP 实现计划

## 1. 目标

本文档给出 Skills Store MVP 的详细实现计划，用于指导后续后端开发、测试和交付。

当前实现目标基于以下前提：

- 技能总量预期 `<= 500`
- 用户总量预期 `<= 1000`
- 当前是轻量级 MVP
- 优先兼容现有 CLI
- 不做大规模系统预优化

相关设计文档：

- [`CODEX.md`](C:\Users\86185\Socialhub-CLI\CODEX.md)
- [skills-store-api-spec.md](C:\Users\86185\Socialhub-CLI\docs\skills-store-api-spec.md)
- [skills-store-db-design.md](C:\Users\86185\Socialhub-CLI\docs\skills-store-db-design.md)
- [skills-store-technical-design.md](C:\Users\86185\Socialhub-CLI\docs\skills-store-technical-design.md)

## 2. 实施原则

- 简单可维护优先
- CLI 兼容优先
- 先打通主链路，再补外围能力
- 每个阶段都必须有明确验收结果
- 不引入 Elasticsearch、Kafka、RabbitMQ、分库分表、读写分离、复杂缓存集群

## 3. 总体阶段划分

1. 实现前校准
2. 项目骨架初始化
3. 数据模型与迁移
4. 认证与账户体系
5. 公开查询接口
6. 开发者提交流程
7. 轻量扫描器
8. 管理员审核流程
9. 签名、证书与下载
10. 吊销、CRL 与更新检查
11. 测试与兼容性验证
12. 文档与交付收尾

## 4. 详细计划

### Phase 0: 实现前校准

目标：

- 确保文档边界和 CLI 契约已经完全收敛

任务：

1. 核对 [`CODEX.md`](C:\Users\86185\Socialhub-CLI\CODEX.md)
2. 核对 [skills-store-api-spec.md](C:\Users\86185\Socialhub-CLI\docs\skills-store-api-spec.md)
3. 核对 [skills-store-db-design.md](C:\Users\86185\Socialhub-CLI\docs\skills-store-db-design.md)
4. 核对 [skills-store-technical-design.md](C:\Users\86185\Socialhub-CLI\docs\skills-store-technical-design.md)
5. 逐行检查 [`store_client.py`](C:\Users\86185\Socialhub-CLI\socialhub\cli\skills\store_client.py)
6. 逐行检查 [`security.py`](C:\Users\86185\Socialhub-CLI\socialhub\cli\skills\security.py)

重点确认：

- 搜索参数使用 `search` 和 `limit`
- 下载路径使用 `/skills/{name}/download`
- 存在 `/skills/{name}/download-info`
- 存在 `/skills/featured`
- 存在 `/categories`
- `verify` 使用 `skill_name`
- `CRL` 格式与 CLI 校验逻辑一致

交付物：

- 实现目录定稿
- 约束清单定稿

验收标准：

- 不再存在文档冲突
- CLI 关键契约无歧义

### Phase 1: 项目骨架初始化

目标：

- 搭建可运行的 FastAPI 基础项目

任务：

1. 初始化后端目录
2. 建立 `pyproject.toml`
3. 建立 `Dockerfile`
4. 建立 `docker-compose.yml`
5. 建立应用入口 `main.py`
6. 建立配置模块 `config.py`
7. 建立数据库模块 `database.py`
8. 建立基础 router：
   - `auth.py`
   - `public.py`
   - `developer.py`
   - `admin.py`
9. 增加健康检查接口
10. 提供 `.env.example`

交付物：

- 可启动的 FastAPI 服务
- 健康检查接口
- 基础配置文件

验收标准：

- 本地可启动
- `/health` 返回 200
- OpenAPI 文档可访问

### Phase 2: 数据模型与迁移

目标：

- 落地数据库结构，作为后续业务实现基础

任务：

1. 定义枚举：
   - `developer_role`
   - `developer_status`
   - `skill_category`
   - `skill_status`
   - `version_status`
   - `review_status`
2. 建立 SQLAlchemy 模型：
   - `Developer`
   - `Skill`
   - `SkillVersion`
   - `SkillCertification`
   - `SkillReview`
3. 生成 Alembic 初始迁移
4. 实现基础种子数据脚本
5. 验证索引、唯一约束、外键

交付物：

- ORM 模型
- 初始迁移脚本
- 种子数据脚本

验收标准：

- 数据库可迁移
- 种子数据可导入
- 表结构与设计文档一致

### Phase 3: 认证与账户体系

目标：

- 完成账户和角色鉴权能力

任务：

1. 实现 `POST /api/v1/auth/register`
2. 实现 `POST /api/v1/auth/login`
3. 实现 `GET /api/v1/auth/me`
4. 实现 `PATCH /api/v1/auth/me`
5. 实现密码哈希
6. 实现 JWT 生成与校验
7. 实现角色权限依赖

交付物：

- 完整认证模块
- 用户资料读写能力
- 角色鉴权依赖

验收标准：

- 注册成功
- 登录成功
- 可获取当前用户信息
- 权限控制生效

### Phase 4: 公开查询接口

目标：

- 先打通 CLI 所需的只读公开能力

任务：

1. 实现 `GET /api/v1/skills`
2. 实现 `GET /api/v1/skills/{name}`
3. 实现 `GET /api/v1/skills/{name}/versions`
4. 实现 `GET /api/v1/categories`
5. 实现 `GET /api/v1/skills/featured`
6. 实现分页、过滤、排序

交付物：

- 全部公开查询接口

验收标准：

- CLI 可搜索技能
- CLI 可读取详情、版本、分类、精选
- `search` / `limit` 契约正确

### Phase 5: 开发者提交流程

目标：

- 打通“创建技能 + 上传版本 + 进入审核”的链路

任务：

1. 实现 `POST /api/v1/developer/skills`
2. 实现 `POST /api/v1/developer/skills/{name}/versions`
3. 保存上传包到本地存储
4. 解析和保存 manifest
5. 计算包哈希和包大小
6. 创建 `skill_versions`
7. 创建初始 `skill_reviews`
8. 实现开发者查看自己技能和版本的接口

交付物：

- 上传与提交能力
- 开发者自有技能查询能力

验收标准：

- 合法 zip 可上传
- 版本进入 `reviewing`
- 数据落库正确

### Phase 6: 轻量扫描器

目标：

- 提供 MVP 必要的包安全与结构检查

任务：

1. 实现 manifest 结构校验
2. 实现包大小限制
3. 实现基础目录结构检查
4. 实现敏感文件初筛
5. 输出扫描摘要到 `scan_summary`
6. 输出详细结果到 `scan_result_json`

交付物：

- 扫描服务
- 扫描结果入库逻辑

验收标准：

- 合法包可通过
- 非法包可拒绝或标记风险
- 管理员可读取扫描结果

### Phase 7: 管理员审核流程

目标：

- 实现版本审核与状态流转

任务：

1. 实现 `GET /api/v1/admin/reviews`
2. 实现 `POST /api/v1/admin/reviews/{review_id}/start`
3. 实现 `POST /api/v1/admin/reviews/{review_id}/approve`
4. 实现 `POST /api/v1/admin/reviews/{review_id}/reject`
5. 记录审核意见和时间
6. 同步更新版本状态

交付物：

- 审核队列
- 审核处理接口
- 状态流转逻辑

验收标准：

- 管理员可查看待审任务
- 可通过或驳回
- 状态与审核记录一致

### Phase 8: 签名、证书与下载

目标：

- 打通发布、下载和 CLI 验签主链路

任务：

1. 实现 Ed25519 签名服务
2. 定义规范化签名载荷
3. 审核通过后签发证书
4. 实现 `GET /api/v1/skills/{name}/download`
5. 实现 `GET /api/v1/skills/{name}/download-info`
6. 限制只有 `published` 版本可下载
7. 更新下载计数

交付物：

- 签名服务
- 证书记录
- 下载接口
- 下载元信息接口

验收标准：

- CLI 可下载包
- CLI 可获取签名与元信息
- 证书记录正确落库

### Phase 9: 吊销、CRL 与更新检查

目标：

- 补齐证书生命周期和客户端更新能力

任务：

1. 实现 `POST /api/v1/skills/verify`
2. 实现 `POST /api/v1/admin/certifications/{certificate_serial}/revoke`
3. 实现 `GET /api/v1/crl`
4. 实现 `POST /api/v1/skills/check-updates`
5. 吊销后同步将版本设为 `revoked`

交付物：

- 验签接口
- 吊销接口
- CRL 接口
- 更新检查接口

验收标准：

- 已签发证书可验证
- 已吊销证书可从 CRL 查询
- CLI 可识别更新

### Phase 10: 管理统计与补充能力

目标：

- 增加管理员最基本的数据视图

任务：

1. 实现 `GET /api/v1/admin/stats`
2. 输出基础统计：
   - 技能总数
   - 已发布版本总数
   - 待审核数
   - 已吊销证书数

交付物：

- 管理统计接口

验收标准：

- 管理端可读取关键统计指标

### Phase 11: 测试与兼容性验证

目标：

- 确保主链路稳定、CLI 契约不偏移

任务：

1. 编写单元测试：
   - 密码哈希
   - JWT
   - 扫描逻辑
   - 签名逻辑
   - 状态流转
2. 编写集成测试：
   - 注册 / 登录 / 当前用户
   - 创建技能 -> 上传版本 -> 扫描 -> 审核 -> 发布
   - 下载 -> download-info -> verify
   - 吊销 -> CRL
3. 编写兼容性测试：
   - `search`
   - `limit`
   - `download-info`
   - `categories`
   - `skills/featured`
   - `skill_name`
4. 编写错误路径测试：
   - 重复邮箱
   - 重复版本
   - 非法包
   - 权限不足
   - 重复吊销

交付物：

- `pytest` 测试集
- 兼容性验证清单

验收标准：

- 主链路测试通过
- CLI 兼容点测试通过
- 关键错误路径测试通过

### Phase 12: 文档与交付收尾

目标：

- 让项目可启动、可交接、可复用

任务：

1. 完善 `.env.example`
2. 完善开发启动说明
3. 补充数据库初始化命令
4. 补充种子数据导入说明
5. 补充测试命令说明
6. 补充 API 联调说明
7. 可选增加初始化脚本：
   - 初始化管理员
   - 导入示例数据
   - 重建 CRL

交付物：

- README 更新
- 环境配置说明
- 常用命令说明

验收标准：

- 新开发者可按文档独立启动项目
- 测试、迁移、种子导入流程清晰

## 5. 推荐执行顺序

建议严格按以下顺序推进：

1. 项目骨架初始化
2. 数据模型与迁移
3. 认证与账户体系
4. 公开查询接口
5. 开发者提交流程
6. 轻量扫描器
7. 管理员审核流程
8. 签名、证书与下载
9. 吊销、CRL 与更新检查
10. 管理统计
11. 测试与兼容性验证
12. 文档与交付收尾

## 6. 每阶段完成定义

每个阶段完成后，至少满足以下条件：

1. 代码已落地
2. 至少有基础测试或手动验证
3. 接口契约未偏离设计文档
4. 没有新增未澄清的设计冲突

## 7. 当前最合理的下一步

当前设计工作已经足够支撑开发，建议立即进入以下实现内容：

1. 初始化 `skills-store/backend`
2. 建立 FastAPI 骨架
3. 建立 SQLAlchemy models
4. 生成 Alembic 初始迁移
