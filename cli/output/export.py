"""Export functionality for CSV, Excel, and JSON formats."""

import json
from pathlib import Path
from typing import Any, Optional, Union

import pandas as pd
from rich.console import Console

console = Console()


class ExportError(Exception):
    """Export error."""

    pass


def export_to_csv(
    data: Union[pd.DataFrame, list[dict[str, Any]]],
    output_path: str,
    encoding: str = "utf-8-sig",  # UTF-8 with BOM for Excel compatibility
) -> str:
    """Export data to CSV file."""
    path = Path(output_path)

    # Ensure parent directory exists
    path.parent.mkdir(parents=True, exist_ok=True)

    try:
        if isinstance(data, pd.DataFrame):
            df = data
        else:
            df = pd.DataFrame(data)

        df.to_csv(path, index=False, encoding=encoding)
        return str(path.absolute())
    except Exception as e:
        raise ExportError(f"Failed to export CSV: {e}")


def export_to_excel(
    data: Union[pd.DataFrame, list[dict[str, Any]], dict[str, pd.DataFrame]],
    output_path: str,
    sheet_name: str = "Data",
) -> str:
    """Export data to Excel file."""
    path = Path(output_path)

    # Ensure .xlsx extension
    if path.suffix.lower() not in (".xlsx", ".xls"):
        path = path.with_suffix(".xlsx")

    # Ensure parent directory exists
    path.parent.mkdir(parents=True, exist_ok=True)

    try:
        # Handle multiple sheets
        if isinstance(data, dict) and all(isinstance(v, pd.DataFrame) for v in data.values()):
            with pd.ExcelWriter(path, engine="openpyxl") as writer:
                for name, df in data.items():
                    df.to_excel(writer, sheet_name=name[:31], index=False)  # Excel sheet name limit
        else:
            if isinstance(data, pd.DataFrame):
                df = data
            else:
                df = pd.DataFrame(data)

            df.to_excel(path, sheet_name=sheet_name[:31], index=False, engine="openpyxl")

        return str(path.absolute())
    except Exception as e:
        raise ExportError(f"Failed to export Excel: {e}")


def export_to_json(
    data: Union[pd.DataFrame, list[dict[str, Any]], dict[str, Any]],
    output_path: str,
    indent: int = 2,
    ensure_ascii: bool = False,
) -> str:
    """Export data to JSON file."""
    path = Path(output_path)

    # Ensure parent directory exists
    path.parent.mkdir(parents=True, exist_ok=True)

    try:
        if isinstance(data, pd.DataFrame):
            # Convert DataFrame to list of dicts
            json_data = data.to_dict(orient="records")
        else:
            json_data = data

        with open(path, "w", encoding="utf-8") as f:
            json.dump(json_data, f, indent=indent, ensure_ascii=ensure_ascii, default=str)

        return str(path.absolute())
    except Exception as e:
        raise ExportError(f"Failed to export JSON: {e}")


def export_data(
    data: Union[pd.DataFrame, list[dict[str, Any]]],
    output_path: str,
    format: Optional[str] = None,
) -> str:
    """Export data to file, auto-detecting format from extension."""
    path = Path(output_path)

    # Determine format from extension if not specified
    if format is None:
        suffix = path.suffix.lower()
        format_map = {
            ".csv": "csv",
            ".xlsx": "excel",
            ".xls": "excel",
            ".json": "json",
        }
        format = format_map.get(suffix, "csv")

    # Export based on format
    if format == "csv":
        return export_to_csv(data, output_path)
    elif format == "excel":
        return export_to_excel(data, output_path)
    elif format == "json":
        return export_to_json(data, output_path)
    else:
        raise ExportError(f"Unsupported export format: {format}")


def format_output(
    data: Union[pd.DataFrame, list[dict[str, Any]], dict[str, Any]],
    format: str = "table",
    output_path: Optional[str] = None,
) -> Optional[str]:
    """Format and output data based on format type."""
    from .table import print_dataframe, print_dict, print_list

    # If output path is specified, export to file
    if output_path:
        return export_data(data, output_path)

    # Otherwise, print to console
    if format == "json":
        if isinstance(data, pd.DataFrame):
            json_data = data.to_dict(orient="records")
        else:
            json_data = data
        console.print_json(json.dumps(json_data, default=str, ensure_ascii=False))
    elif format == "table":
        if isinstance(data, pd.DataFrame):
            print_dataframe(data)
        elif isinstance(data, list):
            print_list(data)
        elif isinstance(data, dict):
            print_dict(data)
    else:
        # Default to table format
        if isinstance(data, pd.DataFrame):
            print_dataframe(data)
        elif isinstance(data, list):
            print_list(data)
        elif isinstance(data, dict):
            print_dict(data)

    return None


def print_export_success(path: str) -> None:
    """Print export success message."""
    console.print(f"[green][OK][/green] Data exported to: [cyan]{path}[/cyan]")
