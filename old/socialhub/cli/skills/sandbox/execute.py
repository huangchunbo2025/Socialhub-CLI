"""Command execution sandbox for skill isolation.

This module provides command execution control for skills,
restricting which external commands can be executed.
"""

import logging
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable, List, Optional, Set, Union

from ..security import SecurityAuditLogger


class CommandExecutionDeniedError(PermissionError):
    """Raised when command execution is denied by sandbox."""

    def __init__(self, skill_name: str, command: str, reason: str = ""):
        self.skill_name = skill_name
        self.command = command
        self.reason = reason
        message = f"Skill '{skill_name}' is not allowed to execute: {command}"
        if reason:
            message += f" ({reason})"
        super().__init__(message)


class ExecuteSandbox:
    """Command execution sandbox for restricting skill command execution.

    This sandbox intercepts subprocess calls and ensures skills can only
    execute authorized commands.
    """

    # Dangerous commands that are always blocked
    DANGEROUS_COMMANDS = {
        # File destruction
        "rm", "rmdir", "del", "rd", "erase",
        # Disk operations
        "format", "fdisk", "mkfs", "dd",
        # System control
        "shutdown", "reboot", "halt", "poweroff", "init",
        # Permission changes
        "chmod", "chown", "chgrp", "icacls", "cacls",
        # Process control
        "kill", "killall", "pkill", "taskkill",
        # Privilege escalation
        "sudo", "su", "runas", "doas",
        # Network configuration
        "iptables", "ip6tables", "netsh", "route",
        # Package management (potential for damage)
        "apt", "yum", "dnf", "pacman", "brew",
        # Registry (Windows)
        "reg", "regedit",
    }

    # Safe commands that are always allowed
    SAFE_COMMANDS = {
        # Basic utilities
        "echo", "cat", "type", "more", "less",
        "head", "tail", "wc", "sort", "uniq",
        "grep", "find", "where", "which",
        # File info
        "ls", "dir", "stat", "file",
        # Date/time
        "date", "time",
        # Text processing
        "awk", "sed", "cut", "tr",
        # Compression (read operations)
        "gzip", "gunzip", "tar", "zip", "unzip",
    }

    def __init__(
        self,
        skill_name: str,
        allow_execute: bool = False,
        allowed_commands: Optional[Set[str]] = None,
        blocked_commands: Optional[Set[str]] = None,
    ):
        """Initialize the execution sandbox.

        Args:
            skill_name: Name of the skill being sandboxed
            allow_execute: Whether to allow any command execution
            allowed_commands: Set of explicitly allowed commands
            blocked_commands: Set of explicitly blocked commands
        """
        self.skill_name = skill_name
        self.allow_execute = allow_execute
        self.allowed_commands = allowed_commands or set()
        self.blocked_commands = blocked_commands or set()
        self._logger = logging.getLogger(__name__)
        self._audit_logger = SecurityAuditLogger()

        # Store original functions
        self._original_run: Optional[Callable] = None
        self._original_popen: Optional[type] = None
        self._original_call: Optional[Callable] = None
        self._original_check_call: Optional[Callable] = None
        self._original_check_output: Optional[Callable] = None
        self._original_system: Optional[Callable] = None
        self._active = False

    def _extract_command_name(self, args: Union[str, List[str]]) -> str:
        """Extract the command name from arguments.

        Args:
            args: Command arguments (string or list)

        Returns:
            Command name
        """
        if isinstance(args, str):
            # Shell command string - extract first word
            parts = args.split()
            if not parts:
                return ""
            cmd = parts[0]
        else:
            # List of arguments
            if not args:
                return ""
            cmd = args[0]

        # Get just the command name without path
        return Path(cmd).stem.lower()

    def is_command_allowed(self, args: Union[str, List[str]]) -> tuple[bool, str]:
        """Check if a command is allowed to execute.

        Args:
            args: Command arguments

        Returns:
            Tuple of (allowed, reason)
        """
        # If execution is completely disabled
        if not self.allow_execute:
            return False, "command execution is disabled"

        cmd_name = self._extract_command_name(args)

        if not cmd_name:
            return False, "empty command"

        # Check explicit blocklist first
        if cmd_name in self.blocked_commands:
            return False, "command is blocked"

        # Check dangerous commands
        if cmd_name in self.DANGEROUS_COMMANDS:
            return False, "command is dangerous"

        # Check explicit allowlist
        if self.allowed_commands:
            if cmd_name in self.allowed_commands:
                return True, ""
            if cmd_name in self.SAFE_COMMANDS:
                return True, ""
            return False, "command is not in allowlist"

        # If no allowlist, allow safe commands and non-dangerous commands
        return True, ""

    def _create_guarded_run(self) -> Callable:
        """Create a guarded subprocess.run function.

        Returns:
            Guarded run function
        """
        original_run = self._original_run or subprocess.run
        sandbox = self

        def guarded_run(
            args: Union[str, List[str]],
            *a,
            **kwargs,
        ) -> subprocess.CompletedProcess:
            allowed, reason = sandbox.is_command_allowed(args)
            if not allowed:
                cmd_name = sandbox._extract_command_name(args)
                sandbox._audit_logger.log_security_violation(
                    sandbox.skill_name,
                    "command_execution_denied",
                    f"Attempted to execute: {cmd_name} ({reason})",
                )
                raise CommandExecutionDeniedError(sandbox.skill_name, cmd_name, reason)

            return original_run(args, *a, **kwargs)

        return guarded_run

    def _create_guarded_popen(self) -> type:
        """Create a guarded subprocess.Popen class.

        Returns:
            Guarded Popen class
        """
        original_popen = self._original_popen or subprocess.Popen
        sandbox = self

        class GuardedPopen(original_popen):
            """Popen class with execution guards."""

            def __init__(self, args, *a, **kwargs):
                allowed, reason = sandbox.is_command_allowed(args)
                if not allowed:
                    cmd_name = sandbox._extract_command_name(args)
                    sandbox._audit_logger.log_security_violation(
                        sandbox.skill_name,
                        "command_execution_denied",
                        f"Attempted to execute: {cmd_name} ({reason})",
                    )
                    raise CommandExecutionDeniedError(
                        sandbox.skill_name, cmd_name, reason
                    )

                super().__init__(args, *a, **kwargs)

        return GuardedPopen

    def _create_guarded_system(self) -> Callable:
        """Create a guarded os.system function.

        Returns:
            Guarded system function
        """
        original_system = self._original_system or os.system
        sandbox = self

        def guarded_system(command: str) -> int:
            allowed, reason = sandbox.is_command_allowed(command)
            if not allowed:
                cmd_name = sandbox._extract_command_name(command)
                sandbox._audit_logger.log_security_violation(
                    sandbox.skill_name,
                    "command_execution_denied",
                    f"Attempted to execute via os.system: {cmd_name} ({reason})",
                )
                raise CommandExecutionDeniedError(sandbox.skill_name, cmd_name, reason)

            return original_system(command)

        return guarded_system

    def activate(self) -> None:
        """Activate the execution sandbox.

        Installs guarded subprocess functions.
        """
        if self._active:
            return

        # Store originals
        self._original_run = subprocess.run
        self._original_popen = subprocess.Popen
        self._original_call = subprocess.call
        self._original_check_call = subprocess.check_call
        self._original_check_output = subprocess.check_output
        self._original_system = os.system

        # Install guards
        subprocess.run = self._create_guarded_run()
        subprocess.Popen = self._create_guarded_popen()
        subprocess.call = self._create_guarded_run()  # Same signature
        subprocess.check_call = self._create_guarded_run()
        subprocess.check_output = self._create_guarded_run()
        os.system = self._create_guarded_system()

        self._active = True
        self._logger.debug(f"Execution sandbox activated for {self.skill_name}")

    def deactivate(self) -> None:
        """Deactivate the execution sandbox.

        Restores original subprocess functions.
        """
        if not self._active:
            return

        # Restore originals
        if self._original_run:
            subprocess.run = self._original_run
        if self._original_popen:
            subprocess.Popen = self._original_popen
        if self._original_call:
            subprocess.call = self._original_call
        if self._original_check_call:
            subprocess.check_call = self._original_check_call
        if self._original_check_output:
            subprocess.check_output = self._original_check_output
        if self._original_system:
            os.system = self._original_system

        # Clear references
        self._original_run = None
        self._original_popen = None
        self._original_call = None
        self._original_check_call = None
        self._original_check_output = None
        self._original_system = None

        self._active = False
        self._logger.debug(f"Execution sandbox deactivated for {self.skill_name}")

    def __enter__(self):
        """Enter the sandbox context."""
        self.activate()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Exit the sandbox context."""
        self.deactivate()
        return False

    def add_allowed_command(self, command: str) -> None:
        """Add a command to the allowed list.

        Args:
            command: Command name to allow
        """
        self.allowed_commands.add(command.lower())

    def add_blocked_command(self, command: str) -> None:
        """Add a command to the blocked list.

        Args:
            command: Command name to block
        """
        self.blocked_commands.add(command.lower())

    def is_active(self) -> bool:
        """Check if the sandbox is currently active."""
        return self._active
