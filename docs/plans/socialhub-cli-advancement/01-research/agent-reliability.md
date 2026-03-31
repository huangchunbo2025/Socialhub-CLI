# AI Agent 执行链可靠性模式调研

**调研维度**: ai-agent-reliability
**日期**: 2026-03-31
**参照系**: claude-code 生产架构 + 业界 2024-2026 最佳实践
**适用范围**: SocialHub CLI `cli/ai/` 执行层

---

## 调研背景与现状诊断

### 当前 AI 执行链架构

```
用户自然语言输入
    ↓
call_ai_api()          ← client.py: threading + httpx，线性 retry（×3）
    ↓
extract_plan_steps()   ← parser.py: 正则解析 [PLAN_START]...[PLAN_END]
    ↓
validate_command()     ← validator.py: Typer 命令树校验
    ↓
execute_plan()         ← executor.py: 串行 subprocess，用户确认失败续行
    ↓
generate_insights()    ← insights.py: AI 二次调用生成分析摘要
```

### 现状问题清单（对照 00-goal.md 差距 #3、#4、#7）

| 问题 | 影响 | 严重度 |
|------|------|--------|
| `execute_plan` 无步骤上限 | 恶意/幻觉 AI 响应触发无界执行 | P0 |
| 无工具级熔断 | 同一命令反复失败时 LLM 可能陷入循环 | P0 |
| 正则解析 `[PLAN_START]...[PLAN_END]` | 格式变体导致 0 步骤解析 | P1 |
| 重复执行同一查询无去重 | 产生重复 API 调用副作用 | P1 |
| 无 AI 决策链追踪 | token 消耗不可归因，调试困难 | P1 |
| 多步计划串行执行 | 独立只读命令浪费 I/O 等待时间 | P2 |
| `client.py` 用 `threading` 做 spinner | 与 asyncio 混用存在稳定性隐患 | P2 |

---

## 模式 A：Circuit Breaker（熔断器）

### 现状分析

`executor.py` 的 `execute_plan()` 在步骤失败时仅提示用户确认是否继续，没有跟踪工具维度的失败频率。当 LLM 生成的计划中包含重复调用同一无效命令时（例如幻觉出不存在的参数），每次失败都会打断用户进行确认，无法自动降级。

`client.py` 的重试逻辑（`max_retries=3`，线性退避 2s/4s）仅处理网络层超时，不涉及 AI 输出质量层面的失败。

### 业界模式

Circuit Breaker 的三态状态机（来源：Portkey、dasroot.net 调研）：

```
CLOSED（正常）→ 失败计数 ≥ threshold → OPEN（熔断）
OPEN → 超过 recovery_timeout → HALF_OPEN（试探）
HALF_OPEN → 试探成功 → CLOSED；试探失败 → OPEN
```

对 AI Agent 的适配扩展：工具级熔断（不是 API 级），针对 LLM 反复生成同类无效命令时自动降级为人工接管或跳过该工具。

### SocialHub CLI 具体问题

- `sh analytics customers --segment vip` 如果当前 MCP 源无此字段，validator 通过但 subprocess 失败
- LLM 可能在多步计划中反复尝试该命令（不同参数变体），每次都触发用户确认，体验极差
- 无状态跟踪，重新发起 AI 查询时失败历史归零

### 改进方案

**工具级失败计数器 + 自动熔断**，作用域为单次 `execute_plan` 调用生命周期。

实现复杂度：**低**（~60 行，无新依赖）
用户体验影响：**正向** — 消除反复确认循环，自动跳过持续失败的步骤

**MVP 代码示例**

```python
# cli/ai/circuit_breaker.py
from dataclasses import dataclass, field
from enum import Enum
import time


class BreakerState(Enum):
    CLOSED = "closed"       # 正常执行
    OPEN = "open"           # 熔断，拒绝执行
    HALF_OPEN = "half_open" # 试探恢复


@dataclass
class ToolCircuitBreaker:
    """单次 execute_plan 生命周期内的工具级熔断器。"""
    failure_threshold: int = 2        # 连续失败 N 次后熔断
    recovery_timeout: float = 30.0    # 熔断后等待秒数（计划级可设短些）

    _counters: dict[str, int] = field(default_factory=dict)
    _states: dict[str, BreakerState] = field(default_factory=dict)
    _open_since: dict[str, float] = field(default_factory=dict)

    def _key(self, cmd: str) -> str:
        """提取命令的工具前缀作为熔断粒度，如 'sh analytics customers'。"""
        parts = cmd.split()
        return " ".join(parts[:3]) if len(parts) >= 3 else cmd

    def is_allowed(self, cmd: str) -> tuple[bool, str]:
        """返回 (是否允许执行, 拒绝原因)。"""
        key = self._key(cmd)
        state = self._states.get(key, BreakerState.CLOSED)

        if state == BreakerState.OPEN:
            elapsed = time.time() - self._open_since.get(key, 0)
            if elapsed >= self.recovery_timeout:
                self._states[key] = BreakerState.HALF_OPEN
                return True, ""
            return False, f"Circuit OPEN for '{key}' (failed {self._counters[key]}x), skipping"

        return True, ""

    def record_success(self, cmd: str) -> None:
        key = self._key(cmd)
        self._counters[key] = 0
        self._states[key] = BreakerState.CLOSED

    def record_failure(self, cmd: str) -> BreakerState:
        key = self._key(cmd)
        self._counters[key] = self._counters.get(key, 0) + 1
        if self._counters[key] >= self.failure_threshold:
            self._states[key] = BreakerState.OPEN
            self._open_since[key] = time.time()
        return self._states.get(key, BreakerState.CLOSED)
```

**在 `execute_plan` 中集成（最小改动）**

```python
# executor.py 中 execute_plan() 函数内添加
from .circuit_breaker import ToolCircuitBreaker, BreakerState

def execute_plan(steps: list[dict], original_query: str = "") -> None:
    breaker = ToolCircuitBreaker(failure_threshold=2)
    # ... 现有代码 ...

    for idx, step in enumerate(steps):
        command = step["command"]

        # 熔断检查
        allowed, reason = breaker.is_allowed(command)
        if not allowed:
            console.print(f"[yellow][SKIP][/yellow] {reason}")
            all_results.append({"step": step["number"], "success": False,
                                 "output": reason, "skipped": True})
            continue

        success, output = execute_command(command)

        if success:
            breaker.record_success(command)
        else:
            state = breaker.record_failure(command)
            if state == BreakerState.OPEN:
                console.print(f"[red]Circuit breaker OPEN for this tool — auto-skipping subsequent calls[/red]")
```

---

## 模式 B：执行步骤上限与 Budget

### 现状分析

`execute_plan()` 接受 `steps: list[dict]`，长度完全由 AI 响应决定。`extract_plan_steps()` 在 `parser.py` 中无上限限制。当前 `max_tokens=1000`（`client.py` 第 77、99 行）间接限制了步骤数，但这是模型层约束，不是执行层约束。

`call_ai_api` 有 `max_retries=3`，但无执行时间预算（wall-clock budget）。一次 `execute_plan` 如果每步耗时 120s（timeout 上限），10 步理论上可阻塞 20 分钟。

### claude-code 参照：maxTurns 机制

claude-code 通过 `maxTurns` 参数限制 Agent 循环的最大对话轮次，防止无界代理循环。其 `StreamingToolExecutor` 在工具调用层面追踪调用深度，超过阈值时注入终止信号而非硬中断，给 LLM 机会生成最终答案。

关键设计思路：**预算是软约束 + 硬截断的组合**。软约束（剩余 budget 低时通知 LLM）优先于硬截断，让 AI 有机会收尾。

### 业界实践

- Langchain AgentExecutor 的 `max_iterations`（默认 15）
- LlamaIndex 的 `max_function_calls`
- AWS Bedrock Agents 的 `maxLength` orchestration 配置
- 生产建议：MAX_STEPS ≤ 10，执行时间预算 ≤ 5 分钟（300s）

### SocialHub CLI 改进方案

三层 Budget 防护：

| 层级 | 参数 | 默认值 | 说明 |
|------|------|--------|------|
| 步骤上限 | `MAX_STEPS` | 10 | parser 截断 + executor 二次检查 |
| 单步超时 | `STEP_TIMEOUT` | 120s | 已实现（subprocess timeout） |
| 总执行预算 | `PLAN_WALL_CLOCK` | 300s | execute_plan 整体时间上限 |

实现复杂度：**低**（~30 行，无新依赖）
用户体验影响：**中性** — 正常查询远不会触及上限；异常时防止长时间卡顿

**MVP 代码示例**

```python
# cli/ai/executor.py 顶部常量
MAX_PLAN_STEPS = 10          # 最大步骤数（可通过 config 覆盖）
PLAN_WALL_CLOCK_BUDGET = 300 # 整个计划的最大执行时间（秒）

def execute_plan(steps: list[dict], original_query: str = "") -> None:
    # 步骤上限检查
    if len(steps) > MAX_PLAN_STEPS:
        console.print(
            f"[yellow]Warning: AI generated {len(steps)} steps, "
            f"truncating to {MAX_PLAN_STEPS} (MAX_PLAN_STEPS)[/yellow]"
        )
        steps = steps[:MAX_PLAN_STEPS]

    plan_start_time = time.time()

    for idx, step in enumerate(steps):
        # 总时间预算检查
        elapsed = time.time() - plan_start_time
        if elapsed > PLAN_WALL_CLOCK_BUDGET:
            console.print(
                f"[red]Plan budget exceeded ({elapsed:.0f}s > {PLAN_WALL_CLOCK_BUDGET}s). "
                f"Stopping at step {step['number']}.[/red]"
            )
            break

        # ... 现有执行逻辑 ...
```

**在 parser.py 中添加上限截断**

```python
# parser.py extract_plan_steps() 末尾
MAX_PLAN_STEPS = 10  # 与 executor 保持一致

def extract_plan_steps(response: str) -> list[dict]:
    # ... 现有解析逻辑 ...
    steps = sorted(steps, key=lambda s: s["number"])
    if len(steps) > MAX_PLAN_STEPS:
        # 记录截断警告，上层 caller 负责展示
        steps = steps[:MAX_PLAN_STEPS]
    return steps
```

---

## 模式 C：幂等性设计

### 现状分析

用户可能对同一查询多次发起 AI 请求（如网络重试、用户手动重试）。`call_ai_api` 每次独立调用，无去重。`execute_plan` 对相同步骤序列无指纹检查。

对于只读命令（`sh analytics overview`），重复执行无副作用。但对于写入类命令（`sh heartbeat add`、`sh workflow run`），重复执行可能产生重复记录或重复调度。

当前 `save_scheduled_task`（`executor.py` 第 91-133 行）在 `Heartbeat.md` 中追加任务，重复调用会产生重复条目。

### 业界模式

幂等性实现的两个关键机制（来源 DZone、Inngest 调研）：

1. **命令指纹（Fingerprint）**: 对命令字符串做 SHA-256，作为执行记录的 key
2. **幂等键（Idempotency Key）**: 请求发起方生成 UUID，服务端用 key 去重；结果缓存后直接返回

对 CLI 场景的适配：使用 `(query_hash, session_id)` 作为幂等 key，在单次会话（进程生命周期）内去重。

### SocialHub CLI 具体风险点

| 命令 | 幂等性 | 重复执行后果 |
|------|--------|-------------|
| `sh analytics overview` | 天然幂等（只读） | 无副作用 |
| `sh heartbeat add ...` | 非幂等 | 重复定时任务 |
| `sh workflow run ...` | 取决于 workflow 实现 | 潜在重复触发 |
| `sh campaigns create ...` | 非幂等 | 重复营销活动（高风险） |

### 改进方案

**阶段 1（MVP）**：单进程会话级去重，防止同一 `execute_plan` 调用内重复步骤执行。

实现复杂度：**低**（~25 行，使用 hashlib，无新依赖）
用户体验影响：**正向** — 防止意外重复操作，对正常使用无感知

```python
# cli/ai/idempotency.py
import hashlib
from functools import lru_cache


class SessionIdempotencyGuard:
    """单次会话（进程生命周期）内的命令去重。"""

    def __init__(self):
        self._executed: dict[str, dict] = {}  # fingerprint → result

    def fingerprint(self, cmd: str) -> str:
        """生成命令的确定性指纹（SHA-256 前 16 位）。"""
        return hashlib.sha256(cmd.strip().encode()).hexdigest()[:16]

    def is_duplicate(self, cmd: str) -> tuple[bool, dict | None]:
        """检查命令是否已执行过，返回 (is_dup, cached_result)。"""
        fp = self.fingerprint(cmd)
        if fp in self._executed:
            return True, self._executed[fp]
        return False, None

    def record(self, cmd: str, result: dict) -> None:
        """记录命令执行结果。"""
        fp = self.fingerprint(cmd)
        self._executed[fp] = result

    def is_readonly_cmd(self, cmd: str) -> bool:
        """判断命令是否为只读（不需要幂等保护）。"""
        readonly_prefixes = [
            "sh analytics", "sh customers search", "sh customers list",
            "sh members", "sh segments list", "sh tags list",
            "sh campaigns list", "sh coupons list", "sh points",
            "sh schema", "sh history",
        ]
        return any(cmd.startswith(p) for p in readonly_prefixes)
```

**阶段 2（roadmap）**：跨会话持久化幂等记录，使用 `~/.socialhub/execution_log.json`，TTL 24h。

---

## 模式 D：结构化输出验证

### 现状分析

**parser.py 的脆弱性**：当前依赖三套正则 fallback（Pattern 1/2/3），对 AI 输出格式变体高度敏感。

已知脆弱场景：
1. LLM 在 `[PLAN_START]` 前插入解释文本，但格式正确 → 可以工作
2. LLM 输出 `[plan_start]`（小写）→ 解析失败，返回 0 步骤
3. LLM 在步骤描述中换行 → Pattern 1 可能提取错误
4. `Step 1：`（中文冒号）vs `Step 1:` → 当前正则 `[：:]` 已处理，但存在先例

**根本问题**：文本标记协议（`[PLAN_START]`）依赖 LLM 严格遵守格式约定，而 LLM 本质上是概率采样，无法保证 100% 合规。

### 业界方案对比

| 方案 | 可靠性 | 迁移成本 | 适用场景 |
|------|--------|----------|----------|
| OpenAI `response_format={"type":"json_object"}` | 高（JSON 模式强制） | 低 | OpenAI 提供商 |
| OpenAI `response_format={"type":"json_schema"}` | 最高（Structured Outputs） | 中 | OpenAI gpt-4o+ |
| Azure OpenAI Structured Outputs | 高 | 低（同 OpenAI API） | Azure 部署 |
| Pydantic + 后处理验证 | 中（仍依赖 LLM 输出 JSON） | 低 | 任何提供商 |
| 保留现有文本标记 + 增强 fallback | 低 | 极低 | 渐进式改进 |

### SocialHub CLI 改进方案

**近期（P1）：增强文本标记解析的健壮性**

```python
# parser.py 改进：宽松预处理 + 严格后验证
import json
import re
from pydantic import BaseModel, field_validator

class PlanStep(BaseModel):
    number: int
    description: str
    command: str

    @field_validator("command")
    @classmethod
    def command_must_start_with_sh(cls, v: str) -> str:
        v = v.strip().strip("`")
        if not v.startswith("sh "):
            raise ValueError(f"command must start with 'sh ', got: {v!r}")
        return v

class Plan(BaseModel):
    steps: list[PlanStep]


def extract_plan_steps_robust(response: str) -> list[dict]:
    """
    双路解析策略：
    1. 尝试 JSON 模式（如 LLM 支持 structured output）
    2. 回退到增强正则（大小写不敏感标记 + 更宽松的步骤格式）
    """
    # 路径 1：JSON 模式（response_format=json_object 时 LLM 可能直接输出 JSON）
    json_match = re.search(r'\{[\s\S]*"steps"[\s\S]*\}', response)
    if json_match:
        try:
            data = json.loads(json_match.group())
            plan = Plan.model_validate(data)
            return [s.model_dump() for s in plan.steps]
        except Exception:
            pass  # 回退到正则路径

    # 路径 2：增强正则（大小写不敏感 + 多种格式变体）
    plan_match = re.search(
        r'\[PLAN_START\](.*?)\[PLAN_END\]',
        response, re.DOTALL | re.IGNORECASE  # 增加 IGNORECASE
    )
    if not plan_match:
        return []

    plan_text = plan_match.group(1)

    # 统一预处理：移除多余空白、标准化冒号
    plan_text = re.sub(r'Step\s*(\d+)\s*[：:]', r'Step \1:', plan_text)

    # ... 现有三套 pattern 匹配逻辑（保持后向兼容）...

    # Pydantic 后验证：过滤掉无效步骤而非抛出异常
    validated = []
    for raw in raw_steps:
        try:
            step = PlanStep.model_validate(raw)
            validated.append(step.model_dump())
        except Exception as e:
            console.print(f"[yellow]Warning: skipping invalid step {raw}: {e}[/yellow]")

    return validated
```

**中期（P1）：为 OpenAI/Azure OpenAI 启用 JSON 模式**

```python
# client.py 中添加 response_format 参数
json_payload = {
    "messages": [...],
    "temperature": 0.7,
    "max_tokens": 1000,
    # 新增：强制 JSON 输出（需要同步更新 SYSTEM_PROMPT 要求输出 JSON）
    "response_format": {"type": "json_object"},
}
```

同步更新 `prompt.py` 的 `SYSTEM_PROMPT`，要求 LLM 输出标准 JSON：

```
输出格式要求（当执行多步计划时）：
{
  "steps": [
    {"number": 1, "description": "...", "command": "sh analytics overview"},
    {"number": 2, "description": "...", "command": "sh analytics customers"}
  ]
}
```

实现复杂度：**中**（需同步改 prompt + parser + Pydantic schema）
用户体验影响：**正向** — 减少 AI 响应解析失败导致的无操作，提升成功率

**对 AI 响应质量的影响**：JSON 模式会略微降低 LLM 的"解释性"文本（因为强制 JSON 格式），但对于 SocialHub CLI 的结构化计划场景是净收益——用户关心的是命令被正确执行，而非 AI 解释文字。

---

## 模式 E：可观测性 / 决策追踪

### 现状分析

当前 `cli/ai/` 层缺乏任何结构化日志。问题排查依赖：
1. Rich console 输出（面向用户，不面向运维）
2. 无法回答：这一步为什么失败？LLM 给了什么原始响应？消耗了多少 token？

`SecurityAuditLogger`（在 `cli/skills/` 中）提供了沙箱违规的结构化审计，但 AI 执行层没有对等机制。

### 业界标准（2025）

**OpenTelemetry GenAI Semantic Conventions**（来源：opentelemetry.io/blog/2025/ai-agent-observability）定义了标准的 span 属性：

| Span 属性 | 说明 |
|-----------|------|
| `gen_ai.system` | 提供商（openai / azure） |
| `gen_ai.request.model` | 模型名称 |
| `gen_ai.usage.input_tokens` | 输入 token 数 |
| `gen_ai.usage.output_tokens` | 输出 token 数 |
| `gen_ai.response.finish_reason` | 完成原因（stop/length/tool_calls） |

**structlog** 是 Python 生态的结构化日志事实标准，支持 JSON 输出，无需 OTel 完整栈即可实现可观测性基础。

### SocialHub CLI 改进方案

**最小可行方案：structlog + 本地 JSONL 执行日志**

不引入 OTel 全栈（避免大型依赖），改用 structlog 写入 `~/.socialhub/ai_trace.jsonl`，每行一个 JSON 事件。

实现复杂度：**低-中**（引入 `structlog` 轻量依赖 ~40KB，约 80 行代码）
用户体验影响：**透明**（后台写文件，不影响 CLI 输出）

```python
# cli/ai/tracer.py
import json
import time
from pathlib import Path
from typing import Any
import hashlib

_TRACE_FILE = Path.home() / ".socialhub" / "ai_trace.jsonl"


def _write_event(event: dict) -> None:
    """追加写入 JSONL 格式的追踪事件（单行 JSON）。"""
    try:
        _TRACE_FILE.parent.mkdir(parents=True, exist_ok=True)
        with _TRACE_FILE.open("a", encoding="utf-8") as f:
            f.write(json.dumps(event, ensure_ascii=False) + "\n")
    except Exception:
        pass  # 追踪失败不应影响主流程


class AIExecutionTracer:
    """
    轻量级 AI 执行追踪器。

    使用示例：
        with AIExecutionTracer(query="分析本月客户留存") as tracer:
            response = call_ai_api(query)
            tracer.record_ai_response(response, tokens_in=150, tokens_out=320)

            for step in steps:
                with tracer.step_span(step["number"], step["command"]) as span:
                    success, output = execute_command(step["command"])
                    span.record_result(success, output)
    """

    def __init__(self, query: str):
        self.query = query
        self.trace_id = hashlib.sha256(
            f"{query}{time.time()}".encode()
        ).hexdigest()[:12]
        self.start_time = time.time()
        self._steps: list[dict] = []
        self.tokens_in = 0
        self.tokens_out = 0

    def __enter__(self):
        _write_event({
            "event": "plan_start",
            "trace_id": self.trace_id,
            "query": self.query,
            "ts": self.start_time,
        })
        return self

    def __exit__(self, *_):
        duration = time.time() - self.start_time
        success_count = sum(1 for s in self._steps if s.get("success"))
        _write_event({
            "event": "plan_end",
            "trace_id": self.trace_id,
            "duration_s": round(duration, 2),
            "steps_total": len(self._steps),
            "steps_success": success_count,
            "tokens_in": self.tokens_in,
            "tokens_out": self.tokens_out,
        })

    def record_ai_response(self, raw_response: str, tokens_in: int = 0, tokens_out: int = 0) -> None:
        """记录 AI 原始响应和 token 消耗。"""
        self.tokens_in = tokens_in
        self.tokens_out = tokens_out
        _write_event({
            "event": "ai_response",
            "trace_id": self.trace_id,
            "response_len": len(raw_response),
            "tokens_in": tokens_in,
            "tokens_out": tokens_out,
            # 仅记录前 200 字符（避免日志过大，保护敏感数据）
            "response_preview": raw_response[:200],
        })

    def step_span(self, step_num: int, command: str) -> "StepSpan":
        return StepSpan(self, step_num, command)

    def _record_step(self, step_data: dict) -> None:
        self._steps.append(step_data)
        _write_event({"event": "step_result", "trace_id": self.trace_id, **step_data})


class StepSpan:
    def __init__(self, tracer: AIExecutionTracer, step_num: int, command: str):
        self.tracer = tracer
        self.step_num = step_num
        self.command = command
        self.start_time = time.time()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        pass

    def record_result(self, success: bool, output: str) -> None:
        duration = time.time() - self.start_time
        self.tracer._record_step({
            "step": self.step_num,
            "command": self.command,
            "success": success,
            "duration_s": round(duration, 2),
            "output_len": len(output),
            # 仅记录失败输出的前 300 字符
            "output_preview": output[:300] if not success else None,
        })
```

**token 消耗归因**

Azure OpenAI API 响应中包含 `usage` 字段，当前 `client.py` 解析 `result["choices"][0]["message"]["content"]` 但丢弃了 `result["usage"]`。

```python
# client.py 改进：从 API 响应中提取 token usage
result = response.json()
usage = result.get("usage", {})
tokens_in = usage.get("prompt_tokens", 0)
tokens_out = usage.get("completion_tokens", 0)
# 返回 (content, tokens_in, tokens_out) 或通过 tracer 传递
```

**追踪日志查询示例**

```bash
# 查看最近 10 次 AI 执行的 token 消耗
python -c "
import json
from pathlib import Path
log = Path('~/.socialhub/ai_trace.jsonl').expanduser()
events = [json.loads(l) for l in log.read_text().splitlines() if l]
ends = [e for e in events if e['event'] == 'plan_end']
for e in ends[-10:]:
    print(f\"trace={e['trace_id']} steps={e['steps_total']} tokens_in={e['tokens_in']} duration={e['duration_s']}s\")
"
```

---

## 模式 F：并发执行

### 现状分析

`execute_plan()` 完全串行：每个步骤等待前一步骤的 `subprocess.run()` 完成。对于包含多个只读分析命令的计划（如"分析本月客户数据、订单趋势、留存率"），三个独立查询串行执行，总耗时 = Σ(每步耗时)。

`client.py` 当前用 `threading` + busy-wait loop 实现 spinner，不是 asyncio 原生，与 asyncio 混用有事件循环冲突风险（`asyncio.to_thread` feedback 已在 MEMORY.md 中记录）。

### claude-code 参照：StreamingToolExecutor

claude-code 的 `StreamingToolExecutor` 在 LLM 流式输出工具调用时并发启动独立工具，使用 `Promise.all` 等价机制。关键设计约束：**只有无数据依赖的工具调用才并发**，LLM 通过不在同一 turn 返回有依赖的工具调用来隐式协调顺序。

### Python asyncio 等价方案

```python
# asyncio.gather 并发执行独立步骤
import asyncio

async def execute_command_async(cmd: str) -> tuple[bool, str]:
    """execute_command 的 async 包装（subprocess 在线程池中运行）。"""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, execute_command, cmd)

async def execute_steps_concurrent(
    step_group: list[dict]
) -> list[dict]:
    """并发执行一组无依赖的步骤。"""
    tasks = [execute_command_async(step["command"]) for step in step_group]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    output = []
    for step, result in zip(step_group, results):
        if isinstance(result, Exception):
            output.append({"step": step["number"], "success": False,
                           "output": str(result)})
        else:
            success, out = result
            output.append({"step": step["number"], "success": success,
                           "output": out})
    return output
```

### SocialHub CLI：哪些命令适合并发？

**安全并发（只读，无共享状态写入）**

| 命令类别 | 示例 | 并发安全 |
|----------|------|----------|
| 分析查询 | `sh analytics overview`, `sh analytics customers` | 是 |
| 数据列表 | `sh customers list`, `sh segments list` | 是 |
| Schema 查询 | `sh schema` | 是 |
| 历史记录 | `sh history` | 是 |

**必须串行（有写入或依赖）**

| 命令类别 | 原因 |
|----------|------|
| `sh heartbeat add ...` | 写入 Heartbeat.md，竞争条件 |
| `sh workflow run ...` | 可能有副作用 |
| `sh config set ...` | 写入 config.json |
| 步骤 N+1 依赖步骤 N 的输出 | 数据依赖 |

### 并发安全检查函数

```python
# cli/ai/executor.py
_READONLY_CMD_PREFIXES = frozenset({
    "sh analytics",
    "sh customers search",
    "sh customers list",
    "sh customers get",
    "sh members",
    "sh segments list",
    "sh tags list",
    "sh campaigns list",
    "sh coupons list",
    "sh points",
    "sh schema",
    "sh history",
})

def _is_concurrent_safe(cmd: str) -> bool:
    """判断命令是否可并发执行（只读，无文件写入副作用）。"""
    return any(cmd.startswith(prefix) for prefix in _READONLY_CMD_PREFIXES)


def _group_steps_for_execution(
    steps: list[dict]
) -> list[list[dict]]:
    """
    将步骤分组：连续的只读步骤合并为并发组，写入步骤独立为串行组。

    示例：
    [analytics, analytics, heartbeat_add, analytics]
    → [[analytics, analytics], [heartbeat_add], [analytics]]
    """
    groups: list[list[dict]] = []
    current_group: list[dict] = []
    current_is_concurrent = None

    for step in steps:
        is_safe = _is_concurrent_safe(step["command"])
        if is_safe == current_is_concurrent:
            current_group.append(step)
        else:
            if current_group:
                groups.append(current_group)
            current_group = [step]
            current_is_concurrent = is_safe

    if current_group:
        groups.append(current_group)

    return groups
```

### 迁移策略

并发执行改造需要将 `execute_plan` 改为 `async def`，这涉及调用链的 async 化（`cli/main.py` 入口需要 `asyncio.run()`）。推荐分阶段：

1. **Phase 1（P2）**: 内部使用 `asyncio.run()` + `asyncio.gather` 执行并发步骤组，外部 `execute_plan` 保持同步接口（通过 `asyncio.run()` 桥接）
2. **Phase 2（roadmap）**: 将整个 AI 执行链 async 化，同步解决 `client.py` 中 `threading` 的稳定性问题

实现复杂度：**高**（涉及调用链改造）
用户体验影响：**正向** — 3 步独立分析查询从串行 ~30s 降至并发 ~10s

---

## 综合优先级与实施路线图

### 优先级矩阵

| 模式 | 优先级 | 实现复杂度 | 用户体验 | 依赖新包 | 推荐版本 |
|------|--------|-----------|---------|---------|---------|
| B. 步骤上限 + Budget | P0 | 极低 | 中性/防护 | 无 | 下个版本 |
| A. Circuit Breaker | P0 | 低 | 正向 | 无 | 下个版本 |
| D. 结构化输出（Pydantic 后验证） | P1 | 低 | 正向 | pydantic（已有） | 下个版本 |
| C. 幂等性（会话级） | P1 | 低 | 正向 | hashlib（标准库） | 下个版本 |
| E. 可观测性（JSONL 追踪） | P1 | 中 | 透明 | 无（纯标准库） | 下个版本 |
| D. 结构化输出（JSON 模式） | P1 | 中 | 正向 | 无（API 参数） | P1 版本 |
| F. 并发执行 | P2 | 高 | 显著正向 | asyncio（标准库） | Roadmap |

### P0 实施清单（下个版本，最小改动）

```
1. executor.py
   + 导入 time
   + 添加 MAX_PLAN_STEPS = 10, PLAN_WALL_CLOCK_BUDGET = 300 常量
   + execute_plan() 开头：截断超长 steps + 记录 plan_start_time
   + 循环内：检查 elapsed > budget 时 break
   + 集成 ToolCircuitBreaker（新文件 circuit_breaker.py）

2. parser.py
   + extract_plan_steps() 末尾：截断超过 MAX_PLAN_STEPS 的步骤

3. cli/ai/circuit_breaker.py（新文件，~60 行）
   + ToolCircuitBreaker dataclass
   + CLOSED/OPEN/HALF_OPEN 三态
```

**估计工作量**：0.5 天，0 新依赖，0 破坏性改动

### P1 实施清单（下个 sprint）

```
4. cli/ai/tracer.py（新文件，~80 行）
   + AIExecutionTracer context manager
   + StepSpan context manager
   + JSONL 写入 ~/.socialhub/ai_trace.jsonl

5. cli/ai/idempotency.py（新文件，~25 行）
   + SessionIdempotencyGuard
   + 非幂等命令白名单

6. parser.py
   + re.IGNORECASE 标记匹配
   + Pydantic PlanStep 后验证（过滤无效步骤而非失败）

7. client.py
   + 从 API 响应中提取并返回 token usage
   + 与 tracer 集成
```

**估计工作量**：1-1.5 天

---

## 关键风险与约束

### 不可违反的项目红线

| 模式 | 涉及红线 | 处理方式 |
|------|---------|---------|
| 并发执行 | `shell=False` 不受影响，但 asyncio + subprocess 需要确保不绕过 validator | 每个并发任务独立调用 `validate_command()` 再 `execute_command()` |
| 结构化输出 JSON 模式 | 无 | 无 |
| 幂等性 | 不能跳过 `validator.py` 校验（即使是缓存命中） | 缓存的是 `execute_command` 结果，validator 仍正常运行 |

### 技术债提示

1. `client.py` 的 `threading` + busy-wait 与 Python asyncio 生态长期不兼容。Phase F 并发执行改造时需要一并解决，将 spinner 改为 `asyncio.sleep`-based 或使用 `asyncio.to_thread(call_ai_api, ...)`（参见 MEMORY.md feedback_asyncio_patterns）。

2. `SYSTEM_PROMPT`（`prompt.py`）需要与结构化输出方案同步演进：启用 JSON 模式后，prompt 中的 `[PLAN_START]...[PLAN_END]` 格式说明应更新为 JSON schema 示例，否则 LLM 会同时输出两种格式造成混乱。

---

## 参考来源

- [Retries, fallbacks, and circuit breakers in LLM apps — Portkey](https://portkey.ai/blog/retries-fallbacks-and-circuit-breakers-in-llm-apps/)
- [Resilience Circuit Breakers for Agentic AI — Medium](https://medium.com/@michael.hannecke/resilience-circuit-breakers-for-agentic-ai-cc7075101486)
- [Building Resilient Systems: Circuit Breakers and Retry Patterns — dasroot.net](https://dasroot.net/posts/2026/01/building-resilient-systems-circuit-breakers-retry-patterns/)
- [The Hidden Cost of Agentic Failure — O'Reilly Radar](https://www.oreilly.com/radar/the-hidden-cost-of-agentic-failure/)
- [Idempotency in AI Tools: Most Expensive Thing Teams Forget — DZone](https://dzone.com/articles/idempotency-in-ai-tools-most-expensive-mistake)
- [Durable Execution: The Key to Harnessing AI Agents in Production — Inngest](https://www.inngest.com/blog/durable-execution-key-to-harnessing-ai-agents)
- [AI Agent Error Handling: 5 Production Patterns That Work](https://blog.jztan.com/ai-agent-error-handling-patterns/)
- [Orchestrating AI Agents in Production: The Patterns That Actually Work — Hatchworks](https://hatchworks.com/blog/ai-agents/orchestrating-ai-agents/)
- [AI Agent Observability — Evolving Standards and Best Practices — OpenTelemetry](https://opentelemetry.io/blog/2025/ai-agent-observability/)
- [The AI Engineer's Guide to LLM Observability with OpenTelemetry — Agenta](https://agenta.ai/blog/the-ai-engineer-s-guide-to-llm-observability-with-opentelemetry)
- [AI Agents at Lightning Speed: The asyncio advantage — Medium](https://medium.com/@geraldolucas/ai-agents-at-lightning-speed-the-asyncio-advantage-8b583b602a2d)
- [Mastering Python asyncio.gather for LLM Processing — Instructor](https://python.useinstructor.com/blog/2023/11/13/learn-async/)
- [How to Use Pydantic for LLMs: Schema, Validation & Prompts — Pydantic](https://pydantic.dev/articles/llm-intro)
- [Structured Output AI Reliability: JSON Schema & Function Calling Guide 2025 — CognitiveToday](https://www.cognitivetoday.com/2025/10/structured-output-ai-reliability/)
- [Agentic AI Guardrails: What They Are and How to Implement Them — Aembit](https://aembit.io/blog/agentic-ai-guardrails-for-safe-scaling/)
- [Resilient AI Agents With MCP: Timeout And Retry Strategies — Octopus](https://octopus.com/blog/mcp-timeout-retry)
- [A Safety and Security Framework for Real-World Agentic Systems — arXiv](https://arxiv.org/html/2511.21990v1)
