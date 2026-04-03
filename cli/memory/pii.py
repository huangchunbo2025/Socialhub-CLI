"""Memory-specific PII scanning.

Independent implementation using the same regex patterns as cli/ai/trace.py
but kept in a separate module to avoid cross-module dependency on internal functions.

WARNING: This module is ONLY for sanitizing content before writing to memory files.
Do NOT use it for sanitizing user input sent to AI (that is cli/ai/sanitizer.py's job).
"""

import re

# ---------------------------------------------------------------------------
# PII patterns (same order as trace.py — order matters for correctness)
# 1. ID card must come before order numbers (both can be 18-digit strings)
# 2. Phone and email before order numbers
# ---------------------------------------------------------------------------

_PATTERNS: list[tuple[re.Pattern, str]] = [
    # Chinese national ID (17 digits + 1 digit or X)
    (re.compile(r"\b\d{17}[\dX]\b", re.IGNORECASE), "[ID_MASKED]"),
    # Chinese mobile (starts with 1, second digit 3-9, total 11 digits)
    (re.compile(r"\b1[3-9]\d{9}\b"), "[PHONE_MASKED]"),
    # Email addresses
    (re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+"), "[EMAIL_MASKED]"),
    # Order numbers (16+ digit numeric strings)
    (re.compile(r"\b\d{16,}\b"), "[ORDER_ID]"),
]

# Tokens that indicate PII was masked
_PII_TOKENS = {"[ID_MASKED]", "[PHONE_MASKED]", "[EMAIL_MASKED]", "[ORDER_ID]"}


# Cap input to prevent regex backtracking on pathological large strings
_MAX_PII_SCAN_CHARS = 10_000


def scan_and_mask(text: str) -> tuple[str, bool]:
    """Apply PII masking to text before writing to memory.

    Args:
        text: Raw text to scan (e.g., AI-generated insight conclusion)

    Returns:
        (masked_text, pii_found) — masked_text has PII replaced with tokens;
        pii_found is True if any pattern matched.
    """
    if not text:
        return "", False

    # Truncate to prevent regex catastrophic backtracking on pathological inputs
    masked = text[:_MAX_PII_SCAN_CHARS]
    for pattern, replacement in _PATTERNS:
        masked = pattern.sub(replacement, masked)

    pii_found = any(token in masked for token in _PII_TOKENS)
    return masked, pii_found
