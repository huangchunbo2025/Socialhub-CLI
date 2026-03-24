"""
Sample Skill: Data Export Plus
==============================

This is a sample skill demonstrating how to create skills for SocialHub.AI CLI.

Skills are Python modules that extend CLI functionality. Each skill must:
1. Have a skill.yaml manifest
2. Export functions that match command definitions
3. Follow the permission model
"""

import json
from pathlib import Path
from typing import Optional


def export_parquet(source: str, output: str, **kwargs) -> str:
    """Export data to Parquet format.

    Args:
        source: Data source name (customers, orders, segments)
        output: Output file path

    Returns:
        Success message
    """
    try:
        import pyarrow as pa
        import pyarrow.parquet as pq
    except ImportError:
        return "Error: pyarrow is required. Install with: pip install pyarrow"

    # Get data from CLI context
    # In real implementation, this would use the CLI's data API
    data = _get_sample_data(source)

    if not data:
        return f"Error: Unknown data source '{source}'"

    # Convert to Arrow Table
    table = pa.Table.from_pylist(data)

    # Write to Parquet
    output_path = Path(output)
    if not output_path.suffix:
        output_path = output_path.with_suffix(".parquet")

    pq.write_table(table, output_path)

    return f"Successfully exported {len(data)} records to {output_path}"


def export_jsonl(source: str, output: str, **kwargs) -> str:
    """Export data to JSON Lines format.

    Args:
        source: Data source name
        output: Output file path

    Returns:
        Success message
    """
    data = _get_sample_data(source)

    if not data:
        return f"Error: Unknown data source '{source}'"

    output_path = Path(output)
    if not output_path.suffix:
        output_path = output_path.with_suffix(".jsonl")

    with open(output_path, "w", encoding="utf-8") as f:
        for record in data:
            f.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")

    return f"Successfully exported {len(data)} records to {output_path}"


def _get_sample_data(source: str) -> Optional[list[dict]]:
    """Get sample data for demonstration.

    In real skills, you would use the CLI's data API:
    from socialhub.cli.api import get_data
    """
    sample_data = {
        "customers": [
            {"id": "C001", "name": "张三", "type": "member", "points": 1000},
            {"id": "C002", "name": "李四", "type": "member", "points": 500},
            {"id": "C003", "name": "王五", "type": "registered", "points": 100},
        ],
        "orders": [
            {"id": "O001", "customer_id": "C001", "amount": 299.00, "status": "completed"},
            {"id": "O002", "customer_id": "C002", "amount": 599.00, "status": "completed"},
        ],
    }

    return sample_data.get(source)


# Skill initialization (optional)
def on_load():
    """Called when skill is loaded."""
    pass


def on_unload():
    """Called when skill is unloaded."""
    pass
