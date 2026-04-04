"""Unified sandbox manager for skill isolation.

This module provides a unified interface for managing all sandbox
components (filesystem, network, execution) during skill execution.

SECURITY NOTE: This sandbox is a Python-level monkey-patch isolation layer,
NOT a process/container-level hard isolation boundary. It blocks known Python
APIs (filesystem, network, subprocess, ctypes) but cannot prevent escapes via
native extensions or interpreter-level exploits. See ADR-002 in docs.
"""

import logging
import threading
from pathlib import Path

from ..security import SecurityAuditLogger
from .execute import CommandExecutionDeniedError, ExecuteSandbox
from .filesystem import FileAccessDeniedError, FileSystemSandbox
from .network import NetworkAccessDeniedError, NetworkSandbox

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
        permissions: set[str],
        allowed_paths: set[Path] | None = None,
        allowed_hosts: set[str] | None = None,
        allowed_commands: set[str] | None = None,
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

        # ctypes originals for restore on deactivate
        self._ctypes_originals: dict | None = None

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

        self._logger.info("Activating sandbox for skill: %s", self.skill_name)
        self._audit_logger.log_permission_granted(
            self.skill_name,
            f"sandbox_activated:permissions={','.join(self.permissions)}",
            "system",
        )

        # Activate in order: execute -> network -> filesystem -> ctypes
        # This ensures lower-level guards are in place first
        self.execute_sandbox.activate()
        self.network_sandbox.activate()
        self.filesystem_sandbox.activate()
        self._activate_ctypes_blocking()

        self._active = True

    def deactivate(self) -> None:
        """Deactivate all sandbox components.

        Components are deactivated in reverse order of activation.
        """
        if not self._active:
            return

        self._logger.info("Deactivating sandbox for skill: %s", self.skill_name)

        # Deactivate in reverse order: ctypes -> filesystem -> network -> execute
        self._deactivate_ctypes_blocking()
        self.filesystem_sandbox.deactivate()
        self.network_sandbox.deactivate()
        self.execute_sandbox.deactivate()

        self._active = False

    def _activate_ctypes_blocking(self) -> None:
        """Block ctypes to prevent native-code escape from sandbox."""
        try:
            import ctypes
            import ctypes.util

            skill_name = self.skill_name

            self._ctypes_originals = {
                "CDLL": ctypes.CDLL,
                "cdll": ctypes.cdll,
                "find_library": ctypes.util.find_library,
            }

            def _blocked_cdll(*args, **kwargs):
                raise PermissionError(
                    f"Skill '{skill_name}' attempted to load a native library via ctypes. "
                    "Native code execution is not allowed in the sandbox."
                )

            def _blocked_find_library(*args, **kwargs):
                return None  # Pretend library doesn't exist

            ctypes.CDLL = _blocked_cdll
            ctypes.cdll = type(
                "BlockedCDLL",
                (),
                {
                    "LoadLibrary": staticmethod(_blocked_cdll),
                    "__getattr__": lambda s, n: _blocked_cdll(n),
                },
            )()
            ctypes.util.find_library = _blocked_find_library

            # Windows-specific: block WinDLL, windll, OleDLL, oledll, PyDLL
            for attr in ("WinDLL", "OleDLL", "PyDLL"):
                if hasattr(ctypes, attr):
                    self._ctypes_originals[attr] = getattr(ctypes, attr)
                    setattr(ctypes, attr, _blocked_cdll)
            for attr in ("windll", "oledll"):
                if hasattr(ctypes, attr):
                    self._ctypes_originals[attr] = getattr(ctypes, attr)
                    setattr(ctypes, attr, type(
                        f"Blocked_{attr}",
                        (),
                        {
                            "LoadLibrary": staticmethod(_blocked_cdll),
                            "__getattr__": lambda s, n: _blocked_cdll(n),
                        },
                    )())

            self._logger.debug("ctypes blocking activated for skill: %s", skill_name)
        except ImportError:
            pass  # ctypes not available — no patching needed

    def _deactivate_ctypes_blocking(self) -> None:
        """Restore original ctypes functions."""
        if self._ctypes_originals is None:
            return
        try:
            import ctypes
            import ctypes.util

            ctypes.CDLL = self._ctypes_originals["CDLL"]
            ctypes.cdll = self._ctypes_originals["cdll"]
            ctypes.util.find_library = self._ctypes_originals["find_library"]

            # Restore Windows-specific ctypes
            for attr in ("WinDLL", "OleDLL", "PyDLL", "windll", "oledll"):
                if attr in self._ctypes_originals:
                    setattr(ctypes, attr, self._ctypes_originals[attr])

            self._logger.debug("ctypes blocking deactivated for skill: %s", self.skill_name)
        except ImportError:
            pass
        finally:
            self._ctypes_originals = None

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
    permissions: set[str],
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
