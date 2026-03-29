# SocialHub × M365 Declarative Agent — CTO 技术审查报告

> 文档版本：1.0
> 审查日期：2026-03-29
> 审查人：CTO（AI 辅助三轮自我对抗迭代）
> 审查基准：CLAUDE.md + 05-prd.md + 06-technical-design.md

---

## 总评级

**有条件批准**

技术方案整体架构清晰，与 CLAUDE.md 原则的对齐度高，在核心安全约束（tenant_id 隔离、缓存 Key 隔离、hmac 防时序攻击）上有扎实的设计思考。但存在一个需要上线前修复的严重安全缺陷（GA 版 JWT 签名验证跳过），以及若干影响生产可维护性的可观测性缺口。

**批准条件（必须在 MVP 上线前满足）**：

1. Round 1 薄弱环节 3 的工具名一致性测试（`test_tool_schema_consistency.py`）必须写完并通过
2. Round 2 修正 2.1-2.3 的结构化日志和 `/health` 上游检查必须实现
3. GA 版 Entra token 验证代码中的 `verify_signature: False` 示例**必须在文档中明确标注「禁止直接使用，必须替换为 JWKS 验证实现」**，即使 MVP 阶段不上线 OAuth，此代码不能作为「示例」存在于代码库（参见「执行备注 1」）

---

## 一、架构一致性审查（逐条对照 CLAUDE.md）

| CLAUDE.md 原则 | 技术方案满足情况 | 风险等级 |
|---|---|---|
| MCP 优先集成：对外集成统一走 MCP 协议，不暴露裸 REST | 满足。HTTP 传输层走 MCP Streamable HTTP，非裸 REST | 无风险 |
| 多租户隔离：通过 tenant_id 隔离数据，禁止跨租户查询 | 满足（需完成 Step 3 改造）。API Key → tenant_id 映射在服务端，客户端传入值被静默删除；缓存 Key 含 tenant_id | 低风险（改造前不可上线） |
| 工具处理器返回 list[TextContent] | 满足。现有 server.py 的 _ok()/_err() 机制保持不变，HTTP 传输层不影响工具层 | 无风险 |
| 工具名称验证：call_tool() 通过 _HANDLERS.get(name) 查找 | 满足。mcp-tools.json 工具名与 _HANDLERS key 一致，plugin.json 的 allowed_tools 限制了可调用范围 | 低风险（需 Round 1 的工具名一致性测试守护） |
| docs/ 目录冻结 | 满足。所有新建文件在 mcp_server/、build/m365-agent/、tests/ 中 | 无风险 |
| 配置分层：代码默认值 → config.json → 环境变量 | 满足。HTTP 模式引入 MCP_API_KEYS 环境变量，符合现有分层约定 | 无风险 |
| Store URL 硬编码 | 不涉及。本次改动不触碰 store_client.py | 无风险 |
| Skills 零信任沙箱 | 不涉及。本次改动不触碰 Skills 系统 | 无风险 |

**架构一致性结论**：通过。设计团队对 CLAUDE.md 约束的理解是准确的，关键红线均未触碰。

---

## 二、安全性深度审查

### 2.1 tenant_id 隔离机制

**隔离链完整性**：

```
HTTP 请求
  → [CORSMiddleware：处理 preflight]
  → [APIKeyMiddleware：X-API-Key/Bearer → _API_KEY_MAP → tenant_id]
  → [ContextVar 注入：_tenant_id_var.set(tenant_id)]
  → [executor 线程：asyncio 自动复制 context]
  → [call_tool()：_get_tenant_id() 读取，客户端传入 tenant_id 被删除]
  → [_cache_key()：f"{tenant_id}:{name}:{args}"]
  → [_run_with_cache()：缓存 Key 含 tenant_id，不同租户不共享缓存]
```

**评估**：隔离链设计扎实，`hmac.compare_digest()` 防时序攻击、ContextVar reset token 防线程池残留，均是正确做法。**隔离机制本身没有已知漏洞**，只要 Step 3 的 server.py 改造完成。

**残余风险**：进程级内存缓存在多 worker 场景下不共享，但当前 `render.yaml` 固定 `--workers 1`，此风险不存在于 MVP 阶段。扩容到多 worker 时需引入 Redis 缓存，届时需重新审查 tenant_id 隔离。

### 2.2 API Key 管理安全性评估

| 维度 | 当前设计 | 漏洞评估 |
|---|---|---|
| Key 格式 | `sh_` + 32 字节随机 Base64URL，约 48 字符 | 足够强度，无问题 |
| Key 传输 | SocialHub 客户后台安全链接，禁止明文邮件 | 运营流程约束，无工程保障，依赖人员自律 |
| Key 存储（服务端） | Render 环境变量（加密存储在 Render 平台） | 可接受，Render 的环境变量 AES-256 加密存储 |
| Key 存储（客户端） | ATK env/.env.production，IT 管理员本地文件 | 风险：.env 文件可能被误提交到 Git；需在部署文档中明确「.gitignore 必须包含 .env*」 |
| Key 轮换窗口 | Render 重部署约 2-3 分钟（零停机时 3.5-4 分钟） | 可接受，已在 Round 1 识别 |
| Key 审计 | 无。只有 Render 日志中的访问记录 | P2 技术债，GA 阶段补充 |

**关键遗漏**：客户端 `.env` 文件的 Git 泄露风险在部署文档中没有提及。需在 Step 6 的部署文档中明确提示。

### 2.3 GA 版 JWT 验证安全漏洞（严重）

已在 Round 1 薄弱环节 1 详细记录。核心风险：`verify_signature: False` 意味着 JWT 签名完全不验证，任何人可伪造 token 获取任意企业数据。**此代码段不得出现在生产代码库中**，即使标注了「需要替换」。

---

## 三、技术债评估

### MVP 上线前必须解决（不可上线债）

| 技术债 | 位置 | 工作量 | 处理期限 |
|---|---|---|---|
| `verify_signature: False` 示例代码 | 06-technical-design.md §8 GA auth.py | 替换文档示例，30 分钟 | 文档修正今日，代码实现在 EA 阶段 |
| 工具名一致性测试缺失 | tests/ 目录 | 2 小时 | Step 8 实现 |
| `/health` 不反映上游连通性 | http_app.py | 1-2 小时 | Step 4 实现 |
| 结构化工具调用日志缺失 | server.py + http_app.py | 2-3 小时 | Step 3/4 实现 |

### MVP 上线可接受，EA 阶段处理（已知债）

| 技术债 | 描述 | 处理时机 |
|---|---|---|
| API Key 即时失效机制缺失 | 泄露后需 ~4 分钟才能失效 | EA 阶段，数据库存储 Key |
| GA 版 Entra Token 验证未实现 | OAuth 方案有骨架但未验证签名 | EA 结束前（触发条件：5 个 EA 客户 + 月活 ≥ 70%） |
| Render 日志仅 7 天保留 | 排障窗口短 | EA 阶段接入外部日志服务（Logtail 等）|
| 内存缓存单 worker 限制 | 扩容到多 worker 时需引入 Redis | 超出 20 个租户时评估 |
| API Key 自助管理界面 | 目前运营手动处理（4 小时 SLA） | GA 阶段 |
| 工具调用审计日志 | 安全合规要求，目前无完整记录 | GA 阶段 |

### 长期技术债观察（不影响 MVP，记录备案）

1. **MCP SDK 版本锁定风险**：方案依赖 `mcp>=1.8.0` 的 `StreamableHTTPSessionManager`，此 API 在 mcp SDK 仍处于活跃开发阶段，接口可能变化。建议锁定到具体版本（如 `mcp==1.26.0`）并在 `pyproject.toml` 中记录当时测试通过的版本号。

2. **declarativeAgent.json instructions 字段的测试覆盖**：Instructions 文本中的工具路由规则（「当用户询问...时调用...」）是纯自然语言约束，没有自动化测试。如果微软更新 M365 Copilot 的 instruction 解析逻辑，工具路由可能静默失效。建议建立「关键 Conversation Starter → 期望调用工具」的 E2E 回归测试清单，至少每次更新 Instructions 时手工验证。

3. **单一 MCP Server 实例是单点故障**：Render Starter 层的 SLA 是 99.9%，但仍有约 9 小时/年的停机时间。当企业客户数量超过 5 家时，应考虑 Render 的多区域部署或 Railway 备份实例。

4. **缓存雪崩风险**：15 分钟 TTL 的内存缓存在 Render 实例重启后全部失效，短时间内所有请求会直接打到上游 MCP Server。当活跃租户数超过 10 个时，重启后的瞬时并发可能超过上游承受能力。应在 `_run_with_cache()` 中增加随机抖动 TTL（如 `900 ± 60` 秒）。

5. **mcp-tools.json 与 plugin.json 的双重维护负担**：目前 mcp-tools.json 和 plugin.json 的 `functions`/`allowed_tools` 需要手动保持同步。随着工具数量增加，这个手动维护会成为错误来源。GA 阶段应考虑生成脚本（从 server.py 的 `TOOLS` 列表自动生成这两个文件的相关字段）。

---

## 四、PRD 验收标准覆盖度检查

| PRD 验收标准 | 技术实现覆盖 | 是否有测试 |
|---|---|---|
| T1：HTTP MCP Server 可用（5条） | 完整覆盖（Step 9 端到端验证） | 部分（curl 手工验证为主） |
| T2：Teams App 包完整（4条） | 完整覆盖（Step 6）| JSON 语法检查 + Teams Validator |
| T3：端到端功能验证（5条） | Step 10 M365 测试覆盖 | 手工验证，无自动化 |
| T4：安全验证（3条） | 覆盖（test_auth.py + Step 9）| 有自动化（test_auth.py） |
| B1：部署耗时 ≤ 30 分钟 | 部署文档覆盖（Step 3.3） | 内测时手工计时验证 |
| B2：工具多样性（≥3种被调用） | 通过 Render 访问日志统计 | 无自动化，运营手工统计 |
| B3：数据信任建立 | 口径说明机制（Instructions + *_definition 字段） | 无，依赖内测用户访谈 |

**未被技术实现覆盖的验收标准**：

- T3 中的「追问（第二轮对话）能基于第一轮上下文回答」：这依赖 M365 Copilot 的 `conversation_memory: true` 功能，技术设计中只声明了配置，但没有验证 M365 Copilot 是否在当前版本完全支持此功能的多轮工具调用。需在 Step 10 专项验证。

- B2 中的工具调用多样性统计：当前没有指明从哪里获取这个数据（Render 日志？需要 grep `tool_call_start tool=`）。建议 Round 2 修正 2.1 的结构化日志上线后，提供一个简单的 shell 脚本给运营：`grep "tool_call_start" mcp_server.log | awk '{print $3}' | sort | uniq -c`。

---

## 五、给开发团队的执行备注（最重要的 5 条）

### 备注 1：今天立刻删除 GA 版 auth.py 中 `verify_signature: False` 的示例代码

`06-technical-design.md` 第 1054 行的 `jwt.decode(token, options={"verify_signature": False})` 是危险示例，必须从文档中删除或替换为 Round 1 修正中提供的正确 JWKS 骨架。

**为什么这条放第一位**：文档中的危险示例代码有极高概率在 EA 阶段被直接复制使用（「文档上就这么写的」），届时生产环境的 OAuth 认证将零安全保护，任何人可伪造 JWT 获取任意企业数据。这是唯一一个如果忽视可能导致严重数据泄露的问题，其余所有问题都是性能/可维护性层面的。

### 备注 2：Step 3（server.py 修改）是全局安全的关键步骤，必须最先提测

`_cache_key()` 不含 `tenant_id` 的现有代码意味着：**所有租户的相同查询会共享同一个缓存结果**。如果先部署了 auth.py（Step 2）但还没有完成 Step 3，两个不同企业的用户用相同参数查询，后来的企业会看到前一个企业的缓存数据。

**行动要求**：在 Git 提交顺序上，Step 2（auth.py）和 Step 3（server.py 缓存修改）必须在同一个 PR 中提交，**不允许分开部署**。即：不能存在一个只有 `auth.py` 但没有 `_cache_key(tenant_id)` 的中间状态被部署到 Render。

### 备注 3：测试先行——在写 auth.py 代码之前先写好 test_auth.py 的测试用例框架

当前开发步骤中测试在 Step 8（最后）编写。这是低效的，而且「认证失败应该返回什么」「/health 应该允许哪些请求」这些边界条件如果不事先定义，实现时容易遗漏。

**具体要求**：Step 2 开始前，先创建 `tests/test_auth.py` 并写好以下 6 个空测试函数（只有函数名，函数体 `pass`）：
- `test_valid_api_key_returns_200`
- `test_invalid_api_key_returns_401`
- `test_missing_api_key_returns_401`
- `test_health_endpoint_skips_auth`
- `test_bearer_token_format_accepted`
- `test_x_api_key_header_accepted`

然后在实现 auth.py 过程中逐一填充测试体，确保每个函数实现后测试立刻通过。

### 备注 4：M365 开发者账号今天申请，不要等到 Step 10

M365 开发者账号申请需要 1-2 个工作日审批，ATK 配置和 API Key Vault 注册需要额外 2-4 小时熟悉。如果等到 Step 9/10 才开始，会在最后时刻卡住整个 pipeline。

**今天的行动**：
1. 访问 https://developer.microsoft.com/microsoft-365/dev-program
2. 注册 E5 Sandbox 账号（免费，包含 M365 Copilot 测试权限）
3. 安装 VS Code Teams Toolkit 插件
4. 阅读 Round 3 修正「补充说明 A-D」，了解常见坑

### 备注 5：图标文件（color.png + outline.png）是 Teams Validator 的强制要求，不要用占位文件

Teams App Validator 会检查图标文件的实际分辨率（不只是检查文件名）：
- `color.png` 必须严格是 192×192 像素（不是 191×193，不是 200×200）
- `outline.png` 必须严格是 32×32 像素，背景必须是透明的（不是白色）

如果用 Photoshop/Figma 导出时尺寸不对或背景是白色，Teams Validator 会报错，ZIP 包上传会失败。建议使用微软官方工具 https://dev.teams.microsoft.com/tools 的 App Icon Generator 直接生成标准规格文件。

---

## 六、三轮迭代的发现和修正记录

### Round 1：薄弱环节识别（「破坏者」视角）

| 发现 | 严重程度 | 修正状态 |
|---|---|---|
| GA 版 JWT 验证代码使用 `verify_signature: False`，任意伪造 token 可绕过认证 | 严重（P0） | 已在文档中提供正确 JWKS 骨架，标记原代码不可直接使用 |
| `_API_KEY_MAP` 进程级单例在 Key 泄露后的失效窗口约 4 分钟（Render 零停机部署延迟） | 中等（P1） | 提供了 `reload_api_key_map()` 紧急失效机制设计，不阻塞 MVP |
| 工具名在 4 个文件中手动维护一致性，无自动化测试保障，任何拼写错误导致 M365 静默失败 | 高（P0） | 提供了 `test_tool_schema_consistency.py` 完整测试代码，加入 Step 8 |

### Round 2：生产事故排障链路（「On-call 工程师」视角）

**场景**：上线第 3 个月，客户投诉「留存率数字和 BI 系统差了 5 个百分点」

**修正前的 30 分钟排障结果**：大概率无法定位，因为：
- `/health` 不显示上游连通性状态
- 工具调用无结构化日志，无参数记录
- Render 日志 7 天保留窗口（3 天前的调用不存在）
- 缓存命中情况不可见

**修正后**（修正 2.1-2.3 实现后）：
- 30 分钟内定位概率从约 30% 提升到约 80%
- 排障路径：`/health` 确认上游状态（2 分钟）→ 结构化日志定位调用参数（8 分钟）→ 缓存命中判断（15 分钟）→ 复现并对比口径（20 分钟）

**开发成本**：2-3 小时，无外部依赖。

### Round 3：开发效率优化（「技术 PM」视角）

**发现的效率问题**：
1. M365 开发者账号申请放到 Step 10，可能在最后一步卡住 1-3 天
2. Step 6+7（M365 文件 + render.yaml）可以与主线并行，被低估了
3. 测试放在 Step 8（最后），应 TDD 前置
4. Python 工程师对 M365 生态的 4 个关键知识点（ATK 注册流程、Teams App 部署方式、mcp-tools.json 非标准 MCP 文件、ngrok 本地调试）在原文档中完全缺失

**修正**：提供了重新排序的执行时间表（4-5 工作日），4 条 M365 新手补充说明，以及 ngrok 本地调试方法。

---

## 七、长期技术债观察（不影响 MVP 上线，记录备案）

以下技术债不影响 MVP 上线，但需要在路线图中有明确的处理时机：

| 技术债 | 风险场景 | 处理时机建议 |
|---|---|---|
| MCP SDK 版本锁定缺失 | SDK 升级导致 StreamableHTTPSessionManager API 变化，无法快速定位 | 上线前锁定版本号到 pyproject.toml |
| Instructions 文本路由规则无自动化测试 | M365 Copilot 更新后工具路由静默失效 | 建立 E2E 测试清单，每次 Instructions 更新时手工验证 |
| 缓存雪崩风险 | 实例重启后短时并发超过上游承受能力 | 超过 10 个活跃租户时，TTL 增加随机抖动 |
| mcp-tools.json / plugin.json 手动同步 | 工具数量增加后维护负担和错误率上升 | GA 阶段提供生成脚本 |
| 单 Render 实例单点故障 | 企业客户 > 5 家后，故障影响面扩大 | EA 阶段评估多区域部署 |
| .env 文件 Git 泄露风险 | 客户端 API Key 被意外提交到代码仓库 | 部署文档补充 .gitignore 说明（即时） |
| Render 日志 7 天保留窗口过短 | 历史调用无法回溯 | EA 阶段接入 Logtail 等外部日志服务 |
