# 项目现状深度扫描

> 扫描时间：2026-03-31
> 扫描范围：cli/, mcp_server/, tests/, pyproject.toml
> 对标基准：Anthropic claude-code（TypeScript，~512K 行）

---

## A. 启动性能

### 发现

**问题：17 个命令模块在启动时全量 import**

`cli/main.py:20-38` 在模块顶层直接 import 了全部 17 个命令模块：

```python
from .commands import (
    ai, analytics, campaigns, config_cmd, coupons, customers,
    heartbeat, history, mcp, members, messages, points,
    schema, segments, skills, tags, workflow,
)
```

每个命令模块又在模块层面进行大量二级 import（见 `cli/commands/analytics.py:1-60`），analytics 一个文件就引入了 `APIClient`、`MCPClient`、`LocalDataReader`、`DataProcessor`、`export`、`table`、10+ 个分析子模块。这意味着即使用户只是运行 `sh --version`，整个 import 链条也会全部执行。

**对比 claude-code 差距**：claude-code 使用 ES Module 动态 `import()` 实现懒加载，工具函数按需引入，`--version` 几乎瞬时返回。

**现有缓解措施（部分）**：

- `cli/main.py:222-228`：在 smart 模式路径下，AI 相关函数（`call_ai_api`、`execute_plan` 等）通过局部 import 方式延迟加载——但这只覆盖了 smart 模式，命令模块仍全量加载。
- `cli/ai/executor.py:47-48`：`from .validator import validate_command` 是函数内局部 import，属于正确做法。
- `cli/ai/executor.py:21`：`from .insights import generate_insights` 是函数内局部 import，正确。
- `cli/skills/manager.py:53-58`：`store_client` 采用 `@property` 懒初始化，正确。

**无启动预热逻辑（CLI 层面）**：CLI 无任何 warmup 机制。MCP Server 有完整预热：`mcp_server/__main__.py:62-63` 启动两个后台线程分别执行 `_load_analytics()` 和 `_warm_cache()`，预热 12 个常用查询（`mcp_server/server.py:105-144`）。但这是 MCP Server 专属逻辑，CLI 主进程没有对应设计。

**改进方向**：将 `app.add_typer()` 调用改为按需动态注册（参考 Typer 的 `lazy_load` 模式），或将 import 移入各 command 函数内部。

---

## B. AI 执行护栏

### B1. 步骤上限

**缺失**：`cli/ai/executor.py:136-196` 的 `execute_plan()` 函数无任何步骤数量限制。理论上 AI 可以在 `[PLAN_START]...[PLAN_END]` 中生成 100 个步骤，`execute_plan` 会无限循环执行直到结束（`cli/ai/executor.py:149`：`for idx, step in enumerate(steps):`）。

**对比 claude-code 差距**：claude-code 有硬编码的工具调用轮数上限（默认 20），超出后自动终止并提示用户。

### B2. Circuit Breaker（连续失败自动停止）

**部分实现，但不充分**：

`cli/ai/executor.py:186-189`：
```python
if idx < len(steps) - 1:
    if not typer.confirm("Continue with remaining steps?", default=False):
        ...
        return
```

当某步骤失败时会询问用户是否继续，`default=False` 意味着回车默认终止。这是一个人工干预的软停止，并非自动 circuit breaker。

**缺失的模式**：
- 无连续失败计数器（如连续 3 步失败自动停止）
- 无失败率阈值（如失败率 > 50% 停止）
- 无超时熔断（单步已有 `timeout=120`，但多步计划无总超时）
- 无重试逻辑（失败即问用户，无自动 retry with backoff）

### B3. validate_command 覆盖范围

**实现较完整，有具体证据**：

`cli/ai/validator.py:114-145`：`validate_command()` 执行三层校验：
1. 命令必须以 `sh ` 开头（:126）
2. 顶级命令必须在 `_MODULE_MAP`（17 个注册命令）中（:138-140）
3. 递归验证子命令路径——从 Typer app 树中动态反射（:63-75），支持任意深度（:85-111）

`cli/ai/executor.py:52-64`：`execute_command()` 在验证之外额外检查 9 类危险字符（`;` `&&` `||` `|` `` ` `` `$` `>` `<` `\n` `\r`）并拒绝执行。

**覆盖盲区**：
- 参数值内容不校验（只校验子命令路径，不校验 `--limit -999` 这类非法参数值）
- 无参数类型/范围验证
- 无幂等性检查（见 B4）

### B4. 幂等性检查

**完全缺失**：无任何幂等性机制。同一个 `execute_plan` 调用如果重复执行（如用户连续触发），会重复执行所有步骤，无去重或结果缓存。

---

## C. Permission 体系

### C1. 只读 vs 破坏性操作区分

**现有区分逻辑（隐式）**：

`cli/ai/executor.py:52-53`：只允许 `sh ` 开头的命令，配合 validator，实际上将可执行操作限制在 CLI 注册命令范围内。但"只读"和"破坏性"没有显式标记。

`cli/skills/sandbox/execute.py:37-57`：ExecuteSandbox 有 `DANGEROUS_COMMANDS`（危险命令黑名单，17 类）和 `SAFE_COMMANDS`（安全命令白名单，22 类），但这只作用于 Skills 沙箱层，不适用于 AI 执行层。

**完全缺失的内容**：
- CLI 命令没有 `read_only=True/False` 的元数据标注
- 没有按命令类型区分审批策略（查询类 vs 写入类 vs 配置修改类）
- 所有操作使用同一个 `typer.confirm()` 审批方式（`cli/main.py:268`、`cli/main.py:281`）

### C2. 分级审批模式

**完全缺失**：无 auto / plan / ask / bypass 四级 Permission 模式（对标 claude-code）。

所有操作统一走"展示计划 → typer.confirm → 执行"的单一路径（`cli/main.py:260-272`）：
- 无静默自动执行只读操作的 auto 模式
- 无仅展示计划不执行的 plan 模式
- 无绕过审批的 bypass 模式（这是合理的安全设计，但缺少 auto 模式影响体验）

---

## D. 可观测性

### D1. AI 决策追踪日志

**完全缺失**：

整个 AI 调用链（`cli/ai/client.py` → `cli/ai/parser.py` → `cli/ai/validator.py` → `cli/ai/executor.py`）无结构化决策日志。具体缺失：
- 无"为什么 AI 选择这个命令"的推理记录
- 无每步执行的耗时记录（executor.py 中无 `start_time` / `elapsed` 计算）
- 无执行计划 JSON 序列化存储
- 无错误决策回溯（validator 拒绝了哪条命令、原因是什么）

`cli/ai/client.py:171`：仅打印 `Completed in {elapsed_time:.1f}s`（用户可见的终端输出），非结构化日志。

`mcp_server/__main__.py:30-40`：MCP Server 有完整的文件日志（`~/.socialhub/logs/mcp_server.log`），格式为 `%(asctime)s %(levelname)s %(name)s %(message)s`——但这是 MCP 层，不是 AI 执行链。

`cli/skills/security.py:SecurityAuditLogger`：Skills 安全审计日志存在，记录签名验证、权限授予、沙箱违规等事件——但这是 Skills 层，不覆盖 AI 决策链。

### D2. Token 消耗追踪

**完全缺失**：

`cli/ai/client.py:169-173`：API 响应解析时只提取 `result["choices"][0]["message"]["content"]`，完全忽略了 `result["usage"]` 字段（OpenAI/Azure 响应中包含 `prompt_tokens`、`completion_tokens`、`total_tokens`）。

对比 claude-code 差距：claude-code 追踪每次工具调用的 input/output token 数，支持 `--max-tokens` 预算控制，并在会话结束时汇报总消耗。

---

## E. Skills 安全现状

### E1. Ed25519 签名验证：真实实现

**结论：真实实现，但公钥是占位符**

`cli/skills/security.py:39`：
```python
OFFICIAL_PUBLIC_KEY_B64 = "MCowBQYDK2VwAyEAK5mPmkJXzWvHxLxV9G6Y8Z3q1fJnRt0vLhQE7YKp2Hw="
```
这是一个格式合法的 DER 编码 Ed25519 公钥（`MCowBQYDK2VwAyE` 是标准 SubjectPublicKeyInfo 头），但值本身是占位符（48行注释 `EXPECTED_KEY_FINGERPRINT = "sha256:a1b2c3d4e5f6..."` 也是占位符）。

密码学验证逻辑是真实实现的：
- `cli/skills/security.py:283-317`：`_verify_ed25519_signature()` 使用 `cryptography` 库的 `Ed25519PublicKey.verify()` 进行真实密码学验证（非 mock）
- `cli/skills/security.py:338-354`：`_build_signed_data()` 构建规范化 JSON 签名数据（sorted keys，无空白）
- `cli/skills/security.py:187-194`：哈希比较使用常量时间算法防止时序攻击

**实际安全风险**：由于嵌入的公钥是占位符（无法解码为有效的 32 字节原始公钥），`load_public_key()` 在 `key_bytes[12:]` 处截取后会得到错误长度的字节，导致 `Ed25519PublicKey.from_public_bytes()` 抛出异常，进而触发 `SecurityError`。这意味着**所有 Skills 安装都会因签名验证失败而被阻断**——除非 Store 服务端返回的 signature 字段为空（`cli/skills/manager.py:122-126`：当 store 未返回 signature 时 `signature = ""`，而后续验证会被完整运行并因公钥问题失败）。

测试文件 `tests/test_security.py:117-124` 中的 `test_load_public_key` 用 `try/except SecurityError: pass` 来处理这个情况，明确预期了占位符公钥场景。

**结论**：签名验证是真实的密码学实现，但尚未用生产公钥配置，属于"实现完整，密钥待配"状态。

### E2. 三层沙箱隔离：真实 monkey-patch 实现

**结论：全部是真实 monkey-patch，非占位**

**Filesystem 层**（`cli/skills/sandbox/filesystem.py`）：
- `activate()` 方法（:161-172）：`self._original_open = builtins.open`，然后 `builtins.open = self._create_guarded_open()`——真实替换 Python 内置 `open` 函数
- 路径检查基于 `Path.resolve()` + `relative_to()` 防目录穿越
- 违规写入 SecurityAuditLogger

**Network 层**（`cli/skills/sandbox/network.py`）：
- `activate()` 方法（:170-181）：`self._original_socket = socket.socket`，然后 `socket.socket = self._create_guarded_socket()`——真实替换 socket 类
- GuardedSocket 重写 `connect()` 和 `connect_ex()` 两个方法（:130-166），覆盖 TCP 连接入口

**Execute 层**（`cli/skills/sandbox/execute.py`）：
- `activate()` 方法（:248-273）：同时替换 `subprocess.run`、`subprocess.Popen`、`subprocess.call`、`subprocess.check_call`、`subprocess.check_output` 和 `os.system`——覆盖最完整的执行入口

**已知逃逸面（未覆盖的向量）**：
- `ctypes` 直接调用系统调用
- `cffi` 绑定的原生库
- 通过 `importlib` 动态加载使用了原始 socket 的已编译扩展模块
- `os.popen()`（仅替换了 `os.system`，未替换 `os.popen`）
- pathlib.Path 的 open 方法（只替换了 `builtins.open`，pathlib.Path.open 有自己的实现路径）

**测试覆盖**：`tests/test_sandbox.py` 对三层均有功能测试（读/写/网络/执行的允许与拒绝场景）。

---

## F. 输出能力

### F1. --output-format 参数

**完全缺失**：

全局搜索 `output.format`、`output_format`、`--json` 均无匹配。所有命令输出使用 Rich 终端渲染（Panel、Table、Markdown），无结构化输出选项。

**局部支持**：`cli/output/export.py` 支持将数据导出为 CSV/Excel/JSON/Markdown **文件**（通过 `--output path.csv` 类参数），但这是文件落盘导出，不是 stdout JSON 流。

### F2. 程序化消费（pipe / jq / 脚本集成）

**不支持**：所有输出混合了 Rich 的 ANSI 控制码，无法直接 pipe 到 `jq` 或其他工具解析。

**对比 claude-code 差距**：claude-code 支持 `--output-format json` / `--output-format stream-json`，所有工具调用结果可以结构化输出，适合 CI/CD 集成和脚本消费。

---

## G. MCP Server 稳定性

### G1. 并发模型

**混合模型：anyio 协程 + threading**

- 协议层（MCP stdio）：`mcp_server/__main__.py:65-70` 使用 `anyio.run()` 运行协程，MCP Server 的 `server.run()` 是 async
- 工具处理层：所有 `_handle_*` 函数是同步函数，在 anyio 的 `run_sync_in_executor` 中执行
- 缓存/预热层：`threading.Thread` + `threading.Event`（`mcp_server/server.py:40-47`）
- HTTP 模式：uvicorn（ASGI）作为 HTTP 服务器

**关键风险**：`mcp_server/server.py:67-102` 的 `_run_with_cache()` 使用 `threading.Lock` + `threading.Event` 作为并发控制——这在 anyio 协程中被调用时会在 anyio 的 executor 线程池中执行，属于阻塞调用，符合 CLAUDE.md 提到的异步模型隐患。

### G2. 超时保护

**部分实现**：

- `mcp_server/server.py:86`：in-flight 等待有 `timeout=180` 秒的超时保护
- `cli/ai/executor.py:74-82`：子进程执行有 `timeout=120` 秒
- `cli/ai/client.py:64,101`：HTTP 请求有 `timeout=60` 秒
- **缺失**：MCP 工具处理器本身无超时限制，如果底层 analytics 查询挂起，整个工具调用会无限等待

### G3. Backpressure

**无 Backpressure 机制**：

`_cache` 是无界 dict（`mcp_server/server.py:44`），无 LRU/最大条目限制，理论上内存可无限增长。`_inflight` 也是无界 dict，高并发下可能积累大量等待条目。无队列深度限制、无连接数限制、无 rate limiting。

---

## H. 现有测试覆盖

### 已覆盖（有测试文件）

| 测试文件 | 覆盖内容 | 质量评估 |
|---------|---------|---------|
| `test_security.py` | HashVerifier、KeyManager、SignatureVerifier、PermissionChecker、RevocationListManager、PermissionStore、PermissionContext | 高质量，覆盖正常路径+异常路径+边界情况 |
| `test_sandbox.py` | FileSystemSandbox、NetworkSandbox、ExecuteSandbox、SandboxManager | 功能测试完整，覆盖 allow/deny 两种场景 |
| `test_cli.py` | version/help/config/analytics 子命令 help | 基础冒烟测试，无 AI 执行路径 |
| `test_auth.py` | MCP 认证中间件（推测） | 存在 |
| `test_cache_isolation.py` | 多租户缓存隔离 | 存在（对应 tenant_id 安全需求） |
| `test_config.py` | 配置加载 | 存在 |
| `test_local_reader.py` | 本地 CSV 读取 | 存在 |
| `test_processor.py` | 数据处理层 | 存在 |
| `test_sandbox.py` | 三层沙箱 | 存在 |
| `test_tool_schema_consistency.py` | MCP 工具 Schema 一致性 | 存在 |

### 未覆盖的关键路径

| 缺失测试 | 风险等级 | 说明 |
|---------|---------|------|
| AI 执行路径端到端测试 | 高 | `execute_plan` / `extract_plan_steps` / `execute_command` 组合路径 |
| validator 边界测试 | 中 | 深度嵌套命令、特殊字符参数、长命令串 |
| 危险字符注入测试 | 高 | `;`、`$()`、`` ` `` 等注入向量是否被 executor 正确拦截 |
| circuit breaker 行为测试 | 中 | 多步失败后的交互行为 |
| AI client 重试逻辑测试 | 中 | timeout/retry 行为 |
| MCP Server 并发安全测试 | 高 | 多线程 cache + in-flight 的竞争条件 |
| Skills loader 沙箱激活顺序测试 | 中 | 三层沙箱的激活/停用顺序是否正确 |

---

## 综合评分

| 维度 | 当前状态 | 与 claude-code 差距 | 改进难度 |
|------|---------|-------------------|---------|
| A. 启动性能 | 17 模块全量 import，无懒加载；MCP 有预热但 CLI 无 | 大（claude-code 懒加载极致，ms 级冷启动） | 中（需重构 import 结构，改动面广但不破坏逻辑） |
| B. AI 执行护栏 | 无步骤上限、软 circuit breaker（人工干预）、无幂等、无 retry | 大（claude-code 有硬性上限+自动熔断） | 小~中（executor.py 局部改动即可） |
| C. Permission 体系 | 单一审批路径，无 auto/plan/ask/bypass 分级 | 大（缺少运营场景中最常用的 auto 只读模式） | 中（需要命令元数据标注 + CLI 参数新增） |
| D. 可观测性 | 无结构化 AI 决策日志，无 token 追踪 | 大（claude-code 有完整决策链追踪） | 中（需引入结构化日志库，token 追踪改动小） |
| E. Skills 安全 | 签名验证真实实现（密钥待配），三层沙箱真实 monkey-patch | 小（架构设计优秀，仅密钥需替换；有逃逸面但已是业界实践水平） | 小（替换生产公钥即可完整启用，逃逸面是长期工程） |
| F. 输出能力 | 纯 Rich 终端渲染，无 `--output-format json` | 大（不可程序化消费，无法集成 CI/CD） | 小（增加全局选项 + 条件渲染路径） |
| G. MCP 稳定性 | 混合并发模型，无 backpressure，无内存上限 | 中（threading + anyio 混用有隐患；无 backpressure） | 中（cache 加 LRU 容易，并发模型重构较复杂） |
| H. 测试覆盖 | 安全层覆盖好，AI 执行路径未覆盖，注入防御无测试 | 中（缺少最关键的端到端 AI 执行测试） | 小（补充 pytest 测试即可，无需改动生产代码） |

---

## 可复用基建（高价值，改进时可直接利用）

| 基建 | 文件 | 可复用说明 |
|-----|------|-----------|
| 三层沙箱 monkey-patch 框架 | `cli/skills/sandbox/` | 架构成熟，可扩展 `os.popen` 等逃逸面 |
| SecurityAuditLogger | `cli/skills/security.py` | 可扩展至 AI 决策链审计 |
| validator 命令树反射 | `cli/ai/validator.py` | 已有良好基础，可在其上加参数类型校验 |
| MCP 缓存 + in-flight 去重 | `mcp_server/server.py:67-102` | 可移植到 CLI 层的 AI 结果缓存 |
| MCP 预热机制 | `mcp_server/server.py:105-146` | 可移植到 CLI 启动预热 |
| PermissionStore 持久化 | `cli/skills/security.py` | 可用于 Permission 模式的权限持久化 |
| 配置分层（代码→config.json→env）| `cli/config.py` | 已完整实现，可供新功能配置项沿用 |

---

*生成者：project-status 调研 Agent — 2026-03-31*
