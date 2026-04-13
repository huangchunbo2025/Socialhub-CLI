#!/usr/bin/env python3
"""通过 MCP HTTP Streamable 协议调用本地服务的所有 16 个分析工具，验证是否正常返回数据。

用法:
    conda run -n dev python scripts/test_all_mcp_tools.py
    conda run -n dev python scripts/test_all_mcp_tools.py --url http://localhost:8092 --key sapbigquerytest
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import uuid
from typing import Any

import requests

# ---------------------------------------------------------------------------
# 默认配置
# ---------------------------------------------------------------------------
DEFAULT_URL = "http://localhost:8092"
DEFAULT_API_KEY = "sapbigquerytest"
MCP_ENDPOINT = "/mcp"

# 所有 16 个工具及其调用参数
TOOLS: list[dict[str, Any]] = [
    {"name": "analytics_overview",   "args": {"period": "30d"}},
    {"name": "analytics_customers",  "args": {"period": "30d", "limit": 10}},
    {"name": "analytics_orders",     "args": {"period": "30d", "limit": 10}},
    {"name": "analytics_retention",  "args": {"period": "30d"}},
    {"name": "analytics_funnel",     "args": {"period": "30d"}},
    {"name": "analytics_rfm",        "args": {"period": "90d"}},
    {"name": "analytics_ltv",        "args": {"period": "365d"}},
    {"name": "analytics_campaigns",  "args": {"period": "30d", "limit": 10}},
    {"name": "analytics_points",     "args": {"period": "30d"}},
    {"name": "analytics_coupons",    "args": {"period": "30d"}},
    {"name": "analytics_loyalty",    "args": {}},
    {"name": "analytics_products",   "args": {"period": "30d", "limit": 10}},
    {"name": "analytics_stores",     "args": {"period": "30d"}},
    {"name": "analytics_repurchase", "args": {"period": "90d"}},
    {"name": "analytics_anomaly",    "args": {"metric": "gmv", "period": "30d"}},
    {"name": "analytics_segment",    "args": {"group_id": "1", "period": "30d"}},
]


# ---------------------------------------------------------------------------
# MCP HTTP Streamable 客户端
# ---------------------------------------------------------------------------

class MCPHTTPClient:
    """极简 MCP HTTP Streamable 客户端（stateless 模式，每次请求独立 session）。"""

    def __init__(self, base_url: str, api_key: str, timeout: int = 60):
        self.base_url = base_url.rstrip("/")
        self.endpoint = self.base_url + MCP_ENDPOINT
        self.api_key = api_key
        self.timeout = timeout
        self.session_id: str | None = None
        self._req_id = 0

    def _next_id(self) -> int:
        self._req_id += 1
        return self._req_id

    def _headers(self) -> dict[str, str]:
        h = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "X-API-Key": self.api_key,
        }
        if self.session_id:
            h["mcp-session-id"] = self.session_id
        return h

    def _post(self, payload: dict | list[dict]) -> dict | None:
        """POST payload, parse SSE or JSON response, return parsed result."""
        resp = requests.post(
            self.endpoint,
            headers=self._headers(),
            json=payload,
            timeout=self.timeout,
            stream=True,
        )
        # Capture session ID from response headers
        if "mcp-session-id" in resp.headers:
            self.session_id = resp.headers["mcp-session-id"]

        ct = resp.headers.get("content-type", "")
        if resp.status_code == 202:
            # Accepted, no body (notification)
            return None
        if "text/event-stream" in ct:
            return self._parse_sse(resp)
        # Plain JSON
        try:
            return resp.json()
        except Exception:
            return {"_raw": resp.text}

    def _parse_sse(self, resp: requests.Response) -> dict | None:
        """Parse first 'message' event from SSE stream."""
        last_data: str | None = None
        for raw_line in resp.iter_lines(decode_unicode=True):
            if not raw_line:
                if last_data:
                    try:
                        return json.loads(last_data)
                    except json.JSONDecodeError:
                        pass
                    last_data = None
                continue
            if raw_line.startswith("data:"):
                last_data = raw_line[5:].strip()
        if last_data:
            try:
                return json.loads(last_data)
            except json.JSONDecodeError:
                return {"_raw": last_data}
        return None

    def initialize(self) -> dict:
        payload = {
            "jsonrpc": "2.0",
            "id": self._next_id(),
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "mcp-tool-tester", "version": "1.0"},
            },
        }
        result = self._post(payload)
        # Send notifications/initialized (fire-and-forget)
        notif = {"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}}
        self._post(notif)
        return result or {}

    def call_tool(self, name: str, arguments: dict) -> dict:
        payload = {
            "jsonrpc": "2.0",
            "id": self._next_id(),
            "method": "tools/call",
            "params": {"name": name, "arguments": arguments},
        }
        return self._post(payload) or {}


# ---------------------------------------------------------------------------
# 结果解析辅助函数
# ---------------------------------------------------------------------------

def _extract_text(response: dict) -> str:
    """从 tools/call 响应中提取文本内容。"""
    result = response.get("result", {})
    if isinstance(result, dict):
        content = result.get("content", [])
        if isinstance(content, list) and content:
            first = content[0]
            if isinstance(first, dict):
                return first.get("text", "")
    return json.dumps(response, ensure_ascii=False)[:200]


def _has_data(text: str) -> bool:
    """粗略判断返回文本是否包含实际数据（非全零/空）。"""
    if not text:
        return False
    lower = text.lower()
    # 包含数字且不全是 0
    if "error" in lower or "exception" in lower:
        return False
    # 检查是否有非零数字
    import re
    nums = re.findall(r'\b([1-9]\d*)\b', text)
    return len(nums) > 0


# ---------------------------------------------------------------------------
# 主逻辑
# ---------------------------------------------------------------------------

def run(base_url: str, api_key: str, timeout: int = 60) -> None:
    client = MCPHTTPClient(base_url, api_key, timeout)

    print(f"\n{'='*60}")
    print(f"  MCP 工具全量测试")
    print(f"  服务: {base_url}")
    print(f"  API Key: {api_key}")
    print(f"{'='*60}\n")

    # Step 1: Initialize
    print("▶ 初始化 MCP session ...", end=" ", flush=True)
    try:
        init_resp = client.initialize()
        if "error" in init_resp:
            print(f"FAIL: {init_resp['error']}")
            sys.exit(1)
        server_info = init_resp.get("result", {}).get("serverInfo", {})
        print(f"OK  ({server_info.get('name', '?')} {server_info.get('version', '')})")
        print(f"    session-id: {client.session_id}\n")
    except Exception as e:
        print(f"FAIL: {e}")
        sys.exit(1)

    # Step 2: Call each tool
    results: list[dict] = []
    for tool in TOOLS:
        name = tool["name"]
        args = tool["args"]
        print(f"▶ {name:<28}", end=" ", flush=True)
        t0 = time.monotonic()
        try:
            resp = client.call_tool(name, args)
            elapsed = time.monotonic() - t0
            if "error" in resp:
                err = resp["error"]
                msg = err.get("message", str(err)) if isinstance(err, dict) else str(err)
                status = "ERROR"
                detail = msg[:80]
            else:
                text = _extract_text(resp)
                has_data = _has_data(text)
                status = "DATA " if has_data else "ZERO "
                detail = text[:100].replace("\n", " ")
            print(f"{status}  {elapsed:.1f}s  {detail}")
            results.append({"tool": name, "status": status, "elapsed": elapsed})
        except Exception as e:
            elapsed = time.monotonic() - t0
            print(f"FAIL   {elapsed:.1f}s  {e}")
            results.append({"tool": name, "status": "FAIL", "elapsed": elapsed})

    # Step 3: Summary
    print(f"\n{'='*60}")
    data_count  = sum(1 for r in results if r["status"].strip() == "DATA")
    zero_count  = sum(1 for r in results if r["status"].strip() == "ZERO")
    error_count = sum(1 for r in results if r["status"].strip() in ("ERROR", "FAIL"))
    print(f"  结果汇总: DATA={data_count}  ZERO={zero_count}  ERROR/FAIL={error_count}")
    if zero_count or error_count:
        print("\n  需关注的工具:")
        for r in results:
            if r["status"].strip() in ("ZERO", "ERROR", "FAIL"):
                print(f"    - {r['tool']} [{r['status'].strip()}]")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="测试本地 MCP 服务所有工具")
    parser.add_argument("--url", default=DEFAULT_URL, help="MCP 服务 base URL")
    parser.add_argument("--key", default=DEFAULT_API_KEY, help="API Key")
    parser.add_argument("--timeout", type=int, default=60, help="每个工具超时秒数")
    args = parser.parse_args()
    run(args.url, args.key, args.timeout)
