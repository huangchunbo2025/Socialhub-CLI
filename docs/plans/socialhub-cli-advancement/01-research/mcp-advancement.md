# MCP 协议最新进展与 SocialHub MCP Server 优化方向

**调研时间**: 2026-03-31
**调研范围**: MCP 协议 2025 全年进展、工具描述工程、服务端稳定性、缓存策略、M365 集成优化
**参照代码**: `mcp_server/server.py`（前 370 行）、`build/m365-agent/`

---

## 摘要

MCP 协议在 2025 年经历了三次重大规范升级（2025-03-26、2025-06-18、2025-11-25），从"单次同步工具调用"演进为支持异步任务、双向 Agent 循环和服务端主动交互的完整 Agentic 协议。SocialHub MCP Server 当前实现（threading + queue、纯 TTL 缓存、固定工具描述）在稳定性、工具选择准确率、长任务支持三个维度上存在明显改进空间，且均有清晰的技术路径可落地。

---

## A. MCP 协议新特性（2025 全年）

### A.1 三次规范升级时间线

| 版本 | 发布日期 | 核心变更 |
|------|---------|---------|
| 2025-03-26 | 2025-03-26 | Streamable HTTP Transport 正式取代 SSE 成为首选传输层；会话 ID 管理规范化 |
| 2025-06-18 | 2025-06-18 | Elicitation（服务器主动请求用户输入）发布；结构化工具输出（Structured Tool Outputs）；OAuth 授权规范化；Resource Indicators 安全强化 |
| 2025-11-25 | 2025-11-25 | Tasks 异步任务原语（call-now fetch-later）；Enhanced Sampling（服务端 Agent 循环、并行工具调用）；MCP Registry；Extensions 系统 |

### A.2 Streamable HTTP Transport 现状与对 SocialHub 的影响

**规范要求**（2025-03-26）：
- 服务端必须在同一端点提供 `POST`（发送 JSON-RPC）和 `GET`（接收流式响应）两种方法
- 服务端在 `InitializeResult` 响应头中通过 `Mcp-Session-Id` 分配全局唯一、密码学安全的会话 ID（推荐：安全随机 UUID 或 JWT）
- 客户端所有 JSON-RPC 消息必须使用新的 HTTP POST 请求，不再维持持久 SSE 连接
- 断线重连时客户端携带 `Last-Event-ID` 头，服务端可据此重放消息

**SocialHub 当前状态**：
- `mcp_server/http_app.py` 已实现 Streamable HTTP Transport（`mcp_server/http_app.py` + uvicorn），满足 M365 Copilot 集成要求
- `__main__.py` 同时支持 stdio（Claude Desktop）和 HTTP 两种传输
- **问题**：SSE 传统传输层在 `mcp.server` 底层库仍被部分保留；会话 ID 的密码学强度和超时管理未在代码层显式控制

**建议**：
- 明确在 `http_app.py` 中设置 `Mcp-Session-Id` 超时策略（建议 30 分钟无活动自动失效）
- 在 `/health` 端点中暴露活跃会话数量，用于监控

### A.3 Elicitation（服务器主动请求用户输入）

**协议机制**（2025-06-18 spec）：
- 服务器在工具执行中途向客户端发送 `elicitation/create` 请求，请求结构化用户输入
- 客户端展示表单/对话框给用户，用户填写后回传
- 支持两种模式：
  - **内联交互**：在 MCP 客户端 UI 内展示输入表单（适合日期范围选择、过滤条件）
  - **URL 模式**：跳转到外部 URL 完成交互（OAuth 流、支付、凭证录入）

**对 SocialHub 的价值**：
- **场景 1：时间范围消歧**：用户说"上个季度的数据"时，服务端可通过 Elicitation 主动询问"请确认时间范围：2025-10-01 至 2025-12-31？"，避免工具猜测导致的结果误差
- **场景 2：分析维度选择**：`analytics_orders` 调用时，如未传 `group_by`，服务端可主动提供选项列表（按渠道/按省份/按商品）
- **场景 3：导出确认**：批量数据操作前的确认提示，提升安全感

**实施前提**：客户端（Claude Desktop / M365 Copilot）必须声明支持 `elicitation` 能力。M365 Copilot 在 Ignite 2025 已宣布支持 MCP Elicitation；Claude Desktop 需确认版本支持情况。

### A.4 Tasks 异步任务原语（2025-11-25）

**协议机制**：
- 服务端工具调用立即返回 `task_id`，客户端可通过 `tasks/get` 轮询状态
- 任务结果在服务端保存一段时间（server-defined duration），客户端可在任意时间取回
- 适用场景：数百万行数据的 RFM 分析、需要 30 秒以上的留存队列计算

**当前 SocialHub 痛点**：
- `analytics_rfm`、`analytics_retention` 等重型查询在慢数据库环境下可能超过 Claude Desktop 默认 60 秒工具超时
- 当前解决方案是缓存预热（`_warm_cache`），但预热覆盖不完整且仅限 stdio 模式

**建议（P1）**：
- 为耗时超过预计 10 秒的工具（rfm、retention、ltv）实现 Tasks 包装层
- 任务 ID 与缓存 key 关联：若缓存命中直接返回 `completed`；否则后台异步计算
- 该功能依赖 MCP Python SDK 对 Tasks 的支持状态（截至 2026-03-31 SDK 已支持实验性 Tasks API）

### A.5 Resource Subscription（资源变更订阅）

**协议机制**：
- 服务端声明 `resources.subscribe: true` 能力
- 客户端订阅特定资源 URI 后，服务端数据变更时推送 `notifications/resources/updated`
- MCP 采用变更通知与数据获取解耦的设计：通知仅告知"有变更"，客户端再主动拉取新数据

**对 SocialHub 的潜在应用**：
- 暴露"当日实时大盘"为资源（如 `socialhub://dashboard/today`），数据刷新时推送通知
- 供 M365 Copilot 构建"数据到达时自动触发分析"的主动式工作流
- **实施复杂度高**：需要底层数据层支持变更检测，当前 SocialHub 数据架构以批处理为主，短期优先级低（P2）

### A.6 MCP Sampling（服务器反向调用 LLM）

**协议机制**（2025-11-25 增强版）：
- 服务端在工具执行中向客户端请求 LLM completion
- 增强版支持服务端在 sampling request 中携带工具定义，实现服务端 Agent 循环
- 支持并行工具调用

**对 SocialHub 的价值**：
- **Insights 集成**：`analytics_rfm` 工具执行完毕后，服务端通过 Sampling 向 LLM 请求生成"RFM 分析洞察摘要"，而非由客户端 LLM 负责解读原始数据
- **异常自动叙述**：`analytics_anomaly` 检测到指标异常后，Sampling 触发 LLM 撰写"业务影响分析"
- **实施前提**：需要客户端声明 `sampling` 能力；Claude Desktop 已支持，M365 Copilot 支持状态需验证

---

## B. 工具描述优化

### B.1 当前实现分析

**server.py 中的工具描述**（已观察到的模式）：
```python
Tool(
    name="analytics_overview",
    description=(
        "Top-level business KPI dashboard — call this tool for daily/weekly/monthly business reviews, "
        "operational summaries, or when the user asks 'how is the business doing', 'show me today's numbers', ..."
    ),
    ...
)
```

**评估**：
- 优点：已采用意图匹配（"when the user asks..."）模式，比纯功能描述更好
- 优点：已在描述中列举返回字段（GMV、AOV、active customers 等），有助于模型判断是否需要该工具
- 不足：描述长度在 200-400 字符区间，没有利用动态生成能力
- 不足：工具间的边界未明确（overview vs customers 的重叠区域未说明互斥性）

**mcp-tools.json（M365 版本）的问题**：
```json
"description": "Get a snapshot of core customer metrics such as active customers, new customers, retention..."
```
描述极度精简（30-50 字符），且与 server.py 中的描述不同步，会导致 M365 Copilot 工具选择准确率下降。

### B.2 工具选择准确率的量化影响

根据 Anthropic 内部测试数据（Advanced Tool Use 研究报告）：
- 工具超过 30-50 个时，模型工具选择准确率显著下降
- Claude 3.5 Opus 4 在启用 Tool Search（精准描述 + 语义索引）后，准确率从 49% 提升至 74%（+25pp）
- 使用 3-4 句描述（含意图关键词）比单行描述准确率提升 15-20%
- **工具名称冲突**是最常见的错误来源（如 `analytics_overview` vs `analytics_customers` 在"客户概览"查询时的混淆）

### B.3 Tool Description 工程最佳实践

**结构化描述模板**（适用于 SocialHub 的分析工具）：

```
[1句：什么情况下调用这个工具，用用户自然语言触发词描述]
[1句：返回什么数据，列举关键字段名]
[可选：参数的核心用法提示，何时设置哪个参数]
[可选：与相邻工具的边界说明，避免混淆]
```

**示例对比**：

当前 `analytics_customers`:
> "Customer base and growth metrics — call this tool when the user asks about customer counts, member growth..."

建议优化方向（不修改代码，仅作设计参考）：
> "Customer base demographics and acquisition — use this tool for questions about HOW MANY customers exist, WHERE customers come from, or the male/female breakdown. Returns total registered, total buyers, active buyers, member split, new acquisitions. Set include_source=true for channel breakdown. DO NOT use this for retention rates (use analytics_retention) or sales revenue (use analytics_orders)."

关键改进：加入**负面边界**（"DO NOT use this for..."），这是减少工具混淆最有效的技术手段之一。

### B.4 动态工具描述（claude-code 模式）

claude-code 的工具定义中，`description()` 是函数而非字符串，根据当前上下文（已有哪些文件、用户在做什么操作）动态生成个性化描述。

**对 SocialHub 的适用性**：
- MCP Python SDK `Tool` 类当前接受静态字符串 `description`
- 动态描述需要通过 `list_tools` handler 在运行时构建 `Tool` 对象列表
- **可行方案**：在 `list_tools` 中根据 tenant_id 注入租户特定信息（如该租户启用了哪些渠道），使工具描述更精准：

  ```python
  # 伪代码示意，不作为实现建议
  # 若租户仅有线上渠道，则去掉 "offline" 相关描述，减少模型困惑
  ```

- **优先级**：P2（静态描述优化先行，动态描述后续迭代）

### B.5 M365 mcp-tools.json Token 预算分析

当前状态：
- 文件记录 8 个工具，实际读取到 4 个工具（mcp-tools.json 内容不完整）
- M365 Declarative Agent 的工具 Schema token 预算为 3000 tokens，当前使用 1172 tokens
- 剩余预算 1828 tokens，有充足空间补充更丰富的工具描述

**建议**：
1. 将 server.py 中已有的高质量描述同步到 mcp-tools.json（避免双重维护漂移）
2. 为每个工具的 `inputSchema` 中的参数补充 `examples` 字段（JSON Schema 支持，不增加实际 token 消耗但提升模型理解）
3. 在 3000 tokens 预算内，将工具描述从平均 40 字符扩展到 150-200 字符

---

## C. MCP Server 稳定性

### C.1 当前 threading + queue 模型的已知问题

**已观察到的代码模式**（server.py）：

```python
_inflight: dict[str, threading.Event] = {}
_inflight_lock = threading.Lock()

# in-flight 去重
event.wait(timeout=180)  # 单次等待 180 秒
```

**问题清单**：

| 问题 | 严重程度 | 说明 |
|------|---------|------|
| _inflight 字典无界增长 | 高 | 若 compute_fn 异常后 `_inflight.pop` 被跳过（理论上 finally 保护，但 KeyboardInterrupt 例外），字典永久膨胀 |
| threading.Event.wait(180) 阻塞线程 | 中 | 在 HTTP 模式下，uvicorn 使用 asyncio；blocking wait 在 async context 中会占用线程池资源 |
| pandas import 在 ProactorEventLoop 内死锁 | 高 | 已知问题，代码注释已标注：`_load_analytics` 必须从普通线程调用，不能在 anyio 线程池中 |
| 缓存 + _inflight 的 TOCTOU 竞态 | 低 | `_get_cached_result` 和 `_inflight.get` 之间无原子性保证，极低概率重复计算 |
| 无心跳机制 | 中 | HTTP 模式下长时间运行的工具调用（rfm、retention）可能被 Render/nginx 的 30 秒空闲超时断开 |

### C.2 asyncio + anyio 迁移的价值和路径

**迁移价值**：
- `asyncio.TaskGroup`（Python 3.11+）提供结构化并发，替代手动 threading.Event 协调
- `anyio.to_thread.run_sync()` 安全地将 pandas 等阻塞操作卸载到线程池，且不干扰事件循环
- MCP Python SDK 内部已基于 anyio；混用 threading 和 asyncio 是当前最大的隐患来源

**迁移路径**（最小侵入）：

```
阶段 1（P0）：高风险点替换
  - _run_with_cache 中的 threading.Event.wait()
    → asyncio.Event().wait()（在 async handler 中）
    或保留 threading 但确保只在线程池中调用
  - _warm_cache 中的 ThreadPoolExecutor
    → asyncio.gather() + anyio.to_thread.run_sync()

阶段 2（P1）：全面 async 化
  - _handle_* 函数改为 async def
  - compute_fn 通过 anyio.to_thread.run_sync(compute_fn) 在线程池执行
  - 统一到 anyio 的结构化并发模型

阶段 3（P2）：任务队列
  - 结合 MCP Tasks 原语，_run_with_cache 返回 task_id
  - 后台异步执行，客户端轮询
```

**关键约束**：pandas 的 import 问题（ProactorEventLoop 死锁）在迁移后需用 `asyncio.to_thread` 或 `anyio.to_thread.run_sync` 包裹，不得在主事件循环线程中 import。

### C.3 连接管理

**心跳机制**（针对 Render 30 秒 idle timeout）：
- Streamable HTTP 规范建议服务端每 15-25 秒发送 SSE keep-alive 注释（`: keep-alive\n\n`）
- 当前 `http_app.py` 是否实现了 keep-alive 需进一步检查
- **Render 平台特殊性**：Render Starter 计划有 100 秒请求超时，长查询需要在 90 秒内返回或切换到异步 Tasks 模式

**断线重连**：
- Streamable HTTP 规范已定义 `Last-Event-ID` 机制
- 当前 `mcp_server/http_app.py` 基于 `mcp` SDK 的 ASGI 适配器，SDK 是否实现重放逻辑取决于版本

**建议（P1）**：
- 在 `http_app.py` 的 `/mcp` 端点包装层中，对超过 25 秒的 GET 响应流注入 keep-alive 帧
- 添加 `X-Request-Id` 响应头，便于 Render 日志追踪

### C.4 背压（Backpressure）处理

**当前问题**：
- 并发工具调用时，多个请求同时触发 `_warm_cache` 或 `_run_with_cache`，`_inflight` 去重逻辑是唯一的并发控制手段
- 没有全局并发上限（如最多 N 个同时运行的重型查询）
- Render Starter 单进程单 worker，内存上限 512MB，pandas + 多并发可能 OOM

**建议（P1）**：
- 引入 `asyncio.Semaphore(3)` 限制重型工具（rfm、retention、ltv）的最大并发数
- 超出并发限制时返回 MCP 错误码（建议自定义错误 `RESOURCE_EXHAUSTED`）而非无限等待

---

## D. 缓存策略优化

### D.1 当前 TTL 缓存的局限

**代码现状**：
```python
_cache: dict[str, tuple[list, float]] = {}
_CACHE_TTL = 900  # 15 分钟

def _get_cached_result(key: str) -> list | None:
    cached = _cache.get(key)
    if cached and time.time() - cached[1] < _CACHE_TTL:
        return cached[0]
    return None
```

**问题分析**：

| 问题 | 风险 | 说明 |
|------|------|------|
| 无 maxsize 上限 | 高 | 36+ 工具 × N 个 tenant × M 个参数组合，_cache 字典无界增长，Render 512MB 内存可能耗尽 |
| 无 LRU 淘汰 | 中 | 长尾低频 key 永久占据内存，热点 key 没有优先保留机制 |
| 无内存用量感知 | 中 | 无法知道缓存当前占用多少内存 |
| TTL 过期不主动清理 | 低 | 过期 entry 在被访问前一直占用内存（lazy eviction）|
| 分析型数据 TTL 固定 15 分钟 | 低 | 实时大盘数据（today）应更短（5 分钟）；历史年报数据（365d）可更长（2 小时）|

### D.2 推荐的缓存改进方案

**方案：分级 TTL + 内存上限（不引入新依赖）**

Python 标准库 `functools.lru_cache` 有 `maxsize` 参数但不支持 TTL。推荐引入 `cachetools`（已是 Python 生态主流，无大型依赖）：

```python
# 设计参考（不作为代码实现）
from cachetools import LRUCache, TTLCache
# 或使用 cachetools.TTLCache(maxsize=500, ttl=900)
# 对不同工具类型使用不同 TTL：
_TTL_BY_TOOL = {
    "analytics_overview": {"today": 300, "30d": 900, "365d": 7200},
    "analytics_rfm": 3600,         # RFM 为慢变数据，可缓存 1 小时
    "analytics_retention": 3600,
    "analytics_funnel": 1800,
    # 其他工具默认 900
}
```

**方案：预热策略优化**

当前预热列表（12 个查询）存在的问题：
- HTTP 模式下 `lifespan` 不调用 `_warm_cache`（代码注释已说明）
- 预热仅在 stdio 模式且 `MCP_TENANT_ID` 不为空时执行
- 预热结果若 15 分钟内未被访问就过期，失去意义

**建议（P1）**：
- HTTP 模式下，在 `lifespan` 的 startup 阶段，根据已知 tenant 列表（从 `MCP_API_KEYS` 解析）触发预热
- 预热优先级排序（先预热热点查询 overview + retention，后预热重型查询 rfm + ltv）
- 预热完成后记录 `INFO` 日志，包含预热条目数和耗时

### D.3 分析型数据的缓存失效策略

**时间 vs 数据变更**：

| 数据类型 | 适用策略 | 建议 TTL |
|---------|---------|---------|
| 当日实时大盘（today）| 时间失效 | 5 分钟 |
| 近 30 天趋势 | 时间失效 | 15 分钟 |
| RFM 分层 | 时间失效（慢变）| 60 分钟 |
| 历史年报（365d）| 时间失效（极慢变）| 2 小时 |
| Campaign 分析 | 时间失效 | 15 分钟 |
| 留存队列 | 时间失效（慢变）| 60 分钟 |

分析型数据的"数据变更触发失效"实现成本极高（需要底层数据管道的变更事件），短期不适合 SocialHub 的架构现状，保持时间失效策略，细化分级 TTL 即可。

---

## E. M365 Declarative Agent 集成优化

### E.1 工具 Schema Token 预算分析

**当前状态**：
- mcp-tools.json：记录 8 个工具（实际文件中仅有 4 个工具的完整定义）
- 声称使用 1172 tokens / 3000 tokens 预算（39%）
- 工具描述极度精简（例："Return order volume and revenue trends for a selected time range."，仅 57 字符）

**优化空间**：
- 当前 1172 tokens 中，工具 Schema 结构（JSON 骨架）本身约占 400 tokens，实际描述文本约 772 tokens
- 3000 tokens 预算允许将平均描述从当前 ~50 字符扩展至 ~250 字符（5 倍）
- 优先补充的信息：意图匹配触发词、关键返回字段名、参数使用时机

**同步漏洞**：server.py 和 mcp-tools.json 的工具描述已发生漂移，建议建立单一来源（SSoT）机制：
- 方案 A：从 server.py 的 TOOLS 列表自动生成 mcp-tools.json（CI 脚本）
- 方案 B：server.py 从 mcp-tools.json 读取描述（M365 作为描述主权文件）
- 推荐方案 A：server.py 是运行时代码，应为主权，M365 JSON 为衍生物

### E.2 Conversation Starters 设计分析

**当前 6 条 Starters**：

| Title | Text | 问题 |
|-------|------|------|
| Overview | "Give me a quick overview of customer health for the last 30 days." | 良好 |
| Retention | "How is customer retention trending recently?" | 良好 |
| RFM | "Show me the customer health overview and sales trend for the last 30 days." | Title 说 RFM，Text 实际触发 overview+orders，不一致 |
| Orders | "How are order volume and revenue trending recently?" | 良好 |
| Campaigns | "How did our latest marketing campaigns perform?" | 良好 |
| Retention detail | "Show retention performance for the last 30 days with a simple comparison." | 与 "Retention" 重复，价值低 |

**最佳实践（Microsoft Learn 官方建议）**：
- Conversation Starters 应展示 Agent 的能力边界，而非重复同类问题
- 每条 Starter 应触发不同的工具或展示不同的参数组合
- Title 与 Text 必须语义一致
- 建议包含一条"复合查询"示例，展示多工具调用能力

**建议重构（6 条覆盖 6 种使用场景）**：

```
1. "业务概览"    → "Give me a business health overview for the last 30 days with period comparison."
2. "订单趋势"    → "Show me daily order volume and revenue for the past 90 days, broken down by channel."
3. "留存分析"    → "What is our 7-day, 30-day, and 90-day customer retention rate?"
4. "客户漏斗"    → "Walk me through the customer lifecycle funnel — how many are new, repeat, loyal, at-risk, or churned?"
5. "活动效果"    → "Which marketing campaigns ran in the last 14 days and how did they perform?"
6. "复合诊断"    → "Give me a full business diagnosis: overview, retention trend, and top campaigns this month."
```

改进点：
- 第 6 条展示复合查询（多工具），体现 Copilot Orchestrator 的核心价值
- 第 2 条使用 `group_by=channel` 参数，测试参数传递准确性
- 第 3 条明确列出多窗口（7/30/90 天），测试数组参数传递

### E.3 Teams App 认证流程分析

**当前架构**：
- 认证方式：API Key（`MCP_API_KEYS=key1:tenant1,key2:tenant2`）
- M365 Plugin 使用 `ApiKeyPluginVault`（Teams Developer Portal 管理密钥）
- 认证中间件：`mcp_server/auth.py`（Starlette BaseHTTPMiddleware + ContextVar）

**已知优化点**：

| 项目 | 当前状态 | 建议 |
|------|---------|------|
| API Key 轮换 | 需手动更新环境变量 + 重启 | 支持多 key 同时有效（已实现：`key1:t1,key2:t1` 允许同一租户有多个 key），但 key 废弃时需要滚动重启 |
| OAuth 2.0 迁移 | 不支持 | MCP 2025-06-18 规范化了 OAuth；M365 支持 Entra ID 集成；长期方向，短期 API Key 够用 |
| 认证失败日志 | 需检查 auth.py 是否记录租户 ID | 应记录 `tenant_id`（脱敏）+ `remote_addr` + `tool_name`，用于审计 |
| Key 泄露响应 | 无紧急撤销机制 | 建议在 `MCP_REVOKED_KEYS` 环境变量中维护撤销列表，auth.py 在认证时检查 |

**M365 2026 扩展性趋势**（Microsoft Ignite 2025 / 2026 路线）：
- Microsoft 365 Agents Toolkit 已支持通过 Visual Studio Code 点击式连接 MCP 端点
- M365 Copilot 正在将 Declarative Agent 能力与 Microsoft 365 Agents（前身 Bot Framework）统一
- 预计 2026 年 Entra ID 原生认证将成为 M365 MCP 集成的标准方式，届时 API Key 方案需迁移

---

## F. 综合优先级矩阵

| 优先级 | 改进项 | 影响维度 | 实施复杂度 | 依赖 |
|--------|-------|---------|-----------|------|
| **P0** | server.py 中工具描述添加负面边界（"不要在X情况下用此工具"）| 工具选择准确率 | 低 | 无 |
| **P0** | mcp-tools.json 描述与 server.py 同步，扩展至 150-200 字符 | M365 工具选择 | 低 | 无 |
| **P0** | _cache 添加 maxsize 上限（防 OOM）| 稳定性 | 低 | cachetools 或自实现 LRU |
| **P1** | HTTP 模式下 lifespan 启动时触发预热（覆盖所有 tenant）| 首次调用延迟 | 中 | 无 |
| **P1** | 分级 TTL：today=5min, 30d=15min, rfm=60min, 365d=2h | 缓存命中率 | 低 | 无 |
| **P1** | 重型工具加 asyncio.Semaphore(3) 并发限制 | 稳定性 | 中 | asyncio |
| **P1** | Conversation Starters 重构（6 条覆盖不同场景）| M365 用户体验 | 低 | 无 |
| **P1** | HTTP keep-alive 帧（防 Render 30s idle timeout）| 稳定性 | 中 | http_app.py |
| **P2** | threading.Event → asyncio.Event（async context 安全）| 稳定性 | 高 | SDK 版本兼容性测试 |
| **P2** | MCP Tasks 包装层（rfm、retention 超时保护）| 长查询可靠性 | 高 | MCP SDK Tasks API |
| **P2** | Elicitation 集成（时间范围消歧、维度选择）| 用户体验 | 高 | 客户端支持确认 |
| **P2** | CI 脚本：从 server.py TOOLS 自动生成 mcp-tools.json | 维护效率 | 中 | CI 环境 |

---

## G. 关键结论

1. **MCP 协议已从"工具调用协议"升级为"Agentic 协议"**。2025-11-25 规范引入的 Tasks、Enhanced Sampling、Elicitation 三大特性，使 MCP Server 可以主动驱动工作流，而非被动响应。SocialHub 应在 P1/P2 阶段逐步接入。

2. **工具描述质量是工具选择准确率的最关键因素**。添加负面边界（"不要在X情况下调用"）和意图触发词，是 ROI 最高的单点优化，且无需改动任何业务逻辑。

3. **threading + asyncio 混用是当前最大的稳定性风险**。pandas ProactorEventLoop 死锁已被代码注释标注，_cache 无界增长是潜在 OOM 风险。P0 阶段应优先修复这两个问题。

4. **M365 集成存在双重漂移**：mcp-tools.json 描述落后于 server.py（定性），且文件只有 4 个工具（非声称的 8 个，需核实是否还有其他工具文件）。应在下个迭代中修复同步机制。

5. **Streamable HTTP Transport 已是业界标准**，SocialHub 已实现。但会话管理（超时、重连、keep-alive）尚需完善，以保证 Render 托管环境下的长连接稳定性。

---

## 参考来源

- [MCP Specification 2025-11-25](https://modelcontextprotocol.io/specification/2025-11-25)
- [One Year of MCP: November 2025 Spec Release](https://blog.modelcontextprotocol.io/posts/2025-11-25-first-mcp-anniversary/)
- [MCP Specs Update - June 2025 (Auth0 Blog)](https://auth0.com/blog/mcp-specs-update-all-about-auth/)
- [MCP's Next Phase: Inside the November 2025 Specification](https://medium.com/@dave-patten/mcps-next-phase-inside-the-november-2025-specification-49f298502b03)
- [Exploring the Future of MCP Transports](https://blog.modelcontextprotocol.io/posts/2025-12-19-mcp-transport-future/)
- [Why MCP Deprecated SSE and Went with Streamable HTTP](https://blog.fka.dev/blog/2025-06-06-why-mcp-deprecated-sse-and-go-with-streamable-http/)
- [MCP Streamable HTTP Transport Specification (2025-03-26)](https://modelcontextprotocol.io/specification/2025-03-26/basic/transports)
- [Introducing Advanced Tool Use - Anthropic Engineering](https://www.anthropic.com/engineering/advanced-tool-use)
- [Writing Effective Tools for Agents - MCP Docs](https://modelcontextprotocol.info/docs/tutorials/writing-effective-tools/)
- [MCP Tool Search - Claude API Docs](https://platform.claude.com/docs/en/agents-and-tools/tool-use/tool-search-tool)
- [What is MCP Tool Search? - atcyrus.com](https://www.atcyrus.com/stories/mcp-tool-search-claude-code-context-pollution-guide)
- [Advanced Caching Strategies for MCP Servers](https://medium.com/@parichay2406/advanced-caching-strategies-for-mcp-servers-from-theory-to-production-1ff82a594177)
- [MCP Async Tasks: Building Long-Running Workflows](https://workos.com/blog/mcp-async-tasks-ai-agent-workflows)
- [Sampling - MCP Specification (2025-06-18)](https://modelcontextprotocol.io/specification/2025-06-18/client/sampling)
- [Memgraph MCP: Elicitation and Sampling Explained](https://memgraph.com/blog/memgraph-mcp-elicitation-and-sampling)
- [Resources - MCP Specification (2025-06-18)](https://modelcontextprotocol.io/specification/2025-06-18/server/resources)
- [Build Declarative Agents for M365 Copilot with MCP](https://devblogs.microsoft.com/microsoft365dev/build-declarative-agents-for-microsoft-365-copilot-with-mcp/)
- [Best Practices for Building Declarative Agents - Microsoft Learn](https://learn.microsoft.com/en-us/microsoft-365/copilot/extensibility/declarative-agent-best-practices)
- [MCP 2025-11-25 Spec Update - WorkOS](https://workos.com/blog/mcp-2025-11-25-spec-update)
- [Anthropic Code Execution with MCP](https://www.anthropic.com/engineering/code-execution-with-mcp)
- [Top 10 Advanced Techniques for Optimizing MCP Server Performance - SuperAGI](https://web.superagi.com/top-10-advanced-techniques-for-optimizing-mcp-server-performance-in-2025/)
