"""Export functionality for CSV, Excel, JSON, and Markdown formats."""

import json
from datetime import datetime
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


def export_to_markdown(
    data: Union[pd.DataFrame, list[dict[str, Any]], dict[str, Any]],
    output_path: str,
    title: str = "Analytics Report",
    metadata: Optional[dict[str, Any]] = None,
) -> str:
    """Export data to a Markdown file with table formatting.

    Handles list[dict] (rendered as a markdown table) and dict (rendered
    as sections). Adds a YAML-style metadata header with timestamp.
    """
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    lines: list[str] = []
    ts = datetime.now().strftime("%Y-%m-%d %H:%M")

    # Header
    lines.append(f"# {title}")
    lines.append(f"\n_Generated: {ts}_")
    if metadata:
        lines.append("\n## Parameters\n")
        for k, v in metadata.items():
            lines.append(f"- **{k}**: {v}")

    def _rows_to_md_table(rows: list[dict]) -> list[str]:
        if not rows:
            return ["_No data_"]
        cols = list(rows[0].keys())
        out = ["| " + " | ".join(str(c) for c in cols) + " |"]
        out.append("| " + " | ".join("---" for _ in cols) + " |")
        for row in rows:
            out.append("| " + " | ".join(str(row.get(c, "")) for c in cols) + " |")
        return out

    def _render(obj: Any, depth: int = 2) -> list[str]:
        result: list[str] = []
        if isinstance(obj, list) and obj and isinstance(obj[0], dict):
            result.extend(_rows_to_md_table(obj))
        elif isinstance(obj, list):
            for item in obj:
                result.append(f"- {item}")
        elif isinstance(obj, dict):
            for k, v in obj.items():
                heading = "#" * min(depth, 6)
                result.append(f"\n{heading} {k}\n")
                if isinstance(v, (list, dict)):
                    result.extend(_render(v, depth + 1))
                else:
                    result.append(str(v))
        else:
            result.append(str(obj))
        return result

    lines.append("\n## Results\n")
    lines.extend(_render(data))
    lines.append(f"\n---\n_Source: SocialHub.AI CLI_")

    path.write_text("\n".join(lines), encoding="utf-8")
    return str(path.absolute())


def export_data(
    data: Union[pd.DataFrame, list[dict[str, Any]]],
    output_path: str,
    format: Optional[str] = None,
    title: str = "Analytics Report",
    metadata: Optional[dict[str, Any]] = None,
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
            ".md": "markdown",
        }
        format = format_map.get(suffix, "csv")

    # Export based on format
    if format == "csv":
        return export_to_csv(data, output_path)
    elif format == "excel":
        return export_to_excel(data, output_path)
    elif format == "json":
        return export_to_json(data, output_path)
    elif format == "markdown":
        return export_to_markdown(data, output_path, title=title, metadata=metadata)
    else:
        raise ExportError(f"Unsupported export format: {format}")


def format_output(
    data: Union[pd.DataFrame, list[dict[str, Any]], dict[str, Any]],
    format: str = "table",
    output_path: Optional[str] = None,
    title: str = "Analytics Report",
    metadata: Optional[dict[str, Any]] = None,
) -> Optional[str]:
    """Format and output data based on format type."""
    from .table import print_dataframe, print_dict, print_list

    # If output path is specified, export to file
    if output_path:
        return export_data(data, output_path, title=title, metadata=metadata)

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
