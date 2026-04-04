"""Prompt helpers for interactive credential entry."""

from __future__ import annotations

import os

import typer


def should_show_password(explicit: bool = False) -> bool:
    """Return whether password input should be visible.

    Visibility can be forced per-command with ``explicit=True`` or globally via
    ``SOCIALHUB_SHOW_PASSWORD=1|true|yes|on`` for terminals where hidden input
    is unreliable.
    """
    if explicit:
        return True
    env_value = os.environ.get("SOCIALHUB_SHOW_PASSWORD", "").strip().lower()
    return env_value in {"1", "true", "yes", "on"}


def prompt_password(*, explicit_visible: bool = False) -> str:
    """Prompt for a password, optionally showing the typed value."""
    show_password = should_show_password(explicit_visible)
    return typer.prompt("Password", hide_input=not show_password)
