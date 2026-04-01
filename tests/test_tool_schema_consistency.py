"""
tests/test_tool_schema_consistency.py

工具名一致性测试 — CTO 审查批准条件（必须通过才可上线）

验证：mcp-tools.json、plugin.json（allowed_tools + functions）、
declarativeAgent.json（instructions 中引用的工具名）与
mcp_server/server.py 的 _HANDLERS dispatch table 完全一致。

任何一处拼写错误都会导致 M365 Copilot 发出 tools/call 请求后
server.py 的 _HANDLERS.get(name) 返回 None，工具调用静默失败。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

# ──────────────────────────────────────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────────────────────────────────────

M365_DIR = Path("build/m365-agent")


@pytest.fixture(scope="module")
def mcp_tools_names() -> list[str]:
    """从 mcp-tools.json 读取工具名列表。"""
    path = M365_DIR / "mcp-tools.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    return [t["name"] for t in data["tools"]]


@pytest.fixture(scope="module")
def plugin_allowed_tools() -> list[str]:
    """从 plugin.json 读取 runtimes[MCPServer].allowed_tools。"""
    path = M365_DIR / "plugin.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    for runtime in data.get("runtimes", []):
        if runtime.get("type") == "MCPServer":
            return runtime.get("allowed_tools", [])
    return []


@pytest.fixture(scope="module")
def plugin_functions() -> list[str]:
    """从 plugin.json 读取 functions[].name。"""
    path = M365_DIR / "plugin.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    return [f["name"] for f in data.get("functions", [])]


@pytest.fixture(scope="module")
def server_handlers() -> set[str]:
    """从 mcp_server/server.py 读取 _HANDLERS keys。"""
    from mcp_server.server import _HANDLERS
    return set(_HANDLERS.keys())


# ──────────────────────────────────────────────────────────────────────────────
# Consistency Tests
# ──────────────────────────────────────────────────────────────────────────────

def test_mcp_tools_names_exist_in_handlers(mcp_tools_names, server_handlers):
    """mcp-tools.json 中声明的每个工具名必须在 _HANDLERS 中存在。"""
    missing = [n for n in mcp_tools_names if n not in server_handlers]
    assert missing == [], (
        f"mcp-tools.json 工具名在 _HANDLERS 中不存在（会导致 M365 tool call 静默失败）: {missing}"
    )


def test_plugin_allowed_tools_exist_in_handlers(plugin_allowed_tools, server_handlers):
    """plugin.json allowed_tools 中每个工具名必须在 _HANDLERS 中存在。"""
    missing = [n for n in plugin_allowed_tools if n not in server_handlers]
    assert missing == [], (
        f"plugin.json allowed_tools 在 _HANDLERS 中不存在: {missing}"
    )


def test_plugin_functions_exist_in_handlers(plugin_functions, server_handlers):
    """plugin.json functions[].name 必须在 _HANDLERS 中存在。"""
    missing = [n for n in plugin_functions if n not in server_handlers]
    assert missing == [], (
        f"plugin.json functions 在 _HANDLERS 中不存在: {missing}"
    )


def test_mcp_tools_and_plugin_allowed_tools_consistent(mcp_tools_names, plugin_allowed_tools):
    """mcp-tools.json 工具名集合与 plugin.json allowed_tools 一致。"""
    mt_set = set(mcp_tools_names)
    pa_set = set(plugin_allowed_tools)
    in_mt_not_pa = mt_set - pa_set
    in_pa_not_mt = pa_set - mt_set
    assert not in_mt_not_pa and not in_pa_not_mt, (
        f"不一致:\n"
        f"  mcp-tools.json 有但 plugin.allowed_tools 无: {in_mt_not_pa}\n"
        f"  plugin.allowed_tools 有但 mcp-tools.json 无: {in_pa_not_mt}"
    )


def test_mcp_tools_and_plugin_functions_consistent(mcp_tools_names, plugin_functions):
    """mcp-tools.json 工具名集合与 plugin.json functions[].name 一致。"""
    mt_set = set(mcp_tools_names)
    pf_set = set(plugin_functions)
    in_mt_not_pf = mt_set - pf_set
    in_pf_not_mt = pf_set - mt_set
    assert not in_mt_not_pf and not in_pf_not_mt, (
        f"不一致:\n"
        f"  mcp-tools.json 有但 plugin.functions 无: {in_mt_not_pf}\n"
        f"  plugin.functions 有但 mcp-tools.json 无: {in_pf_not_mt}"
    )


def test_manifest_references_declarative_agent():
    """manifest.json 正确引用 declarativeAgent.json。"""
    path = M365_DIR / "manifest.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    agents = data.get("copilotAgents", {}).get("declarativeAgents", [])
    assert len(agents) >= 1, "manifest.json 必须至少声明一个 declarativeAgent"
    files = [a.get("file") for a in agents]
    assert "declarativeAgent.json" in files, (
        f"manifest.json 未引用 declarativeAgent.json，实际引用: {files}"
    )


def test_declarative_agent_references_plugin():
    """declarativeAgent.json actions 正确引用 plugin.json。"""
    path = M365_DIR / "declarativeAgent.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    actions = data.get("actions", [])
    assert len(actions) >= 1, "declarativeAgent.json 必须至少声明一个 action"
    files = [a.get("file") for a in actions]
    assert "plugin.json" in files, (
        f"declarativeAgent.json 未引用 plugin.json，实际引用: {files}"
    )


def test_mcp_tools_no_duplicate_names(mcp_tools_names):
    """mcp-tools.json 中没有重复的工具名。"""
    seen = set()
    duplicates = []
    for name in mcp_tools_names:
        if name in seen:
            duplicates.append(name)
        seen.add(name)
    assert not duplicates, f"mcp-tools.json 中有重复工具名: {duplicates}"


def test_mcp_tools_have_required_schema_fields(mcp_tools_names):
    """每个工具的 inputSchema 有必要字段（type=object, properties）。"""
    path = M365_DIR / "mcp-tools.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    errors = []
    for tool in data["tools"]:
        schema = tool.get("inputSchema", {})
        if schema.get("type") != "object":
            errors.append(f"{tool['name']}: inputSchema.type != 'object'")
        if "properties" not in schema:
            errors.append(f"{tool['name']}: inputSchema 缺少 'properties'")
        if not tool.get("description"):
            errors.append(f"{tool['name']}: 缺少 description 字段")
    assert not errors, "工具 Schema 字段验证失败:\n" + "\n".join(errors)


def test_declarative_agent_instructions_tool_names_exist_in_handlers(server_handlers):
    """declarativeAgent.json instructions 中出现的 analytics_* 工具名必须在 _HANDLERS 中存在。

    Instructions 文本内联了工具路由规则（例如「调用 analytics_overview」），
    若工具名拼写错误，M365 Copilot 会按指令路由到不存在的工具，工具调用静默失败。
    """
    import re
    path = M365_DIR / "declarativeAgent.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    instructions = data.get("instructions", "")

    # 从 instructions 中提取所有 analytics_* 模式的工具名
    found_tool_names = set(re.findall(r"analytics_[a-z_]+", instructions))

    missing = found_tool_names - server_handlers
    assert not missing, (
        f"declarativeAgent.json instructions 中引用的工具名在 _HANDLERS 中不存在: {missing}\n"
        f"（这会导致 M365 Copilot 按指令路由到不存在的工具，工具调用静默失败）"
    )
