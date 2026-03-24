"""Local file reader for CSV and Excel files."""

from pathlib import Path
from typing import Any, Optional

import pandas as pd
from rich.console import Console

console = Console()


class FileReadError(Exception):
    """File read error."""

    pass


class LocalDataReader:
    """Reader for local data files (CSV, Excel)."""

    def __init__(self, data_dir: str = "./data"):
        self.data_dir = Path(data_dir)

    def _resolve_path(self, filename: str) -> Path:
        """Resolve file path, checking both absolute and relative to data_dir."""
        path = Path(filename)
        if path.is_absolute() and path.exists():
            return path

        relative_path = self.data_dir / filename
        if relative_path.exists():
            return relative_path

        if path.exists():
            return path

        raise FileReadError(f"File not found: {filename}")

    def read_csv(
        self,
        filename: str,
        encoding: str = "utf-8",
        **kwargs: Any,
    ) -> pd.DataFrame:
        """Read CSV file."""
        path = self._resolve_path(filename)
        try:
            return pd.read_csv(path, encoding=encoding, **kwargs)
        except Exception as e:
            raise FileReadError(f"Failed to read CSV {filename}: {e}")

    def read_excel(
        self,
        filename: str,
        sheet_name: Optional[str | int] = 0,
        **kwargs: Any,
    ) -> pd.DataFrame:
        """Read Excel file."""
        path = self._resolve_path(filename)
        try:
            return pd.read_excel(path, sheet_name=sheet_name, **kwargs)
        except Exception as e:
            raise FileReadError(f"Failed to read Excel {filename}: {e}")

    def read_file(self, filename: str, **kwargs: Any) -> pd.DataFrame:
        """Read file based on extension."""
        path = self._resolve_path(filename)
        suffix = path.suffix.lower()

        if suffix == ".csv":
            return self.read_csv(filename, **kwargs)
        elif suffix in (".xlsx", ".xls"):
            return self.read_excel(filename, **kwargs)
        else:
            raise FileReadError(f"Unsupported file format: {suffix}")

    def list_files(self, pattern: str = "*") -> list[Path]:
        """List files in data directory matching pattern."""
        if not self.data_dir.exists():
            return []
        return list(self.data_dir.glob(pattern))

    def file_exists(self, filename: str) -> bool:
        """Check if file exists."""
        try:
            self._resolve_path(filename)
            return True
        except FileReadError:
            return False


def read_customers_csv(filename: str, data_dir: str = "./data") -> pd.DataFrame:
    """Read customers from CSV file with standard column mapping."""
    reader = LocalDataReader(data_dir)
    df = reader.read_csv(filename)

    # Standard column mapping (Chinese to English)
    column_mapping = {
        "客户ID": "id",
        "客户编号": "id",
        "姓名": "name",
        "客户名称": "name",
        "手机": "phone",
        "手机号": "phone",
        "电话": "phone",
        "邮箱": "email",
        "电子邮箱": "email",
        "客户类型": "customer_type",
        "类型": "customer_type",
        "注册时间": "created_at",
        "创建时间": "created_at",
        "最后活跃": "last_active_at",
        "最后活跃时间": "last_active_at",
        "订单数": "total_orders",
        "订单总数": "total_orders",
        "消费金额": "total_spent",
        "累计消费": "total_spent",
        "积分余额": "points_balance",
        "积分": "points_balance",
        "标签": "tags",
        "渠道": "channels",
    }

    # Rename columns if mapping exists
    df = df.rename(columns={k: v for k, v in column_mapping.items() if k in df.columns})

    return df


def read_segments_csv(filename: str, data_dir: str = "./data") -> pd.DataFrame:
    """Read segments from CSV file with standard column mapping."""
    reader = LocalDataReader(data_dir)
    df = reader.read_csv(filename)

    column_mapping = {
        "分群ID": "id",
        "分群编号": "id",
        "分群名称": "name",
        "名称": "name",
        "描述": "description",
        "状态": "status",
        "客户数": "customer_count",
        "人数": "customer_count",
        "创建时间": "created_at",
        "更新时间": "updated_at",
    }

    df = df.rename(columns={k: v for k, v in column_mapping.items() if k in df.columns})
    return df


def read_orders_csv(filename: str, data_dir: str = "./data") -> pd.DataFrame:
    """Read orders from CSV file with standard column mapping."""
    reader = LocalDataReader(data_dir)
    df = reader.read_csv(filename)

    column_mapping = {
        "订单ID": "id",
        "订单编号": "id",
        "订单号": "id",
        "客户ID": "customer_id",
        "客户编号": "customer_id",
        "订单金额": "amount",
        "金额": "amount",
        "实付金额": "paid_amount",
        "订单状态": "status",
        "状态": "status",
        "渠道": "channel",
        "下单渠道": "channel",
        "下单时间": "created_at",
        "订单时间": "created_at",
        "支付时间": "paid_at",
        "省份": "province",
        "城市": "city",
    }

    df = df.rename(columns={k: v for k, v in column_mapping.items() if k in df.columns})

    # Convert date columns
    for col in ["created_at", "paid_at"]:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors="coerce")

    return df
