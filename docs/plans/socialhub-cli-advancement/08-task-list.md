# 开发任务列表

## 元数据
- slug: socialhub-cli-advancement
- baseline_commit: d003968e0136a242a8afd3652836f9c2ab642e0f
- branch: feat/cli-advancement
- 技术设计: docs/plans/socialhub-cli-advancement/06-technical-design.md
- PRD: docs/plans/socialhub-cli-advancement/05-prd.md

## 任务

| # | 任务 | 涉及文件 | 依赖 | 规模 | 验证 |
|---|------|---------|------|------|------|
| T01 | 扩展 config.py（新增 SessionConfig/TraceConfig/NetworkConfig）| `cli/config.py` | 无 | S | pytest tests/test_config.py |
| T02 | 新建 cli/ai/sanitizer.py（用户输入净化）| `cli/ai/sanitizer.py` | 无 | S | pytest tests/test_sanitizer.py（新建）|
| T03 | 修改 executor.py（步骤上限+时间预算+Circuit Breaker）| `cli/ai/executor.py` | T01 | M | pytest tests/test_executor.py（新建）|
| T04 | 修改 main.py — 接入 sanitizer + --output-format 全局选项 + -c session 标志 | `cli/main.py` | T01, T02 | M | pytest tests/test_cli.py |
| T05 | 新建 cli/output/formatter.py（OutputFormatter：text/json/csv/stream-json）| `cli/output/formatter.py` | 无 | M | pytest tests/test_formatter.py（新建）|
| T06 | 修改 analytics.py 接入 OutputFormatter | `cli/commands/analytics.py` | T04, T05 | M | pytest tests/test_cli.py -k analytics |
| T07 | 修改 customers.py 接入 OutputFormatter | `cli/commands/customers.py` | T04, T05 | S | pytest tests/test_cli.py -k customers |
| T08 | 新建 cli/ai/session.py（SessionStore）| `cli/ai/session.py` | T01 | M | pytest tests/test_session.py（新建）|
| T09 | 新建 cli/commands/session_cmd.py + 注册到 main.py | `cli/commands/session_cmd.py`, `cli/main.py` | T08 | S | pytest tests/test_cli.py -k session |
| T10 | 修改 cli/ai/client.py（接入 session history + 提取 usage）| `cli/ai/client.py` | T08 | S | pytest tests/test_cli.py |
| T11 | 新建 cli/ai/trace.py（TraceLogger + PII 脱敏 + TOCTOU 安全写入）| `cli/ai/trace.py` | T01 | M | pytest tests/test_trace.py（新建）|
| T12 | 新建 cli/commands/trace_cmd.py + 注册到 main.py | `cli/commands/trace_cmd.py`, `cli/main.py` | T11 | S | pytest tests/test_cli.py -k trace |
| T13 | 新建 cli/network.py + 修改 api/client.py + store_client.py（代理/CA）| `cli/network.py`, `cli/api/client.py`, `cli/skills/store_client.py` | T01 | M | pytest tests/test_network.py（新建）|
| T14 | 修改 config_cmd.py（新增代理/CA 配置项 + verify-network 命令）| `cli/commands/config_cmd.py` | T13 | S | pytest tests/test_cli.py -k config |
| T15 | 修改 skills/security.py（替换占位符公钥 + 更新指纹）| `cli/skills/security.py` | 无 | S | pytest tests/test_security.py |
| T16 | 修改 skills/commands.py（--dev-mode 本地安装）| `cli/commands/skills.py` | T15 | M | pytest tests/test_skill_integration.py |
| T17 | 修改 mcp_server/server.py（工具描述三段式 + BoundedTTLCache）| `mcp_server/server.py` | 无 | M | pytest tests/test_tool_schema_consistency.py |
| T18 | 更新 build/m365-agent/mcp-tools.json（同步 8 工具描述）| `build/m365-agent/mcp-tools.json` | T17 | S | 人工 diff 验证 |
| T19 | 全量测试验证 + lint 修复 | 全部 | T01-T18 | M | pytest tests/ -x -q && ruff check cli/ mcp_server/ |

## 执行顺序

```
并行批次 A（无依赖）：T01, T02, T05, T11, T15, T17
    ↓ A 完成后
并行批次 B：T03(依赖T01), T08(依赖T01), T10(依赖T08), T13(依赖T01), T16(依赖T15)
    ↓ B 完成后
并行批次 C：T04(依赖T01,T02), T06(依赖T04,T05), T07(依赖T04,T05), T09(依赖T08), T12(依赖T11), T14(依赖T13), T18(依赖T17)
    ↓ C 完成后
T19：全量验证
```
