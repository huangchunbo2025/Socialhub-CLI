"""File system sandbox for skill isolation.

This module provides file system access control for skills,
restricting read/write operations to authorized directories only.
"""

import builtins
import logging
from pathlib import Path
from typing import Any, Callable, Optional, Set, Union

from ..security import SecurityAuditLogger


class FileAccessDeniedError(PermissionError):
    """Raised when file access is denied by sandbox."""

    def __init__(self, skill_name: str, path: Path, operation: str):
        self.skill_name = skill_name
        self.path = path
        self.operation = operation
        super().__init__(
            f"Skill '{skill_name}' is not allowed to {operation}: {path}"
        )


class FileSystemSandbox:
    """File system sandbox for restricting skill file access.

    This sandbox intercepts file operations and ensures skills can only
    access files within their authorized directories.
    """

    # Default allowed directories relative to user home
    DEFAULT_ALLOWED_DIRS = [
        ".socialhub/skills/sandbox",  # Skill sandbox directory
        "Documents",  # User documents
        "Downloads",  # Downloads folder
    ]

    def __init__(
        self,
        skill_name: str,
        allowed_paths: Optional[Set[Path]] = None,
        allow_read: bool = True,
        allow_write: bool = False,
    ):
        """Initialize the file system sandbox.

        Args:
            skill_name: Name of the skill being sandboxed
            allowed_paths: Set of allowed paths (absolute)
            allow_read: Whether to allow file:read permission
            allow_write: Whether to allow file:write permission
        """
        self.skill_name = skill_name
        self.allow_read = allow_read
        self.allow_write = allow_write
        self._logger = logging.getLogger(__name__)
        self._audit_logger = SecurityAuditLogger()

        # Set up allowed paths
        self.allowed_paths: Set[Path] = set()

        # Skill's own sandbox directory (always allowed)
        self.sandbox_dir = (
            Path.home() / ".socialhub" / "skills" / "sandbox" / skill_name
        )
        self.sandbox_dir.mkdir(parents=True, exist_ok=True)
        self.allowed_paths.add(self.sandbox_dir)

        # Skill's installation directory (read-only)
        skill_install_dir = Path.home() / ".socialhub" / "skills" / "installed" / skill_name
        if skill_install_dir.exists():
            self.allowed_paths.add(skill_install_dir)

        # Add custom allowed paths
        if allowed_paths:
            self.allowed_paths.update(allowed_paths)

        # Add default allowed directories
        home = Path.home()
        for rel_dir in self.DEFAULT_ALLOWED_DIRS:
            dir_path = home / rel_dir
            if dir_path.exists():
                self.allowed_paths.add(dir_path)

        # Store original functions for restoration
        self._original_open: Optional[Callable] = None
        self._active = False

    def is_path_allowed(self, path: Union[str, Path], for_write: bool = False) -> bool:
        """Check if a path is allowed for access.

        Args:
            path: Path to check
            for_write: Whether this is a write operation

        Returns:
            bool: True if access is allowed
        """
        try:
            # Resolve to absolute path
            resolved = Path(path).resolve()

            # Check permission flags
            if for_write and not self.allow_write:
                return False

            if not for_write and not self.allow_read:
                return False

            # Check if path is within allowed directories
            for allowed in self.allowed_paths:
                try:
                    resolved.relative_to(allowed.resolve())
                    return True
                except ValueError:
                    continue

            return False

        except Exception:
            return False

    def _create_guarded_open(self) -> Callable:
        """Create a guarded version of the open function.

        Returns:
            Guarded open function
        """
        original_open = self._original_open or builtins.open
        sandbox = self

        def guarded_open(
            file: Union[str, Path, int],
            mode: str = "r",
            *args,
            **kwargs,
        ) -> Any:
            # Skip if file is a file descriptor (integer)
            if isinstance(file, int):
                return original_open(file, mode, *args, **kwargs)

            path = Path(file)
            is_write = any(m in mode for m in ["w", "a", "x", "+"])

            if not sandbox.is_path_allowed(path, for_write=is_write):
                operation = "write to" if is_write else "read"
                sandbox._audit_logger.log_security_violation(
                    sandbox.skill_name,
                    "file_access_denied",
                    f"Attempted to {operation}: {path}",
                )
                raise FileAccessDeniedError(sandbox.skill_name, path, operation)

            return original_open(file, mode, *args, **kwargs)

        return guarded_open

    def activate(self) -> None:
        """Activate the file system sandbox.

        Installs the guarded open function.
        """
        if self._active:
            return

        self._original_open = builtins.open
        builtins.open = self._create_guarded_open()
        self._active = True
        self._logger.debug(f"File system sandbox activated for {self.skill_name}")

    def deactivate(self) -> None:
        """Deactivate the file system sandbox.

        Restores the original open function.
        """
        if not self._active:
            return

        if self._original_open:
            builtins.open = self._original_open
            self._original_open = None

        self._active = False
        self._logger.debug(f"File system sandbox deactivated for {self.skill_name}")

    def __enter__(self):
        """Enter the sandbox context."""
        self.activate()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Exit the sandbox context."""
        self.deactivate()
        return False

    def add_allowed_path(self, path: Union[str, Path]) -> None:
        """Add a path to the allowed list.

        Args:
            path: Path to allow
        """
        self.allowed_paths.add(Path(path).resolve())

    def remove_allowed_path(self, path: Union[str, Path]) -> None:
        """Remove a path from the allowed list.

        Args:
            path: Path to remove
        """
        resolved = Path(path).resolve()
        self.allowed_paths.discard(resolved)

    def get_sandbox_path(self, relative_path: str = "") -> Path:
        """Get a path within the skill's sandbox directory.

        Args:
            relative_path: Relative path within sandbox

        Returns:
            Absolute path within sandbox
        """
        return self.sandbox_dir / relative_path

    def is_active(self) -> bool:
        """Check if the sandbox is currently active."""
        return self._active
