# 开发任务列表

## 元数据
- slug: memory-system-design
- baseline_commit: e0c46b18e3099b1ef65a0d525eb7137615b160ab
- date: 2026-04-02

## 任务

| # | 任务 | 涉及文件 | 依赖 | 规模 | 验证 |
|---|------|---------|------|------|------|
| T01 | 创建 `cli/memory/models.py`：所有 Pydantic v2 模型 | cli/memory/models.py（新建） | 无 | M | `pytest tests/memory/test_models.py` |
| T02 | 创建 `cli/memory/pii.py`：独立 PII 扫描 | cli/memory/pii.py（新建） | 无 | S | `pytest tests/memory/test_pii.py` |
| T03 | 创建 `cli/memory/store.py`：MemoryStore CRUD + 原子写 + TTL | cli/memory/store.py（新建） | T01 | L | `pytest tests/memory/test_store.py` |
| T04 | 创建 `cli/memory/injector.py`：build_system_prompt + tiktoken | cli/memory/injector.py（新建） | T01 | M | `pytest tests/memory/test_injector.py` |
| T05 | 修改 `cli/ai/prompt.py`：拆分 BASE_SYSTEM_PROMPT 为可导入常量 | cli/ai/prompt.py（修改） | 无 | S | `ruff check cli/ai/prompt.py` |
| T06 | 创建 `cli/memory/extractor.py`：LLM 摘要提炼 + 30s 超时 | cli/memory/extractor.py（新建） | T01 | M | `pytest tests/memory/test_extractor.py`（mock LLM）|
| T07 | 修改 `cli/config.py`：增加 `memory: MemoryConfig` 字段 | cli/config.py（修改） | T01 | S | `pytest tests/test_config.py` |
| T08 | 创建 `cli/memory/manager.py`：MemoryManager 5 个公开方法 | cli/memory/manager.py（新建） | T02,T03,T04,T06 | L | `pytest tests/memory/test_manager.py` |
| T09 | 创建 `cli/memory/__init__.py`：re-export MemoryManager/MemoryContext | cli/memory/__init__.py（新建） | T08 | S | `python -c "from cli.memory import MemoryManager"` |
| T10 | 修改 `cli/ai/trace.py`：新增 `log_memory_write()` + `log_memory_injection()` | cli/ai/trace.py（修改） | 无 | S | `pytest tests/test_trace.py` |
| T11 | 修改 `cli/ai/client.py`：`call_ai_api()` 接受 `memory_context` 参数 + 动态 prompt | cli/ai/client.py（修改） | T08,T09 | M | 现有测试 + `ruff check` |
| T12 | 修改 `cli/main.py`：接入 `load()` + `build_system_prompt()` + `save_session_memory()` + `--no-memory` | cli/main.py（修改） | T08,T11 | M | `pytest tests/test_main_memory_integration.py` |
| T13 | 修改 `cli/ai/insights.py`：调用 `save_insight_from_ai()` 钩子 | cli/ai/insights.py（修改） | T08 | S | `pytest tests/test_insights.py` |
| T14 | 修改 `cli/commands/ai.py`：`ai_chat()` 接入 memory load/save + `--no-memory` + `-c/--session`（CTO FIX-1） | cli/commands/ai.py（修改） | T08,T11 | M | `pytest tests/test_ai_chat.py` |
| T15 | 修改 `cli/skills/sandbox/filesystem.py`：扩展 PROTECTED_PATHS 覆盖 memory 目录 | cli/skills/sandbox/filesystem.py（修改） | 无 | S | `pytest tests/test_sandbox.py` |
| T16 | 创建 `cli/commands/memory.py`：sh memory 8 个子命令（init/list/show/set/delete/clear/add-campaign/update-campaign/status） | cli/commands/memory.py（新建） | T08 | L | `pytest tests/test_memory_commands.py` |
| T17 | 修改 `cli/main.py`：注册 `memory` 子命令 | cli/main.py（修改） | T16 | S | `sh memory --help` |
| T18 | 创建所有测试文件（test_pii/test_store/test_injector/test_models/test_manager）| tests/memory/（新建）| T01-T08 | M | `pytest tests/memory/ -v` |
| T19 | 全量验证：`pytest tests/ -x -q` + `ruff check cli/ mcp_server/` + `mypy cli/` | 全部 | T01-T17 | S | 全部通过 |

## 依赖图

```
T01, T02 → T03 → T08
T01      → T04 → T08
T05                      (无依赖，最早可做)
T01      → T06 → T08
T01      → T07           (可与 T03 并行)
T10                      (无依赖，随时可做)
T15                      (无依赖，随时可做)
T08 → T09 → T11 → T12
             T11 → T14
T08 → T13
T08 → T16 → T17
```

## Demo 里程碑 M0

最小可演示路径（CTO FIX-7）：
T01 → T03（部分：load_user_profile）→ T04 → T05 → T07 → T08（前两方法）→ T09 → T11 → T12（仅加载部分）

演示效果：`sh memory init` 手动写入偏好 → `sh ai chat "分析数据"` → SYSTEM_PROMPT 包含偏好内容
