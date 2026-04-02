"""Input sanitizer — prevents prompt injection via control markers.

PRD AC-1: [PLAN_START] injected in user input must NOT trigger plan execution.
PRD AC-7: sanitize_user_input() is called in cli/main.py BEFORE call_ai_api().
No new dependencies — pure standard library (re, logging).
"""

import logging
import re

from rich.console import Console

logger = logging.getLogger(__name__)
_console = Console(stderr=True)

# Regex that matches all control markers recognised by parser.py:
#   [PLAN_START], [PLAN_END]
#   [SCHEDULE_TASK], [/SCHEDULE_TASK]
#   [STEP_…] — any token that starts with STEP_ inside brackets
_MARKER_RE = re.compile(
    r"\[(?:PLAN_START|PLAN_END|SCHEDULE_TASK|/SCHEDULE_TASK|STEP_[^\]]*)\]",
    re.IGNORECASE,
)


def sanitize_user_input(text: str) -> str:
    """Strip control markers from user input to prevent plan injection.

    If any marker is detected the raw input snippet (first 50 characters) is
    logged at WARNING level before the markers are removed.

    Args:
        text: Raw user input string.

    Returns:
        Text with all control markers removed.  Normal input is returned
        unchanged.
    """
    if not _MARKER_RE.search(text):
        return text

    logger.warning("Control marker detected in user input — stripping: %r", text[:50])
    _console.print("[yellow]Warning: control markers detected in input and were removed.[/yellow]")

    sanitized = _MARKER_RE.sub("", text)
    return sanitized


def validate_input_length(text: str, max_chars: int = 2000) -> tuple[bool, str]:
    """Validate that *text* does not exceed *max_chars* characters.

    Args:
        text: The string to validate.
        max_chars: Maximum allowed length (default 2000).

    Returns:
        A ``(is_valid, result_text)`` tuple.  When the input is within the
        limit ``is_valid`` is ``True`` and ``result_text`` is the original
        string.  When the input exceeds the limit ``is_valid`` is ``False``
        and ``result_text`` is the string truncated to *max_chars* characters.
    """
    if len(text) <= max_chars:
        return True, text
    return False, text[:max_chars]
