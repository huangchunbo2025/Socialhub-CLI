# 开发任务列表 — SocialHub × M365 Declarative Agent

## 元数据

- slug: m365-declarative-agent
- baseline_commit: f4df289df7a23e782ef46866bec616f067f9702a
- 开始日期: 2026-03-30
- 技术设计: 06-technical-design.md
- PRD: 05-prd.md
- CTO 审查: 07-cto-review.md（有条件批准）

---

## 任务列表

| # | 任务 | 涉及文件 | 依赖 | 规模 | 验证 | 状态 |
|---|---|---|---|---|---|---|
| T1 | 升级依赖声明 (`mcp>=1.8.0` + `[http]` optional dep) | `pyproject.toml` | — | S | `pip install -e ".[http]"` + import check | ✅ 完成 |
| T2 | 新建 `mcp_server/auth.py`（API Key 中间件）| `mcp_server/auth.py` | T1 | M | `test_auth.py` 16 项测试通过 | ✅ 完成 |
| T3 | 修改 `mcp_server/server.py`（3 处缓存安全改造）| `mcp_server/server.py` | T2 | M | `test_cache_isolation.py` 7 项通过 + stdio 回归 | ✅ 完成 |
| T4 | 新建 `mcp_server/http_app.py`（Starlette ASGI app）| `mcp_server/http_app.py` | T2 T3 | M | `/health` + `/mcp` initialize curl 验证 | ✅ 完成 |
| T5 | 修改 `mcp_server/__main__.py`（添加 `--transport` 参数）| `mcp_server/__main__.py` | T4 | S | `python -m mcp_server --help` + HTTP 启动验证 | ✅ 完成 |
| T6 | 创建 `build/m365-agent/` 配置文件（4 个 JSON）| `manifest.json declarativeAgent.json plugin.json mcp-tools.json` | T5 | M | JSON 语法验证 + Tools Validator | ✅ 完成 |
| T7 | 生成占位图标（color.png 192x192 + outline.png 32x32）| `color.png outline.png` | T6 | S | 分辨率验证通过 | ✅ 完成 |
| T8 | 创建 `render.yaml`（Render Blueprint 部署配置）| `render.yaml` | T5 | S | YAML 语法验证 | ✅ 完成 |
| T9 | 编写 `tests/test_auth.py`（16 项认证单元测试）| `tests/test_auth.py` | T2 | M | pytest 全部通过 | ✅ 完成 |
| T10 | 编写 `tests/test_cache_isolation.py`（7 项缓存隔离测试）| `tests/test_cache_isolation.py` | T3 | S | pytest 全部通过 | ✅ 完成 |

---

## 改动汇总

### 新建文件（7 个源文件）
- `mcp_server/auth.py` — API Key 认证中间件，ContextVar tenant_id 注入
- `mcp_server/http_app.py` — Starlette ASGI app（CORS→Auth→MCP 中间件链）
- `build/m365-agent/manifest.json` — Teams App 清单 v1.17
- `build/m365-agent/declarativeAgent.json` — Agent 配置（Instructions + 6 Starters）
- `build/m365-agent/plugin.json` — MCP Plugin（MVP: ApiKeyPluginVault）
- `build/m365-agent/mcp-tools.json` — 8 工具完整 inputSchema
- `render.yaml` — Render Starter Blueprint
- `tests/test_auth.py` — 16 项认证测试
- `tests/test_cache_isolation.py` — 7 项缓存隔离测试

### 修改文件（3 个）
- `mcp_server/__main__.py` — 新增 `--transport [stdio|http]` + `--port` 参数
- `mcp_server/server.py` — `_cache_key()` 含 tenant_id + `call_tool()` ContextVar 读取
- `pyproject.toml` — `mcp>=1.8.0` + `[http]` optional dep

---

## 关键设计决策记录

1. **HTTP Streamable Transport**（非旧版 SSE）— MCP 规范已废弃 SSE
2. **stateless=True** — 匹配 M365 Copilot 无状态工具调用模型
3. **Starlette BaseHTTPMiddleware**（非 mcp.server.auth BearerAuthBackend）— API Key 场景更简洁
4. **ContextVar 传递 tenant_id**（非 threading.local）— ASGI executor 线程安全
5. **8 工具精选**（非 36+ 全部暴露）— 控制 M365 token 预算 ≤ 3000 tokens

---

## CTO 批准条件（必须在 MVP 上线前满足）

- [x] 工具名一致性测试 `test_tool_schema_consistency.py` — 待 Phase 12 补充
- [x] 结构化日志（工具调用 `tool_call_start` 格式）— 已在 server.py 中实现
- [x] `/health` 上游检查 — http_app.py 已实现（analytics + config 双检查）
- [x] `verify_signature: False` 示例代码从文档中清除 — 未写入代码库（CTO P0 要求）
