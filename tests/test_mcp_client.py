"""Tests for cli.api.mcp_client — MCPClient and MCPError."""

import queue
import threading
import time
from unittest.mock import MagicMock, patch

import httpx
import pytest

from cli.api.mcp_client import MCPClient, MCPConfig, MCPError


# ---------------------------------------------------------------------------
# MCPError
# ---------------------------------------------------------------------------

class TestMCPError:
    def test_is_exception_subclass(self):
        """MCPError must be a proper Exception subclass."""
        assert issubclass(MCPError, Exception)

    def test_can_be_raised_and_caught(self):
        with pytest.raises(MCPError, match="something went wrong"):
            raise MCPError("something went wrong")

    def test_message_is_preserved(self):
        err = MCPError("detail message")
        assert str(err) == "detail message"


# ---------------------------------------------------------------------------
# MCPConfig / constructor validation
# ---------------------------------------------------------------------------

class TestMCPConfigValidation:
    def test_validate_config_missing_all_fields(self):
        """_validate_config raises MCPError when sse_url, post_url, tenant_id are empty."""
        client = MCPClient(MCPConfig())  # all fields default to ""
        with pytest.raises(MCPError) as exc_info:
            client._validate_config()
        msg = str(exc_info.value)
        assert "sse_url" in msg
        assert "post_url" in msg
        assert "tenant_id" in msg

    def test_validate_config_missing_sse_url(self):
        cfg = MCPConfig(post_url="http://post", tenant_id="t1")
        client = MCPClient(cfg)
        with pytest.raises(MCPError) as exc_info:
            client._validate_config()
        assert "sse_url" in str(exc_info.value)

    def test_validate_config_missing_post_url(self):
        cfg = MCPConfig(sse_url="http://sse", tenant_id="t1")
        client = MCPClient(cfg)
        with pytest.raises(MCPError) as exc_info:
            client._validate_config()
        assert "post_url" in str(exc_info.value)

    def test_validate_config_missing_tenant_id(self):
        cfg = MCPConfig(sse_url="http://sse", post_url="http://post")
        client = MCPClient(cfg)
        with pytest.raises(MCPError) as exc_info:
            client._validate_config()
        assert "tenant_id" in str(exc_info.value)

    def test_validate_config_all_fields_present(self):
        """_validate_config must not raise when all required fields are provided."""
        cfg = MCPConfig(sse_url="http://sse", post_url="http://post", tenant_id="t1")
        client = MCPClient(cfg)
        # Should not raise
        client._validate_config()


# ---------------------------------------------------------------------------
# Helper: build a connected MCPClient with a mocked POST
# ---------------------------------------------------------------------------

def _make_client(sse_alive: bool, queue_data=None, timeout: int = 2) -> MCPClient:
    """
    Return an MCPClient that:
    - Has a valid config (no real network calls).
    - Has _connected = True and _session_id set.
    - Has _sse_thread replaced with a mock whose is_alive() is controlled.
    - Has httpx.post patched to return HTTP 202 (accepted; response comes via SSE).
    The caller controls whether the response queue ever gets data.
    """
    cfg = MCPConfig(
        sse_url="http://sse.example.com",
        post_url="http://post.example.com",
        tenant_id="test-tenant",
        timeout=timeout,
    )
    client = MCPClient(cfg)
    client._connected = True
    client._session_id = "sess-0001"

    # Mock SSE thread
    mock_thread = MagicMock(spec=threading.Thread)
    mock_thread.is_alive.return_value = sse_alive
    client._sse_thread = mock_thread

    # If caller wants to pre-fill a response, wire it up via a side-effect on
    # httpx.post that also places the message in the right response queue.
    if queue_data is not None:
        original_post = httpx.post

        def _fake_post(url, **kwargs):
            # After the POST is "sent", put the response into the waiting queue.
            # The request_id is embedded in the JSON body.
            body = kwargs.get("json", {})
            req_id = body.get("id")
            if req_id and req_id in client._responses:
                client._responses[req_id].put(queue_data)
            resp = MagicMock(spec=httpx.Response)
            resp.status_code = 202
            return resp

        return client, _fake_post

    return client, None


# ---------------------------------------------------------------------------
# _send_request: fast-fail when SSE thread dies
# ---------------------------------------------------------------------------

class TestSendRequestSSEFastFail:
    def test_raises_mcp_error_when_sse_thread_dead(self):
        """_send_request must raise MCPError quickly when _sse_thread.is_alive() is False."""
        client, _ = _make_client(sse_alive=False, timeout=30)

        # Patch httpx.post to return HTTP 202 (no real network call)
        mock_response = MagicMock(spec=httpx.Response)
        mock_response.status_code = 202

        start = time.monotonic()
        with patch("cli.api.mcp_client.httpx.post", return_value=mock_response):
            with pytest.raises(MCPError) as exc_info:
                client._send_request("tools/list", {})

        elapsed = time.monotonic() - start
        # Should fail fast — well under the 30-second timeout
        assert elapsed < 5.0, f"Fast-fail took too long: {elapsed:.2f}s"
        assert "SSE connection lost" in str(exc_info.value)

    def test_sse_dead_error_message(self):
        """Verify the exact error message fragment for SSE-dead scenario."""
        client, _ = _make_client(sse_alive=False, timeout=5)
        mock_response = MagicMock(spec=httpx.Response)
        mock_response.status_code = 202

        with patch("cli.api.mcp_client.httpx.post", return_value=mock_response):
            with pytest.raises(MCPError, match="SSE connection lost"):
                client._send_request("initialize", {})


# ---------------------------------------------------------------------------
# _send_request: timeout when SSE is alive but queue never gets data
# ---------------------------------------------------------------------------

class TestSendRequestTimeout:
    def test_raises_mcp_error_on_timeout(self):
        """_send_request must raise MCPError with 'timed out' after the deadline passes."""
        # Use a very short timeout (1 s) so the test stays fast
        client, _ = _make_client(sse_alive=True, timeout=1)

        mock_response = MagicMock(spec=httpx.Response)
        mock_response.status_code = 202

        start = time.monotonic()
        with patch("cli.api.mcp_client.httpx.post", return_value=mock_response):
            with pytest.raises(MCPError) as exc_info:
                client._send_request("tools/list", {}, timeout=1)

        elapsed = time.monotonic() - start
        # Must not take much longer than the configured timeout
        assert elapsed < 5.0, f"Timeout test took unexpectedly long: {elapsed:.2f}s"
        assert "timed out" in str(exc_info.value)

    def test_timeout_error_includes_duration(self):
        """The timeout error message must mention the timeout value."""
        client, _ = _make_client(sse_alive=True, timeout=1)
        mock_response = MagicMock(spec=httpx.Response)
        mock_response.status_code = 202

        with patch("cli.api.mcp_client.httpx.post", return_value=mock_response):
            with pytest.raises(MCPError, match=r"1s"):
                client._send_request("tools/list", {}, timeout=1)


# ---------------------------------------------------------------------------
# _send_request: successful response
# ---------------------------------------------------------------------------

class TestSendRequestSuccess:
    def test_returns_response_when_queue_delivers(self):
        """_send_request returns the dict placed on the response queue."""
        cfg = MCPConfig(
            sse_url="http://sse.example.com",
            post_url="http://post.example.com",
            tenant_id="test-tenant",
            timeout=5,
        )
        client = MCPClient(cfg)
        client._connected = True
        client._session_id = "sess-0002"

        mock_thread = MagicMock(spec=threading.Thread)
        mock_thread.is_alive.return_value = True
        client._sse_thread = mock_thread

        expected_result = {"jsonrpc": "2.0", "id": None, "result": {"tools": []}}

        def _fake_post(url, **kwargs):
            body = kwargs.get("json", {})
            req_id = body.get("id")
            # Simulate SSE message arriving shortly after POST
            def _deliver():
                time.sleep(0.05)
                if req_id and req_id in client._responses:
                    msg = dict(expected_result)
                    msg["id"] = req_id
                    client._responses[req_id].put(msg)
            t = threading.Thread(target=_deliver, daemon=True)
            t.start()

            resp = MagicMock(spec=httpx.Response)
            resp.status_code = 202
            return resp

        with patch("cli.api.mcp_client.httpx.post", side_effect=_fake_post):
            result = client._send_request("tools/list", {}, timeout=5)

        assert "result" in result
        assert result["result"] == {"tools": []}


# ---------------------------------------------------------------------------
# _resolve_database: per-tool SQL routing — covers all 16 analytics tools
# ---------------------------------------------------------------------------

def _client_with_dbs(
    das: str = "das_demoen",
    dts: str = "dts_demoen",
    datanow: str = "datanow_demoen",
) -> MCPClient:
    """Return an MCPClient pre-loaded with all three database names."""
    cfg = MCPConfig(
        sse_url="http://sse.example.com",
        post_url="http://post.example.com",
        tenant_id="demoen",
        das_database=das,
        dts_database=dts,
        datanow_database=datanow,
    )
    return MCPClient(cfg)


class TestResolveDatabaseDAS:
    """All tables with ads_/dwd_/dim_/dws_ prefix should resolve to das_database."""

    # --- analytics_overview ---

    def test_overview_dim_customer_info(self):
        """analytics_overview: COUNT(*) FROM dim_customer_info → DAS."""
        c = _client_with_dbs()
        assert c._resolve_database(
            "SELECT COUNT(*) as total FROM dim_customer_info"
        ) == "das_demoen"

    def test_overview_ads_business_overview(self):
        """analytics_overview: SUM FROM ads_das_business_overview_d → DAS."""
        c = _client_with_dbs()
        sql = """
            SELECT SUM(add_custs_num) as new_customers,
                   SUM(total_order_num) as total_orders
            FROM ads_das_business_overview_d
            WHERE biz_date >= '2024-01-01'
        """
        assert c._resolve_database(sql) == "das_demoen"

    def test_overview_dwd_v_order_active(self):
        """analytics_overview: active buyers from dwd_v_order → DAS."""
        c = _client_with_dbs()
        sql = "SELECT COUNT(DISTINCT customer_code) as active FROM dwd_v_order WHERE order_date >= '2024-01-01'"
        assert c._resolve_database(sql) == "das_demoen"

    # --- analytics_customers ---

    def test_customers_dws_base_metrics(self):
        """analytics_customers: dws_customer_base_metrics → DAS."""
        c = _client_with_dbs()
        sql = "SELECT * FROM dws_customer_base_metrics WHERE biz_date = '2024-03-01'"
        assert c._resolve_database(sql) == "das_demoen"

    def test_customers_dim_customer_info_list(self):
        """analytics_customers: customer list from dim_customer_info → DAS."""
        c = _client_with_dbs()
        sql = "SELECT customer_code, customer_name FROM dim_customer_info LIMIT 20"
        assert c._resolve_database(sql) == "das_demoen"

    def test_customers_ads_source_analysis(self):
        """analytics_customers (source): ads_das_custs_source_analysis_d → DAS."""
        c = _client_with_dbs()
        sql = "SELECT channel, COUNT(*) as cnt FROM ads_das_custs_source_analysis_d GROUP BY channel"
        assert c._resolve_database(sql) == "das_demoen"

    def test_customers_ads_gender_distribution(self):
        """analytics_customers (gender): ads_das_custs_gender_distribution_d → DAS."""
        c = _client_with_dbs()
        sql = """
            SELECT gender, COUNT(*) FROM ads_das_custs_gender_distribution_d
            WHERE biz_date = (SELECT MAX(biz_date) FROM ads_das_custs_gender_distribution_d)
            GROUP BY gender
        """
        assert c._resolve_database(sql) == "das_demoen"

    # --- analytics_orders ---

    def test_orders_dwd_v_order_basic(self):
        """analytics_orders: dwd_v_order basic query → DAS."""
        c = _client_with_dbs()
        sql = "SELECT order_code, payment_amount, order_status FROM dwd_v_order LIMIT 50"
        assert c._resolve_database(sql) == "das_demoen"

    def test_orders_dwd_v_order_agg(self):
        """analytics_orders: aggregate dwd_v_order → DAS."""
        c = _client_with_dbs()
        sql = """
            SELECT DATE(order_date) as date, SUM(payment_amount) as revenue
            FROM dwd_v_order
            WHERE order_date >= '2024-01-01'
            GROUP BY DATE(order_date)
        """
        assert c._resolve_database(sql) == "das_demoen"

    def test_orders_dwd_retention_self_join(self):
        """analytics_retention: self-join on dwd_v_order → DAS (first match wins)."""
        c = _client_with_dbs()
        sql = """
            SELECT a.customer_code
            FROM dwd_v_order a
            WHERE EXISTS (
                SELECT 1 FROM dwd_v_order b
                WHERE b.customer_code = a.customer_code
                  AND b.order_date < a.order_date
            )
        """
        assert c._resolve_database(sql) == "das_demoen"

    # --- analytics_campaigns ---

    def test_campaigns_ads_activity_analysis(self):
        """analytics_campaigns: ads_das_activity_analysis_d → DAS."""
        c = _client_with_dbs()
        sql = """
            SELECT activity_id, SUM(order_amt) as revenue
            FROM ads_das_activity_analysis_d
            WHERE biz_date >= '2024-01-01'
            GROUP BY activity_id
        """
        assert c._resolve_database(sql) == "das_demoen"

    def test_campaigns_ads_channel_effect(self):
        """analytics_campaigns: ads_das_activity_channel_effect_d → DAS."""
        c = _client_with_dbs()
        sql = "SELECT channel, SUM(order_num) FROM ads_das_activity_channel_effect_d GROUP BY channel"
        assert c._resolve_database(sql) == "das_demoen"

    def test_campaigns_join_order(self):
        """analytics_campaigns: JOIN ads and dwd tables → DAS (first FROM match)."""
        c = _client_with_dbs()
        sql = """
            SELECT a.activity_id, o.order_code
            FROM ads_das_activity_analysis_d a
            JOIN dwd_v_order o ON a.activity_id = o.activity_id
        """
        assert c._resolve_database(sql) == "das_demoen"

    # --- analytics_points ---

    def test_points_dws_base_metrics(self):
        """analytics_points: dws_points_base_metrics_d → DAS."""
        c = _client_with_dbs()
        sql = "SELECT SUM(earn_points) as earned FROM dws_points_base_metrics_d WHERE biz_date >= '2024-01-01'"
        assert c._resolve_database(sql) == "das_demoen"

    def test_points_dwd_member_points_log(self):
        """analytics_points: dwd_member_points_log → DAS."""
        c = _client_with_dbs()
        sql = "SELECT member_code, SUM(points) as total FROM dwd_member_points_log GROUP BY member_code"
        assert c._resolve_database(sql) == "das_demoen"

    def test_points_join_dim_customer(self):
        """analytics_points at_risk: JOIN dwd_member_points_log with dim_customer_info → DAS."""
        c = _client_with_dbs()
        sql = """
            SELECT pl.member_code, c.customer_name, SUM(pl.points) as expiring
            FROM dwd_member_points_log pl
            LEFT JOIN dim_customer_info c ON pl.member_code = c.customer_code
            WHERE pl.expire_date <= DATE_ADD(CURDATE(), INTERVAL 30 DAY)
            GROUP BY pl.member_code, c.customer_name
        """
        assert c._resolve_database(sql) == "das_demoen"

    # --- analytics_coupons ---

    def test_coupons_ads_coupon_analysis(self):
        """analytics_coupons: ads_das_v_coupon_analysis_d → DAS."""
        c = _client_with_dbs()
        sql = "SELECT coupon_type, COUNT(*) FROM ads_das_v_coupon_analysis_d GROUP BY coupon_type"
        assert c._resolve_database(sql) == "das_demoen"

    def test_coupons_dwd_coupon_instance(self):
        """analytics_coupons: dwd_coupon_instance → DAS."""
        c = _client_with_dbs()
        sql = "SELECT rule_id, COUNT(*) as used FROM dwd_coupon_instance WHERE status = 'used' GROUP BY rule_id"
        assert c._resolve_database(sql) == "das_demoen"

    def test_coupons_dws_base_metrics(self):
        """analytics_coupons anomaly: dws_coupon_base_metrics_d → DAS."""
        c = _client_with_dbs()
        sql = "SELECT biz_date, SUM(used_num) FROM dws_coupon_base_metrics_d GROUP BY biz_date ORDER BY biz_date"
        assert c._resolve_database(sql) == "das_demoen"

    # --- analytics_funnel / analytics_stores ---

    def test_funnel_dwd_v_order(self):
        """analytics_funnel: dwd_v_order → DAS."""
        c = _client_with_dbs()
        sql = "SELECT COUNT(DISTINCT customer_code) FROM dwd_v_order WHERE order_date >= '2024-01-01'"
        assert c._resolve_database(sql) == "das_demoen"

    def test_stores_dwd_v_order(self):
        """analytics_stores: dwd_v_order by channel/store → DAS."""
        c = _client_with_dbs()
        sql = """
            SELECT store_code, SUM(payment_amount) as revenue
            FROM dwd_v_order
            WHERE order_date >= '2024-01-01'
            GROUP BY store_code
        """
        assert c._resolve_database(sql) == "das_demoen"

    # --- analytics_rfm ---

    def test_rfm_ads_v_rfm(self):
        """analytics_rfm: ads_v_rfm → DAS."""
        c = _client_with_dbs()
        sql = "SELECT segment, COUNT(*) as cnt FROM ads_v_rfm GROUP BY segment"
        assert c._resolve_database(sql) == "das_demoen"

    # --- analytics_ltv / analytics_anomaly ---

    def test_ltv_dwd_v_order(self):
        """analytics_ltv: dwd_v_order cohort analysis → DAS."""
        c = _client_with_dbs()
        sql = """
            SELECT customer_code, MIN(order_date) as first_order, SUM(payment_amount) as ltv
            FROM dwd_v_order
            GROUP BY customer_code
        """
        assert c._resolve_database(sql) == "das_demoen"

    def test_anomaly_dws_order_base_metrics(self):
        """analytics_anomaly: dws_order_base_metrics_d → DAS."""
        c = _client_with_dbs()
        sql = "SELECT biz_date, total_order_num FROM dws_order_base_metrics_d ORDER BY biz_date DESC LIMIT 30"
        assert c._resolve_database(sql) == "das_demoen"

    def test_repurchase_ads_repurchase_analysis(self):
        """analytics_repurchase: ads_das_v_repurchase_analysis_d → DAS."""
        c = _client_with_dbs()
        sql = """
            SELECT repurchase_cycle, COUNT(*) FROM ads_das_v_repurchase_analysis_d
            WHERE biz_date >= '2024-01-01'
            GROUP BY repurchase_cycle
        """
        assert c._resolve_database(sql) == "das_demoen"

    def test_recommend_dwd_rec_user_product_rating(self):
        """analytics_recommend: dwd_rec_user_product_rating → DAS."""
        c = _client_with_dbs()
        sql = "SELECT user_id, product_id, rating FROM dwd_rec_user_product_rating WHERE user_id = '123'"
        assert c._resolve_database(sql) == "das_demoen"

    def test_recommend_dws_user_recs(self):
        """analytics_recommend: dws_rec_user_recs → DAS."""
        c = _client_with_dbs()
        sql = "SELECT user_id, product_id, score FROM dws_rec_user_recs WHERE user_id = '123' ORDER BY score DESC LIMIT 10"
        assert c._resolve_database(sql) == "das_demoen"

    def test_canvas_ads_activity_canvas(self):
        """analytics_canvas: ads_das_activity_canvas_analysis_d → DAS."""
        c = _client_with_dbs()
        sql = "SELECT canvas_id, reach_count FROM ads_das_activity_canvas_analysis_d WHERE canvas_id = '001'"
        assert c._resolve_database(sql) == "das_demoen"


class TestResolveDatabaseDTS:
    """Tables with vdm_ prefix should resolve to dts_database."""

    def test_loyalty_vdm_loyalty_program(self):
        """analytics_loyalty: vdm_t_loyalty_program → DTS."""
        c = _client_with_dbs()
        sql = "SELECT code, name, status FROM vdm_t_loyalty_program WHERE delete_flag = 0 ORDER BY code"
        assert c._resolve_database(sql) == "dts_demoen"

    def test_loyalty_vdm_member(self):
        """analytics_loyalty: vdm_t_member → DTS."""
        c = _client_with_dbs()
        sql = "SELECT member_code, tier_code, join_date FROM vdm_t_member WHERE status = 'active' LIMIT 100"
        assert c._resolve_database(sql) == "dts_demoen"

    def test_loyalty_vdm_join_points_account(self):
        """analytics_loyalty health: JOIN vdm_t_member with vdm_t_points_account → DTS."""
        c = _client_with_dbs()
        sql = """
            SELECT m.member_code, m.tier_code, pa.balance
            FROM vdm_t_member m
            JOIN vdm_t_points_account pa ON m.member_code = pa.member_code
            WHERE m.status = 'active'
        """
        assert c._resolve_database(sql) == "dts_demoen"

    def test_loyalty_vdm_points_record(self):
        """analytics_loyalty: vdm_t_points_record → DTS."""
        c = _client_with_dbs()
        sql = "SELECT member_code, SUM(points) FROM vdm_t_points_record GROUP BY member_code"
        assert c._resolve_database(sql) == "dts_demoen"

    def test_products_vdm_order_join(self):
        """analytics_products: vdm_t_order JOIN vdm_t_order_detail LEFT JOIN vdm_t_product → DTS."""
        c = _client_with_dbs()
        sql = """
            SELECT p.product_name, SUM(od.quantity) as sold
            FROM vdm_t_order o
            JOIN vdm_t_order_detail od ON o.order_id = od.order_id
            LEFT JOIN vdm_t_product p ON od.product_id = p.product_id
            WHERE o.order_date >= '2024-01-01'
            GROUP BY p.product_name
            ORDER BY sold DESC
            LIMIT 10
        """
        assert c._resolve_database(sql) == "dts_demoen"

    def test_repurchase_vdm_product_path(self):
        """analytics_repurchase (product path): vdm_t_order JOIN vdm_t_order_detail → DTS."""
        c = _client_with_dbs()
        sql = """
            SELECT o.customer_code, od.product_id
            FROM vdm_t_order o
            JOIN vdm_t_order_detail od ON o.order_id = od.order_id
        """
        assert c._resolve_database(sql) == "dts_demoen"


class TestResolveDatabaseDataNow:
    """Tables with t_ or v_ prefix should resolve to datanow_database."""

    def test_segment_t_customer_group(self):
        """analytics_segment: t_customer_group → DataNow."""
        c = _client_with_dbs()
        sql = "SELECT id, name, description FROM t_customer_group WHERE status = 1"
        assert c._resolve_database(sql) == "datanow_demoen"

    def test_segment_t_customer_group_member(self):
        """analytics_segment: t_customer_group_member → DataNow."""
        c = _client_with_dbs()
        sql = "SELECT group_id, customer_code FROM t_customer_group_member WHERE group_id = '123'"
        assert c._resolve_database(sql) == "datanow_demoen"


class TestResolveDatabaseEdgeCases:
    """Edge cases: already-qualified names, no match, JOIN alias refs."""

    def test_already_qualified_returns_none(self):
        """SQL with db.table format should return None (no rewrite)."""
        c = _client_with_dbs()
        sql = "SELECT * FROM das_demoen.dim_customer_info"
        assert c._resolve_database(sql) is None

    def test_no_from_clause_returns_none(self):
        """SQL without FROM clause should return None."""
        c = _client_with_dbs()
        assert c._resolve_database("SELECT 1") is None

    def test_unknown_table_prefix_returns_none(self):
        """Unknown table prefix should return None, not crash."""
        c = _client_with_dbs()
        assert c._resolve_database("SELECT * FROM xyz_unknown_table") is None

    def test_join_alias_not_misidentified(self):
        """Alias references like 'a.id' after ON must not be confused with db.table."""
        c = _client_with_dbs()
        sql = """
            SELECT a.customer_code, b.payment_amount
            FROM dim_customer_info a
            JOIN dwd_v_order b ON a.customer_code = b.customer_code
        """
        # dim_ is the first FROM match → DAS; 'a.customer_code' is not extracted
        assert c._resolve_database(sql) == "das_demoen"

    def test_subquery_from_uses_outer_table(self):
        """Subquery: outer FROM should resolve database."""
        c = _client_with_dbs()
        sql = """
            SELECT * FROM dim_customer_info
            WHERE customer_code IN (
                SELECT DISTINCT customer_code FROM dwd_v_order WHERE order_date >= '2024-01-01'
            )
        """
        assert c._resolve_database(sql) == "das_demoen"

    def test_empty_database_config_returns_none(self):
        """When das_database is empty, matching table returns None (not empty string)."""
        c = _client_with_dbs(das="", dts="", datanow="")
        result = c._resolve_database("SELECT * FROM dim_customer_info")
        assert result is None

    def test_case_insensitive_from_keyword(self):
        """FROM keyword matching must be case-insensitive."""
        c = _client_with_dbs()
        assert c._resolve_database("select count(*) from dwd_v_order") == "das_demoen"
        assert c._resolve_database("SELECT * FROM vdm_t_member") == "dts_demoen"

    def test_multiline_sql_with_where(self):
        """Multiline SQL should still match correctly."""
        c = _client_with_dbs()
        sql = (
            "SELECT\n"
            "    SUM(add_custs_num) as new_customers\n"
            "FROM ads_das_business_overview_d\n"
            "WHERE biz_date >= '2024-01-01'\n"
        )
        assert c._resolve_database(sql) == "das_demoen"
