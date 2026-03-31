# 交付结论 — M365 Declarative Agent

> 日期：2026-03-30
> CTO 评级：B+（Phase 8 终审）
> E2E 状态：23/23 本地可执行检查项全部通过

---

## 交付物清单

### 新增文件

| 文件 | 类型 | 说明 |
|---|---|---|
| `mcp_server/auth.py` | 源码 | API Key 认证中间件（Starlette BaseHTTPMiddleware + ContextVar 多租户隔离） |
| `mcp_server/http_app.py` | 源码 | HTTP Streamable Transport ASGI 应用（StreamableHTTPSessionManager + 健康探针） |
| `build/m365-agent/manifest.json` | 配置 | Teams App 包 — manifest v1.17 |
| `build/m365-agent/declarativeAgent.json` | 配置 | M365 Declarative Agent（Instructions + 6 Conversation Starters） |
| `build/m365-agent/plugin.json` | 配置 | M365 Plugin（ApiKeyPluginVault + MCPServer runtime） |
| `build/m365-agent/mcp-tools.json` | 配置 | 8 个分析工具 Schema（1172/3000 tokens） |
| `render.yaml` | 部署 | Render Blueprint（Starter plan，/health 探针，--workers 1） |
| `tests/test_auth.py` | 测试 | 18 项认证测试（含 2 项 ContextVar 串行隔离测试） |
| `tests/test_cache_isolation.py` | 测试 | 9 项缓存隔离测试（含 2 项 _run_with_cache 行为层测试） |
| `tests/test_tool_schema_consistency.py` | 测试 | 10 项工具名一致性测试（含 instructions 正则提取验证） |

### 修改文件

| 文件 | 改动 |
|---|---|
| `pyproject.toml` | `mcp>=1.8.0`；新增 `[http]` optional dep（uvicorn/starlette） |
| `mcp_server/__main__.py` | `--transport [stdio\|http]` + `--port` 参数；删除无用 `http_mode` 参数 |
| `mcp_server/server.py` | `_cache_key` 加 `tenant_id`；`_run_with_cache` 签名更新；`call_tool._run()` 注入 tenant_id；`_warm_cache` 空 tid 守卫 |

---

## 质量指标

| 指标 | 数值 |
|---|---|
| 开发任务数 | 10/10 全部完成 |
| Code Review 发现 | 10 项（R1-R10）|
| Code Review 修复 | 8 项（R1-R8 全修）|
| Code Review 技术债（EA 阶段）| 2 项（R9/R10）|
| 测试总数 | 37 项（18 auth + 9 cache + 10 schema）|
| 测试通过率 | 37/37（100%）|
| E2E 轮次 | 3 轮 |
| E2E 通过率 | 23/23 本地可执行项（100%）|
| E2E 代码修正 | 0 项（三轮 E2E 零修正，Code Review 阶段已清零缺陷）|
| mcp-tools.json token 用量 | 1172/3000（39%，余量充裕）|

---

## 关键设计决策记录

| 决策 | 选择 | 理由 |
|---|---|---|
| HTTP 传输方式 | `StreamableHTTPSessionManager(stateless=True)` | M365 Copilot 每次请求独立，无需 session 持久化 |
| 多租户 tenant_id 传递 | `ContextVar` + API Key Map | 避免循环依赖（server.py 不依赖 auth.py 在模块级），延迟导入 |
| CORS vs Auth 中间件顺序 | CORS 外层，Auth 内层 | Starlette add_middleware 是栈式 prepend，OPTIONS preflight 由 CORS 优先处理 |
| client 传入 tenant_id 处理 | 从 safe_args 中剥离 | 防止租户冒充攻击，tenant_id 只能来自 API Key Map |
| `probe_upstream_mcp()` 执行方式 | `asyncio.to_thread()` | 同步阻塞调用不阻塞 async lifespan 事件循环，防止 Render 健康探针超时 |
| /health 503 触发条件 | 仅 API Key 未配置 | analytics 加载中返回 200+"degraded"，避免 Render 探针误触发重启循环 |
| `_warm_cache` HTTP 模式守卫 | `if not warm_tid: return` | HTTP 模式下 MCP_TENANT_ID 未设置，_warm_cache 是 stdio 专属逻辑 |

---

## 已知限制与后续建议

### 待外部环境验证（不阻塞当前交付）

| 验证项 | 前提条件 | 预期结论 |
|---|---|---|
| T1.4: MCP Inspector 验证 | Render 部署 + 真实 API Key | 协议层已本地验证，预期通过 |
| T2: Teams App Validator / Developer Portal | Teams 账号 | JSON 结构已通过本地语法验证，预期通过 |
| T3: M365 Copilot 端到端功能 | M365 E5 开发者账号 | 建议受控小范围试点（1-2 个内部团队）先验证路由准确性和响应时间 |

### EA 阶段技术债

| 技术债 | 描述 | 建议时机 |
|---|---|---|
| `_build_session_manager()` 模块级副作用 | 启动失败无优雅降级路径 | EA 阶段移入 lifespan |
| `_get_tenant_id` 下划线前缀 | mypy 无法感知跨模块使用 | EA 阶段升级为公共接口 |
| `_run_with_cache` 缺少 docstring 和类型注解 | compute_fn 类型不可验证 | EA 阶段补充 |

### 核心客户体验验证点（需真实 M365 环境）

- 自然语言 → 工具路由准确性（US-01 至 US-05 全部核心场景）
- 响应时间体感（Conversation Starters ≤ 5 秒目标）
- 多轮追问上下文保持（`conversation_memory: true` M365 版本支持情况）
- 数据口径说明是否真实出现在 Agent 回答中

---

## 部署 SOP（快速参考）

```bash
# 1. 设置 Render 环境变量
MCP_API_KEYS=<key1>:<tenant1>,<key2>:<tenant2>
PORT=8090

# 2. 构建命令（render.yaml 中已配置）
pip install -e ".[http]"

# 3. 启动命令（render.yaml 中已配置）
uvicorn mcp_server.http_app:app --host 0.0.0.0 --port $PORT --workers 1

# 4. 验证
curl https://mcp.socialhub.ai/health  # 预期: {"status":"ok",...}

# 5. Teams App 包上传
cd build/m365-agent && zip socialhub-agent.zip manifest.json declarativeAgent.json plugin.json mcp-tools.json color.png outline.png
# 上传至 Teams Developer Portal → 验证
```
