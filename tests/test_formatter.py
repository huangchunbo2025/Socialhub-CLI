"""Tests for cli.output.formatter.OutputFormatter."""

import json
import sys
from io import StringIO

import pytest

from cli.output.formatter import OutputFormatter, get_formatter


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

SAMPLE_ROWS = [
    {"segment": "VIP", "count": 120, "revenue": 98000.5},
    {"segment": "Regular", "count": 450, "revenue": 35000.0},
]

SAMPLE_RECORD = {"name": "Alice", "orders": 7, "revenue": 1200.0}


def _capture_stdout(func, *args, **kwargs):
    """Call *func* with *args*/*kwargs* and return whatever was written to stdout."""
    buf = StringIO()
    old = sys.stdout
    sys.stdout = buf
    try:
        func(*args, **kwargs)
    finally:
        sys.stdout = old
    return buf.getvalue()


# ---------------------------------------------------------------------------
# test_text_format_print_table
# ---------------------------------------------------------------------------


def test_text_format_print_table():
    """text mode print_table must not raise and must render something."""
    formatter = OutputFormatter(format="text")
    # Rich renders to its own internal console; we just verify no exception is raised
    formatter.print_table(SAMPLE_ROWS, title="Test Table")


def test_text_format_print_table_empty():
    """text mode with empty data must not raise."""
    formatter = OutputFormatter(format="text")
    formatter.print_table([], title="Empty")


# ---------------------------------------------------------------------------
# test_json_format_print_table
# ---------------------------------------------------------------------------


def test_json_format_print_table():
    """json mode print_table must write a valid JSON array to stdout."""
    formatter = OutputFormatter(format="json")
    output = _capture_stdout(formatter.print_table, SAMPLE_ROWS)
    parsed = json.loads(output.strip())
    assert isinstance(parsed, list)
    assert len(parsed) == 2
    assert parsed[0]["segment"] == "VIP"


def test_json_format_print_record():
    """json mode print_record must write a valid JSON object to stdout."""
    formatter = OutputFormatter(format="json")
    output = _capture_stdout(formatter.print_record, SAMPLE_RECORD)
    parsed = json.loads(output.strip())
    assert isinstance(parsed, dict)
    assert parsed["name"] == "Alice"


def test_json_format_no_ansi():
    """json mode output must not contain ANSI escape sequences."""
    formatter = OutputFormatter(format="json")
    output = _capture_stdout(formatter.print_table, SAMPLE_ROWS)
    assert "\x1b[" not in output


# ---------------------------------------------------------------------------
# test_csv_format_print_table
# ---------------------------------------------------------------------------


def test_csv_format_print_table():
    """csv mode print_table stdout must contain a CSV header line."""
    formatter = OutputFormatter(format="csv")
    output = _capture_stdout(formatter.print_table, SAMPLE_ROWS)
    lines = [ln for ln in output.splitlines() if ln.strip()]
    assert len(lines) >= 1, "Expected at least a header line"
    # Header must be the column names joined by commas
    assert lines[0] == "segment,count,revenue"


def test_csv_format_print_table_rows():
    """csv mode print_table must include data rows after the header."""
    formatter = OutputFormatter(format="csv")
    output = _capture_stdout(formatter.print_table, SAMPLE_ROWS)
    lines = [ln for ln in output.splitlines() if ln.strip()]
    # header + 2 data rows
    assert len(lines) == 3


def test_csv_format_print_table_no_ansi():
    """csv mode output must not contain ANSI escape sequences."""
    formatter = OutputFormatter(format="csv")
    output = _capture_stdout(formatter.print_table, SAMPLE_ROWS)
    assert "\x1b[" not in output


def test_csv_format_empty_data():
    """csv mode with empty data must produce no output and not raise."""
    formatter = OutputFormatter(format="csv")
    output = _capture_stdout(formatter.print_table, [])
    assert output == ""


# ---------------------------------------------------------------------------
# test_stream_json_emit
# ---------------------------------------------------------------------------


def test_stream_json_emit():
    """stream-json emit_stream_event must write a valid NDJSON line per call."""
    formatter = OutputFormatter(format="stream-json")
    output = _capture_stdout(
        formatter.emit_stream_event, "progress", {"message": "loading"}
    )
    line = output.strip()
    parsed = json.loads(line)
    assert parsed["type"] == "progress"
    assert parsed["data"]["message"] == "loading"


def test_stream_json_print_table():
    """stream-json print_table must write valid NDJSON lines for start/data/end."""
    formatter = OutputFormatter(format="stream-json")
    output = _capture_stdout(formatter.print_table, SAMPLE_ROWS)
    lines = [ln for ln in output.splitlines() if ln.strip()]
    # Each line must be a valid JSON object
    parsed_lines = [json.loads(ln) for ln in lines]
    types = [obj["type"] for obj in parsed_lines]
    assert types[0] == "start"
    assert types[-1] == "end"
    data_lines = [obj for obj in parsed_lines if obj["type"] == "data"]
    assert len(data_lines) == len(SAMPLE_ROWS)


def test_stream_json_emit_noop_in_other_modes():
    """emit_stream_event must be a no-op in non stream-json modes."""
    for fmt in ("text", "json", "csv"):
        formatter = OutputFormatter(format=fmt)
        output = _capture_stdout(formatter.emit_stream_event, "ping", {"x": 1})
        assert output == "", f"Expected empty stdout for format={fmt!r}, got {output!r}"


# ---------------------------------------------------------------------------
# test_get_formatter_default
# ---------------------------------------------------------------------------


def test_get_formatter_default():
    """get_formatter(None) must return a text-mode OutputFormatter."""
    formatter = get_formatter(None)
    assert isinstance(formatter, OutputFormatter)
    assert formatter.fmt == "text"
    assert formatter.is_text_mode()


def test_get_formatter_from_ctx_obj():
    """get_formatter with a ctx_obj dict must respect the output_format key."""
    for fmt in ("json", "csv", "stream-json"):
        formatter = get_formatter({"output_format": fmt})
        assert formatter.fmt == fmt, f"Expected {fmt!r}, got {formatter.fmt!r}"


def test_get_formatter_empty_dict():
    """get_formatter with an empty dict must default to text mode."""
    formatter = get_formatter({})
    assert formatter.fmt == "text"


def test_get_formatter_unknown_format():
    """get_formatter with an unknown format string must fall back to text mode."""
    formatter = get_formatter({"output_format": "xml"})
    assert formatter.fmt == "text"


# ---------------------------------------------------------------------------
# print_message and print_error (stderr routing — smoke tests)
# ---------------------------------------------------------------------------


def test_print_message_does_not_write_stdout_in_json_mode():
    """In json mode, print_message must not write anything to stdout."""
    formatter = OutputFormatter(format="json")
    output = _capture_stdout(formatter.print_message, "hello", "info")
    assert output == ""


def test_print_error_does_not_write_stdout():
    """print_error must never write to stdout regardless of format."""
    for fmt in ("text", "json", "csv", "stream-json"):
        formatter = OutputFormatter(format=fmt)
        output = _capture_stdout(formatter.print_error, "something went wrong")
        assert output == "", f"print_error wrote to stdout in {fmt!r} mode"
