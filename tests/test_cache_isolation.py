"""
tests/test_cache_isolation.py

Unit tests for tenant_id isolation in mcp_server/server.py cache layer.
验证 PRD §6.3：缓存 Key 必须含 tenant_id，防止跨租户数据泄露。
"""

from __future__ import annotations


# ---------------------------------------------------------------------------
# _cache_key isolation tests
# ---------------------------------------------------------------------------

def test_cache_key_tenant_isolation():
    """不同 tenant_id 产生不同 cache key（跨租户隔离核心验收）。"""
    from mcp_server.server import _cache_key
    k1 = _cache_key("analytics_overview", {"days": 30}, "tenant-a")
    k2 = _cache_key("analytics_overview", {"days": 30}, "tenant-b")
    assert k1 != k2, "不同租户的相同查询必须产生不同 cache key，否则存在跨租户数据泄露风险"


def test_cache_key_same_tenant_same_args():
    """相同 tenant_id 和参数产生相同 key（缓存命中正常工作）。"""
    from mcp_server.server import _cache_key
    k1 = _cache_key("analytics_overview", {"days": 30}, "tenant-a")
    k2 = _cache_key("analytics_overview", {"days": 30}, "tenant-a")
    assert k1 == k2, "相同租户和参数必须产生相同 cache key，否则缓存无效"


def test_cache_key_includes_tenant_id():
    """cache key 必须包含 tenant_id 字符串。"""
    from mcp_server.server import _cache_key
    k = _cache_key("analytics_overview", {}, "tenant-xyz-789")
    assert "tenant-xyz-789" in k, "cache key 必须包含 tenant_id 以便于排障"


def test_cache_key_different_tools_different_keys():
    """相同 tenant_id 但不同工具名产生不同 key。"""
    from mcp_server.server import _cache_key
    k1 = _cache_key("analytics_overview", {}, "tenant-a")
    k2 = _cache_key("analytics_retention", {}, "tenant-a")
    assert k1 != k2


def test_cache_key_different_args_different_keys():
    """相同 tenant_id 和工具名但不同参数产生不同 key。"""
    from mcp_server.server import _cache_key
    k1 = _cache_key("analytics_overview", {"days": 30}, "tenant-a")
    k2 = _cache_key("analytics_overview", {"days": 90}, "tenant-a")
    assert k1 != k2


def test_cache_key_empty_tenant_id():
    """empty tenant_id 产生与 non-empty tenant_id 不同的 key（防止无 tenant 请求命中有 tenant 缓存）。"""
    from mcp_server.server import _cache_key
    k_empty = _cache_key("analytics_overview", {"days": 30}, "")
    k_real = _cache_key("analytics_overview", {"days": 30}, "tenant-a")
    assert k_empty != k_real


def test_cache_key_args_order_independent():
    """参数字典中键的顺序不影响 cache key（使用 sort_keys=True）。"""
    from mcp_server.server import _cache_key
    k1 = _cache_key("analytics_overview", {"days": 30, "start_date": "2026-01-01"}, "tenant-a")
    k2 = _cache_key("analytics_overview", {"start_date": "2026-01-01", "days": 30}, "tenant-a")
    assert k1 == k2, "参数顺序不同不应产生不同的 cache key"


# ──────────────────────────────────────────────────────────────────────────────
# _run_with_cache 行为层测试 — 验证 tenant_id 实际作为独立缓存命名空间（PRD §6.3）
# ──────────────────────────────────────────────────────────────────────────────

def test_run_with_cache_tenant_isolation():
    """最核心的安全测试：不同 tenant_id 的相同查询不共享缓存结果。
    tenant-a 的缓存结果绝不能被 tenant-b 命中。
    """
    from mcp_server.server import _run_with_cache, _cache, _CACHE_TTL

    call_count_a = 0
    call_count_b = 0

    def compute_a() -> list:
        nonlocal call_count_a
        call_count_a += 1
        return [f"result-from-tenant-a-call-{call_count_a}"]

    def compute_b() -> list:
        nonlocal call_count_b
        call_count_b += 1
        return [f"result-from-tenant-b-call-{call_count_b}"]

    # tenant-a 第一次调用（缓存未命中，计算 compute_a）
    result_a1 = _run_with_cache("analytics_overview", {"days": 30}, "tenant-a", compute_a)
    assert call_count_a == 1, "tenant-a 首次调用应触发 compute_a"
    assert "tenant-a" in result_a1[0]

    # tenant-b 相同参数调用（不应命中 tenant-a 缓存，应触发 compute_b）
    result_b1 = _run_with_cache("analytics_overview", {"days": 30}, "tenant-b", compute_b)
    assert call_count_b == 1, "tenant-b 相同参数应触发 compute_b，不命中 tenant-a 缓存"
    assert "tenant-b" in result_b1[0], "tenant-b 的结果不应包含 tenant-a 的数据"
    assert result_a1 != result_b1, "两个租户的缓存结果必须完全独立"

    # tenant-a 再次相同参数调用（应命中缓存，compute_a 不再被调用）
    result_a2 = _run_with_cache("analytics_overview", {"days": 30}, "tenant-a", compute_a)
    assert call_count_a == 1, "tenant-a 第二次调用应命中缓存，compute_a 不应再被触发"
    assert result_a2 == result_a1, "缓存命中应返回相同结果"


def test_run_with_cache_same_tenant_hits_cache():
    """相同 tenant_id + 相同参数的第二次调用命中缓存（性能验证）。"""
    from mcp_server.server import _run_with_cache

    call_count = 0

    def expensive_compute() -> list:
        nonlocal call_count
        call_count += 1
        return ["expensive-result"]

    # 第一次：缓存未命中
    _run_with_cache("analytics_retention", {"days": 7}, "tenant-cache-test", expensive_compute)
    assert call_count == 1

    # 第二次：应命中缓存，compute_fn 不被调用
    _run_with_cache("analytics_retention", {"days": 7}, "tenant-cache-test", expensive_compute)
    assert call_count == 1, "缓存命中：compute_fn 不应被再次调用"
