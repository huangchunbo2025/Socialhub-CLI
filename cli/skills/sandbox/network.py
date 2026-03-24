"""Network sandbox for skill isolation.

This module provides network access control for skills,
restricting connections to authorized hosts and ports.
"""

import logging
import socket
from typing import Any, Callable, Optional, Set, Tuple
from urllib.parse import urlparse

from ..security import SecurityAuditLogger


class NetworkAccessDeniedError(PermissionError):
    """Raised when network access is denied by sandbox."""

    def __init__(self, skill_name: str, host: str, port: int):
        self.skill_name = skill_name
        self.host = host
        self.port = port
        super().__init__(
            f"Skill '{skill_name}' is not allowed to connect to: {host}:{port}"
        )


class NetworkSandbox:
    """Network sandbox for restricting skill network access.

    This sandbox intercepts socket connections and ensures skills can only
    connect to authorized hosts.
    """

    # Local addresses
    LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1", "0.0.0.0"}

    # Local network prefixes
    LOCAL_PREFIXES = ("192.168.", "10.", "172.16.", "172.17.", "172.18.",
                      "172.19.", "172.20.", "172.21.", "172.22.", "172.23.",
                      "172.24.", "172.25.", "172.26.", "172.27.", "172.28.",
                      "172.29.", "172.30.", "172.31.")

    def __init__(
        self,
        skill_name: str,
        allow_local: bool = False,
        allow_internet: bool = False,
        allowed_hosts: Optional[Set[str]] = None,
        allowed_ports: Optional[Set[int]] = None,
    ):
        """Initialize the network sandbox.

        Args:
            skill_name: Name of the skill being sandboxed
            allow_local: Whether to allow local network connections
            allow_internet: Whether to allow internet connections
            allowed_hosts: Set of allowed hostnames/IPs
            allowed_ports: Set of allowed ports (None = all ports)
        """
        self.skill_name = skill_name
        self.allow_local = allow_local
        self.allow_internet = allow_internet
        self.allowed_hosts = allowed_hosts or set()
        self.allowed_ports = allowed_ports
        self._logger = logging.getLogger(__name__)
        self._audit_logger = SecurityAuditLogger()

        # Store original socket class
        self._original_socket: Optional[type] = None
        self._active = False

    def is_local_address(self, host: str) -> bool:
        """Check if an address is local.

        Args:
            host: Hostname or IP address

        Returns:
            bool: True if the address is local
        """
        if host in self.LOCAL_HOSTS:
            return True

        if host.startswith(self.LOCAL_PREFIXES):
            return True

        # Check for IPv6 local addresses
        if host.startswith("fe80:") or host.startswith("fc00:"):
            return True

        return False

    def is_connection_allowed(self, host: str, port: int) -> bool:
        """Check if a connection is allowed.

        Args:
            host: Target hostname/IP
            port: Target port

        Returns:
            bool: True if the connection is allowed
        """
        # Check port restrictions
        if self.allowed_ports is not None and port not in self.allowed_ports:
            return False

        # Check explicit allowlist
        if host in self.allowed_hosts:
            return True

        # Check local connections
        if self.is_local_address(host):
            return self.allow_local

        # Check internet connections
        return self.allow_internet

    def _create_guarded_socket(self) -> type:
        """Create a guarded socket class.

        Returns:
            Guarded socket class
        """
        original_socket = self._original_socket or socket.socket
        sandbox = self

        class GuardedSocket(original_socket):
            """Socket class with connection guards."""

            def connect(self, address: Tuple[str, int]) -> None:
                """Guarded connect method."""
                try:
                    host = address[0]
                    port = address[1] if len(address) > 1 else 0
                except (IndexError, TypeError):
                    host = str(address)
                    port = 0

                if not sandbox.is_connection_allowed(host, port):
                    sandbox._audit_logger.log_security_violation(
                        sandbox.skill_name,
                        "network_access_denied",
                        f"Attempted connection to: {host}:{port}",
                    )
                    raise NetworkAccessDeniedError(sandbox.skill_name, host, port)

                return super().connect(address)

            def connect_ex(self, address: Tuple[str, int]) -> int:
                """Guarded connect_ex method."""
                try:
                    host = address[0]
                    port = address[1] if len(address) > 1 else 0
                except (IndexError, TypeError):
                    host = str(address)
                    port = 0

                if not sandbox.is_connection_allowed(host, port):
                    sandbox._audit_logger.log_security_violation(
                        sandbox.skill_name,
                        "network_access_denied",
                        f"Attempted connection to: {host}:{port}",
                    )
                    raise NetworkAccessDeniedError(sandbox.skill_name, host, port)

                return super().connect_ex(address)

        return GuardedSocket

    def activate(self) -> None:
        """Activate the network sandbox.

        Installs the guarded socket class.
        """
        if self._active:
            return

        self._original_socket = socket.socket
        socket.socket = self._create_guarded_socket()
        self._active = True
        self._logger.debug(f"Network sandbox activated for {self.skill_name}")

    def deactivate(self) -> None:
        """Deactivate the network sandbox.

        Restores the original socket class.
        """
        if not self._active:
            return

        if self._original_socket:
            socket.socket = self._original_socket
            self._original_socket = None

        self._active = False
        self._logger.debug(f"Network sandbox deactivated for {self.skill_name}")

    def __enter__(self):
        """Enter the sandbox context."""
        self.activate()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Exit the sandbox context."""
        self.deactivate()
        return False

    def add_allowed_host(self, host: str) -> None:
        """Add a host to the allowed list.

        Args:
            host: Hostname or IP to allow
        """
        self.allowed_hosts.add(host)

    def remove_allowed_host(self, host: str) -> None:
        """Remove a host from the allowed list.

        Args:
            host: Hostname or IP to remove
        """
        self.allowed_hosts.discard(host)

    def add_allowed_port(self, port: int) -> None:
        """Add a port to the allowed list.

        Args:
            port: Port number to allow
        """
        if self.allowed_ports is None:
            self.allowed_ports = set()
        self.allowed_ports.add(port)

    def is_active(self) -> bool:
        """Check if the sandbox is currently active."""
        return self._active

    @staticmethod
    def parse_url_host(url: str) -> Tuple[str, int]:
        """Parse host and port from a URL.

        Args:
            url: URL to parse

        Returns:
            Tuple of (host, port)
        """
        parsed = urlparse(url)
        host = parsed.hostname or ""
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        return host, port
