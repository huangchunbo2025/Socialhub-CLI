"""Tests for data processor."""

from datetime import datetime, timedelta

import pandas as pd
import pytest

from cli.local.processor import DataProcessor


@pytest.fixture
def sample_customers():
    """Create sample customers DataFrame."""
    return pd.DataFrame({
        "id": ["C001", "C002", "C003"],
        "name": ["张三", "李四", "王五"],
        "customer_type": ["member", "member", "registered"],
        "created_at": pd.to_datetime([
            datetime.now() - timedelta(days=10),
            datetime.now() - timedelta(days=5),
            datetime.now() - timedelta(days=2),
        ]),
    })


@pytest.fixture
def sample_orders():
    """Create sample orders DataFrame."""
    return pd.DataFrame({
        "id": ["O001", "O002", "O003", "O004"],
        "customer_id": ["C001", "C001", "C002", "C001"],
        "amount": [500.0, 800.0, 600.0, 300.0],
        "channel": ["wechat", "tmall", "wechat", "wechat"],
        "province": ["上海", "上海", "北京", "上海"],
        "created_at": pd.to_datetime([
            datetime.now() - timedelta(days=5),
            datetime.now() - timedelta(days=3),
            datetime.now() - timedelta(days=2),
            datetime.now() - timedelta(days=1),
        ]),
    })


def test_parse_period():
    """Test period parsing."""
    # Test predefined periods
    start, end = DataProcessor.parse_period("7d")
    assert (end - start).days >= 7

    start, end = DataProcessor.parse_period("30d")
    assert (end - start).days >= 30

    # Test ytd
    start, end = DataProcessor.parse_period("ytd")
    assert start.month == 1 and start.day == 1

    # Test custom days
    start, end = DataProcessor.parse_period("14d")
    assert (end - start).days >= 14


def test_parse_period_invalid():
    """Test invalid period parsing."""
    with pytest.raises(ValueError):
        DataProcessor.parse_period("invalid")


def test_filter_by_date(sample_orders):
    """Test filtering by date range."""
    now = datetime.now()

    # Filter last 4 days
    filtered = DataProcessor.filter_by_date(
        sample_orders,
        "created_at",
        start_date=now - timedelta(days=4),
        end_date=now,
    )

    assert len(filtered) == 3  # O002, O003, O004


def test_calculate_overview(sample_customers, sample_orders):
    """Test calculating analytics overview."""
    result = DataProcessor.calculate_overview(
        sample_customers,
        sample_orders,
        period="7d",
    )

    assert "total_customers" in result
    assert "total_orders" in result
    assert "total_revenue" in result
    assert "average_order_value" in result

    assert result["total_customers"] == 3
    assert result["total_orders"] == 4
    assert result["total_revenue"] == 2200.0
    assert result["average_order_value"] == 550.0


def test_calculate_order_metrics(sample_orders):
    """Test calculating order metrics."""
    result = DataProcessor.calculate_order_metrics(
        sample_orders,
        period="30d",
    )

    assert "total_sales" in result
    assert "total_orders" in result
    assert "unique_customers" in result
    assert "repurchase_rate" in result

    assert result["total_sales"] == 2200.0
    assert result["total_orders"] == 4
    assert result["unique_customers"] == 2


def test_group_by_channel(sample_orders):
    """Test grouping by channel."""
    result = DataProcessor.group_by_channel(sample_orders, period="30d")

    assert "wechat" in result.index
    assert "tmall" in result.index
    assert result.loc["wechat", "order_count"] == 3
    assert result.loc["tmall", "order_count"] == 1


def test_group_by_province(sample_orders):
    """Test grouping by province."""
    result = DataProcessor.group_by_province(sample_orders, period="30d")

    assert "上海" in result.index
    assert "北京" in result.index
    assert result.loc["上海", "order_count"] == 3
    assert result.loc["北京", "order_count"] == 1
