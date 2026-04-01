# SocialHub CLI 架构先进性提升 — CTO 终审报告

**审查日期**: 2026-03-31
**审查对象**: 06-technical-design.md v1.0
**需求基准**: 05-prd.md v1.0
**架构基准**: CLAUDE.md（项目红线与架构原则）
**审查人**: CTO（Claude Sonnet 4.6 扮演）

---

## 评级：有条件批准

**核心理由**：方案架构设计总体健全，PRD 需求覆盖完整，红线遵守情况良好。但存在 5 个必须在编码开始前解决的实现缺陷（见 Round 1/2 修正项），其中 2 个是生产安全问题，1 个是会导致 CI 测试立即失败的实现漏洞。条件：工程师 Day 1 必须阅读并确认本报告中所有"CTO 修正"标注，方可开始编码。

---

## 一、架构一致性审查（CLAUDE.md 逐条对照）

### 1.1 架构原则符合情况

| 原则 | 方案符合情况 | 备注 |
|------|------------|------|
| 自然语言安全执行链（validator → shell=False） | 符合 | sanitize_user_input 新增为 call_ai_api 前置层，不替代 validator |
| MCP 优先集成 | 符合 | 改进七仅修改描述，不改变协议 |
| Skills 零信任沙箱 | 符合 | --dev-mode 跳过签名但沙箱激活路径在 loader.py（执行阶段），安装阶段无沙箱是正确设计 |
| 配置分层（代码默认值 → config.json → 环境变量） | 符合 | NetworkConfig/SessionConfig/AIConfig 新增字段均遵循三层优先级 |
| 多租户隔离 | 符合 | TraceWriter 记录 tenant_id，session 文件不跨用户共享 |
| Store URL 硬编码 | 符合 | build_httpx_client() 只注入代理，不触及 STORE_BASE_URL 常量 |

### 1.2 红线遵守情况

| 红线 | 检查结果 |
|------|---------|
| 禁止 shell=True | 通过。executor.py 改动不改变 shell=False 约束 |
| 危险字符过滤 | 通过。sanitize_user_input 是新增层，不替代现有危险字符过滤 |
| AI 命令必须通过 validator | 通过。sanitize 在 call_ai_api 之前，validate 在 execute 之前，两层保留 |
| 签名验证不可跳过 | 通过。--dev-mode 只作用于本地文件路径，URL 安装被代码拒绝；正式 Store 安装链路不受影响 |
| Store URL 不可覆盖 | 通过 |
| 沙箱必须激活 | 通过。沙箱在执行阶段由 loader.py 激活，--dev-mode 安装的 Skill 执行时同样经过沙箱 |
| MCP 工具处理器返回类型 | 通过。改进七只改 description 字符串 |
| 账户表严格隔离 | 通过。7 项改进均不触及 skills-store/backend/ |
| docs/ 目录冻结 | 通过 |
| developers.saved_skills 冻结 | 通过 |

**结论：所有红线保持完整，无违规。**

---

## 二、PRD 需求覆盖检查

| PRD 需求 | AC 数量 | 技术方案覆盖 | 缺口 |
|---------|---------|------------|------|
| 改进一：Ed25519 密钥修复 | AC-1~7 | §1.1~1.4 完整覆盖 | 无 |
| 改进二：--output-format | AC-1~9 | §2.1~2.4 完整覆盖 | 无 |
| 改进三：AI 执行护栏 | AC-1~8 | §3.1~3.4 完整覆盖 | 无 |
| 改进四：AI Session | AC-1~12 | §4.1~4.6 完整覆盖 | 无 |
| 改进五：AI 可观测性 | AC-1~10 | §5.1~5.6 完整覆盖 | 无 |
| 改进六：企业代理/CA | AC-1~8 | §6.1~6.5 完整覆盖 | 无 |
| 改进七：MCP 描述优化 | AC-1~4 | §7.1~7.4 覆盖 | **_get_tool_definitions() 未列入改动清单（已修正）** |
| PRD §C2-F3 日志文件权限 600 | AC-4 | TraceWriter._write() 实现 | **TOCTOU 窗口（已修正）** |

**PRD 覆盖率：7/7 改进全覆盖，无漏项。**

---

## 三、技术债评估

### 新引入的技术债

| 技术债 | 可控性 | 评估 |
|--------|--------|------|
| SessionStore.index.json 无文件锁 | 可控 | 单进程正常使用无并发；脚本并发场景下 index.json 可能有轻微重复记录，但 session 数据文件完整性不受影响。接受。 |
| ai_trace.jsonl 在 Windows 上并发追加不保证原子性 | 可控 | NDJSON 单行追加，最坏情况损坏单行，不破坏整个文件。接受。 |
| PII 脱敏正则订单号误杀 | 已修正 | 已将最小长度从 10 提高到 16 位，误杀率大幅降低 |
| httpx proxies= 废弃 API | 需要处理 | 工程师必须在实现时确认 httpx 版本约束（见 Round 2 修正） |
| main.py sys.argv 直接解析 | 已修正 | 已在代码注释中明确要求使用 ctx.obj 替代 |

### 比现有方案更干净的路径（参考建议，不是强制修改项）

- `_BoundedTTLCache.MAX_SIZE=500` 是死路径代码（实际永远不会驱逐），建议改为 200 或暴露为启动参数
- `verify-network` 命令直接在 `config_cmd.py` 里 hardcode 了 Skills Store 的健康检查 URL，与 CLAUDE.md 中的 Store URL 分开定义，存在漂移风险。建议从 `store_client.py` 的 `STORE_BASE_URL` 常量派生

---

## 四、YAGNI 检查（过度设计评估）

### 通过的设计

- `_BoundedTTLCache` LRU 逻辑：虽然 MAX_SIZE=500 下实际不运行，但代码本身不复杂（30行），不构成过度设计
- Session index.json：两级文件结构（index + 独立 session 文件）是合理的，避免单文件无限增长
- `_usage_out: Optional[list]` mutable container pattern：这是 Python 向后兼容的标准做法，不过度

### 已推后的功能（YAGNI 已落地）

- Permission 模式分级、Session compact、SIEM 集成、密钥轮换、CRL 填充全部推后。决策正确。

### 建议可以进一步简化的点

- `trace stats --period today`：`today` 是一个硬编码的 period 参数，但实现里需要解析日期过滤，这是 ~20 行额外代码。PRD AC-7 要求此命令，不可删除，但可以 MVP 版本只支持 `today`，不支持 `--period last_7_days` 等扩展（PRD 也只要求 today）。
- `OutputFormatter.emit_progress()`：对于 csv 和 json 模式的静默行为，可以直接用 `if formatter.fmt in ("json", "csv"): return` 替代 `emit_progress()` 方法调用，减少 API 表面积。

---

## 五、三轮迭代发现与修正记录

### Round 1：薄弱环节检查

#### R1-CTO-1：PII 脱敏订单号正则误杀严重

**发现**：`\b\d{10,20}\b` 会把所有 10-20 位纯数字（客户ID、ERP编号、积分账户号）全部替换为 `[ORDER_ID]`，trace 日志丧失诊断价值。

**修正**：
1. 将最小位数从 10 改为 16（`\b\d{16,20}\b`）
2. 新增配置项 `ai.trace_order_id_min_digits: int = 16`，IT 管理员可根据实际业务调整
3. 在 trace.py 注释中明确：`_mask_pii()` 只用于日志脱敏，绝对不能用于净化传给 AI 的输入
4. 已在 06-technical-design.md §5.2 追加 CTO 修正段落

**影响文件**：`cli/ai/trace.py`（正则修改）、`cli/config.py`（新增配置项）

#### R1-CTO-2：main.py 直接解析 sys.argv 绕过 Typer

**发现**：第 1078-1082 行直接扫描 `sys.argv` 检测 `--continue`/`--session`，而 Typer 回调已将这两个参数存入 `ctx.obj`。sys.argv 解析绕过 Typer，导致 `--session=a3f2`（等号格式）解析失败、子命令路径错误触发 session 加载。

**修正**：已在对应代码块追加 CTO 修正注释，明确要求工程师使用 `ctx.obj.get("continue_session")` 和 `ctx.obj.get("session_id")` 替代 sys.argv 扫描。

**影响文件**：`cli/main.py`

#### R1-CTO-3：`_get_tool_definitions()` 未列入改动清单

**发现**：`test_tool_schema_consistency.py` 的 `test_description_sync` 测试依赖从 `mcp_server.server` import `_get_tool_definitions`，但这个函数在改进七的改动清单里没有明确要求实现，仅在测试代码注释里隐含。工程师只看改动清单时极易遗漏，导致 CI 立即失败。

**修正**：已在 06-technical-design.md §7.3 追加 CTO 修正段落，明确函数签名规范和隔离要求（无 async 上下文、纯 import 不抛异常）。建议在文件改动总表中补充此条目。

**影响文件**：`mcp_server/server.py`（新增函数）

---

### Round 2：生产事故回溯视角

#### R2-CTO-1：TraceWriter 文件权限 TOCTOU 窗口

**场景**：多用户共享服务器上，`ai_trace.jsonl` 从创建到 chmod 600 之间有时间窗口（默认 umask 权限可能是 644），其他进程可读取 trace 内容（租户 ID、查询摘要等敏感业务信息）。

**风险等级**：中（企业共享服务器场景存在实际风险，PII 虽脱敏但业务信息仍敏感）

**修正**：用 `os.open(path, O_WRONLY|O_CREAT|O_APPEND, mode=0o600)` 替代 `open() + chmod`，文件从创建起即为 600 权限，消除 TOCTOU 窗口。已在 06-technical-design.md §5.3 TraceWriter._write() 后追加 CTO 修正段落，含完整替换代码。

**影响文件**：`cli/ai/trace.py`

**缓解措施充分性**：修正后完全消除此风险。PRD AC-4 "文件权限 600" 验收条件可通过。

#### R2-CTO-2：httpx proxies= 参数废弃

**场景**：用户通过 pip 升级 httpx 到 >= 0.24 后，`build_httpx_client()` 中的 `proxies=` 参数产生 DeprecationWarning；未来 httpx 版本删除此参数后，所有 API 调用（AI 调用、Skills Store 调用）在代理环境下立即失败，完全影响企业用户（代理环境正是改进六的目标用户）。

**风险等级**：高（企业环境 pip 升级是常见运维操作，且代理场景是此改进的核心目标）

**修正**：已在 06-technical-design.md §6.2 build_httpx_client() 后追加 CTO 修正段落，说明：
1. 检查 pyproject.toml 的 httpx 版本约束
2. 提供 `mounts=` 新 API 的替代实现代码
3. 建议固定 `httpx>=0.24,<1.0` 并使用新 API

**影响文件**：`cli/network.py`

**缓解措施充分性**：工程师实现时按 CTO 修正执行可完全消除此风险。

---

### Round 3：开发效率视角

#### R3-CTO-1：工程师 B 的 Day 2 上午被浪费

**发现**：原方案中工程师 B 在 Day 2 下午才开始 P1 工作（Session/Trace），但 `cli/ai/session.py` 和 `cli/ai/trace.py` 只依赖 `config.py`（Day 1 上午完成），与 main.py 无依赖关系，可以提前到 Day 2 上午开始。原方案让工程师 B 在 Day 2 上午等待工程师 A 做完 executor.py/proxy 注入，浪费了半天。

**修正**：实现顺序重排，工程师 B 的 P1 工作提前至 Day 2 上午，节省约 0.5 天（整体进度从 3.5 天压缩到 3 天）。已更新 §Round 3 实现顺序。

#### R3-CTO-2：MCP 两类任务混在同一提交

**发现**：`_BoundedTTLCache`（内存安全修复，有 threading.Lock 逻辑）和工具描述更新（纯文本修改）混在 Day 3 的同一步骤，难以独立调试和回滚。

**修正**：拆分为两个独立 commit，`_BoundedTTLCache` 先提交（步骤 20），工具描述更新后提交（步骤 21）。

#### R3-CTO-3：_BoundedTTLCache MAX_SIZE=500 是死路径

**发现**：MCP cache key 格式为 `{tenant_id}:{tool_name}:{params_hash}`，实际条目数极少超过 100（即使多租户场景）。MAX_SIZE=500 意味着 LRU 驱逐逻辑永远不运行，`popitem(last=False)` 是死路径代码。

**修正建议**：将 MAX_SIZE 调整为 200，或暴露为 MCP Server 启动参数（不是强制要求，但应在代码注释中说明为何选择此值）。

---

## 六、最终开发计划（含并行策略与顺序依赖）

### 依赖关系图

```
config.py (Day 1 上午)
    ├── network.py (Day 1 上午)
    │   ├── api/client.py (Day 2 上午)
    │   └── skills/store_client.py (Day 2 上午)
    ├── output/formatter.py (Day 1 下午，工程师B)
    │   ├── commands/analytics.py (Day 1 下午)
    │   └── commands/customers.py (Day 1 下午)
    ├── ai/session.py (Day 2 上午，工程师B)
    │   └── commands/session_cmd.py (Day 2 下午)
    └── ai/trace.py (Day 2 上午，工程师B)
        └── commands/trace_cmd.py (Day 2 下午)

ai/sanitizer.py (Day 1 下午，无依赖)
    └── ai/executor.py (Day 2 上午)

skills/security.py (Day 1 下午，独立运维操作)
    └── skills/manager.py → commands/skills.py (Day 1 下午)

main.py (Day 2 下午，串行，工程师A)
    聚合：output_format + sanitize + session + SSL警告 + 子命令注册

mcp_server/server.py (Day 3，独立，任意工程师)
```

### 任务分解与时间表

| 天 | 时段 | 工程师 A | 工程师 B | 里程碑 |
|----|------|---------|---------|--------|
| 1 | 上午 | config.py + network.py（2个文件，基础设施） | 同上（单人完成，避免冲突） | 基础设施完成，解锁所有后续工作 |
| 1 | 下午 | sanitizer.py + security.py + manager.py + commands/skills.py | output/formatter.py + analytics.py + customers.py | P0 安全链 + P0 输出格式完成 |
| 2 | 上午 | executor.py + api/client.py + store_client.py + config_cmd.py | ai/session.py + ai/trace.py（P1 提前） | P0 全部完成；P1 核心逻辑完成 |
| 2 | 下午 | cli/main.py（唯一操作者，一次性完成所有修改） | commands/session_cmd.py + commands/trace_cmd.py + ai/client.py | CLI 全功能集成完毕 |
| 3 | 全天 | mcp_server/server.py（cache修复 + 描述更新 + _get_tool_definitions） + mcp-tools.json + 测试 | 测试覆盖 + 端到端验证 | 全部 7 项改进交付 |

**预计总工作量**：3 个自然日（2 个工程师并行），比原方案 3.5 天快 0.5 天。

### 不可并行的串行依赖

1. `config.py` 必须在所有其他文件之前合并（Day 1 上午）
2. `cli/main.py` 必须单人完成（Day 2 下午），不允许多人同时修改
3. `mcp-tools.json` 必须在 `server.py` 工具描述更新完成后手工对照（不可自动化，逐字核对）

---

## 七、工程师 Day 1 必做清单

在写第一行代码之前，工程师必须确认以下事项：

### 安全确认

- [ ] 阅读 06-technical-design.md 中所有标注"CTO 修正"的段落（共 5 处）
- [ ] 确认 `_mask_pii()` 代码注释已写明：此函数只用于 TraceWriter 日志脱敏，不得用于净化 AI 输入
- [ ] 确认 main.py session 处理使用 `ctx.obj` 而非 `sys.argv` 扫描
- [ ] 确认 TraceWriter._write() 使用 `os.open()` 而非 `open() + chmod`

### 环境确认

- [ ] 检查项目 pyproject.toml 中 httpx 的版本约束，确认使用 `proxies=` 还是 `mounts=`（见 06-technical-design.md §6.2 CTO 修正段落）
- [ ] 运行 `pytest tests/ -x -q` 确认基线测试通过，记录当前覆盖率作为基准

### 运维协作（改进一）

- [ ] 联系运维在 Day 1 下午完成 Ed25519 密钥对生成（需要 openssl 环境）
- [ ] 确认 Render Secret 已创建 `SKILL_SIGNING_PRIVATE_KEY` 占位符，等待写入真实私钥
- [ ] 确认私钥生成后 PEM 文件立即 `shred -u` 删除，不留在工程师本地

### 实现规范确认

- [ ] 确认改进七的 `_get_tool_definitions()` 函数已列入 server.py 的改动计划（此函数是 test_description_sync 的前提）
- [ ] 确认 `_BoundedTTLCache.MAX_SIZE` 选择了合理值（200 或带注释说明选 500 的依据）
- [ ] 确认 PII 正则订单号最小位数为 16 而非 10

---

## 八、长期建议

### v1.1（2-4 周后）

1. **Session compact 命令**：当 token 消耗超过 4000 时，自动触发 AI 生成摘要并压缩历史，防止 context 窗口爆炸。比手动截断（当前 10 条策略）更优雅。
2. **--output-format 覆盖剩余命令**：campaigns/skills list 等，低工作量但补全了用户体验

### v2.0（架构级投资）

3. **密钥轮换机制**：当前方案密钥一旦泄漏，所有已签名的 Skill 都需要重新签名。v2.0 应实现带版本号的公钥链（Public Key Set），允许渐进轮换。
4. **SIEM/日志集中化**：将 `ai_trace.jsonl` 的写入模块设计为可插拔的 Sink（本地文件 / HTTP 上传 / Syslog），当前版本只启用本地 Sink，v2.0 开启 HTTP Sink，无需改动调用方。
5. **MCP 工具描述单一事实来源**：当前 `server.py` 和 `mcp-tools.json` 需要手工保持同步（逐字核对），这是长期的维护负担。建议 v2.0 引入代码生成：`server.py` 作为单一事实来源，CI 自动生成 `mcp-tools.json`。
6. **sys.addaudithook 沙箱补强**：当前沙箱是 monkey-patch 级别（builtins.open / socket / subprocess），Python 3.8+ 的 `sys.addaudithook` 可以提供更底层的审计钩子，防止通过 ctypes 等方式绕过 monkey-patch。

### 架构持续健康

7. **mypy strict 模式**：当前 `mypy cli/` 使用默认配置。SessionStore/TraceWriter/OutputFormatter 等新增的核心类应配置为 strict mypy，防止类型漂移。
8. **test coverage 基线**：7 项改进落地后，强烈建议在 CI 中设置覆盖率下限（建议 60%），防止后续功能开发降低测试质量。

---

## 九、总结

方案的总体质量是合格的。7 项改进全面覆盖 PRD 需求，架构原则和红线遵守情况优秀，3 轮自我对抗迭代已识别并修正了主要的边界条件问题。

本次 CTO 审查发现的关键问题集中在**实现细节层面**（而非架构层面），这是积极信号：

- 5 处必须修正（PII 正则误杀、sys.argv 绕过、_get_tool_definitions 遗漏、TOCTOU 窗口、httpx API 废弃）
- 1 处并行优化（节省 0.5 天开发时间）
- 1 处设计简化（MCP 任务拆分、MAX_SIZE 调整）

所有修正已直接写入 06-technical-design.md 对应章节，工程师无需再看本报告即可找到具体实现指导。

**批准条件**：工程师 Day 1 必做清单全部打勾，方可正式开始编码。

---

*CTO 审查：有条件批准 — 2026-03-31*
*审查方法：3 轮自我对抗迭代（薄弱环节 / 生产事故回溯 / 开发效率）*
*修正数量：Round 1 — 3 项；Round 2 — 2 项；Round 3 — 3 项；合计 8 项*
