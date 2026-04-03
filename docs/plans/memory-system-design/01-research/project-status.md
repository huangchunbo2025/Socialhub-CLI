# 项目记忆系统现状分析

## 调用链图

```
用户输入自然语言
    │
    ▼
cli/main.py :: cli()  [智能模式检测]
    │
    ├─ SessionStore.load(session_id) ──── 读取 ~/.socialhub/sessions/{id}.json
    │
    ▼
cli/ai/client.py :: call_ai_api(messages, session)
    │   ├─ _build_messages()  ← SYSTEM_PROMPT (完全静态) + session.get_history()
    │   └─ Azure OpenAI API 调用
    │
    ▼
cli/ai/parser.py :: extract_plan()
    │   └─ 提取 [PLAN_START]...[PLAN_END]
    │
    ▼
cli/ai/validator.py :: validate_command()
    │   └─ 对照 Typer 命令树校验合法性
    │
    ▼
cli/ai/executor.py :: execute_plan()
    │   ├─ TraceLogger.log_plan_start()  ──── 写 ~/.socialhub/ai_trace.jsonl
    │   ├─ 逐步 subprocess.run(shell=False)
    │   ├─ TraceLogger.log_step()        ──── 写 ~/.socialhub/ai_trace.jsonl
    │   └─ TraceLogger.log_plan_end()    ──── 写 ~/.socialhub/ai_trace.jsonl
    │
    ▼
cli/ai/insights.py :: generate_insights()
    │   └─ 生成 AI 洞察 → 仅打印到终端，【不持久化】
    │
    ▼
Session.add_turn(user_message, assistant_message)
    │
    ▼
SessionStore.save(session)  ──── 写 ~/.socialhub/sessions/{id}.json
```

**特殊路径 - `sh ai chat`**：
```
cli/commands/ai.py :: chat()
    └─ 直接调用 call_ai_api()，【无 session 支持】
       每次对话完全独立，无历史注入
```

---

## 各组件分析

### SessionStore (`cli/ai/session.py`)
| 属性 | 详情 |
|------|------|
| **写入时机** | 每次 smart-mode 对话完成后，add_turn() + save() |
| **读取时机** | smart-mode 入口，通过 `--session` 参数或 config 中存储的 session_id 加载 |
| **生命周期** | TTL 24h（默认），max_history 10 turns，超出则滑动窗口截断 |
| **存储格式** | `~/.socialhub/sessions/{timestamp}-{uid}.json`，含 messages 列表 |
| **安全** | 原子写入（tmp → rename），文件权限 0o600，session_id allowlist 校验 |
| **缺口** | 仅保存原始消息文本，无语义提取；24h 后全部丢失；`ai chat` 命令不支持 |

### RunHistory (`cli/commands/history.py`)
| 属性 | 详情 |
|------|------|
| **写入时机** | **【严重发现】`save_run()` 在整个代码库中从未被调用** |
| **读取时机** | 用户手动执行 `sh history list/show/rerun` |
| **生命周期** | 无 TTL，永久保留 |
| **存储格式** | `~/.socialhub/runs/{timestamp}_{uid}.json`，含 sql_trace/exec_time_ms/output_artifact |
| **缺口** | 死代码 — `~/.socialhub/runs/` 目录永远为空；AI 不可读；无结构化洞察 |

### TraceLogger (`cli/ai/trace.py`)
| 属性 | 详情 |
|------|------|
| **写入时机** | execute_plan() 每步执行，写 plan_start/step/plan_end 事件 |
| **读取时机** | 仅供运维/调试人工查看，AI 从不读取 |
| **生命周期** | NDJSON 轮转（默认 10MB → 1 backup），无 TTL |
| **存储格式** | `~/.socialhub/ai_trace.jsonl`，PII 脱敏，线程安全 |
| **缺口** | 纯运维日志；AI 完全感知不到；有价值的 command/success/duration 数据未被利用 |

### Config (`cli/config.py`)
| 属性 | 详情 |
|------|------|
| **功能** | 静态配置（AI provider、MCP 端点、session TTL 等） |
| **缺口** | 不是记忆，不随使用积累；无偏好学习机制 |

### SkillRegistry (`cli/skills/registry.py`)
| 属性 | 详情 |
|------|------|
| **功能** | 已安装 Skills 的元数据（name/version/category/enabled） |
| **缺口** | 仅安装元数据，无使用频率、无偏好标记 |

---

## SYSTEM_PROMPT 动态化现状

**当前状态：完全静态**

```python
# cli/ai/prompt.py
SYSTEM_PROMPT = """You are the intelligent assistant for SocialHub.AI CLI..."""
# 一个巨大的硬编码字符串常量，约 180 行
```

- `_build_messages()` 始终将完整 SYSTEM_PROMPT 作为第一条 system message
- 零个性化注入：不知道用户是谁、企业规模如何、历史偏好是什么
- 不知道哪些 Skills 已安装可用
- 不知道任何历史分析结论

---

## 可复用能力

| 能力 | 位置 | 可复用价值 |
|------|------|-----------|
| 原子文件写入（0o600）| `session.py::SessionStore.save()` | 记忆文件的安全写入基础设施 |
| PII 脱敏引擎 | `trace.py::_mask_pii()` | 记忆写入前的脱敏处理 |
| TTL + 过期清理 | `session.py::is_expired()` + `purge_expired()` | 记忆 TTL 管理 |
| Config Pydantic 模型 | `config.py::SessionConfig/TraceConfig` | 新 MemoryConfig 的设计范式 |
| Skills Registry 模式 | `skills/registry.py` | JSON 注册表模式可复用于记忆索引 |
| `_SESSION_ID_RE` allowlist | `session.py` | 路径遍历防护模式 |

---

## 需改造模块

| 模块 | 改造内容 |
|------|---------|
| `cli/ai/prompt.py` | 静态 SYSTEM_PROMPT → 动态构建函数，注入记忆上下文 |
| `cli/ai/client.py` | `_build_messages()` 接收动态 memory_context 参数 |
| `cli/main.py` | 在 session 加载后，额外加载 memory_context，注入 AI 调用 |
| `cli/ai/insights.py` | `generate_insights()` 除打印外，同时触发记忆提取写入 |
| `cli/commands/history.py` | 接入 `save_run()` 调用（当前完全是死代码） |

---

## 明显缺口

1. **跨会话失忆**：24h 后用户所有对话上下文全部丢失，AI 永远是陌生人
2. **insights 只活在终端**：`generate_insights()` 每次产生有价值的业务洞察，但秒消失
3. **AI 不知道已装哪些 Skills**：SYSTEM_PROMPT 没有注入已安装 Skills 列表
4. **无分析偏好积累**：用户每次都要重新说"按渠道分析"、"导出 CSV"
5. **历史命令不可查询**：RunHistory 是死代码，AI 无法说"上次你查的是..."
6. **无企业业务上下文**：AI 不知道这家企业的主营品类、核心指标基准值
7. **`ai chat` 完全无记忆**：与 smart-mode 的 session 机制完全割裂

---

## 技术债

| 债务 | 严重程度 | 说明 |
|------|---------|------|
| `history.save_run()` 从不被调用 | 高 | 完整的审计基础设施但是死代码 |
| `ai chat` 无 session 支持 | 中 | 与 smart-mode 的记忆能力不一致 |
| SYSTEM_PROMPT 无法动态化 | 高 | 架构上需要从常量改为构建函数 |
| insights 不持久化 | 高 | 最有价值的 AI 输出每次都被丢弃 |
