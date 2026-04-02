# 结论 — SocialHub CLI Advancement

**完成日期**: 2026-03-31
**分支**: feat/cli-advancement
**Baseline commit**: d003968e0136a242a8afd3652836f9c2ab642e0f
**CTO 评级**: 有条件批准

---

## 交付物总览

### 新增文件

| 文件 | 功能 | 测试覆盖 |
|------|------|---------|
| `cli/ai/sanitizer.py` | 用户输入净化 + 注入标记剥离 | 10 tests |
| `cli/ai/session.py` | AI 多轮对话 SessionStore（原子写入 + TTL + 路径遍历防护） | 15 tests |
| `cli/ai/trace.py` | AI 决策追踪 NDJSON 日志（PII 脱敏 + TOCTOU 安全写入 + 文件轮转） | 25 tests |
| `cli/output/formatter.py` | 四模式输出格式器（text/json/csv/stream-json，stdout/stderr 分离） | 18 tests |
| `cli/network.py` | 企业代理 + CA 证书支持（`build_httpx_kwargs` / `build_httpx_client`） | 8 tests |
| `cli/commands/session_cmd.py` | `sh session` 命令组（list/show/clear/purge） | — |
| `cli/commands/trace_cmd.py` | `sh trace` 命令组（list/clear/status） | — |

### 修改文件

| 文件 | 变更摘要 |
|------|---------|
| `cli/config.py` | 新增 `SessionConfig` / `TraceConfig` / `NetworkConfig` |
| `cli/ai/executor.py` | `MAX_PLAN_STEPS=10` + `PLAN_WALL_CLOCK=300s` + `ToolCircuitBreaker` |
| `cli/ai/client.py` | session_history 注入 + usage 提取 + 代理支持 + daemon thread |
| `cli/ai/session.py` | — (新建) |
| `cli/commands/ai.py` | 接入 sanitizer |
| `cli/commands/analytics.py` | OutputFormatter 集成 |
| `cli/commands/customers.py` | OutputFormatter 集成 |
| `cli/commands/config_cmd.py` | `verify-network` 命令 |
| `cli/commands/skills.py` | `--dev-mode` 本地安装（含 zip-slip 防护） |
| `cli/main.py` | `--output-format` 全局选项 + `-c SESSION_ID` 会话标志 + sanitizer 接入 |
| `cli/skills/security.py` | 真实 Ed25519 密钥对替换占位符 |
| `mcp_server/server.py` | `_BoundedTTLCache`（OrdredDict LRU+TTL）+ 5 工具描述三段式更新 |
| `build/m365-agent/mcp-tools.json` | 同步 4 工具描述 |

---

## 质量指标

| 指标 | 数值 |
|------|------|
| 测试总数 | **380 passed, 2 skipped** |
| 新增测试文件 | 6 个 |
| 新增测试用例 | 103 个 |
| Code Review 发现 | 35 项（8 CRITICAL, 15 IMPORTANT, 12 MINOR） |
| 已修复 | 10 项（所有 CRITICAL + 关键 IMPORTANT） |
| Lint 错误（新增） | 0 |

---

## 决策记录

1. **`call_ai_api` 返回 tuple** — 从 `str` 改为 `tuple[str, Optional[dict]]` 以携带 token usage，向后兼容通过 `response, _ = call_ai_api(...)` 处理。

2. **Circuit Breaker 实现三态** — 实现了完整的 closed/open/half-open 状态机（技术设计建议两态）。更健壮但每次 `execute_plan()` 重置，跨计划状态持久化已在已知问题中记录。

3. **`_install_local_skill` 使用 `manifest.json`** — 技术设计指定 YAML，但实现使用 JSON（更无依赖）。已记录格式不一致。

4. **zip-slip 防护优先于 warning 顺序** — 代码审查后调整了 warning 与 extraction 的顺序，extraction 后才打印 warning 的问题已修复。

---

## 已知限制

1. **TraceLogger 未接入主执行流** — `trace.py` 基础设施完整，但 `main.py` / `executor.py` 中的主 AI 执行路径未调用 `log_plan_start` / `log_step` / `log_plan_end`。trace 文件对真实用户仍为空。需要下一轮迭代接入。

2. **no_proxy 未传递给 httpx** — `NetworkConfig.no_proxy` 已捕获环境变量，但 `build_httpx_kwargs` 未将其传递给 httpx（需要 `mounts` API）。企业环境内部主机仍会通过代理路由。

3. **Session ID 通过 sys.argv 解析** — `main.py` 智能模式中通过遍历 `sys.argv` 获取 session ID，而非通过 Typer `ctx.obj`。`--session=<id>` 等号格式会解析失败。

4. **Circuit Breaker 跨计划非持久** — 每次 `execute_plan()` 重新创建 breaker，跨多个用户查询的连续失败不会累积。

5. **`trace show` / `trace stats` 命令缺失** — PRD AC-6/7 定义的命令未在本次实现，`trace list` 已覆盖基本使用场景。

---

## 后续建议

1. **接入 TraceLogger 到主执行流** — 在 `main.py` 和 `executor.py` 中调用 `TraceLogger` 方法，完成 AI 可观测性闭环。

2. **Session ID 从 ctx.obj 读取** — 重构 `main.py` 智能模式中的 session ID 读取，使用 `ctx.find_root().obj.get("session_id")`。

3. **Circuit Breaker 持久化** — 考虑将 breaker 状态存储到 `~/.socialhub/breaker_state.json`，实现跨计划持久保护。

4. **`no_proxy` httpx 支持** — 使用 httpx 的 `mounts` API 正确支持 `no_proxy` bypass 域名列表。

5. **完善 trace 命令** — 添加 `trace show <trace_id>` 和 `trace stats` 子命令。
