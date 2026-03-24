"""Tests for local data reader."""

import tempfile
from pathlib import Path

import pandas as pd
import pytest

from cli.local.reader import (
    FileReadError,
    LocalDataReader,
    read_customers_csv,
    read_orders_csv,
)


@pytest.fixture
def temp_data_dir(tmp_path):
    """Create temporary data directory with test files."""
    data_dir = tmp_path / "data"
    data_dir.mkdir()

    # Create test customers CSV
    customers_csv = data_dir / "customers.csv"
    customers_csv.write_text(
        "id,name,phone,email,customer_type,created_at,total_orders,total_spent\n"
        "C001,张三,13800138001,zhangsan@example.com,member,2024-01-15,12,8500.00\n"
        "C002,李四,13900139002,lisi@example.com,registered,2024-02-01,3,1500.00\n",
        encoding="utf-8"
    )

    # Create test orders CSV
    orders_csv = data_dir / "orders.csv"
    orders_csv.write_text(
        "id,customer_id,amount,status,channel,created_at,province\n"
        "O001,C001,580.00,completed,wechat,2024-03-01,上海\n"
        "O002,C001,1200.00,completed,tmall,2024-03-05,上海\n"
        "O003,C002,850.00,completed,wechat,2024-03-02,北京\n",
        encoding="utf-8"
    )

    return data_dir


def test_read_csv(temp_data_dir):
    """Test reading CSV file."""
    reader = LocalDataReader(str(temp_data_dir))
    df = reader.read_csv("customers.csv")

    assert len(df) == 2
    assert "id" in df.columns
    assert df.iloc[0]["name"] == "张三"


def test_read_csv_not_found():
    """Test reading non-existent file."""
    reader = LocalDataReader("./nonexistent")

    with pytest.raises(FileReadError):
        reader.read_csv("missing.csv")


def test_read_file_auto_detect(temp_data_dir):
    """Test auto-detecting file format."""
    reader = LocalDataReader(str(temp_data_dir))

    df = reader.read_file("customers.csv")
    assert len(df) == 2


def test_read_customers_csv(temp_data_dir):
    """Test reading customers with column mapping."""
    df = read_customers_csv("customers.csv", str(temp_data_dir))

    assert "id" in df.columns
    assert "name" in df.columns
    assert "phone" in df.columns
    assert len(df) == 2


def test_read_orders_csv(temp_data_dir):
    """Test reading orders with column mapping."""
    df = read_orders_csv("orders.csv", str(temp_data_dir))

    assert "id" in df.columns
    assert "customer_id" in df.columns
    assert "amount" in df.columns
    assert len(df) == 3


def test_file_exists(temp_data_dir):
    """Test file existence check."""
    reader = LocalDataReader(str(temp_data_dir))

    assert reader.file_exists("customers.csv")
    assert not reader.file_exists("missing.csv")


def test_list_files(temp_data_dir):
    """Test listing files."""
    reader = LocalDataReader(str(temp_data_dir))
    files = reader.list_files("*.csv")

    assert len(files) == 2
