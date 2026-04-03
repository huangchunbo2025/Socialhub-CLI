# CTO 终审报告 — 记忆系统技术设计

> 评级：**B+（可推进，含强制修正项）**
> 日期：2026-04-02
> 审查人：CTO（基于 CLAUDE.md + 05-prd.md + 06-technical-design.md + 真实代码库）
> 审查基准：cli/main.py / cli/commands/ai.py / cli/commands/history.py / cli/ai/trace.py

---

## 评级说明

| 维度 | 评分 | 说明 |
|------|------|------|
| 架构分层一致性 | A | cli/memory/ 层次清晰，依赖方向单向，隔离 MCP 正确 |
| 技术债覆盖 | C | history.save_run() 死代码未修复；ai chat 无 session 漏洞未解决 |
| 风险识别完整性 | B+ | 8 个风险覆盖全面，但最高优先级风险（R3:extractor 同步策略）需补强 |
| 可扩展性设计 | B | 文件型存储清晰，SaaS 演进路径和向量检索升级路径未明确 |
| 审计与可观测性 | C+ | content_hash 存在但无 memory_write 事件类型定义；排查路径有盲区 |
| 开发效率 | B+ | 并行机会识别良好，但 demo 里程碑未明确，存在可裁剪任务 |

**综合评级：B+**

主要问题：技术债未处理 + 审计事件定义不完整，导致生产排查路径残缺。其余设计质量较高，允许进入开发阶段，但以下强制项必须在阶段 4 完成前解决。

---

## 一、架构一致性审查

### 结论：通过

**正面确认：**

1. `cli/memory/` 与现有 `cli/ai/`、`cli/skills/` 平行，符合分层原则。外部只通过 `from cli.memory import MemoryManager` 访问，__init__.py 是单一入口，无暴露内部结构。
2. 依赖方向正确：`memory/` 依赖 `cli/ai/client.py`（call_ai_api），`cli/ai/insights.py` 和 `cli/main.py` 依赖 `memory/`，不存在反向依赖。循环导入风险已通过 `extractor.py` 的 `ai_caller` 可注入参数切断。
3. MCP 隔离设计无误：`mcp_adapter.py` 不修改（记忆本地存储），`mcp_server/server.py` 不修改，满足"本地 memory 不泄漏到多租户 MCP"的核心约束。PROTECTED_PATHS 扩展覆盖 Skills 沙箱向量，是安全合规关键步骤，已在改动清单中。
4. `sh memory` 不走 validator.py 的判断正确——直接注册的 Typer 命令无需 AI 安全执行链校验。

**潜在风险（已在 R2 对抗中识别）：**

`cli/config.py` 引入 `from cli.memory.models import MemoryConfig` 造成 config.py → memory/models.py 的依赖。若 models.py 将来反向引用 config.py（比如读取某配置默认值），则形成循环。**建议：models.py 中 MemoryConfig 使用 Field(default=...) 纯硬编码默认值，禁止在 models.py 内部 import config.py。**

---

## 二、技术债评估

### 强制修正项 1：`history.save_run()` 是死代码

**现状（通过代码审查确认）：**

`cli/commands/history.py` 中 `save_run()` 函数（第 29 行起）定义完整、有详细注释，但在整个代码库中**从未被任何文件调用**。实际的历史记录由 `cli/main.py` 中的 `save_history()` 函数（第 163 行）执行，写入 `~/.socialhub/history.json`，格式完全不同（仅存 `last_query` + `last_commands`）。

两套"历史"并存：
- `history.save_run()` — 设计完整（含 sql_trace、exec_time_ms、output_artifact），写 `~/.socialhub/runs/{run_id}.json`，**零调用**
- `save_history()` — 简陋实现（只存最后一条），实际在用

**影响范围：** 技术设计 06 中并未提及修复此死代码，意味着记忆系统接入后，`ai_trace.jsonl` 有完整 trace，但 `history.save_run()` 的丰富 audit 字段（sql_trace、exec_time_ms）仍然无人调用。这是**遗留审计盲区**，与记忆系统的"可追溯性"目标相悖。

**决定：本期技术设计需明确处理策略**（见 R1 修正建议 #1）。

### 强制修正项 2：`ai chat` 命令缺少 session 和 memory 支持

**现状（通过代码审查确认）：**

`cli/commands/ai.py::ai_chat()` 是独立的 Typer 命令（`sh ai chat "..."`），其实现（第 44 行）：

```python
response, _ = call_ai_api(query, api_key)
```

与 `cli/main.py` smart mode（第 314 行）：

```python
response, _usage = call_ai_api(query, session_history=session_history)
```

相比，`ai chat` 命令**完全没有**：
- Session 加载（`-c/--session` 支持）
- MemoryManager.load() 调用
- save_session_memory() 调用
- `--no-memory` 参数

**影响范围：** 技术设计 06 的改动清单在 `cli/main.py` 中增加了 memory 接入，但**没有提及 `cli/commands/ai.py`**。用户若通过 `sh ai chat "..."` 而非智能模式访问 AI，完全无法获得记忆功能，且不写入任何摘要。PRD M17、M16 的目标在此路径下静默失效。

**决定：必须在阶段 6 补充 ai.py 改动**（见 R1 修正建议 #2）。

---

## 三、风险评估

### 最大技术风险：R-03 extractor 同步策略

技术设计 R-03 的缓解策略为：`extractor.extract()` 用 `concurrent.futures.ThreadPoolExecutor` + `future.result(timeout=30)` 调用 LLM。

**CTO 对抗：此策略存在重要遗漏。**

`ThreadPoolExecutor` 在超时时 `future.result(timeout=30)` 会抛出 `concurrent.futures.TimeoutError`，但**后台线程仍在运行**，继续消耗 API 配额，直到 LLM 返回（可能需要额外 30-60s）。在 CLI 短生命周期进程中，进程退出后线程会被强制终止，但如果 call_ai_api 内部持有 httpx.Client 连接，会造成连接泄漏告警。

**缓解方案（补充到 06 中）：**
- 使用 `threading.Event` + `daemon=True` 线程模式替代 ThreadPoolExecutor，确保后台线程随进程退出而终止
- 或在 extractor 层显式 cancel http 请求（httpx 支持 `client.close()`）
- 超时后在审计日志中写入 `{"type": "memory_write", "status": "skipped", "reason": "extractor_timeout"}` 而非静默

### 次要风险：注入预算裁剪方向矛盾

技术设计中两处注入优先级描述不一致：

- `manager.py` 方法注释：`tiktoken 总预算 ≤ 4000 tokens，超出时按 L3→L2→L4 顺序裁剪`（L4 最后裁剪 = 最高优先级）
- `injector.py` 职责说明：`超预算裁剪顺序 L3 > L2 > L4`（> 表示先裁剪）

两处一致，L4 确实最高优先级，但文字表述"L3→L2→L4 顺序裁剪"容易被理解为 L4 最先被裁剪。建议统一改为"**先裁剪 L3，再裁剪 L2，最后裁剪 L4（L4 优先级最高，最后裁剪）**"。

---

## 四、可扩展性评估

### SaaS 多用户演进

当前设计：单用户，记忆文件在 `~/.socialhub/memory/`，MemoryConfig.memory_dir 可配置。

**演进路径（无需颠覆性重写）：**

1. `MemoryStore` 构造时接收 `user_id` 参数，将存储路径从 `~/.socialhub/memory/` 改为 `~/.socialhub/memory/{user_id}/`，其余逻辑不变。
2. SaaS 模式下，`user_id` 来自认证 token 解析（auth.gate 层已有 ensure_authenticated()）。
3. 云端同步层作为可选 Mixin：`CloudMemoryStore(MemoryStore)` 覆盖 save/load 方法，将本地文件同步到远端 API。本地文件作为缓存层保留。
4. 多租户 MCP 场景中，memory 仍保持 CLI 本地，不通过 MCP 暴露，与现有 `tenant_id` 隔离机制正交。

**改动量估算：** `store.py` 约 20 行改动（路径构造），`manager.py` 增加 `user_id` 参数，`MemoryConfig` 增加 `cloud_sync: bool` 字段。影响范围小。

### 向量检索升级（bm25s → sqlite-vec）

当前 MVP 不做向量检索，使用文件名/时间倒序检索最近 N 条。

**升级路径：**

当前 `store.load_recent_insights(n=5)` 返回时间倒序的 N 条。升级 sqlite-vec 时：
1. `store.py` 新增 `MemoryIndex`（sqlite 连接），在 `save_insight()` 时同时写入 embedding。
2. `load_recent_insights()` 接口签名不变，增加可选参数 `query_text: str = ""`，有 query 时走向量检索，无 query 时走文件时间倒序（向后兼容）。
3. `injector.py` 不需要改动，因为接口层隔离良好。

**改动量估算：** `store.py` 约 80-100 行新增，`injector.py` 零改动，`manager.py` 约 10 行改动（load 调用传 query 参数）。影响范围可控。

---

## 五、三轮对抗

---

### R1：最薄弱 3 个环节

#### 薄弱环节 1：`history.save_run()` 死代码未处理，技术债继续积累

**问题描述（如上）：** `history.save_run()` 从未被调用，而技术设计完全未提及此问题。记忆系统上线后，`ai_trace.jsonl` 有完整计划级 trace，但命令级 audit（sql_trace、exec_time_ms）仍缺失。

**修正建议（写入 06 的不修改文件清单）：**

明确策略：本期**不**修复 `history.save_run()`，原因是该函数的完整调用需要 executor.py 改造（捕获 exec_time_ms），超出 memory 系统范围。但技术设计须在"不需要改的文件"清单中**明确记录此为已知技术债**，推迟至下期 executor.py 重构时处理。不能让它继续无声地存在。

#### 薄弱环节 2：`sh ai chat` 路径对记忆系统不可见

**问题描述（如上）：** `cli/commands/ai.py::ai_chat()` 未在改动清单中，导致 memory 功能对 `sh ai chat` 用户完全失效。

**修正建议（补充到改动清单阶段 6）：**

```
6-F  cli/commands/ai.py：
     - ai_chat() 增加 --no-memory 参数
     - 调用 MemoryManager().load() 获取 memory_context
     - call_ai_api() 增加 memory_context 参数传递
     - 会话结束后调用 save_session_memory()
     - 与 main.py 的 -c/--session 联通（ai_chat 目前无 session 支持，需同步修复）
```

规模：M（与 6-A/6-B 同级，不是 S，因为还要补 session 支持）

#### 薄弱环节 3：`memory_write` 审计事件结构未定义

**问题描述：** `trace_logger.log_memory_write()` 在技术设计中反复被提及（`save_session_memory` 流程中出现 3 次），但**事件字段结构从未定义**。`TraceLogger` 现有 3 个事件类型（`plan_start`/`step`/`plan_end`），`memory_write` 是新类型，需要明确字段，否则生产排查时无法 `grep type==memory_write` 找到对应记录。

**修正建议（补充到 06 的 trace.py 改动说明中）：**

```python
# 新增 memory_write 事件结构（写入 ai_trace.jsonl）
{
    "ts": "2026-04-02T10:00:00Z",
    "type": "memory_write",
    "trace_id": "<与当次 plan 相同的 trace_id>",
    "session_id": "<session_id>",
    "memory_type": "insight" | "summary" | "preference",
    "memory_id": "<insight/{date}-{slug} 或 summary/{session_id}>",
    "content_hash": "<sha256[:16]>",
    "pii_hit": false,
    "skipped": false,
    "skip_reason": "" | "pii_hit" | "extractor_timeout" | "no_memory_flag"
}
```

---

### R2：生产事故回溯视角

**场景：** 上线后第 7 天，某用户报告"AI 给了错误的分析建议，我认为是记忆导致的，但我不知道是哪条"。

#### 完整排查路径

**Step 1：确认该对话是否注入了记忆**

```bash
sh trace list --since=7d | grep memory_write
```

如果 `ai_trace.jsonl` 有 `memory_write` 事件，说明有记忆被写入。但**注入（读取）事件不记录**——这是当前设计的盲区。

**Step 2：查看该会话注入的 SYSTEM_PROMPT 内容**（当前设计无此能力）

当前设计中，`build_system_prompt()` 是运行时计算函数，**不记录每次构建的结果**。用户说"这次 AI 用了错误的记忆"，但系统无法回放"该次对话实际注入了什么"。

**这是设计缺口。**

**Step 3：查看用户当前记忆内容**

```bash
sh memory list
sh memory show --injection-preview
```

这只能看当前状态，不能看第 7 天前的状态。

**Step 4：用 `sh memory show summary/<ID>` 找到嫌疑条目**

如果用户记得某次对话后的 summary ID（因为有 BR-06 提示），可以直接查看。但如果用户不记得，只能逐条翻 list，人工判断哪条可能导致了错误建议。

**Step 5：删除嫌疑条目**

```bash
sh memory delete <ID>
```

#### 当前审计设计够用吗？

**不够用。存在 3 个盲区：**

| 盲区 | 影响 | 缓解方案 |
|------|------|---------|
| 注入事件未记录（只记写入，不记读取） | 无法回放"该次对话实际使用了哪些记忆" | 在 `build_system_prompt()` 调用时写入 `memory_injection` 事件（含使用的 memory_id 列表和 token 数）到 ai_trace.jsonl |
| SYSTEM_PROMPT 内容未保存 | 无法 diff 前后注入差异 | 在 `memory_injection` 事件中记录 `memory_ids: list[str]`（不存全文，避免冗余，但记录 ID 列表可回溯） |
| 记忆文件无版本历史 | 无法知道第 7 天前某条 insight 的内容（可能已被更新） | 短期：PRD 已提到"洞察文件可 git 管理"，可在 `sh memory status` 输出中提示用户 `git init ~/.socialhub/memory`；长期：insight 写入时追加 `.bak` 或 JSONL 增量记录 |

**强制补充（写入 06 改动清单）：**

在 `injector.py` 的 `build_system_prompt()` 返回前，增加审计事件写入（通过回调而非直接依赖 TraceLogger，保持 injector 纯计算特性）：

```
6-G  cli/memory/injector.py：build_system_prompt() 增加 on_inject 回调参数
     on_inject(memory_ids: list[str], token_count: int) -> None
     manager.py 在调用时传入 trace_logger.log_memory_injection 作为回调
     
     trace.py 新增 log_memory_injection 事件：
     {"type": "memory_injection", "trace_id": ..., "session_id": ...,
      "memory_ids": [...], "token_count": N, "truncated_layers": [...]}
```

---

### R3：开发效率视角

#### 第一个可以 demo 的里程碑

**里程碑 M0：记忆读写可见（预计 2-3 天）**

完成以下任务后即可 demo：
- 0-A（models.py）
- 1-A（store.py）
- 2-A + 2-B（injector.py + BASE_SYSTEM_PROMPT）
- 4-A 的 `load()` 和 `build_system_prompt()` 两个方法（不需要全部 5 个方法）
- 5-A（config.py）
- 6-A（client.py 接入 memory_context）
- 6-B 的加载部分（不需要 save_session_memory，仅需 load + build_system_prompt）

**demo 场景：** `sh memory init` 手动创建 `user_profile.yaml` → 重新运行 `sh ai chat "..."` → 验证 SYSTEM_PROMPT 包含偏好内容。

这是价值最高的一段路：用户能立即感知"AI 记住了我的角色/偏好"，比摘要写入（需要 LLM 超时机制、PII 扫描等完整链路）早至少 3 天。

#### 可并行开发的任务对

技术设计已识别并行机会，以下是补充确认：

| 并行对 | 前提 | 备注 |
|--------|------|------|
| `1-A（store.py）` + `2-A（injector.py）` | 0-A 完成 | 两者均只依赖 models.py，无相互依赖 |
| `3-A（extractor.py）` + `1-A（store.py）` | 0-A 完成 | extractor 只依赖 call_ai_api + models |
| `6-D（trace.py 扩展）` + `6-E（sandbox PROTECTED_PATHS）` | 无依赖 | 随时可做，各 1 小时内完成 |
| `tests/memory/test_store.py` + `tests/memory/test_injector.py` | 各自对应模块完成 | 测试可与实现同步进行 |
| `7-A（sh memory 命令）` 中各子命令 | 4-A 完成 | init/list/show/set/delete 可拆给不同开发者 |

**新增并行对（本次审查发现）：**

- `6-F（ai.py 补 memory 接入）` 与 `6-B（main.py memory 接入）` 可完全并行，接口相同，只是不同命令入口。

#### 可裁剪的任务（不影响 MVP）

| 任务 | 裁剪建议 | 原因 |
|------|---------|------|
| `get_injection_preview()` 完整实现 | 可裁剪到 v1.1，MVP 只返回 `system_prompt` 和 `token_count`，不需要 `layers` 细分 | 用户最需要的是"总量"，层级细分是 debug 工具，优先级低 |
| `get_status()` 的 `token 用量估算` | 可裁剪：只返回文件数量和大小，不做 tiktoken 估算 | token 估算需要加载所有文件内容，与 MVP 性能目标矛盾 |
| `store.purge_expired()` 在 `load()` 中的惰性调用 | 降级为独立命令触发（`sh memory status` 顺带清理），不在每次 load 时执行 | 每次 AI 调用都执行 glob+stat 排序有轻微性能成本，MVP 阶段可接受手动触发 |
| `extractor.py` 中 `user_preferences_update` 合并逻辑 | 可裁剪：MVP 只写 insight 和 summary，不自动更新 user_profile | 自动偏好合并逻辑复杂（冲突处理），与 S3 推迟的理由一致；手动 `sh memory set` 更可控 |

---

## 六、强制修正项汇总

以下 7 项必须在 `06-technical-design.md` 中补充，优先级 P0（进入开发前完成）：

| 编号 | 修正内容 | 对应环节 | 修改位置 |
|------|---------|---------|---------|
| FIX-1 | 改动清单增加 `6-F: cli/commands/ai.py` memory + session 接入 | R1-薄弱环节2 | 改动清单 阶段 6 |
| FIX-2 | 不改文件清单注明 `cli/commands/ai.py`（已改）；同时注明 `cli/commands/history.py::save_run()` 为已知技术债 | R1-薄弱环节1 | 不改文件清单 |
| FIX-3 | `trace.py` 改动说明补充 `memory_write` 事件字段定义 | R1-薄弱环节3 | 改动清单 阶段 6 |
| FIX-4 | 改动清单增加 `6-G: injector.py on_inject 回调 + log_memory_injection 事件` | R2-生产事故 | 改动清单 阶段 6 |
| FIX-5 | 风险表 R-03 补充 daemon 线程 + http cancel 策略 | R1-最大风险 | 风险与缓解策略 |
| FIX-6 | injector.py 裁剪预算描述歧义（统一为"先裁剪 L3，再 L2，L4 最后裁剪"） | 次要风险 | injector.py 职责说明 |
| FIX-7 | 开发步骤增加 demo 里程碑 M0 标注（0-A+1-A+2-A+2-B+4-A 前两方法+5-A+6-A+6-B 加载部分） | R3-开发效率 | 开发步骤 |

---

## 七、建议（非强制）

1. **为 `sh memory` 增加 `--dry-run` 支持：** `sh memory clear --dry-run` 显示将要删除的文件列表而不实际删除，减少误操作风险（R-07 的补充）。

2. **`ai_trace.jsonl` 查询增强：** 当前 `sh trace list` 按类型过滤，建议增加 `sh trace list --type=memory_injection` 快捷过滤，配合 FIX-4 的新事件类型，使排查路径闭环。

3. **`sh memory init` 增加预览确认步骤：** 用户填完所有问题后，显示 "将写入以下偏好：..." 并询问确认，而不是直接写入。成本低，降低错填风险。

4. **考虑 `MemoryConfig.encrypt` 字段的设计时机：** 当前 `encrypt: bool = False` 字段已定义但无实现计划。建议在 MVP 中移除此字段（或标注 `# 未实现，预留给企业版`），避免用户误以为已有加密支持。

---

## 八、开发计划调整建议

### 调整前（原版）

```
阶段 0 → 阶段 1/2/3（并行）→ 阶段 4 → 阶段 5 → 阶段 6 → 阶段 7
```

### 调整后（含新增任务）

```
阶段 0（0-A + 0-B）
  │
  ├── 阶段 1（1-A + 1-B）           并行
  ├── 阶段 2（2-A + 2-B + 2-C）     并行
  ├── 阶段 3（3-A）                  并行
  └── 5-A（config.py）              并行（最早可做）

阶段 4（4-A + 4-B + 4-C）

─── demo 里程碑 M0 检查点 ───
  完成：4-A 前两方法 + 6-A + 6-B 加载部分
  验收：sh memory init → sh ai chat "..." → SYSTEM_PROMPT 含偏好

阶段 5（已完成）+ 阶段 6（6-A 到 6-G）
  6-A：client.py memory_context 参数
  6-B：main.py load + save + --no-memory
  6-C：insights.py 钩子
  6-D：trace.py log_memory_write + log_memory_injection（FIX-3/4）
  6-E：sandbox PROTECTED_PATHS
  6-F：ai.py memory + session 接入（新增，FIX-1）
  6-G：injector.py on_inject 回调（新增，FIX-4）

阶段 7（7-A：sh memory 全部子命令）

─── MVP v1.0 验收 ───
```

### 工期影响

新增 3 个任务（6-F、6-G、FIX-3 定义）：
- 6-F（ai.py）：M 规模，1-1.5 天，与 6-B 并行不增加关键路径
- 6-G（injector callback）：S 规模，0.5 天，在 4-A 后即可做
- FIX-3（事件定义）：S 规模，0.5 天，与 6-D 合并

**关键路径总工期增加约 0.5 天（6-G），不影响整体计划。**
