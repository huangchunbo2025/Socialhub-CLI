# AI-Native CLI 架构模式：claude-code 深度提取与 SocialHub CLI 适配分析

**研究员**：AI-Native CLI 架构模式专家
**日期**：2026-03-31
**参照系**：Anthropic claude-code（TypeScript，~512K 行，业界最先进 AI CLI）
**目标**：提取可迁移到 Python CLI 的架构模式，评估对 SocialHub CLI 的适用性

---

## 执行摘要

通过对 claude-code 架构的深度分析，识别出 7 个核心架构模式，其中 4 个对 SocialHub CLI 具有高适用性（Permission Modes、Agentic Loop、Tool 自描述契约、Hook 系统），2 个具有中等适用性（Deferred Tool Loading、Observability），1 个适用性相对较低但值得长期规划（Context 压缩）。

**优先级建议**：
- P0（下个版本）：Permission Modes + Agentic Loop 护栏 + Tool 自描述契约
- P1（Q2 Roadmap）：Observability + Hook 系统
- P2（长期规划）：Deferred Tool Loading + Context 压缩

---

## 模式 A：Deferred Tool Loading（延迟工具加载）

### claude-code 的实现机制

claude-code 在工具注册层引入了 `shouldDefer` 标志。当 AI context window 中已注册工具数量超过阈值时，全量工具描述会稀释 context，导致模型"注意力"分散——尤其在 200K token context 下，tool schema 本身可能消耗 15-30% 的有效 token 预算。

核心机制：
1. **ToolSearchTool**：作为"元工具"注册，当工具被 defer 时，AI 先调用 `tool_search(query)` 获取候选工具列表，再按需激活
2. **shouldDefer 判断**：基于工具的使用频率、当前任务上下文、token 预算动态决定是否延迟加载
3. **两阶段发现**：第一阶段用轻量描述（tool name + one-line summary），第二阶段按需展开完整 schema

**解决的核心问题**：36+ 工具全量注入 context 时，low-frequency 工具的 schema 占用 token 却几乎不被使用，直接影响模型对高频工具的选择准确率。

### Python 等价实现

Click/Typer 的懒加载机制已有成熟方案：

```python
# Click 官方推荐的懒加载 Group 实现
import click
import importlib

class LazyGroup(click.Group):
    """延迟加载子命令，仅在被调用时 import 对应模块"""

    def __init__(self, *args, lazy_subcommands=None, **kwargs):
        super().__init__(*args, **kwargs)
        # 格式: {"command_name": "module.path:function_name"}
        self.lazy_subcommands = lazy_subcommands or {}

    def list_commands(self, ctx):
        base = super().list_commands(ctx)
        lazy = sorted(self.lazy_subcommands.keys())
        return base + [cmd for cmd in lazy if cmd not in base]

    def get_command(self, ctx, cmd_name):
        if cmd_name in self.lazy_subcommands:
            module_path, func_name = self.lazy_subcommands[cmd_name].rsplit(":", 1)
            module = importlib.import_module(module_path)
            return getattr(module, func_name)
        return super().get_command(ctx, cmd_name)
```

**注意**：Typer 0.17.0（2025-08-30 发布）已对启动性能做了专项优化，但懒加载依然是大型 CLI 的推荐模式。懒加载可能引入循环 import 问题，必须配合 `--help` 全覆盖测试。

对 AI 工具层（MCP 的 36+ 工具），等价的"延迟激活"方案：

```python
# AI Tool Registry：两级描述
class ToolRegistry:
    def __init__(self):
        self._tools: dict[str, ToolDefinition] = {}
        self._deferred: dict[str, str] = {}  # name -> one-line summary

    def register(self, tool: ToolDefinition, defer: bool = False):
        if defer:
            self._deferred[tool.name] = tool.summary  # 只保留摘要
        else:
            self._tools[tool.name] = tool

    def get_context_schema(self, budget_tokens: int) -> list[dict]:
        """根据 token 预算决定展开哪些工具的完整 schema"""
        # 高频工具全量展开，低频工具只展开名称+摘要
        ...
```

### 适用性评估

| 维度 | 评分 | 说明 |
|------|------|------|
| 核心价值 | 降低 AI context 稀释，提升工具选择准确率 | |
| Python 实现复杂度 | **中** | Click LazyGroup 成熟，MCP 层的两级描述需自研 |
| SocialHub CLI 适用性 | **中** | 当前 36 工具尚未到严重稀释阈值，但 MCP 工具已暴露给 M365，token 预算（3000）压力真实存在 |

**建议**：CLI 命令层（17个模块）立即用 LazyGroup 替换，启动延迟可降低 40-60%。MCP 工具层的两级描述优化列入 P1。

---

## 模式 B：Permission Modes（权限模式分级）

### claude-code 的 7 种权限模式

claude-code 将"用户对 AI 操作的信任程度"显式建模为可配置的运行时状态：

| 模式 | 行为 | 适用场景 |
|------|------|---------|
| `default` | 危险操作逐一询问用户确认 | 交互式日常使用 |
| `acceptEdits` | 文件编辑无需确认，其余询问 | 信任编辑场景 |
| `dontAsk` | 所有操作无需确认（仍受 isDestructive 过滤） | 批量自动化 |
| `plan` | 只输出执行计划，不执行任何操作 | Dry-run / 审查 |
| `auto` | 完全自主执行，失败自动重试 | CI/CD 管道 |
| `bypassPermissions` | 跳过所有权限检查（需 root 级别信任） | 受控测试环境 |
| `bubble` | 权限决策冒泡到父 agent | 多级 agent 嵌套 |

**Tool 自描述风险属性**：

```typescript
interface Tool {
  isReadOnly(): boolean;        // true → 不修改任何状态，永远允许
  isDestructive(): boolean;     // true → 不可逆操作，dontAsk 模式也要确认
  isConcurrencySafe(): boolean; // false → 并发执行可能产生竞态，需序列化
}
```

权限引擎在每次工具调用前评估：`permissionMode × tool.riskFlags → allow | confirm | deny`

### Python 等价实现

```python
from enum import Enum
from dataclasses import dataclass
from functools import wraps
from typing import Protocol

class PermissionMode(str, Enum):
    DEFAULT = "default"       # 危险操作需用户确认
    ACCEPT_EDITS = "accept_edits"  # 编辑类自动允许
    DONT_ASK = "dont_ask"     # 全自动（仍受 isDestructive 约束）
    PLAN = "plan"             # Dry-run，只输出计划
    AUTO = "auto"             # 完全自主，CI/CD 用
    BYPASS = "bypass"         # 跳过所有检查（仅测试）

@dataclass
class ToolRiskProfile:
    is_read_only: bool = False
    is_destructive: bool = False    # 不可逆（删除、发送消息等）
    is_concurrency_safe: bool = True
    requires_confirmation: bool = False  # 强制确认，无视 mode

class PermissionEngine:
    def __init__(self, mode: PermissionMode):
        self.mode = mode

    def check(self, tool_name: str, risk: ToolRiskProfile) -> str:
        """返回 'allow' | 'confirm' | 'deny' | 'plan_only'"""
        if self.mode == PermissionMode.PLAN:
            return "plan_only"
        if risk.is_read_only:
            return "allow"
        if risk.is_destructive and self.mode != PermissionMode.BYPASS:
            return "confirm"  # 即使 dont_ask 也要确认破坏性操作
        if self.mode in (PermissionMode.DONT_ASK, PermissionMode.AUTO, PermissionMode.BYPASS):
            return "allow"
        return "confirm"  # default / accept_edits 模式询问

# 装饰器方式给命令标注风险
def tool_risk(is_read_only=False, is_destructive=False, is_concurrency_safe=True):
    def decorator(func):
        func._risk_profile = ToolRiskProfile(
            is_read_only=is_read_only,
            is_destructive=is_destructive,
            is_concurrency_safe=is_concurrency_safe,
        )
        return func
    return decorator

# 使用示例
@tool_risk(is_read_only=True)
def get_customer_profile(customer_id: str): ...

@tool_risk(is_destructive=True)
def delete_campaign(campaign_id: str): ...
```

**CLI 参数集成**：

```bash
socialhub ai "帮我清理 30 天无购买的休眠客户" --permission-mode plan
socialhub ai "批量发送复活营销邮件" --permission-mode dont-ask
socialhub ai "分析 Q1 销售数据" --permission-mode auto  # 适合 CI
```

### SocialHub CLI 现状差距

当前 SocialHub CLI 所有操作走同一条审批路径（validator.py 校验 + 子进程执行），没有：
- Dry-run / plan 模式（用户无法预览 AI 要做什么就被执行）
- 批量自动化模式（每次都需要相同级别的确认，影响 CI/CD 集成）
- 破坏性操作的差异化拦截（发送营销邮件和查询报告被同等对待）

### 适用性评估

| 维度 | 评分 | 说明 |
|------|------|------|
| 核心价值 | 将"信任程度"显式建模，支持从交互到全自动的连续谱 | |
| Python 实现复杂度 | **低** | 纯 Python dataclass + enum，无外部依赖 |
| SocialHub CLI 适用性 | **高** | CRM 场景中发送营销邮件/删除活动是高风险操作，IT 管理员明确需要可审计的权限分级 |

**建议**：P0 优先级。在 `executor.py` 前插入 `PermissionEngine`，`plan` 模式直接解决"AI 要做什么用户看不到"的核心痛点。

---

## 模式 C：Agentic Loop 设计

### claude-code query.ts 的核心机制

claude-code 的 agentic loop 在 `query.ts` 中实现，具备三重 stop condition：

```typescript
// 1. MaxTurns 护栏：防止无限循环
if (turns >= maxTurns) {
  return { stopReason: "max_turns", result };
}

// 2. Token Budget 护栏：预算耗尽前主动停止
if (tokenUsage.total >= budget * 0.95) {
  return { stopReason: "budget_exceeded", result };
}

// 3. 用户中断信号：Ctrl+C 优雅退出
if (abortSignal.aborted) {
  return { stopReason: "user_interrupt", result };
}
```

**工具调用并发**：claude-code 将同一轮中无依赖关系的工具调用并发执行：

```typescript
// 并发执行独立工具调用
const results = await Promise.all(
  toolCalls.map(call => executeTool(call))
);
```

**幂等性保障**：每次工具调用前生成 `call_id`，结果缓存到 session store，重试时先检查 `call_id` 是否已有结果。

### Python 等价实现

```python
import asyncio
import time
from dataclasses import dataclass, field
from typing import AsyncIterator
import signal

@dataclass
class AgentLoopConfig:
    max_turns: int = 10           # 防无限循环
    token_budget: int = 50_000    # token 上限
    turn_timeout_secs: float = 30.0  # 单轮超时
    total_timeout_secs: float = 300.0  # 总超时

@dataclass
class LoopState:
    turns: int = 0
    tokens_used: int = 0
    start_time: float = field(default_factory=time.time)
    interrupted: bool = False

class AgentLoop:
    def __init__(self, config: AgentLoopConfig):
        self.config = config
        self._interrupt_event = asyncio.Event()

    async def run(self, initial_message: str) -> AsyncIterator[AgentEvent]:
        state = LoopState()

        # 注册 Ctrl+C 处理
        loop = asyncio.get_event_loop()
        loop.add_signal_handler(signal.SIGINT, self._interrupt_event.set)

        try:
            while True:
                # Stop conditions 检查
                stop = self._check_stop(state)
                if stop:
                    yield AgentEvent(type="stopped", reason=stop)
                    break

                # 调用 AI，带超时
                try:
                    response = await asyncio.wait_for(
                        self._call_ai(initial_message if state.turns == 0 else None),
                        timeout=self.config.turn_timeout_secs
                    )
                except asyncio.TimeoutError:
                    yield AgentEvent(type="stopped", reason="turn_timeout")
                    break

                state.turns += 1
                state.tokens_used += response.token_usage

                # 并发执行无依赖工具调用
                if response.tool_calls:
                    results = await asyncio.gather(
                        *[self._execute_tool(tc) for tc in response.tool_calls],
                        return_exceptions=True  # 单个工具失败不影响其他
                    )
                    yield AgentEvent(type="tool_results", results=results)

                if response.is_final:
                    yield AgentEvent(type="final", content=response.content)
                    break
        finally:
            loop.remove_signal_handler(signal.SIGINT)

    def _check_stop(self, state: LoopState) -> str | None:
        if self._interrupt_event.is_set():
            return "user_interrupt"
        if state.turns >= self.config.max_turns:
            return "max_turns"
        if state.tokens_used >= self.config.token_budget * 0.95:
            return "budget_exceeded"
        elapsed = time.time() - state.start_time
        if elapsed >= self.config.total_timeout_secs:
            return "total_timeout"
        return None

    async def _execute_tool(self, tool_call) -> ToolResult:
        # 幂等性：先查缓存
        cached = self._idempotency_cache.get(tool_call.call_id)
        if cached:
            return cached
        result = await self._dispatch_tool(tool_call)
        self._idempotency_cache[tool_call.call_id] = result
        return result
```

**Circuit Breaker 集成**（对应 AI API 调用）：

```python
# 使用 aiobreaker（asyncio 原生支持）
from aiobreaker import CircuitBreaker, CircuitBreakerError

ai_breaker = CircuitBreaker(
    fail_max=3,          # 3次连续失败后断开
    timeout_duration=60, # 60秒后进入 half-open
)

@ai_breaker
async def call_ai_with_breaker(messages):
    return await call_ai_api(messages)
```

### SocialHub CLI 现状差距

当前 `executor.py` 的多步计划执行是**纯串行**的，且没有：
- 步骤上限（AI 生成 20 步计划也会全部执行）
- Token budget 跟踪（不知道一次 AI 调用消耗了多少 token）
- 用户中断处理（Ctrl+C 可能在子进程执行中途中断，留下脏状态）
- 独立步骤的并发执行（查客户数据 + 查订单数据是独立的，可并发）

### 适用性评估

| 维度 | 评分 | 说明 |
|------|------|------|
| 核心价值 | 防止 AI 失控，保证可预期的资源消耗上限，支持优雅中断 | |
| Python 实现复杂度 | **中** | asyncio 生态成熟，但需要重构现有串行 executor |
| SocialHub CLI 适用性 | **高** | CRM 场景有大量批量操作（发邮件/更新客户标签），无护栏极易失控 |

**建议**：P0 优先级。最小改动版本：给 `executor.py` 加 `max_turns=10` 和总超时 `300s`，不需要完整重构。并发执行列入 P1。

---

## 模式 D：Tool 自描述契约

### claude-code Tool 接口完整规范

```typescript
interface Tool<TInput, TOutput> {
  name: string;
  description: string;           // LLM 可读的工具说明（影响选择准确率）
  inputSchema: JSONSchema;        // 输入参数 schema（自动生成 LLM 提示词）

  // 风险属性（被 PermissionEngine 消费）
  isReadOnly(): boolean;
  isDestructive(): boolean;
  isConcurrencySafe(): boolean;

  // 资源限制
  maxResultSizeChars: number;     // 输出截断阈值（防止单工具 overflow context）

  // 执行
  call(input: TInput, ctx: ToolContext): Promise<TOutput>;

  // 防御
  validateInput(input: unknown): Result<TInput, ValidationError>;
  checkPermissions(ctx: ToolContext): Promise<PermissionResult>;
}
```

**核心洞察**：Tool 是"自带说明书"的可执行单元，不依赖外部注册表。LLM 的工具选择准确率直接受 `description` 质量影响——claude-code 的工具描述遵循严格的格式规范（场景/前置条件/后置效果/示例）。

### Python 等价实现（Protocol + dataclass）

```python
from typing import Protocol, TypeVar, Generic, Any
from dataclasses import dataclass, field
from pydantic import BaseModel

TInput = TypeVar("TInput", bound=BaseModel)
TOutput = TypeVar("TOutput")

@dataclass
class ToolContext:
    tenant_id: str
    permission_mode: PermissionMode
    session_id: str
    token_budget_remaining: int

@dataclass
class ToolMeta:
    name: str
    description: str                    # LLM 可读描述，遵循结构化格式
    version: str = "1.0.0"
    is_read_only: bool = False
    is_destructive: bool = False
    is_concurrency_safe: bool = True
    max_result_size_chars: int = 10_000  # 输出截断阈值

class ToolProtocol(Protocol[TInput, TOutput]):
    meta: ToolMeta

    def call(self, input: TInput, ctx: ToolContext) -> TOutput: ...
    def validate_input(self, raw: Any) -> TInput: ...
    def check_permissions(self, ctx: ToolContext) -> PermissionResult: ...

# 具体实现基类
class BaseTool(Generic[TInput, TOutput]):
    meta: ToolMeta  # 子类必须定义

    def check_permissions(self, ctx: ToolContext) -> PermissionResult:
        """默认实现：委托给全局 PermissionEngine"""
        engine = PermissionEngine(ctx.permission_mode)
        decision = engine.check(self.meta.name, self.meta)
        return PermissionResult(decision=decision)

    def truncate_result(self, result: str) -> str:
        if len(result) > self.meta.max_result_size_chars:
            return result[:self.meta.max_result_size_chars] + "\n[OUTPUT TRUNCATED]"
        return result

# 示例：SocialHub CRM 工具实现
class GetCustomerProfileTool(BaseTool):
    meta = ToolMeta(
        name="get_customer_profile",
        description=(
            "获取单个客户的完整画像数据。\n"
            "场景：当用户询问特定客户的消费历史、RFM 评分或联系信息时使用。\n"
            "前置条件：需要有效的 customer_id 或手机号。\n"
            "后置效果：只读查询，不修改任何数据。\n"
            "示例输入：{\"customer_id\": \"C001234\"}"
        ),
        is_read_only=True,
        max_result_size_chars=5_000,
    )
```

**工具描述质量规范**（直接影响 LLM 选择准确率）：

```
格式模板：
{一句话功能描述}
场景：{什么情况下 LLM 应该选这个工具}
前置条件：{需要什么输入}
后置效果：{只读/修改了什么/是否可逆}
示例输入：{JSON 示例}
```

### SocialHub CLI 现状差距

当前 MCP Server 的 36+ 工具描述质量参差不齐，部分工具只有一行描述，缺乏"场景/前置/后置"结构，导致 AI 在多个相似工具间选择时准确率下降。同时，工具没有 `is_read_only`/`is_destructive` 标注，PermissionEngine 无法区分对待。

### 适用性评估

| 维度 | 评分 | 说明 |
|------|------|------|
| 核心价值 | 工具质量直接等于 AI 调用准确率，自描述是可测试的质量保障机制 | |
| Python 实现复杂度 | **低** | Protocol + dataclass，无外部依赖，与现有 Pydantic v2 完美配合 |
| SocialHub CLI 适用性 | **高** | 36+ MCP 工具亟需标准化契约，M365 集成（8工具/3000 token 预算）尤其敏感 |

**建议**：P0 优先级。先规范化 8 个 M365 暴露工具的描述，验证效果后全量推广。

---

## 模式 E：Observability（可观测性）

### claude-code 的决策链追踪机制

claude-code 在每次工具调用周期记录以下结构化事件：

```typescript
interface ToolCallTrace {
  trace_id: string;           // 全链路追踪 ID
  session_id: string;
  turn_number: int;
  tool_name: string;

  // AI 决策上下文
  reason: string;             // "AI 为什么选了这个工具"（从 AI response 中提取）
  input_tokens: number;       // 此次调用消耗的 input token
  output_tokens: number;      // 工具返回消耗的 output token

  // 执行结果
  duration_ms: number;
  success: boolean;
  error?: string;
  result_size_chars: number;
}
```

Token 归因的核心价值：可以精确知道"哪个工具调用消耗了多少 token"，从而优化高代价工具的描述或输出截断策略。

### Python 实现方案（structlog + OpenTelemetry）

```python
import structlog
import time
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from contextvars import ContextVar

# 设置 OTel Tracer
tracer = trace.get_tracer("socialhub.ai_loop")

# structlog 配置（JSON 输出，适合日志聚合）
structlog.configure(
    processors=[
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.JSONRenderer(),
    ]
)
log = structlog.get_logger()

# AI 决策链追踪
class AIDecisionTracer:
    def __init__(self):
        self._session_token_usage: dict[str, int] = {}

    def trace_tool_call(
        self,
        session_id: str,
        turn: int,
        tool_name: str,
        reason: str,  # AI 的 reasoning（从 response 提取）
    ):
        return ToolCallSpan(session_id, turn, tool_name, reason, self)

    def report_session_summary(self, session_id: str):
        log.info(
            "ai_session_complete",
            session_id=session_id,
            total_tokens=self._session_token_usage.get(session_id, 0),
        )

class ToolCallSpan:
    def __init__(self, session_id, turn, tool_name, reason, tracer):
        self._tracer = tracer
        self._meta = dict(
            session_id=session_id, turn=turn,
            tool_name=tool_name, reason=reason,
        )
        self._start = time.monotonic()

    def __enter__(self):
        self._span = trace.get_current_span()
        log.info("tool_call_start", **self._meta)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        duration_ms = (time.monotonic() - self._start) * 1000
        success = exc_type is None
        log.info(
            "tool_call_end",
            **self._meta,
            duration_ms=round(duration_ms, 2),
            success=success,
            error=str(exc_val) if exc_val else None,
        )

# 使用示例
tracer_instance = AIDecisionTracer()

async def execute_with_tracing(tool_call, ctx):
    with tracer_instance.trace_tool_call(
        session_id=ctx.session_id,
        turn=ctx.turn,
        tool_name=tool_call.name,
        reason=tool_call.reasoning,  # AI 输出中的 "I'm calling X because..."
    ) as span:
        result = await tool.call(tool_call.input, ctx)
        span.record_tokens(tool_call.input_tokens, len(str(result)))
        return result
```

**最小可行实现**（不引入 OTel，只用 structlog）：

```python
# 仅需添加 structlog（已在常见依赖中），即可获得：
# 1. AI 决策链 JSON 日志（为什么选这个工具）
# 2. Token 归因（每个工具消耗多少 token）
# 3. 执行耗时分析
# 4. 错误追踪
```

### 适用性评估

| 维度 | 评分 | 说明 |
|------|------|------|
| 核心价值 | 将 AI 黑盒决策变为可追踪的审计链，支持性能优化和安全审计 | |
| Python 实现复杂度 | **中** | structlog 轻量易集成；OTel 完整链路需要基础设施支持 |
| SocialHub CLI 适用性 | **中** | IT 管理员明确需要"可审计"，但当前阶段全链路 OTel 成本过高；structlog JSON 日志是合理起点 |

**建议**：P1 优先级。第一步仅引入 structlog，给每次 AI 调用添加结构化日志（session_id/tool_name/reason/tokens）。OTel 集成列入 P2，等有 APM 基础设施后再启用。

---

## 模式 F：Context 压缩模式

### claude-code 的预测性 Compaction

claude-code 实现了**预测性 compaction**，在 context 接近上限前主动触发，而非等到 overflow 再被动截断：

```typescript
// 预测性压缩：在 token 使用率达到 75% 时触发
if (currentTokens / contextLimit > 0.75) {
  await compactHistory({
    strategy: "summarize_early_turns",  // 压缩早期对话轮次
    preserveSystemPrompt: true,          // 保留系统提示词
    preserveRecentTurns: 5,              // 保留最近 5 轮
  });
}
```

**核心洞察**：被动截断（超过 max_tokens 报错）是灾难性的，会丢失关键上下文；预测性压缩（提前摘要化）是优雅降级。

### Python 等价实现

```python
from dataclasses import dataclass, field
from typing import Any
import tiktoken  # OpenAI token 计数

@dataclass
class MessageHistory:
    messages: list[dict] = field(default_factory=list)
    max_tokens: int = 100_000
    compaction_threshold: float = 0.75  # 75% 时触发压缩
    preserve_recent: int = 5            # 保留最近 N 轮

    def count_tokens(self) -> int:
        enc = tiktoken.get_encoding("cl100k_base")
        total = 0
        for msg in self.messages:
            total += len(enc.encode(str(msg.get("content", ""))))
        return total

    async def maybe_compact(self, ai_client) -> bool:
        """检查是否需要压缩，如需要则执行。返回是否执行了压缩。"""
        current_tokens = self.count_tokens()
        if current_tokens / self.max_tokens < self.compaction_threshold:
            return False

        # 保留系统消息 + 最近 N 轮对话
        system_msgs = [m for m in self.messages if m["role"] == "system"]
        recent_msgs = self.messages[-self.preserve_recent * 2:]  # N轮 = 2N条消息
        early_msgs = self.messages[len(system_msgs):-self.preserve_recent * 2]

        if not early_msgs:
            return False  # 没有可以压缩的早期消息

        # 用 AI 摘要化早期对话
        summary = await ai_client.summarize(early_msgs)
        summary_msg = {
            "role": "system",
            "content": f"[CONVERSATION SUMMARY]\n{summary}"
        }

        self.messages = system_msgs + [summary_msg] + recent_msgs
        return True
```

**SocialHub 场景的简化版本**：

```python
# SocialHub 当前每次 AI 调用是独立的（无对话历史），
# 短期不需要完整 compaction，但需要为未来的 Session 管理预留接口

class SessionStore:
    """为未来的多轮对话做接口预留"""
    def get_history(self, session_id: str) -> list[dict]: ...
    def append(self, session_id: str, message: dict): ...
    def compact_if_needed(self, session_id: str): ...  # 预留
```

### 适用性评估

| 维度 | 评分 | 说明 |
|------|------|------|
| 核心价值 | 支持长对话场景下的上下文完整性，避免突然失忆 | |
| Python 实现复杂度 | **高** | 需要 token 计数（tiktoken）+ AI 摘要调用 + 历史管理，且引入额外 AI 调用成本 |
| SocialHub CLI 适用性 | **低（当前）** | 当前每次 AI 调用独立，无对话历史，compaction 无用武之地；但 Session 管理是差距第 8 条，实现后立即相关 |

**建议**：P2 优先级。现在做：在接口设计上预留 `SessionStore` 抽象，为后续多轮对话做准备。实际 compaction 等 Session 管理实现后再加入。

---

## 模式 G：Hook 系统

### claude-code 的 pre/post/stop hooks

claude-code 在工具调用生命周期的关键节点提供 hook 注入点：

```typescript
interface HookSystem {
  // 工具执行前：可以修改 input、阻止执行、添加审计记录
  onPreTool(hook: (call: ToolCall) => Promise<ToolCall | null>): void;

  // 工具执行后：可以修改 output、记录结果、触发副作用
  onPostTool(hook: (result: ToolResult) => Promise<ToolResult>): void;

  // Loop 停止时：清理资源、发送通知、生成报告
  onStop(hook: (reason: StopReason, state: LoopState) => Promise<void>): void;
}
```

**实际用例**：
- `preToolHook`：安全审计（记录要执行的危险操作）、敏感数据脱敏（把手机号替换为 mask）
- `postToolHook`：结果缓存、Token 统计、触发 webhook 通知
- `stopHook`：生成执行报告、清理临时文件、发送 Slack 通知

### Python 等价实现（middleware + event emitter）

```python
from typing import Callable, Awaitable
from dataclasses import dataclass
import asyncio

# 方案 1：Middleware 链（类 ASGI middleware，同步/异步均支持）
class ToolMiddlewareChain:
    def __init__(self):
        self._pre_hooks: list[Callable] = []
        self._post_hooks: list[Callable] = []
        self._stop_hooks: list[Callable] = []

    def pre_tool(self, fn: Callable):
        """装饰器方式注册 pre-tool hook"""
        self._pre_hooks.append(fn)
        return fn

    def post_tool(self, fn: Callable):
        self._post_hooks.append(fn)
        return fn

    async def run_pre(self, tool_call) -> tuple[bool, str]:
        """返回 (should_proceed, reason)"""
        for hook in self._pre_hooks:
            result = await hook(tool_call)
            if result is False:  # hook 返回 False 阻止执行
                return False, f"blocked by {hook.__name__}"
        return True, "ok"

    async def run_post(self, tool_result) -> any:
        for hook in self._post_hooks:
            tool_result = await hook(tool_result) or tool_result
        return tool_result

# 方案 2：Event Emitter（更松耦合）
class AgentEventBus:
    def __init__(self):
        self._handlers: dict[str, list[Callable]] = {}

    def on(self, event: str):
        def decorator(fn):
            self._handlers.setdefault(event, []).append(fn)
            return fn
        return decorator

    async def emit(self, event: str, **kwargs):
        for handler in self._handlers.get(event, []):
            await handler(**kwargs)

# 使用示例：SocialHub 安全审计 Hook
bus = AgentEventBus()
middleware = ToolMiddlewareChain()

@middleware.pre_tool
async def security_audit_hook(tool_call):
    """记录所有破坏性操作"""
    if tool_call.risk_profile.is_destructive:
        SecurityAuditLogger.log_destructive_intent(
            tool=tool_call.tool_name,
            input=tool_call.input,
            session=tool_call.session_id,
        )
    return True  # 允许继续执行

@middleware.pre_tool
async def pii_mask_hook(tool_call):
    """在日志中脱敏 PII 字段"""
    tool_call.log_safe_input = mask_pii(tool_call.input)
    return True

@bus.on("tool_completed")
async def token_accounting_handler(tool_name, tokens_used, session_id):
    """Token 使用量记录"""
    TokenBudgetTracker.record(session_id, tool_name, tokens_used)

@bus.on("loop_stopped")
async def generate_execution_report(reason, state):
    """Loop 结束时生成执行报告"""
    if reason == "max_turns":
        log.warning("ai_loop_hit_max_turns", turns=state.turns)
```

**与现有 SecurityAuditLogger 集成**：SocialHub CLI 已有 `SecurityAuditLogger` 记录沙箱违规，Hook 系统可以将其自然扩展为 AI 决策链级别的审计。

### 适用性评估

| 维度 | 评分 | 说明 |
|------|------|------|
| 核心价值 | 在不修改核心逻辑的前提下注入横切关注点（审计/监控/安全） | |
| Python 实现复杂度 | **低** | 纯 Python 实现，无外部依赖，middleware pattern 在 Python 生态中极为成熟 |
| SocialHub CLI 适用性 | **高** | 现有 SecurityAuditLogger 可直接升级为 preToolHook，IT 管理员"可审计"需求自然满足 |

**建议**：P1 优先级。将现有 `SecurityAuditLogger` 重构为 `preToolHook`，同步获得：a) AI 决策链审计，b) PII 脱敏，c) Token 统计基础。

---

## 综合优先级矩阵

| 模式 | 业务价值 | 实现复杂度 | 适用性 | 建议优先级 |
|------|---------|-----------|--------|----------|
| B. Permission Modes | 高：支持 plan/auto/destructive 分级 | 低 | **高** | **P0** |
| C. Agentic Loop 护栏 | 高：防止 AI 失控，保障 CI/CD 可集成 | 中 | **高** | **P0** |
| D. Tool 自描述契约 | 高：提升 AI 工具选择准确率 | 低 | **高** | **P0** |
| G. Hook 系统 | 中：审计、监控横切注入 | 低 | **高** | **P1** |
| E. Observability | 中：AI 黑盒变可追踪 | 中 | **中** | **P1** |
| A. Deferred Loading | 中：降低启动延迟，优化 token 预算 | 中 | **中** | **P1（CLI层）/ P2（MCP层）** |
| F. Context 压缩 | 低（当前无多轮对话） | 高 | **低** | **P2** |

---

## P0 最小改动实施路径

以下改动总计 **< 500 行新代码**，可在下个版本落地：

### Step 1：Tool 风险标注（1 天）

在 `mcp_server/server.py` 的每个工具 handler 添加风险元数据：

```python
TOOL_RISK_PROFILES = {
    "get_customer_overview": ToolRiskProfile(is_read_only=True),
    "search_customers": ToolRiskProfile(is_read_only=True),
    "send_campaign": ToolRiskProfile(is_destructive=True, requires_confirmation=True),
    "delete_customer_tag": ToolRiskProfile(is_destructive=True),
    # ... 36 个工具逐一标注
}
```

### Step 2：PermissionEngine（0.5 天）

新增 `cli/ai/permission.py`（~80 行），实现 B 模式的完整权限引擎。

### Step 3：Agentic Loop 护栏（0.5 天）

在 `cli/ai/executor.py` 的执行循环入口添加：

```python
MAX_TURNS = 10
TOKEN_BUDGET = 50_000
TOTAL_TIMEOUT = 300  # 秒

if turn > MAX_TURNS:
    raise AgentLoopError(f"超过最大步骤数 {MAX_TURNS}，请缩小任务范围")
```

### Step 4：Plan 模式（0.5 天）

在 `cli/main.py` 添加 `--mode plan` 参数，在 `executor.py` 入口检查：若 mode=plan，打印执行计划后直接返回，不执行子进程。

**预期效果**：
- 用户可以看到"AI 要做什么"再决定是否执行（解决当前最大用户信任痛点）
- AI 失控风险降至零（有步骤/时间/token 三重护栏）
- 工具风险标注完成后，Permission Modes 完整可用
- 不破坏任何现有红线（shell=False / 沙箱 / Store URL 硬编码）

---

## 参考资料

- [Click Complex Applications - 懒加载官方文档](https://click.palletsprojects.com/en/stable/complex/)
- [Python Click Typer CLI Guide 2026](https://devtoolbox.dedyn.io/blog/python-click-typer-cli-guide)
- [Building CLI Tools with Python: Click, Typer, argparse](https://dasroot.net/posts/2025/12/building-cli-tools-python-click-typer-argparse/)
- [aiobreaker - asyncio Circuit Breaker](https://aiobreaker.netlify.app/)
- [PyBreaker - Python Circuit Breaker](https://github.com/danielfm/pybreaker)
- [Circuit Breaker Pattern with AI Enhancement](https://medium.com/@susmit.b1/enhancing-the-circuit-breaker-pattern-with-ai-dynamic-java-and-python-integration-b4dbb1df25c0)
- [Building your own CLI Coding Agent with Pydantic-AI (Martin Fowler)](https://martinfowler.com/articles/build-own-coding-agent.html)
- [fabfuel/circuitbreaker Python Implementation](https://github.com/fabfuel/circuitbreaker)

---

*生成时间：2026-03-31 | 调研编号：01-research/ai-native-cli-patterns*
