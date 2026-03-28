"""Command validator — checks AI-generated commands before execution."""

import importlib
from typing import Optional

# Top-level commands mirrored from main.py registrations.
# Kept in sync via the module map below (no separate VALID_COMMANDS import
# to avoid circular dependencies).
_MODULE_MAP: dict[str, str] = {
    "analytics": "cli.commands.analytics",
    "members":   "cli.commands.members",
    "customers": "cli.commands.customers",
    "segments":  "cli.commands.segments",
    "tags":      "cli.commands.tags",
    "campaigns": "cli.commands.campaigns",
    "coupons":   "cli.commands.coupons",
    "points":    "cli.commands.points",
    "messages":  "cli.commands.messages",
    "config":    "cli.commands.config_cmd",
    "ai":        "cli.commands.ai",
    "skills":    "cli.commands.skills",
    "skill":     "cli.commands.skills",
    "mcp":       "cli.commands.mcp",
    "schema":    "cli.commands.schema",
    "heartbeat": "cli.commands.heartbeat",
    "history":   "cli.commands.history",
    "workflow":  "cli.commands.workflow",
}

# Lazily populated on first validation call
# cmd_name → None (leaf) | dict (nested group with same structure)
_CMD_TREE: Optional[dict[str, dict]] = None


def _build_cmd_tree_for_app(app) -> dict:
    """Recursively build a command tree for a Typer app.

    Leaf commands map to None.
    Sub-groups map to a nested dict of their own commands.
    """
    tree: dict = {}

    for cmd_info in getattr(app, "registered_commands", []):
        name = cmd_info.name
        if not name and cmd_info.callback:
            name = cmd_info.callback.__name__.replace("_", "-")
        if name:
            tree[name] = None  # leaf

    for grp_info in getattr(app, "registered_groups", []):
        if grp_info.name:
            sub_app = getattr(grp_info, "typer_instance", None)
            tree[grp_info.name] = _build_cmd_tree_for_app(sub_app) if sub_app else {}

    return tree


def _build_full_cmd_tree() -> dict[str, dict]:
    """Build the full command tree by lazily importing every top-level module."""
    tree: dict[str, dict] = {}
    seen: dict[str, dict] = {}

    for cmd, module_path in _MODULE_MAP.items():
        if module_path in seen:
            tree[cmd] = seen[module_path]
            continue
        try:
            mod = importlib.import_module(module_path)
            subtree = _build_cmd_tree_for_app(mod.app) if hasattr(mod, "app") else {}
            tree[cmd] = subtree
            seen[module_path] = subtree
        except Exception:
            tree[cmd] = {}

    return tree


def _get_cmd_tree() -> dict[str, dict]:
    global _CMD_TREE
    if _CMD_TREE is None:
        _CMD_TREE = _build_full_cmd_tree()
    return _CMD_TREE


def _check_tokens(tree: Optional[dict], tokens: list[str], path: str) -> tuple[bool, str]:
    """Recursively validate remaining tokens against the command tree.

    tokens: non-flag words remaining after the current level.
    path:   human-readable command path so far (for error messages).
    """
    if not tokens or tokens[0].startswith("-"):
        return True, ""

    token = tokens[0]

    if tree is None:
        # Leaf node — no sub-commands expected; remaining tokens are args/flags.
        return True, ""

    if not tree:
        # Group exists but we couldn't introspect it — skip validation.
        return True, ""

    if token not in tree:
        valid = sorted(tree.keys())
        return False, (
            f"Unknown sub-command '{path} {token}'. "
            f"Valid: {', '.join(valid)}"
        )

    return _check_tokens(tree[token], tokens[1:], f"{path} {token}")


def validate_command(cmd: str) -> tuple[bool, str]:
    """Validate an AI-generated 'sh ...' command.

    Returns (is_valid, reason). Checks:
      1. Starts with 'sh '
      2. Top-level command is registered
      3. Every subsequent non-flag token exists in the Typer command tree
         (handles arbitrary nesting depth, e.g. sh coupons rules list)

    Options/flags (starting with '-') stop traversal — Typer itself
    rejects unrecognised flags at runtime.
    """
    if not cmd.startswith("sh "):
        return False, "Command must start with 'sh '"

    parts = cmd[3:].strip().split()
    if not parts:
        return False, "Empty command after 'sh'"

    top_cmd = parts[0]

    if top_cmd.startswith("-"):
        return True, ""

    if top_cmd not in _MODULE_MAP:
        valid = sorted(_MODULE_MAP.keys())
        return False, f"Unknown command '{top_cmd}'. Valid top-level commands: {', '.join(valid)}"

    # Strip flags from the remaining tokens before walking the tree
    remaining = [t for t in parts[1:] if not t.startswith("-")]
    tree = _get_cmd_tree()
    return _check_tokens(tree.get(top_cmd), remaining, top_cmd)
