# 技术设计

> CTO 审查: B+（可推进，含强制修正项 FIX-1～FIX-7） -- 2026-04-02

> 版本：v1.0  
> 日期：2026-04-02  
> 作者：架构师（含 3 轮自我对抗修正）  
> 依赖：CLAUDE.md / 01-research/ / 05-prd.md

---

## 模块架构（cli/memory/ 目录结构 + 职责说明）

```
cli/memory/
├── __init__.py          # 公开 MemoryManager + MemoryContext 供外部 import
├── manager.py           # MemoryManager：统一协调入口，load()/save()/build_system_prompt()
├── store.py             # MemoryStore：文件存储 CRUD（0o600 原子写、TTL、上限清理）
├── models.py            # Pydantic v2 数据模型（UserProfile / BusinessContext / Insight / SessionSummary / MemoryContext / MemoryConfig）
├── injector.py          # build_system_prompt()：动态组装，tiktoken 预算控制，归档过滤
├── extractor.py         # SessionExtractor：会话结束时 LLM structured-output 摘要提炼（同步调用，可超时跳过）
└── pii.py               # memory 专用 PII 扫描（基于 trace.py 相同正则，模块独立）
```

### 各文件职责详述

| 文件 | 职责 | 关键约束 |
|------|------|---------|
| `__init__.py` | 仅 re-export `MemoryManager`, `MemoryContext`；不含逻辑 | 外部调用 `from cli.memory import MemoryManager` |
| `manager.py` | 协调 store / extractor / injector / pii 四个子模块；对外暴露 5 个公开方法（见下节）；实例不是单例，每次 CLI 调用 `main.py` 中创建一个实例 | 任何子模块异常必须 catch，降级到无记忆模式，不向上抛 |
| `store.py` | `MemoryStore`：读写 YAML/JSON；原子写（tmp→replace）；创建时权限 0o600；TTL 过期清理；文件数量上限清理 | 禁止 `shell=True`；路径 allowlist 防遍历；不得直接 import `cli.commands.*` |
| `models.py` | `UserProfile` / `BusinessContext` / `Campaign` / `Insight` / `SessionSummary` / `MemoryContext` / `MemoryConfig`；Pydantic v2 `model_validate` + 严格字段验证；`Campaign.status` 由 `BR-01` property 计算 | Pydantic ValidationError 不可传出 manager.py 边界 |
| `injector.py` | `build_system_prompt(context: MemoryContext) -> str`；token 计数（tiktoken）；超预算时**先裁剪 L3，再裁剪 L2，最后裁剪 L4**（L4 优先级最高，最后被裁减）；归档活动不注入（BR-02）；`on_inject` 回调在返回前通知审计层（FIX-6） | 不做 IO，纯计算；≤ 50ms |
| `extractor.py` | `SessionExtractor.extract(session) -> ExtractionResult`；调用 `call_ai_api()` structured output；30s 超时跳过（BR-15）；返回 `ExtractionResult.skipped=True` 而非抛出异常 | 同步调用，不用 asyncio；由 `manager.py` 在 `save_session_memory()` 中调用 |
| `pii.py` | `scan_and_mask(text: str) -> tuple[str, bool]`（返回脱敏后文本 + 是否命中）；与 `trace.py._build_pii_patterns()` 使用相同正则但独立实现，避免跨模块依赖内部函数 | 仅供 memory 写入路径使用；不用于 AI 输入净化（见 CLAUDE.md sanitizer.py 职责说明） |

### 存储目录布局

```
~/.socialhub/
└── memory/                           # 0o700，创建时设置
    ├── user_profile.yaml             # L4 偏好层（0o600）
    ├── business_context.yaml         # L4 业务上下文层（0o600）
    ├── analysis_insights/            # L3 语义记忆（0o700）
    │   └── {date}-{slug}.json        # 每条洞察一个文件（0o600）
    └── session_summaries/            # L2 情节记忆（0o700）
        └── {session_id}.json         # 每会话一个摘要（0o600）
```

---

## 公开 API（MemoryManager 方法签名）

```python
class MemoryManager:
    """统一记忆管理入口。每次 CLI 调用创建新实例（非单例）。
    
    任何方法抛出的异常均在方法内部 catch，降级返回空/默认值，
    保证主 AI 调用流程不受记忆子系统故障影响。
    """

    def __init__(self, config: Optional["MemoryConfig"] = None) -> None:
        """
        config 为 None 时从 load_config() 读取 MemoryConfig 子节。
        目录不存在时自动创建（0o700）。
        """

    # ------------------------------------------------------------------
    # 读取路径（会话启动时调用）
    # ------------------------------------------------------------------

    def load(self) -> "MemoryContext":
        """
        加载四层记忆，组装 MemoryContext。
        
        执行步骤：
          1. store.load_user_profile()       → UserProfile（含解析失败降级）
          2. store.load_business_context()   → BusinessContext
          3. store.load_recent_insights(n=5) → list[Insight]（时间倒序，过滤归档活动关联）
          4. store.load_recent_summaries(n=3)→ list[SessionSummary]
          5. store.purge_expired()           → 惰性清理过期文件（TTL + 数量上限）
        
        任何步骤失败 catch 后继续，失败层返回空默认值。
        
        Returns:
            MemoryContext（即使全部失败也返回空 context，不返回 None）
        
        Complexity: ≤ 100ms（全本地 IO，无网络）
        """

    def build_system_prompt(self, context: "MemoryContext") -> str:
        """
        根据 MemoryContext 构建动态 SYSTEM_PROMPT。
        
        委托 injector.build_system_prompt(context) 执行：
          - L4 优先注入（user_profile + business_context）
          - L2 次之（最近摘要）
          - L3 最后（最相关洞察）
          - 归档活动不注入（BR-02）
          - tiktoken 总预算 ≤ 4000 tokens，超出时先裁剪 L3，再裁剪 L2，最后裁剪 L4（L4 优先级最高，最后被裁减）
        
        Returns:
            str — 完整 SYSTEM_PROMPT 字符串，可直接传给 call_ai_api()
        
        Complexity: ≤ 50ms（纯计算，无 IO）
        """

    # ------------------------------------------------------------------
    # 写入路径（会话结束时调用）
    # ------------------------------------------------------------------

    def save_session_memory(
        self,
        session: "Session",
        trace_id: str,
        no_memory: bool = False,
    ) -> Optional[str]:
        """
        会话结束时：提炼摘要 + 写入洞察 + 审计日志。
        
        执行步骤：
          1. no_memory=True 时立即返回 None，跳过所有写入（BR-13）
          2. extractor.extract(session) — LLM structured output，30s 超时（BR-15）
             超时/失败 → skipped=True，跳过后续写入，不抛出
          3. 对 extraction.business_insights 逐条 pii.scan_and_mask()
             命中 PII → 打印 dim 提示，跳过该条写入（BR-05）
          4. store.save_insight(insight, trace_id) × n 条
          5. store.save_summary(summary, trace_id) — 写入 session_summaries/
          6. 更新 user_profile（合并 extraction.user_preferences_update）
          7. trace_logger.log_memory_write() × 每条写入
        
        Returns:
            summary_id: str | None（摘要写入成功时返回 ID，供终端提示输出 BR-06）
        
        Side effects:
            - 终端打印低调提示（由调用方 main.py 负责，非此方法职责）
            - 审计写入 ai_trace.jsonl（内部通过 TraceLogger）
        """

    def save_insight_from_ai(
        self,
        raw_content: str,
        topic: str,
        tags: list[str],
        session_id: str,
        trace_id: str,
        no_memory: bool = False,
    ) -> bool:
        """
        insights.py 钩子：单条洞察写入（M15）。
        
        执行步骤：
          1. no_memory=True 时返回 False
          2. pii.scan_and_mask(raw_content)
             命中 → 打印 dim 提示，返回 False（BR-05）
          3. store.save_insight(Insight(...), trace_id)
          4. trace_logger.log_memory_write(...)
        
        Returns:
            bool — True 表示成功写入，False 表示跳过或失败
        """

    # ------------------------------------------------------------------
    # 查询路径（sh memory 命令使用）
    # ------------------------------------------------------------------

    def get_status(self) -> "MemoryStatus":
        """
        返回记忆系统健康概览（M8）：
          - 各层文件数量 / 大小
          - 活跃活动数 / 归档活动数
          - token 用量估算
          - TTL 即将过期的条目数
        """

    def get_injection_preview(self) -> dict:
        """
        返回下次注入 SYSTEM_PROMPT 的预览（M3 --injection-preview）：
          {
            "system_prompt": str,        # 完整注入文本
            "token_count": int,          # 总 token 数
            "layers": {                  # 各层 token 用量
              "L4": int, "L3": int, "L2": int
            },
            "truncated_layers": list[str]  # 被裁剪的层
          }
        """
```

### MemoryContext 数据模型

```python
class MemoryContext(BaseModel):
    """传递给 build_system_prompt() 的完整记忆快照。只读，不可变。"""
    user_profile: Optional[UserProfile] = None
    business_context: Optional[BusinessContext] = None
    recent_insights: list[Insight] = []      # 最多 5 条，时间倒序
    recent_summaries: list[SessionSummary] = []  # 最多 3 条，时间倒序
    no_memory: bool = False                  # --no-memory 时 True

class MemoryConfig(BaseModel):
    """嵌入 cli/config.py::Config.memory 子节。"""
    enabled: bool = True
    memory_dir: str = Field(
        default_factory=lambda: str(Path.home() / ".socialhub" / "memory")
    )
    insights_ttl_days: int = 90       # L3 TTL
    insights_max_count: int = 200     # L3 上限
    summaries_ttl_days: int = 30      # L2 TTL
    summaries_max_count: int = 60     # L2 上限
    token_budget: int = 4000          # 总 token 预算
    extraction_timeout_s: int = 30    # extractor LLM 超时（BR-15）
    encrypt: bool = False             # 可选加密（企业高安全场景）
```

---

## 改动清单

### 新增文件（全部在 cli/memory/）

| 文件 | 规模 | 说明 |
|------|------|------|
| `cli/memory/__init__.py` | S | re-export MemoryManager, MemoryContext |
| `cli/memory/manager.py` | L | 主协调层，5 个公开方法 |
| `cli/memory/store.py` | L | 文件存储 CRUD + TTL + 原子写 |
| `cli/memory/models.py` | M | 所有 Pydantic v2 数据模型 |
| `cli/memory/injector.py` | M | SYSTEM_PROMPT 动态构建 + tiktoken |
| `cli/memory/extractor.py` | M | LLM 摘要提炼，30s 超时跳过 |
| `cli/memory/pii.py` | S | 独立 PII 扫描（与 trace.py 正则一致但独立） |
| `cli/commands/memory.py` | L | `sh memory` 所有子命令（Typer app） |
| `tests/memory/test_store.py` | M | MemoryStore 单元测试 |
| `tests/memory/test_injector.py` | M | injector token 预算裁剪单元测试 |
| `tests/memory/test_manager.py` | M | MemoryManager 集成测试（mock LLM） |
| `tests/memory/test_pii.py` | S | PII 扫描单元测试 |

### 修改文件

| 文件 | 改动位置 | 改动原因 |
|------|---------|---------|
| `cli/config.py` | `Config` 模型末尾增加 `memory: MemoryConfig` 字段；从 `cli.memory.models` import `MemoryConfig` | 将记忆配置纳入统一配置体系（配置分层原则），无破坏性变更 |
| `cli/main.py` | 在 session 加载后调用 `MemoryManager().load()` 获取 `memory_context`；将 `memory_context` 传给 `call_ai_api()`；会话结束后调用 `manager.save_session_memory()`；输出 summary_id 提示（BR-06）；解析 `--no-memory` 参数 | 接入记忆系统主流程 |
| `cli/ai/client.py` | `call_ai_api(messages, session, memory_context=None)` 新增 `memory_context` 可选参数；`_build_messages()` 改为调用 `MemoryManager.build_system_prompt(memory_context)` 而非直接使用 `SYSTEM_PROMPT` 常量；`memory_context is None` 时回退到静态 `SYSTEM_PROMPT`（向后兼容） | 支持动态 SYSTEM_PROMPT 注入（M17）；保持向后兼容 |
| `cli/ai/prompt.py` | 保留静态 `SYSTEM_PROMPT` 常量（作为 fallback 和测试基准）；新增 `BASE_SYSTEM_PROMPT`（不含记忆注入的核心 prompt 文本，供 `injector.py` 拼接使用） | injector.py 需要基础 prompt 文本；不删除常量确保回退路径 |
| `cli/ai/insights.py` | 在 `generate_insights()` 末尾增加对 `MemoryManager.save_insight_from_ai()` 的调用（M15）；接收 `no_memory` 参数向下传递 | 接入洞察自动写入 |
| `cli/skills/sandbox/filesystem.py` | 在 `PROTECTED_PATHS` 中增加 `Path.home() / ".socialhub" / "memory"` | 防止 Skills 读写记忆文件（安全合规要求）|
| `cli/ai/trace.py` | 新增公开方法 `log_memory_write(event: dict) -> None` 和 `log_memory_injection(event: dict) -> None`，与 `_write()` 相同逻辑；保留 `_write()` 内部方法不变。`memory_write` 事件字段：`{type, ts, trace_id, session_id, memory_type, memory_id, content_hash, pii_hit, skipped, skip_reason}`；`memory_injection` 事件字段：`{type, ts, trace_id, session_id, memory_ids: list[str], token_count, truncated_layers: list[str]}`（FIX-3/4） | 记忆审计事件需要写入 ai_trace.jsonl；新增注入事件用于生产排查记忆来源（安全合规要求）|
| `cli/commands/ai.py` | `ai_chat()` 增加 `--no-memory` 参数；调用 `MemoryManager().load()` 获取 `memory_context`；将 `memory_context` 传给 `call_ai_api()`；增加 `-c/--session` 支持（与 main.py smart mode 对齐）；会话结束后调用 `manager.save_session_memory()`（FIX-1） | `sh ai chat` 是独立命令入口，不经过 main.py smart mode，若不修改则 memory 功能对此路径完全无效 |
| `cli/memory/injector.py` | `build_system_prompt()` 增加 `on_inject: Optional[Callable[[list[str], int], None]] = None` 回调参数；在返回前调用 `on_inject(memory_ids, token_count)`；`manager.py` 调用时传入 `trace_logger.log_memory_injection` 作为回调（FIX-4，保持 injector 纯计算特性） | 注入事件审计不能在 injector 内部直接写日志（injector 为纯计算层），通过回调由 manager 层完成 |

### 不需要改的文件（明确说明）

| 文件 | 不改原因 |
|------|---------|
| `cli/analytics/mcp_adapter.py` | Memory 系统是 CLI 本地层，不涉及 MCP 集成；CLAUDE.md 明确此层为稳定接口不得绕过 |
| `mcp_server/server.py` | 记忆文件本地存储，不跨网络，不暴露给 MCP Server（PIPL 第38条：禁止向外传输） |
| `cli/ai/validator.py` | `sh memory` 子命令均为直接执行的 Typer 命令，不经过 AI 生成；不进入 AI 安全执行链 |
| `cli/ai/executor.py` | 同上，memory 命令不走 AI executor |
| `cli/ai/parser.py` | 无改动点 |
| `cli/commands/analytics.py` | 无改动点（insights.py 是改动文件，analytics 只是调用者） |
| `cli/skills/manager.py` | Skills 安装流水线无关记忆 |
| `cli/skills/security.py` | 无改动点 |
| `skills-store/` 全部 | 完全独立的后端服务，与 CLI 记忆无关 |
| `frontend/` 全部 | 前端不展示 CLI 记忆 |
| `docs/` 全部 | 硬约束：冻结目录 |
| `cli/commands/history.py::save_run()` | **已知技术债**：`save_run()` 函数设计完整（含 sql_trace、exec_time_ms 等 audit 字段）但当前代码库中**零调用**，实际历史记录由 `cli/main.py::save_history()` 执行。修复此技术债需要改造 executor.py（捕获执行计时），超出 memory 系统范围。**推迟至下期 executor.py 重构时处理。**（FIX-2）|

---

## 数据流

### 会话启动时：记忆加载 → SYSTEM_PROMPT 构建 → AI 调用

```
用户输入自然语言（cli/main.py）
    │
    ├─ [已有] SessionStore.load(session_id)
    │         └─ 读取 ~/.socialhub/sessions/{id}.json
    │
    ├─ [新增] MemoryManager.load()
    │         ├─ store.load_user_profile()       → UserProfile (L4)
    │         │     失败 → empty UserProfile，继续
    │         ├─ store.load_business_context()   → BusinessContext (L4)
    │         │     失败 → empty BusinessContext，继续
    │         ├─ store.load_recent_insights(n=5) → list[Insight] (L3)
    │         │     失败 → []，继续
    │         ├─ store.load_recent_summaries(n=3)→ list[SessionSummary] (L2)
    │         │     失败 → []，继续
    │         └─ store.purge_expired()           → 惰性 TTL 清理（静默）
    │                   返回 MemoryContext
    │
    ├─ [新增] MemoryManager.build_system_prompt(context)
    │         └─ injector.build_system_prompt(context)
    │               ├─ BASE_SYSTEM_PROMPT（核心文本）
    │               ├─ L4 注入（role + 偏好 + 活跃活动，约 1000 tokens）
    │               ├─ L2 注入（最近 3 条摘要，约 1000 tokens）
    │               ├─ L3 注入（最相关 3-5 条洞察，约 2000 tokens）
    │               └─ tiktoken 计数 → 超出 4000 tokens 时按 L3→L2→L4 顺序裁剪
    │                   返回动态 SYSTEM_PROMPT 字符串
    │
    └─ call_ai_api(messages, session, memory_context)
              ├─ _build_messages() 使用动态 SYSTEM_PROMPT
              └─ Azure OpenAI API 调用（不变）
```

### 会话结束时：摘要提炼 → 记忆写入 → 审计日志

```
AI 执行完成，Session.add_turn() 后（cli/main.py）
    │
    ├─ [已有] SessionStore.save(session)
    │         └─ 写 ~/.socialhub/sessions/{id}.json
    │
    ├─ [新增] MemoryManager.save_session_memory(session, trace_id, no_memory)
    │         │
    │         ├─ no_memory=True → return None（BR-13）
    │         │
    │         ├─ extractor.extract(session)     # LLM structured output
    │         │     ├─ 30s 超时 → skipped=True，return None（BR-15）
    │         │     └─ 返回 ExtractionResult:
    │         │           {user_preferences_update, business_insights, session_summary, nothing_to_save}
    │         │
    │         ├─ nothing_to_save=True → return None（无记忆价值的对话）
    │         │
    │         ├─ 对每条 business_insight：
    │         │     ├─ pii.scan_and_mask(content)
    │         │     │     命中 PII → 打印 dim 提示，跳过本条（BR-05）
    │         │     ├─ store.save_insight(insight, trace_id)   # 0o600 原子写
    │         │     └─ trace_logger.log_memory_write(content_hash, trace_id, ...)
    │         │
    │         ├─ store.save_summary(session_summary, trace_id) # 0o600 原子写
    │         ├─ trace_logger.log_memory_write(summary_hash, trace_id, ...)
    │         │
    │         └─ user_preferences_update 非空时：
    │               store.merge_user_profile(updates)          # 原子写，合并偏好
    │               返回 summary_id
    │
    └─ [新增] 终端打印低调提示（main.py）：
              "已记录本次会话摘要 · sh memory show summary/{summary_id} 查看"（BR-06）

另一写入路径（会话执行中 insights.py）：
    cli/ai/insights.py :: generate_insights()
        ├─ [已有] 打印洞察到终端
        └─ [新增] MemoryManager.save_insight_from_ai(
                    raw_content, topic, tags, session_id, trace_id, no_memory
                  )
                  ├─ pii.scan_and_mask → 命中打印 dim 提示（BR-05）
                  └─ store.save_insight(insight, trace_id)（0o600 原子写）
```

---

## 开发步骤（依赖序，含规模 S/M/L）

### 阶段 0：基础设施（无外部依赖，可并行开发）

| 步骤 | 任务 | 规模 | 依赖 | 说明 |
|------|------|------|------|------|
| 0-A | `cli/memory/models.py`：所有 Pydantic v2 模型 | M | 无 | 最先写，后续所有任务依赖类型定义 |
| 0-B | `cli/memory/pii.py`：独立 PII 扫描 | S | 无 | 可与 0-A 并行 |

### 阶段 1：存储层（依赖 0-A）

| 步骤 | 任务 | 规模 | 依赖 | 说明 |
|------|------|------|------|------|
| 1-A | `cli/memory/store.py`：MemoryStore CRUD + 原子写 + TTL + 权限 | L | 0-A | 核心存储层 |
| 1-B | `tests/memory/test_store.py` | M | 1-A | 与 1-A 同步开发 |

### 阶段 2：计算层（依赖 0-A，可与阶段 1 并行）

| 步骤 | 任务 | 规模 | 依赖 | 说明 |
|------|------|------|------|------|
| 2-A | `cli/memory/injector.py`：build_system_prompt + tiktoken | M | 0-A | 纯计算，无 IO 依赖 |
| 2-B | `cli/ai/prompt.py`：拆分 BASE_SYSTEM_PROMPT | S | 无 | 为 injector 提供基础文本 |
| 2-C | `tests/memory/test_injector.py` | M | 2-A | token 预算裁剪逻辑必须测试 |

### 阶段 3：提炼层（依赖 0-A）

| 步骤 | 任务 | 规模 | 依赖 | 说明 |
|------|------|------|------|------|
| 3-A | `cli/memory/extractor.py`：LLM 摘要提炼 + 超时 | M | 0-A | 依赖 call_ai_api()，需 mock 测试 |

### 阶段 4：协调层（依赖全部阶段 0-3）

| 步骤 | 任务 | 规模 | 依赖 | 说明 |
|------|------|------|------|------|
| 4-A | `cli/memory/manager.py`：MemoryManager 5 个方法 | L | 1-A, 2-A, 3-A, 0-B | 协调层，最后实现 |
| 4-B | `cli/memory/__init__.py` | S | 4-A | 一行 re-export |
| 4-C | `tests/memory/test_manager.py`：集成测试（mock LLM） | M | 4-A | 关键路径测试 |

### 阶段 5：配置层（依赖 0-A，可提前）

| 步骤 | 任务 | 规模 | 依赖 | 说明 |
|------|------|------|------|------|
| 5-A | `cli/config.py`：增加 `memory: MemoryConfig` | S | 0-A | 非破坏性追加字段 |

### 阶段 6：接入现有系统（依赖 4-A + 5-A）

| 步骤 | 任务 | 规模 | 依赖 | 说明 |
|------|------|------|------|------|
| 6-A | `cli/ai/client.py`：memory_context 参数 + 动态 prompt | M | 4-A | 关键接入点，需回退路径 |
| 6-B | `cli/main.py`：load() + save_session_memory() + --no-memory | M | 4-A, 6-A | 主流程接入 |
| 6-C | `cli/ai/insights.py`：钩子调用 save_insight_from_ai() | S | 4-A | 简单追加 |
| 6-D | `cli/ai/trace.py`：新增 `log_memory_write()` + `log_memory_injection()` 公开方法，含完整事件字段定义（FIX-3/4） | S | 无 | 审计能力；事件结构见改动清单 trace.py 说明 |
| 6-E | `cli/skills/sandbox/filesystem.py`：扩展 PROTECTED_PATHS | S | 无 | 安全加固 |
| 6-F | `cli/commands/ai.py`：`ai_chat()` 增加 `--no-memory` + `-c/--session` + memory load/save 全流程，与 main.py smart mode 对齐（FIX-1） | M | 4-A, 6-A | **CTO 强制新增**：sh ai chat 是独立命令入口，不接入则 memory 对此路径完全无效 |
| 6-G | `cli/memory/injector.py`：`build_system_prompt()` 增加 `on_inject` 回调参数，注入时触发审计（FIX-4） | S | 4-A | 保持 injector 纯计算，审计由 manager 层通过回调完成 |

> **demo 里程碑 M0（FIX-7）**：完成 0-A + 1-A + 2-A + 2-B + 4-A（前两方法 load/build_system_prompt）+ 5-A + 6-A + 6-B（仅加载部分）即可 demo：`sh memory init` 手动创建偏好 → `sh ai chat "..."` → 验证 SYSTEM_PROMPT 包含偏好内容。这是最高价值最短路径，建议作为第一个迭代检查点。

### 阶段 7：sh memory 命令（依赖 4-A）

| 步骤 | 任务 | 规模 | 依赖 | 说明 |
|------|------|------|------|------|
| 7-A | `cli/commands/memory.py`：init / list / show / set / delete / clear / add-campaign / update-campaign / status | L | 4-A | 命令层，最后实现 |

### 关键并行机会

```
0-A ──┬── 1-A ─────────────────────────┐
      ├── 2-A ──── (与1-A并行) ─────────┤
      ├── 3-A ──── (与1-A并行) ─────────┤── 4-A ── 6-A/6-B/7-A
      └── 0-B ── (与1-A并行) ───────────┘
2-B ── (无依赖，最早可做)
5-A ── (依赖 0-A，可与 1-A 并行)
6-D,6-E ── (无依赖，随时可做)
6-F ── (依赖 4-A + 6-A，与 6-B 完全并行)
6-G ── (依赖 4-A，可在 4-A 完成后立即开始)
```

---

## 风险与缓解策略

| 风险 ID | 描述 | 概率 | 影响 | 缓解策略 |
|---------|------|------|------|---------|
| R-01 | tiktoken 安装失败（企业内网环境）| 中 | 高 | `injector.py` 对 `import tiktoken` 做 `try/except`；失败时用字符数估算（1 token ≈ 4 chars）作为降级方案；不阻断启动 |
| R-02 | `user_profile.yaml` YAML 格式损坏 | 低 | 中 | `store.load_user_profile()` 用 `yaml.safe_load` + try/except；失败时返回空 `UserProfile()`，打印 `[yellow]警告：偏好文件损坏，使用默认值[/yellow]`，主 AI 调用正常继续（见 R1 对抗） |
| R-03 | 会话摘要 LLM 超时 | 中 | 低 | `extractor.extract()` 使用 `daemon=True` 后台线程（不用 ThreadPoolExecutor）+ `threading.Event`；`future.result(timeout=30)` 超时后后台线程随进程退出自动终止，避免连接泄漏；超时返回 `ExtractionResult(skipped=True, reason="extractor_timeout")`；超时时向 ai_trace.jsonl 写入 `{type: memory_write, skipped: true, skip_reason: extractor_timeout}` 而非静默跳过；不丢失当次分析结果，仅跳过摘要写入（BR-15）（FIX-5）|
| R-04 | `analysis_insights/` 积累 200 条后读取性能下降 | 低 | 低 | `store.load_recent_insights()` 只读最新 N 条（按文件 mtime 倒序，取前 5）；200 条文件 glob 在 SSD 上 < 20ms |
| R-05 | MemoryManager 在 `async def lifespan()` 中被调用阻塞事件循环 | 中 | 高 | **设计约束**：`MemoryManager` 所有方法均为同步函数；`cli/main.py` 是同步入口（Typer 的 `cli()` 是同步的），不存在 async 上下文；`extractor.py` 调用 `call_ai_api()` 若为 async，使用 `asyncio.run()` 或改为同步版本（见 R1 对抗详述） |
| R-06 | PII 扫描正则误报（如年份 "2026" 被识别为部分号码）| 低 | 低 | 复用 `trace.py` 已验证的正则（顺序固定，身份证先于订单号）；误报时洞察被跳过，用户会看到 dim 提示，可意识到问题 |
| R-07 | `sh memory clear --all` 误操作不可撤销 | 低 | 高 | 三次确认交互；--all 标志必须明确输入；可建议用户先 `git init ~/.socialhub/memory` 做版本控制（不强制实现）|
| R-08 | Windows 路径 `0o600` 权限无效 | 低 | 低 | 复用 `SessionStore` 已有逻辑（`os.open` + POSIX 权限），在 Windows 上会静默忽略，与现有 sessions/ 行为一致 |

---

## 测试策略

### 单元测试

**`tests/memory/test_pii.py`**
- 手机号 / 身份证 / 邮箱 / 订单号被正确 mask
- 聚合数据（"GMV 占比 60%"）不被误报
- 空字符串输入不崩溃

**`tests/memory/test_store.py`**
- `save_insight()` 写入后文件权限为 0o600
- `save_insight()` 使用原子写（tmp → replace），中断不留残余文件
- 已损坏的 YAML 文件 `load_user_profile()` 返回空 UserProfile 而非抛出
- `purge_expired()` 删除超出 TTL 的文件，保留未过期文件
- `purge_expired()` 文件数量超上限时删除最旧文件
- 路径遍历：`..` 字符在 insight_id 中被拒绝（allowlist 验证）

**`tests/memory/test_injector.py`**
- `build_system_prompt()` 在 context 全空时返回 BASE_SYSTEM_PROMPT（有效降级）
- token 预算超出 4000 时按 L3→L2 顺序裁剪
- L4 不被裁剪（最高优先级）
- 归档活动（status=archived）不出现在输出中（BR-02）
- `build_system_prompt()` 耗时 ≤ 50ms（性能断言）

**`tests/memory/test_models.py`**
- `Campaign.status` 在 `period.end < today` 时自动返回 "archived"（BR-01）
- `MemoryConfig` 从 `Config` 正确解析
- `MemoryContext` 所有字段可为空，不 raise

### 集成测试

**`tests/memory/test_manager.py`**（mock `call_ai_api` + mock 文件系统）
- `load()` 在所有层文件不存在时返回空 MemoryContext，不抛出
- `load()` 在 user_profile.yaml 损坏时返回空 UserProfile，其余层正常加载
- `save_session_memory(no_memory=True)` 不写入任何文件
- `save_session_memory()` 在 LLM 超时时跳过写入，返回 None
- `save_session_memory()` 在 PII 命中时跳过该洞察，写入其他洞察
- `save_insight_from_ai()` PII 命中时不写文件，返回 False
- 完整轮次：`load()` → `build_system_prompt()` → `save_session_memory()` → 下一次 `load()` 能读到摘要
- 审计日志：每次 save 后 ai_trace.jsonl 包含对应 memory_write 事件

**`tests/test_main_memory_integration.py`**（端到端，mock AI + 文件系统）
- `--no-memory` 参数：AI 调用完成后无新增记忆文件
- `sh memory init` 创建 user_profile.yaml 后，下次 AI 调用的 SYSTEM_PROMPT 包含偏好内容

### 边界场景测试（来自 R1 对抗）

- 并发：两个进程同时写同一个 insight 文件，只有一个成功（原子写保证）
- 大量文件：预填 200 条 insight 文件，`load_recent_insights()` 耗时 ≤ 100ms
- 空会话：`session.messages = []` 时 `save_session_memory()` 不崩溃

---

## 迭代记录（R1/R2/R3 对抗摘要及修正）

---

### R1：破坏者（极端场景 / 并发 / 大数据）

**对抗问题及原始设计缺陷**

**Q1：`user_profile.yaml` 损坏时 AI 调用是否中断？**

初始设计中 `store.load_user_profile()` 未明确规定失败时的行为，可能抛出 `yaml.YAMLError` 向上传播，导致 `MemoryManager.load()` 失败，继而阻断主 AI 调用。

**修正**：
- `store.load_user_profile()` 显式 `try/except (yaml.YAMLError, OSError, ValidationError)`；
- 失败时打印 `[yellow]警告：偏好文件损坏，使用默认值[/yellow]`，返回 `UserProfile()`；
- `MemoryManager.load()` 本身也有外层 try/except；
- 任何记忆层失败均不阻断 AI 调用（PRD 可靠性要求）。

**Q2：会话摘要提炼 LLM 超时失败，会话数据是否丢失？**

原始设计中 `extractor.extract()` 若 LLM 超时抛出 `httpx.TimeoutException`，`save_session_memory()` 会向上传播异常，导致调用方 `main.py` 感知到错误。

**修正**：
- `extractor.extract()` 内部捕获所有异常（包括超时）；
- 超时或失败时返回 `ExtractionResult(skipped=True, reason="timeout")`；
- `save_session_memory()` 检查 `skipped=True` 后直接返回 `None`；
- 当次会话数据（SessionStore 已保存）不受影响；
- 超时只影响 L2/L3 记忆写入，不影响 L1 session 保存（BR-15）。

**Q3：100 条洞察文件同时被 `sh memory list` 读取，性能是否可接受？**

原始设计未限制 `list` 命令的读取数量，可能一次全量 JSON parse 200 条文件。

**修正**：
- `store.list_insights()` 使用 `Path.glob("*.json")` + `stat().st_mtime` 排序，只取前 N 条；
- 对 `sh memory list` 的分组视图（M2），最多读取 20 条（洞察 3 + 摘要 3 + 少量元数据）；
- `--all` 参数才全量读取；
- 验收标准：200 条文件 `list` 命令 ≤ 500ms（本地 SSD）。

**Q4：MemoryManager.load() 在 `async def lifespan()` 中被调用是否违反 asyncio 规则？**

Memory 来自对 `asyncio.to_thread()` 的记忆：同步阻塞函数不得在 async context 中直接调用。

**分析**：`cli/main.py` 的 `cli()` 是 Typer 的同步入口函数，不是 `async def`，不存在 async context。`MemoryManager.load()` 也是同步函数，在同步入口中调用完全合规。`extractor.py` 调用 `call_ai_api()`——需确认 `call_ai_api()` 是否为 async：

**修正**：
- `extractor.py` 调用 `call_ai_api()` 时，若 `call_ai_api` 内部使用 `asyncio.run()`，则在 `extractor.py` 中不再嵌套 `asyncio.run()`（嵌套会报 `RuntimeError: This event loop is already running`）；
- 采用策略：`extractor.py` 提供同步接口，内部用 `concurrent.futures.ThreadPoolExecutor` + `future.result(timeout=30)` 调用 LLM，确保不进入 async 上下文；
- 明确约束写入代码注释：`SessionExtractor.extract()` 是同步方法，调用方不得在 async context 中调用。

**R1 导致的设计修正**：
1. `store.py` 所有 load 方法加 try/except，返回空默认值
2. `extractor.py` 使用 `ThreadPoolExecutor.submit().result(timeout=30)` 而非 asyncio
3. `store.list_insights()` 加 N 条上限，全量读取需显式 `--all`
4. `manager.py` 增加外层 try/except 保护所有 5 个公开方法

---

### R2：CLAUDE.md 守护者（逐条对照原则和硬约束）

**对抗问题及检查结果**

**Q1：MCP adapter 层（`cli/analytics/mcp_adapter.py`）是否需要修改？**

CLAUDE.md 明确："`cli/analytics/mcp_adapter.py` 是 MCP Server 访问 CLI 分析能力的稳定接口，不得绕过直接 import `cli.commands.analytics`"。

**检查结论**：记忆系统是 CLI 本地层，数据存储在 `~/.socialhub/memory/`，不通过 MCP 协议传输，也不需要调用分析适配层。**不修改 mcp_adapter.py**，完全符合 CLAUDE.md。

**Q2：`sh memory` 命令是否需要通过 `validator.py`？**

CLAUDE.md 说："AI 命令必须通过 `validator.py`"（原文："所有 AI 生成的命令必须经过 `validator.py` 校验"）。

**关键区分**：`sh memory` 是用户直接执行的 Typer 注册命令，不是 AI 生成的命令。`validator.py` 的职责是校验 AI 生成的命令字符串，对照 Typer 命令树验证合法性。`sh memory` 本身就是 Typer 命令树的一部分，无需再自我验证。**不需要 `validator.py`**。

**Q3：记忆写入是否使用 `shell=True`？**

CLAUDE.md 红线："禁止 `shell=True`"。

**检查**：`store.py` 所有写入均使用 `os.open()` + `os.fdopen()` + `os.replace()` 文件 API，不涉及任何 `subprocess` 调用，更无 `shell=True`。**完全合规**。

**Q4：Skills 沙箱是否需要扩展以保护 memory 目录？**

安全合规文档明确要求扩展 `PROTECTED_PATHS`。

**修正**：确认在改动清单中包含 `cli/skills/sandbox/filesystem.py` 扩展，将 `Path.home() / ".socialhub" / "memory"` 加入 `PROTECTED_PATHS`。**已包含在修改文件清单中**。

**Q5：`cli/ai/trace.py` 中 `_mask_pii()` 是内部函数，memory 系统是否可以直接 import？**

安全合规文档注意项："`_mask_pii()` 是 TraceLogger 内部函数，Memory 系统复用时需提升为公开函数，或在 `memory/` 中独立实现"。

**修正**（已在初始设计中采纳）：`cli/memory/pii.py` 独立实现相同正则逻辑，不 import `trace.py` 内部函数。原因：①避免跨模块内部依赖脆弱性；②`pii.py` 返回 `(masked_text, bool)` 元组，与 trace 的单返回值接口不同；③memory 的 PII 扫描语义是"是否命中则跳过写入"，与 trace 的"脱敏后继续写入"语义不同。**已在设计中正确处理**。

**R2 导致的设计修正**：
1. 明确 `sh memory` 不走 validator.py（补充了不改文件清单中的说明）
2. 明确 `mcp_adapter.py` 不修改（记忆本地存储，不经 MCP）
3. 确认 `filesystem.py` PROTECTED_PATHS 扩展在改动清单中
4. 确认 `pii.py` 独立实现，不跨模块依赖 trace.py 内部函数

---

### R3：新入职工程师（可理解 / 步骤清晰 / 依赖明确）

**对抗问题及检查结果**

**Q1：`cli/memory/` 模块是否可以独立测试，不依赖 MCP server？**

原始设计中 `extractor.py` 直接调用 `call_ai_api()`，而 `call_ai_api()` 可能需要有效的 Azure OpenAI 配置。若测试环境没有 API Key，测试会失败。

**修正**：
- `extractor.py` 接收可注入的 `ai_caller` 参数（`Callable[[list[dict]], str]`），默认为 `None` 时内部 import `call_ai_api`；
- 测试时传入 mock callable，完全无需真实 API；
- `store.py`、`injector.py`、`pii.py` 纯文件 IO 和计算，无任何外部依赖；
- 结论：**`cli/memory/` 可完全独立单元测试，无需 MCP Server**。

**Q2：`build_system_prompt()` 函数是否比 `SYSTEM_PROMPT` 常量更难维护？**

常量的维护成本：修改时一行改定；函数的维护成本：需理解 token 预算逻辑 + 多层注入顺序。

**回应**：接受这个维护成本，原因：
- 函数的复杂性有上界：`injector.py` 单文件，约 100 行；
- 静态常量无法满足 PRD M17（动态注入）；
- 降级路径明确：`memory_context is None` 时 `client.py` 回退到静态 `SYSTEM_PROMPT`，向后兼容；
- 测试覆盖：`test_injector.py` 验证各分支，维护时有安全网。

**修正**（补充可理解性）：
- `injector.py` 增加详细注释描述注入顺序和裁剪策略；
- `BASE_SYSTEM_PROMPT` 在 `prompt.py` 中单独定义，`injector.py` import 使用，便于文本编辑；
- 新入职工程师修改 prompt 文本只需改 `prompt.py::BASE_SYSTEM_PROMPT`，不需要理解 `injector.py` 逻辑。

**Q3：`MemoryManager` 是否需要成为单例？还是每次 CLI 调用创建新实例？**

单例模式的问题：CLI 是一次性进程，每次命令调用独立启动 Python 进程；单例没有意义，反而引入全局状态，增加测试难度（需要重置单例状态）。

**决策：每次 CLI 调用创建新实例**，理由：
- CLI 是短生命周期进程（< 5 秒），无需单例缓存；
- 实例化成本可忽略（仅创建 Path 对象和 MemoryStore）；
- 测试友好：每个测试用例独立创建实例，无全局状态污染；
- `main.py` 中创建一个 manager 实例，传给各调用点（依赖注入，不是全局变量）。

**Q4（新增）：开发步骤依赖关系是否清晰，新人能独立完成一个模块？**

**补充**：每个阶段的任务独立可验证：
- 阶段 0：`models.py` 可以独立运行 `pytest tests/memory/test_models.py`
- 阶段 1：`store.py` 测试时不需要任何 AI 依赖
- 阶段 2：`injector.py` 测试时只需要一个假的 `MemoryContext` 对象
- 阶段 3：`extractor.py` 通过 mock `ai_caller` 独立测试
- 所有测试均可在无网络的环境中运行

**R3 导致的设计修正**：
1. `extractor.py` 增加 `ai_caller: Optional[Callable] = None` 可注入参数，默认使用 `call_ai_api`
2. `MemoryManager` 明确文档化为"非单例，每次进程创建新实例"
3. `injector.py` 的 `build_system_prompt()` 设计增加注释：文本修改入口在 `prompt.py::BASE_SYSTEM_PROMPT`
4. 所有测试用例说明：无需网络，无需 MCP Server，可完全本地运行

---

### 三轮对抗后的关键设计决策总结

| 决策 | 原因 | 来源 |
|------|------|------|
| `pii.py` 独立实现，不依赖 `trace.py` 内部函数 | 接口语义不同，避免内部依赖 | R2 |
| `extractor.py` 用 `ThreadPoolExecutor` 而非 asyncio | CLI 入口是同步函数，防止 asyncio 嵌套 | R1 |
| `store.py` 所有 load 方法 try/except 返回空默认 | 记忆失败不阻断主流程 | R1 |
| `extractor.py` 接收可注入 `ai_caller` 参数 | 独立单元测试，无需真实 API | R3 |
| `MemoryManager` 非单例，每进程创建新实例 | CLI 短生命周期，单例无意义 | R3 |
| `sh memory` 不走 `validator.py` | 直接注册 Typer 命令，不是 AI 生成命令 | R2 |
| `mcp_adapter.py` 不修改 | 记忆本地存储，不经 MCP 协议 | R2 |
| `store.list_insights()` 默认限制读取数量 | 100+ 文件全量读取性能风险 | R1 |
