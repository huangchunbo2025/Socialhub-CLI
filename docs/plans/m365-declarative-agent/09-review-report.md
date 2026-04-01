# Code Review 报告 — M365 Declarative Agent

> 日期：2026-03-30
> 审查范围：Phase 9-10 全部改动（3 个修改文件 + 9 个新建文件）
> 审查方式：4 维度并行 Agent（架构/可靠性/性能/卫生）+ Pattern Scan

---

## 发现汇总

| # | 位置 | 严重度 | 描述 | 状态 |
|---|---|---|---|---|
| R1 | `http_app.py:lifespan` | **重要** | `probe_upstream_mcp()` 是同步阻塞调用，在 async lifespan 中直接调用会阻塞事件循环最长 15s，可能导致 Render 健康探针超时触发部署回滚 | ✅ 已修复：改为 `asyncio.to_thread()` |
| R2 | `http_app.py:101` | 改进 | `datetime.utcnow()` 在 Python 3.12 已废弃 | ✅ 已修复：改为 `datetime.now(timezone.utc)` |
| R3 | `__main__.py:_configure_logging` | 改进 | `http_mode: bool` 参数有签名无实现，误导维护者 | ✅ 已修复：删除无用参数 |
| R4 | `server.py:_warm_cache` | 改进 | `warm_tid` 为空时仍调用 `_run_with_cache`，写入 `":{name}:{args}"` 格式的无效缓存 Key | ✅ 已修复：添加 `if not warm_tid: return` 守卫 |
| R5 | `auth.py:dispatch` | 改进 | 使用 `# type: ignore[override]` 绕过 mypy，缺少正确类型注解 | ✅ 已修复：导入 `RequestResponseEndpoint`，完善签名 |
| R6 | `test_auth.py` | **重要** | 缺少多请求串行 ContextVar reset 验证（`_tenant_id_var.reset(token)` 核心安全机制无测试保护） | ✅ 已修复：新增 2 项串行测试 |
| R7 | `test_cache_isolation.py` | **重要** | 只覆盖 `_cache_key` 字符串层，未穿透验证 `_run_with_cache` 行为（PRD §6.3 核心安全需求） | ✅ 已修复：新增 2 项 `_run_with_cache` 行为测试 |
| R8 | `test_tool_schema_consistency.py` | **重要** | 未验证 `declarativeAgent.json` instructions 文本中的工具名一致性 | ✅ 已修复：新增正则提取验证测试 |
| R9 | `http_app.py:_build_session_manager` | 改进 | 模块级调用，启动失败时错误信息不清晰 | ⏳ 记录为 EA 阶段技术债：MVP 阶段 `create_server()` 无已知失败路径 |
| R10 | `auth.py:_get_tenant_id` | 改进 | 下划线前缀使跨模块延迟导入在 mypy 中不可见 | ⏳ 记录为 EA 阶段技术债 |

---

## 修复清单

| 修复 | 涉及文件 | 验证方式 |
|---|---|---|
| `asyncio.to_thread(probe_upstream_mcp)` | `http_app.py` | 代码审阅 |
| `datetime.now(timezone.utc)` | `http_app.py` | 代码审阅 |
| 删除 `http_mode` 参数 | `__main__.py` | `python -m mcp_server --help` |
| `_warm_cache` 空 tid 守卫 | `server.py` | 代码审阅 |
| `dispatch` 类型注解 | `auth.py` | `python -c "import mcp_server.auth"` |
| ContextVar 多请求串行测试 | `test_auth.py` | `pytest test_auth.py::test_context_var_reset_between_requests` |
| `_run_with_cache` 行为层测试 | `test_cache_isolation.py` | `pytest test_cache_isolation.py::test_run_with_cache_tenant_isolation` |
| instructions 工具名验证测试 | `test_tool_schema_consistency.py` | `pytest test_tool_schema_consistency.py::test_declarative_agent_instructions_tool_names_exist_in_handlers` |

---

## 已知问题（待 EA 阶段处理）

| 技术债 | 描述 | 建议处理时机 |
|---|---|---|
| `_build_session_manager()` 模块级副作用 | 启动失败无优雅降级路径，错误信息不清晰 | EA 阶段移入 lifespan |
| `_get_tenant_id` 下划线前缀 | mypy 无法感知跨模块使用，重构时运行时 ImportError | EA 阶段升级为公共接口 |
| `_run_with_cache` 缺少 docstring 和类型注解 | compute_fn 类型不可验证 | EA 阶段补充 |

---

## 测试统计

| 测试文件 | 修复前 | 修复后 |
|---|---|---|
| `test_auth.py` | 16 项 | **18 项** |
| `test_cache_isolation.py` | 7 项 | **9 项** |
| `test_tool_schema_consistency.py` | 9 项 | **10 项** |
| **合计** | **32 项** | **37 项** |

全部 37 项通过 ✅
