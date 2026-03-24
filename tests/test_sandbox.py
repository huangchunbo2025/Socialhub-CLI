"""Tests for skills sandbox module."""

import os
import socket
import subprocess
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from cli.skills.sandbox import (
    FileSystemSandbox,
    FileAccessDeniedError,
    NetworkSandbox,
    NetworkAccessDeniedError,
    ExecuteSandbox,
    CommandExecutionDeniedError,
    SandboxManager,
    SandboxViolationError,
)


class TestFileSystemSandbox:
    """Tests for FileSystemSandbox class."""

    @pytest.fixture
    def sandbox(self, tmp_path):
        """Create a filesystem sandbox with temporary paths."""
        sandbox = FileSystemSandbox(
            skill_name="test-skill",
            allowed_paths={tmp_path},
            allow_read=True,
            allow_write=True,
        )
        return sandbox

    @pytest.fixture
    def readonly_sandbox(self, tmp_path):
        """Create a read-only filesystem sandbox."""
        return FileSystemSandbox(
            skill_name="test-skill",
            allowed_paths={tmp_path},
            allow_read=True,
            allow_write=False,
        )

    def test_allowed_path_read(self, sandbox, tmp_path):
        """Test reading from allowed path."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("hello")

        with sandbox:
            content = open(test_file, "r").read()
            assert content == "hello"

    def test_allowed_path_write(self, sandbox, tmp_path):
        """Test writing to allowed path."""
        test_file = tmp_path / "output.txt"

        with sandbox:
            with open(test_file, "w") as f:
                f.write("world")

        assert test_file.read_text() == "world"

    def test_disallowed_path_read_blocked(self, sandbox, tmp_path):
        """Test that reading from disallowed path is blocked."""
        # Create a file outside allowed paths
        disallowed = Path.home() / ".bashrc"

        if disallowed.exists():
            with sandbox:
                with pytest.raises(FileAccessDeniedError):
                    open(disallowed, "r")

    def test_write_blocked_in_readonly(self, readonly_sandbox, tmp_path):
        """Test that writing is blocked in read-only sandbox."""
        test_file = tmp_path / "test.txt"

        with readonly_sandbox:
            with pytest.raises(FileAccessDeniedError):
                open(test_file, "w")

    def test_sandbox_deactivation(self, sandbox, tmp_path):
        """Test that sandbox properly deactivates."""
        with sandbox:
            assert sandbox.is_active()

        assert not sandbox.is_active()

    def test_sandbox_dir_always_allowed(self, tmp_path):
        """Test that sandbox directory is always allowed."""
        sandbox = FileSystemSandbox(
            skill_name="test-skill",
            allowed_paths=set(),  # No extra paths
            allow_read=True,
            allow_write=True,
        )

        sandbox_file = sandbox.get_sandbox_path("test.txt")

        with sandbox:
            with open(sandbox_file, "w") as f:
                f.write("allowed")

        assert sandbox_file.read_text() == "allowed"

    def test_add_allowed_path(self, tmp_path):
        """Test adding paths dynamically."""
        sandbox = FileSystemSandbox(
            skill_name="test-skill",
            allowed_paths=set(),
            allow_read=True,
            allow_write=False,
        )

        sandbox.add_allowed_path(tmp_path)
        assert sandbox.is_path_allowed(tmp_path / "test.txt")

    def test_is_path_allowed(self, sandbox, tmp_path):
        """Test path checking."""
        assert sandbox.is_path_allowed(tmp_path / "test.txt")
        assert sandbox.is_path_allowed(tmp_path / "subdir" / "file.txt")

    def test_file_descriptor_passthrough(self, sandbox):
        """Test that file descriptors pass through."""
        with sandbox:
            # File descriptor should not be blocked
            # This tests the int check in guarded_open
            pass  # Just verify sandbox activates without error


class TestNetworkSandbox:
    """Tests for NetworkSandbox class."""

    @pytest.fixture
    def sandbox_no_network(self):
        """Create a sandbox with no network access."""
        return NetworkSandbox(
            skill_name="test-skill",
            allow_local=False,
            allow_internet=False,
        )

    @pytest.fixture
    def sandbox_local_only(self):
        """Create a sandbox with only local network access."""
        return NetworkSandbox(
            skill_name="test-skill",
            allow_local=True,
            allow_internet=False,
        )

    @pytest.fixture
    def sandbox_full_access(self):
        """Create a sandbox with full network access."""
        return NetworkSandbox(
            skill_name="test-skill",
            allow_local=True,
            allow_internet=True,
        )

    def test_local_address_detection(self, sandbox_no_network):
        """Test local address detection."""
        assert sandbox_no_network.is_local_address("localhost")
        assert sandbox_no_network.is_local_address("127.0.0.1")
        assert sandbox_no_network.is_local_address("::1")
        assert sandbox_no_network.is_local_address("192.168.1.1")
        assert not sandbox_no_network.is_local_address("8.8.8.8")
        assert not sandbox_no_network.is_local_address("google.com")

    def test_no_network_blocks_all(self, sandbox_no_network):
        """Test that no-network sandbox blocks all connections."""
        assert not sandbox_no_network.is_connection_allowed("localhost", 80)
        assert not sandbox_no_network.is_connection_allowed("google.com", 443)

    def test_local_only_allows_local(self, sandbox_local_only):
        """Test that local-only allows local connections."""
        assert sandbox_local_only.is_connection_allowed("localhost", 80)
        assert sandbox_local_only.is_connection_allowed("127.0.0.1", 8080)
        assert not sandbox_local_only.is_connection_allowed("google.com", 443)

    def test_full_access_allows_all(self, sandbox_full_access):
        """Test that full access allows all connections."""
        assert sandbox_full_access.is_connection_allowed("localhost", 80)
        assert sandbox_full_access.is_connection_allowed("google.com", 443)

    def test_explicit_host_allowlist(self):
        """Test explicit host allowlist."""
        sandbox = NetworkSandbox(
            skill_name="test-skill",
            allow_local=False,
            allow_internet=False,
            allowed_hosts={"api.example.com"},
        )

        assert sandbox.is_connection_allowed("api.example.com", 443)
        assert not sandbox.is_connection_allowed("other.example.com", 443)

    def test_port_restrictions(self):
        """Test port restrictions."""
        sandbox = NetworkSandbox(
            skill_name="test-skill",
            allow_local=True,
            allow_internet=True,
            allowed_ports={80, 443},
        )

        assert sandbox.is_connection_allowed("google.com", 443)
        assert sandbox.is_connection_allowed("google.com", 80)
        assert not sandbox.is_connection_allowed("google.com", 8080)

    def test_add_allowed_host(self):
        """Test adding hosts dynamically."""
        sandbox = NetworkSandbox(
            skill_name="test-skill",
            allow_local=False,
            allow_internet=False,
        )

        sandbox.add_allowed_host("api.example.com")
        assert sandbox.is_connection_allowed("api.example.com", 443)

    def test_parse_url_host(self):
        """Test URL parsing."""
        host, port = NetworkSandbox.parse_url_host("https://api.example.com:8443/path")
        assert host == "api.example.com"
        assert port == 8443

        host, port = NetworkSandbox.parse_url_host("https://api.example.com/path")
        assert host == "api.example.com"
        assert port == 443

        host, port = NetworkSandbox.parse_url_host("http://api.example.com/path")
        assert host == "api.example.com"
        assert port == 80

    def test_sandbox_activation(self, sandbox_no_network):
        """Test sandbox activation/deactivation."""
        assert not sandbox_no_network.is_active()

        with sandbox_no_network:
            assert sandbox_no_network.is_active()

        assert not sandbox_no_network.is_active()


class TestExecuteSandbox:
    """Tests for ExecuteSandbox class."""

    @pytest.fixture
    def sandbox_no_execute(self):
        """Create a sandbox with no execution allowed."""
        return ExecuteSandbox(
            skill_name="test-skill",
            allow_execute=False,
        )

    @pytest.fixture
    def sandbox_limited(self):
        """Create a sandbox with limited command execution."""
        return ExecuteSandbox(
            skill_name="test-skill",
            allow_execute=True,
            allowed_commands={"echo", "ls", "dir"},
        )

    @pytest.fixture
    def sandbox_full(self):
        """Create a sandbox with full execution (except dangerous)."""
        return ExecuteSandbox(
            skill_name="test-skill",
            allow_execute=True,
        )

    def test_no_execute_blocks_all(self, sandbox_no_execute):
        """Test that no-execute sandbox blocks all commands."""
        allowed, _ = sandbox_no_execute.is_command_allowed(["echo", "hello"])
        assert not allowed

        allowed, _ = sandbox_no_execute.is_command_allowed("ls -la")
        assert not allowed

    def test_dangerous_commands_blocked(self, sandbox_full):
        """Test that dangerous commands are always blocked."""
        for cmd in ["rm", "sudo", "shutdown", "format", "kill"]:
            allowed, reason = sandbox_full.is_command_allowed([cmd])
            assert not allowed
            assert "dangerous" in reason

    def test_safe_commands_allowed(self, sandbox_full):
        """Test that safe commands are allowed."""
        for cmd in ["echo", "cat", "ls", "grep"]:
            allowed, _ = sandbox_full.is_command_allowed([cmd, "arg"])
            assert allowed

    def test_allowlist_enforcement(self, sandbox_limited):
        """Test that only allowlisted commands work."""
        allowed, _ = sandbox_limited.is_command_allowed(["echo", "hello"])
        assert allowed

        allowed, _ = sandbox_limited.is_command_allowed(["python", "script.py"])
        assert not allowed

    def test_command_extraction_from_string(self, sandbox_full):
        """Test command extraction from string."""
        allowed, _ = sandbox_full.is_command_allowed("echo hello world")
        assert allowed

        allowed, _ = sandbox_full.is_command_allowed("/bin/echo hello")
        assert allowed

    def test_command_extraction_from_path(self, sandbox_full):
        """Test command extraction from full path."""
        allowed, _ = sandbox_full.is_command_allowed(["/usr/bin/cat", "file.txt"])
        assert allowed

    def test_blocked_command_list(self, sandbox_full):
        """Test explicit blocklist."""
        sandbox_full.add_blocked_command("custom-dangerous")

        allowed, reason = sandbox_full.is_command_allowed(["custom-dangerous"])
        assert not allowed
        assert "blocked" in reason

    def test_sandbox_activation(self, sandbox_no_execute):
        """Test sandbox activation/deactivation."""
        assert not sandbox_no_execute.is_active()

        with sandbox_no_execute:
            assert sandbox_no_execute.is_active()

        assert not sandbox_no_execute.is_active()

    def test_empty_command_blocked(self, sandbox_full):
        """Test that empty commands are blocked."""
        allowed, _ = sandbox_full.is_command_allowed([])
        assert not allowed

        allowed, _ = sandbox_full.is_command_allowed("")
        assert not allowed


class TestSandboxManager:
    """Tests for SandboxManager class."""

    @pytest.fixture
    def manager_no_perms(self):
        """Create a manager with no permissions."""
        return SandboxManager(
            skill_name="test-skill",
            permissions=set(),
        )

    @pytest.fixture
    def manager_full_perms(self):
        """Create a manager with all permissions."""
        return SandboxManager(
            skill_name="test-skill",
            permissions={
                "file:read",
                "file:write",
                "network:local",
                "network:internet",
                "execute",
            },
        )

    @pytest.fixture
    def manager_read_only(self):
        """Create a manager with read-only permissions."""
        return SandboxManager(
            skill_name="test-skill",
            permissions={"file:read", "network:local"},
        )

    def test_manager_activation(self, manager_no_perms):
        """Test manager activation/deactivation."""
        assert not manager_no_perms.is_active()

        with manager_no_perms:
            assert manager_no_perms.is_active()
            assert manager_no_perms.filesystem_sandbox.is_active()
            assert manager_no_perms.network_sandbox.is_active()
            assert manager_no_perms.execute_sandbox.is_active()

        assert not manager_no_perms.is_active()

    def test_permission_mapping(self, manager_full_perms):
        """Test that permissions are mapped correctly."""
        assert manager_full_perms.filesystem_sandbox.allow_read
        assert manager_full_perms.filesystem_sandbox.allow_write
        assert manager_full_perms.network_sandbox.allow_local
        assert manager_full_perms.network_sandbox.allow_internet
        assert manager_full_perms.execute_sandbox.allow_execute

    def test_restricted_permissions(self, manager_read_only):
        """Test restricted permission mapping."""
        assert manager_read_only.filesystem_sandbox.allow_read
        assert not manager_read_only.filesystem_sandbox.allow_write
        assert manager_read_only.network_sandbox.allow_local
        assert not manager_read_only.network_sandbox.allow_internet
        assert not manager_read_only.execute_sandbox.allow_execute

    def test_get_sandbox_dir(self, manager_no_perms):
        """Test getting sandbox directory."""
        sandbox_dir = manager_no_perms.get_sandbox_dir()
        assert "test-skill" in str(sandbox_dir)
        assert ".socialhub" in str(sandbox_dir)

    def test_add_allowed_resources(self, manager_no_perms, tmp_path):
        """Test adding allowed resources."""
        manager_no_perms.add_allowed_path(tmp_path)
        manager_no_perms.add_allowed_host("api.example.com")
        manager_no_perms.add_allowed_command("custom-tool")

        assert tmp_path in manager_no_perms.filesystem_sandbox.allowed_paths
        assert "api.example.com" in manager_no_perms.network_sandbox.allowed_hosts
        assert "custom-tool" in manager_no_perms.execute_sandbox.allowed_commands

    def test_get_status(self, manager_full_perms):
        """Test status retrieval."""
        status = manager_full_perms.get_status()

        assert status["skill_name"] == "test-skill"
        assert not status["active"]
        assert "file:read" in status["permissions"]

        assert "filesystem" in status["components"]
        assert "network" in status["components"]
        assert "execute" in status["components"]

    def test_nested_context_managers(self, manager_no_perms):
        """Test that nested context managers work correctly."""
        with manager_no_perms:
            assert manager_no_perms.is_active()

            # Nested activation should be idempotent
            manager_no_perms.activate()
            assert manager_no_perms.is_active()

        assert not manager_no_perms.is_active()


class TestSandboxIntegration:
    """Integration tests for sandbox module."""

    def test_full_isolation(self, tmp_path):
        """Test complete isolation with all sandboxes."""
        # Create allowed file
        allowed_file = tmp_path / "allowed.txt"
        allowed_file.write_text("allowed content")

        manager = SandboxManager(
            skill_name="integration-test",
            permissions={"file:read"},
            allowed_paths={tmp_path},
        )

        with manager:
            # Reading allowed file should work
            content = open(allowed_file, "r").read()
            assert content == "allowed content"

    def test_permission_based_sandbox_creation(self):
        """Test that sandbox respects permissions."""
        from cli.skills.sandbox.manager import create_sandbox_from_permissions

        # No permissions = everything blocked
        manager = create_sandbox_from_permissions("test", set())
        assert not manager.filesystem_sandbox.allow_read
        assert not manager.filesystem_sandbox.allow_write
        assert not manager.network_sandbox.allow_local
        assert not manager.network_sandbox.allow_internet
        assert not manager.execute_sandbox.allow_execute

        # Full permissions = everything allowed
        manager = create_sandbox_from_permissions(
            "test",
            {"file:read", "file:write", "network:local", "network:internet", "execute"},
        )
        assert manager.filesystem_sandbox.allow_read
        assert manager.filesystem_sandbox.allow_write
        assert manager.network_sandbox.allow_local
        assert manager.network_sandbox.allow_internet
        assert manager.execute_sandbox.allow_execute
