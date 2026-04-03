"""OutputFormatter — unified output format management with strict stdout/stderr separation.

Design constraints (from PRD §4.1):
- json mode: stdout contains exactly one complete JSON line, no ANSI escape codes
- csv mode: first line is column headers, values UTF-8, no ANSI escape codes
- stream-json mode: each line is a self-contained valid JSON object (NDJSON)
- text mode: existing Rich rendering unchanged (backward compatible)
"""

import csv
import json
import sys
from datetime import datetime, timezone
from typing import Any

from rich import box
from rich.console import Console
from rich.table import Table

# stderr-only console: progress and diagnostic messages go here, never pollute stdout
_stderr_console = Console(stderr=True)

# stdout-only console: text mode Rich rendering goes here
_stdout_console = Console()

VALID_FORMATS = {"text", "json", "stream-json", "csv"}

_LEVEL_STYLES: dict[str, str] = {
    "info": "[blue][INFO][/blue]",
    "warning": "[yellow][WARN][/yellow]",
    "error": "[red][ERROR][/red]",
    "success": "[green][OK][/green]",
}


class OutputFormatter:
    """Context-aware output formatter supporting text / json / csv / stream-json modes.

    Usage in command handlers::

        formatter = OutputFormatter.from_context(ctx)
        formatter.print_table(rows, title="Overview")
    """

    def __init__(self, format: str = "text", console: Console = None) -> None:  # noqa: A002
        """Initialise formatter.

        Args:
            format: One of ``"text"``, ``"json"``, ``"csv"``, ``"stream-json"``.
                    Unknown values silently fall back to ``"text"``.
            console: Override the Rich Console instance.  When *None*, text mode
                     uses a stdout console; all other modes use a stderr console so
                     that human-readable output never contaminates the machine-
                     readable stdout stream.
        """
        self.fmt = format if format in VALID_FORMATS else "text"
        if console is not None:
            self.console = console
        else:
            # Non-text modes: Rich output must only go to stderr
            self.console = _stdout_console if self.fmt == "text" else _stderr_console

    # ------------------------------------------------------------------
    # Factory helpers
    # ------------------------------------------------------------------

    @classmethod
    def from_context(cls, ctx: Any) -> "OutputFormatter":
        """Construct from a Typer Context object.

        Reads ``ctx.find_root().obj["output_format"]``.  Falls back to
        ``"text"`` when the context object is absent or the key is missing.
        """
        try:
            obj = ctx.find_root().obj or {}
        except AttributeError:
            obj = {}
        fmt = obj.get("output_format", "text")
        return cls(format=fmt)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def print_table(self, data: list[dict], title: str = "") -> None:
        """Output tabular data.

        - text: Rich table rendered to stdout.
        - json: Single-line JSON array written to stdout.
        - csv: CSV rows (with header) written to stdout.
        - stream-json: One NDJSON ``{"type": "data", "data": {...}}`` line per
          row, preceded by a ``start`` event and followed by an ``end`` event.
        """
        if self.fmt == "text":
            self._text_table(data, title)

        elif self.fmt == "json":
            print(json.dumps(data, ensure_ascii=False), file=sys.stdout)
            sys.stdout.flush()

        elif self.fmt == "csv":
            if not data:
                return
            cols = list(data[0].keys())
            writer = csv.DictWriter(
                sys.stdout,
                fieldnames=cols,
                quoting=csv.QUOTE_MINIMAL,
                extrasaction="ignore",
                lineterminator="\n",
            )
            writer.writeheader()
            writer.writerows(data)
            sys.stdout.flush()

        elif self.fmt == "stream-json":
            now = datetime.now(timezone.utc).isoformat()
            self._write_ndjson({"type": "start", "timestamp": now})
            for row in data:
                self._write_ndjson({"type": "data", "data": row})
            self._write_ndjson({"type": "end", "metadata": {"record_count": len(data)}})

    def print_record(self, data: dict, title: str = "") -> None:
        """Output a single record.

        - text: Two-column key/value Rich table rendered to stdout.
        - json: Single-line JSON object written to stdout.
        - csv: One-row CSV (with header) written to stdout.
        - stream-json: A single ``{"type": "data", "data": {...}}`` NDJSON line.
        """
        if self.fmt == "text":
            self._text_record(data, title)

        elif self.fmt == "json":
            print(json.dumps(data, ensure_ascii=False), file=sys.stdout)
            sys.stdout.flush()

        elif self.fmt == "csv":
            if not data:
                return
            cols = list(data.keys())
            writer = csv.DictWriter(
                sys.stdout,
                fieldnames=cols,
                quoting=csv.QUOTE_MINIMAL,
                extrasaction="ignore",
                lineterminator="\n",
            )
            writer.writeheader()
            writer.writerow(data)
            sys.stdout.flush()

        elif self.fmt == "stream-json":
            now = datetime.now(timezone.utc).isoformat()
            self._write_ndjson({"type": "start", "timestamp": now})
            self._write_ndjson({"type": "data", "data": data})
            self._write_ndjson({"type": "end", "metadata": {"record_count": 1}})

    def print_message(self, message: str, level: str = "info") -> None:
        """Output a human-readable message.

        In *text* mode the message is printed to stdout via Rich with colour
        coding.  In all other modes the message is written to stderr so it
        never contaminates the machine-readable stdout stream.

        Args:
            message: The message string.
            level: One of ``"info"`` (default), ``"warning"``, ``"error"``,
                   ``"success"``.  Controls colour in text mode.
        """
        prefix = _LEVEL_STYLES.get(level, "[blue][INFO][/blue]")

        if self.fmt == "text":
            self.console.print(f"{prefix} {message}")
        else:
            # Non-text mode: always write to stderr to keep stdout clean
            _stderr_console.print(f"{prefix} {message}")

    def print_error(self, message: str) -> None:
        """Output an error message.

        Always writes to stderr regardless of output format so that error
        messages never pollute machine-readable stdout streams.
        """
        _stderr_console.print(f"[red][ERROR][/red] {message}")

    def emit_stream_event(self, event_type: str, data: dict) -> None:
        """Emit a single NDJSON event line to stdout.

        Only meaningful in ``stream-json`` mode; in all other modes this is a
        no-op.  The line format is::

            {"type": "<event_type>", "data": {...}}

        Args:
            event_type: Arbitrary event type string (e.g. ``"progress"``,
                        ``"heartbeat"``).
            data: Payload dict merged as the ``"data"`` key.
        """
        if self.fmt == "stream-json":
            self._write_ndjson({"type": event_type, "data": data})

    # ------------------------------------------------------------------
    # Convenience predicates
    # ------------------------------------------------------------------

    def is_text_mode(self) -> bool:
        """Return ``True`` when the formatter is in text (Rich) mode."""
        return self.fmt == "text"

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _text_table(self, data: list[dict], title: str) -> None:
        """Render a list of dicts as a Rich table to stdout."""
        if not data:
            self.console.print("[yellow]No data to display[/yellow]")
            return
        cols = list(data[0].keys())
        headers = [c.replace("_", " ").title() for c in cols]
        tbl = Table(
            title=title or None,
            show_header=True,
            show_lines=False,
            box=box.ROUNDED,
            header_style="bold cyan",
            title_style="bold magenta",
        )
        for h in headers:
            tbl.add_column(h)
        for row in data:
            tbl.add_row(*[self._format_cell(row.get(c)) for c in cols])
        self.console.print(tbl)

    def _text_record(self, data: dict, title: str) -> None:
        """Render a single dict as a two-column key/value Rich table to stdout."""
        tbl = Table(
            title=title or None,
            show_header=True,
            show_lines=False,
            box=box.ROUNDED,
            header_style="bold cyan",
            title_style="bold magenta",
        )
        tbl.add_column("Field")
        tbl.add_column("Value")
        for key, value in data.items():
            tbl.add_row(key.replace("_", " ").title(), self._format_cell(value))
        self.console.print(tbl)

    @staticmethod
    def _format_cell(value: Any) -> str:
        """Convert a cell value to a display string."""
        if value is None:
            return "-"
        if isinstance(value, float):
            return f"{value:,.2f}"
        if isinstance(value, int):
            return f"{value:,}"
        if isinstance(value, list):
            return ", ".join(str(v) for v in value)
        return str(value)

    def _write_ndjson(self, obj: dict) -> None:
        """Write one NDJSON line to stdout and flush immediately."""
        print(json.dumps(obj, ensure_ascii=False), file=sys.stdout)
        sys.stdout.flush()


# ---------------------------------------------------------------------------
# Module-level factory helper
# ---------------------------------------------------------------------------


def get_formatter(ctx_obj: dict | None = None) -> OutputFormatter:
    """Construct an OutputFormatter from a Typer context *obj* dict.

    This is a convenience wrapper for callers that already have the context
    ``obj`` dict (e.g. ``ctx.obj``) rather than the full ``typer.Context``.

    Args:
        ctx_obj: The ``ctx.obj`` dictionary, or ``None``.  When ``None`` or
                 when the ``"output_format"`` key is absent, defaults to
                 ``"text"`` mode.

    Returns:
        An :class:`OutputFormatter` instance.
    """
    if not ctx_obj:
        return OutputFormatter(format="text")
    fmt = ctx_obj.get("output_format", "text")
    return OutputFormatter(format=fmt)
