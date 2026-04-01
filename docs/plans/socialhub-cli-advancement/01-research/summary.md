# 调研汇总

## 最重要的发现：项目比预期更成熟，但有三处根基性缺陷

初始评估（基于 GitHub 代码快照）严重低估了项目现状。本地代码已具备：
- 真实的 Ed25519 签名验证 + SHA-256 哈希（cryptography 库，非占位）
- 三层 monkey-patch 沙箱（filesystem / network / execute）
- shell=False 执行链 + validator + 危险字符过滤
- MCP 多租户缓存隔离（tenant_id 纳入 cache key）
- M365 Declarative Agent 集成（已上线）

**这意味着安全基础比竞品强，改进重点应从"修安全漏洞"转移到"工程卓越性与架构先进性"。**

---

## 调研共识：三个根基性缺陷（跨多个调研方向一致指出）

### 缺陷 1：AI 执行无护栏（所有调研方向均提及）

`execute_plan()` 无步骤上限、无时间预算、无 circuit breaker、无步骤数量截断。
同时，用户输入可伪造 `[PLAN_START]...[PLAN_END]` 标记绕过 AI 环节直接注入执行计划（**Critical 级安全缺陷**）。

- **project-status**: executor.py:136 — 无步骤上限
- **security-practices**: parser.py — 未净化用户输入中的计划标记
- **agent-reliability**: 无 circuit breaker，工具连续失败无自动停止
- **ai-native-cli-patterns**: claude-code maxTurns 机制是业界标准

**一致结论：P0，约 0.5 天，0 新依赖，必须修。**

### 缺陷 2：无机器可读输出（竞品格局 + 项目现状一致指出）

所有竞品（AWS CLI、Azure CLI、claude-code、GitHub CLI）均支持 `--output-format json`。
SocialHub CLI 的 Rich 渲染全部混入 stdout，`sh analytics overview | jq` 必然失败。
影响：CI/CD 集成不可用、AI Agent 链接不可用、程序化消费不可用。

- **competitive-landscape**: 行业标准已形成，缺失是明显的产品短板
- **project-status**: 无任何 --output-format 参数
- **ai-native-cli-patterns**: claude-code 的 stream-json 模式是架构标准

**一致结论：P0，约 1.5 天，影响产品可集成性。**

### 缺陷 3：公钥是占位符，Skills 实际不可用（project-status + security-practices 一致指出）

`security.py:39` 的 `OFFICIAL_PUBLIC_KEY_B64` 是虚构值 `"MCowBQYDK2VwAyEAK5mPmkJXzWvHxLxV9G6Y8Z3q1fJnRt0vLhQE7YKp2Hw="`，
验证时会因公钥不匹配导致所有 Skills 安装被阻断。框架完整但关键参数缺失，Skills 生态事实上处于不可用状态。

**一致结论：P0，约 0.25 天（生成真实密钥对 + 替换），解锁整个 Skills 生态。**

---

## 高价值改进（P1）：4 项

### P1-A：命令懒加载（启动性能）

main.py 全量 import 17 个模块，`sh --version` 也会触发 analytics、MCP 等重型模块。
claude-code 通过懒加载将启动路径缩至仅元数据加载。
Python 等价：Click LazyGroup 或 `importlib.import_module` on-demand。
预计降低启动延迟 40-60%。

### P1-B：AI 决策可观测性

每次 AI 调用的决策链（为什么选这个命令、哪步消耗了多少 token）完全无追踪。
`client.py` 的 `usage` 字段被丢弃，token 消耗不可归因。
纯标准库实现：写 `~/.socialhub/ai_trace.jsonl`，structlog 结构化日志。
同时为将来的 Billing/配额管理提供数据基础。

### P1-C：MCP 工具描述优化（已有工具的免费升级）

`mcp-tools.json`（M365 集成用）与 `server.py` 描述已漂移，且描述缺少"负面边界"。
添加"不要在 X 情况下调用此工具"可将工具选择准确率提升 15-25pp（Anthropic 数据）。
零代码改动，纯文本优化，极高 ROI。

### P1-D：MCP 缓存加 maxsize 上限

`_cache` 是无界 dict，多租户高并发下有 OOM 风险。
用 `functools.lru_cache` 或 `cachetools.TTLCache(maxsize=500)` 替换，一行改动。

---

## 战略性改进（P2）：3 项

### P2-A：Permission 模式分级

借鉴 claude-code 的 auto/plan/ask/bypass 模式，给命令标注 `is_read_only` / `is_destructive` 元数据。
只读分析命令自动执行，破坏性命令强制确认，plan 模式展示计划后再执行。
实现复杂度中等，但对企业客户的安全合规价值很高。

### P2-B：AI Session 管理（多轮对话）

当前每次 AI 调用独立，无法做到："上周数据 → 上上周对比 → 原因分析"的连贯追问。
引入 `SessionStore`（`~/.socialhub/sessions/`），持久化对话历史。
CRM 分析场景中多轮追问价值极高，是差异化竞争力。

### P2-C：Skill 参数化模板

Skills 当前静态，相似场景需多个文件。引入 Jinja2 模板 + manifest `parameters` 字段。
同一 Skill 适配不同时间范围、不同客户细分，大幅提升 Skills 生态复用性。

---

## 非显而易见的洞察

1. **monkey-patch 沙箱有绕过路径**（`io.FileIO`、`os.execvp`、`awk system()`），但这是 Python 沙箱的固有局限，不是 SocialHub 特有问题。补救是 `sys.addaudithook()`（PEP 578），而非重写沙箱。

2. **`sh` 命令名与系统 shell 工具冲突**（在 Linux/macOS 上 `sh` 是 `/bin/sh`），竞品调研发现这是 CLI 工具的常见坑，影响某些 CI/CD 环境的使用。建议保留 `socialhub` 作为主命令，`sh` 降级为开发环境别名。

3. **MCP Tasks 原语（MCP 2025-03-26）直接解决了 rfm/retention 重型查询的超时问题**，比当前的 startup pre-warm 更优雅，是 MCP Server 的下一个重大升级方向。

4. **`OFFICIAL_PUBLIC_KEY_B64` 的字节结构有误**：`from_public_bytes(key_bytes[12:])` 跳过了 12 字节的 SubjectPublicKeyInfo header，这是 Ed25519 公钥 DER 编码的正确处理方式，但用了虚构 base64 值，整个流程无法正常工作。

5. **竞品均未进入 CRM+CLI+AI 细分**：Salesforce Einstein、HubSpot AI 均是 Web UI 形态，SocialHub CLI 的定位有明显先发窗口期（Gartner 预测 2026 年底 40% 企业应用含任务专用 AI Agent）。

---

## 可复用资源

| 资源 | 用途 |
|------|------|
| `pybreaker` / `aiobreaker` | Circuit Breaker（P0，但可纯自实现更轻量） |
| `cachetools.TTLCache` | MCP 缓存 maxsize 限制（P1） |
| `keyring` | API Key 安全存储（P1） |
| `jinja2` | Skill 参数化模板（P2，已是常见依赖） |
| `sys.addaudithook()` PEP 578 | 沙箱逃逸检测补强（P2） |
| MCP Tasks 原语 | 重型查询异步化（P2） |

---

## 改进优先级矩阵

| 优先级 | 改进项 | 工作量 | 影响面 | 依赖 |
|--------|--------|--------|--------|------|
| **P0** | 用户输入净化（阻断计划伪造） | 0.25d | 安全 Critical | 无 |
| **P0** | execute_plan 步骤上限 + 时间预算 | 0.25d | 安全 + 稳定性 | 无 |
| **P0** | 生成真实 Ed25519 密钥对 | 0.25d | Skills 生态解锁 | 无 |
| **P0** | --output-format json/stream-json | 1.5d | 可集成性 | 无 |
| **P1** | 命令懒加载 | 0.5d | 启动性能 | 无 |
| **P1** | AI 决策可观测性（trace log） | 1d | 可运维性 | 无 |
| **P1** | MCP 工具描述优化 + 负面边界 | 0.5d | M365 准确率 | 无 |
| **P1** | MCP 缓存 maxsize | 0.1d | 稳定性 | cachetools |
| **P1** | API Key 迁移到 keyring | 0.5d | 安全 | keyring |
| **P2** | Permission 模式分级 | 2d | UX + 合规 | 无 |
| **P2** | AI Session 多轮对话 | 2d | 差异化 | 无 |
| **P2** | Skill 参数化模板 | 1.5d | 生态扩展 | jinja2 |
| **P2** | sys.addaudithook 沙箱补强 | 1d | 安全深度 | 无 |
| **P2** | MCP Tasks 原语（异步查询） | 3d | 性能 | mcp SDK |
