"""Unified sandbox manager for skill isolation.

This module provides a unified interface for managing all sandbox
components (filesystem, network, execution) during skill execution.
"""

import logging
import threading
from pathlib import Path
from typing import Optional, Set

from ..security import SecurityAuditLogger
from .filesystem import FileSystemSandbox, FileAccessDeniedError
from .network import NetworkSandbox, NetworkAccessDeniedError
from .execute import ExecuteSandbox, CommandExecutionDeniedError

# Global serialization lock: monkey-patch sandboxes are non-reentrant because they
# overwrite process-global symbols (socket.socket, builtins.open, etc.). Concurrent
# activation by two threads would corrupt each other's saved originals.
# All SandboxManager.__enter__/__exit__ pairs acquire/release this lock so that at
# most one sandbox is active at any time.  Combined with _HANDLER_SEMAPHORE(50) in
# mcp_server/server.py this serializes skill executions without causing deadlocks.
_GLOBAL_SANDBOX_LOCK = threading.Lock()


class SandboxViolationError(PermissionError):
    """Base class for sandbox violation errors."""

    def __init__(self, skill_name: str, violation_type: str, details: str):
        self.skill_name = skill_name
        self.violation_type = violation_type
        self.details = details
        super().__init__(
            f"Sandbox violation by '{skill_name}': {violation_type} - {details}"
        )


class SandboxManager:
    """Unified sandbox manager for skill isolation.

    This class coordinates all sandbox components and provides a single
    context manager interface for skill execution sandboxing.
    """

    # Permission to sandbox mapping
    PERMISSION_MAP = {
        "file:read": ("filesystem", "allow_read"),
        "file:write": ("filesystem", "allow_write"),
        "network:local": ("network", "allow_local"),
        "network:internet": ("network", "allow_internet"),
        "execute": ("execute", "allow_execute"),
    }

    def __init__(
        self,
        skill_name: str,
        permissions: Set[str],
        allowed_paths: Optional[Set[Path]] = None,
        allowed_hosts: Optional[Set[str]] = None,
        allowed_commands: Optional[Set[str]] = None,
    ):
        """Initialize the sandbox manager.

        Args:
            skill_name: Name of the skill being sandboxed
            permissions: Set of granted permission strings
            allowed_paths: Additional allowed file paths
            allowed_hosts: Additional allowed network hosts
            allowed_commands: Additional allowed commands
        """
        self.skill_name = skill_name
        self.permissions = permissions
        self._logger = logging.getLogger(__name__)
        self._audit_logger = SecurityAuditLogger()
        self._active = False

        # Parse permissions
        allow_file_read = "file:read" in permissions
        allow_file_write = "file:write" in permissions
        allow_network_local = "network:local" in permissions
        allow_network_internet = "network:internet" in permissions
        allow_execute = "execute" in permissions

        # Initialize sandbox components
        self.filesystem_sandbox = FileSystemSandbox(
            skill_name=skill_name,
            allowed_paths=allowed_paths,
            allow_read=allow_file_read,
            allow_write=allow_file_write,
        )

        self.network_sandbox = NetworkSandbox(
            skill_name=skill_name,
            allow_local=allow_network_local,
            allow_internet=allow_network_internet,
            allowed_hosts=allowed_hosts,
        )

        self.execute_sandbox = ExecuteSandbox(
            skill_name=skill_name,
            allow_execute=allow_execute,
            allowed_commands=allowed_commands,
        )

    def activate(self) -> None:
        """Activate all sandbox components.

        Note: Sandboxes are activated in a specific order to ensure
        proper isolation. They are deactivated in reverse order.
        """
        if self._active:
            return

        self._logger.info(f"Activating sandbox for skill: {self.skill_name}")
        self._audit_logger.log_permission_granted(
            self.skill_name,
            f"sandbox_activated:permissions={','.join(self.permissions)}",
            "system",
        )

        # Activate in order: execute -> network -> filesystem
        # This ensures lower-level guards are in place first
        self.execute_sandbox.activate()
        self.network_sandbox.activate()
        self.filesystem_sandbox.activate()

        self._active = True

    def deactivate(self) -> None:
        """Deactivate all sandbox components.

        Components are deactivated in reverse order of activation.
        """
        if not self._active:
            return

        self._logger.info(f"Deactivating sandbox for skill: {self.skill_name}")

        # Deactivate in reverse order: filesystem -> network -> execute
        self.filesystem_sandbox.deactivate()
        self.network_sandbox.deactivate()
        self.execute_sandbox.deactivate()

        self._active = False

    def __enter__(self):
        """Enter the sandbox context.

        Acquires the global sandbox lock first to prevent concurrent monkey-patch
        races between two simultaneous skill executions.
        """
        _GLOBAL_SANDBOX_LOCK.acquire()
        try:
            self.activate()
        except Exception:
            _GLOBAL_SANDBOX_LOCK.release()
            raise
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Exit the sandbox context.

        Deactivates sandboxes and releases the global lock regardless of outcome.
        """
        try:
            self.deactivate()

            # Log sandbox violations
            if exc_type is not None:
                if issubclass(exc_type, (FileAccessDeniedError, NetworkAccessDeniedError,
                                         CommandExecutionDeniedError)):
                    self._audit_logger.log_security_violation(
                        self.skill_name,
                        exc_type.__name__,
                        str(exc_val),
                    )
        finally:
            _GLOBAL_SANDBOX_LOCK.release()

        return False

    def is_active(self) -> bool:
        """Check if the sandbox is currently active."""
        return self._active

    def get_sandbox_dir(self) -> Path:
        """Get the skill's sandbox directory.

        Returns:
            Path to the sandbox directory
        """
        return self.filesystem_sandbox.sandbox_dir

    def add_allowed_path(self, path: Path) -> None:
        """Add a path to the filesystem allowlist.

        Args:
            path: Path to allow
        """
        self.filesystem_sandbox.add_allowed_path(path)

    def add_allowed_host(self, host: str) -> None:
        """Add a host to the network allowlist.

        Args:
            host: Hostname or IP to allow
        """
        self.network_sandbox.add_allowed_host(host)

    def add_allowed_command(self, command: str) -> None:
        """Add a command to the execution allowlist.

        Args:
            command: Command name to allow
        """
        self.execute_sandbox.add_allowed_command(command)

    def get_status(self) -> dict:
        """Get the current sandbox status.

        Returns:
            Dict with sandbox component status
        """
        return {
            "skill_name": self.skill_name,
            "active": self._active,
            "permissions": list(self.permissions),
            "components": {
                "filesystem": {
                    "active": self.filesystem_sandbox.is_active(),
                    "allow_read": self.filesystem_sandbox.allow_read,
                    "allow_write": self.filesystem_sandbox.allow_write,
                    "allowed_paths": [
                        str(p) for p in self.filesystem_sandbox.allowed_paths
                    ],
                },
                "network": {
                    "active": self.network_sandbox.is_active(),
                    "allow_local": self.network_sandbox.allow_local,
                    "allow_internet": self.network_sandbox.allow_internet,
                    "allowed_hosts": list(self.network_sandbox.allowed_hosts),
                },
                "execute": {
                    "active": self.execute_sandbox.is_active(),
                    "allow_execute": self.execute_sandbox.allow_execute,
                    "allowed_commands": list(self.execute_sandbox.allowed_commands),
                },
            },
        }


def create_sandbox_from_permissions(
    skill_name: str,
    permissions: Set[str],
) -> SandboxManager:
    """Create a sandbox manager from a set of permissions.

    This is a convenience function that creates a properly configured
    sandbox manager based on the granted permissions.

    Args:
        skill_name: Name of the skill
        permissions: Set of granted permission strings

    Returns:
        Configured SandboxManager instance
    """
    return SandboxManager(skill_name=skill_name, permissions=permissions)
