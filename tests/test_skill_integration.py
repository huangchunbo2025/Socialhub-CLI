"""Integration tests for the Skills system with report-generator skill."""

import io
import json
import os
import shutil
import tempfile
import zipfile
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch, call

import pytest
import yaml

# Add project root to path
import sys
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "cli"))


class TestSkillInstallation:
    """Test skill installation flow."""

    @pytest.fixture
    def temp_skill_dir(self):
        """Create a temporary skill directory for testing."""
        tmpdir = tempfile.mkdtemp()
        yield tmpdir
        shutil.rmtree(tmpdir, ignore_errors=True)

    @pytest.fixture
    def report_generator_skill_path(self):
        """Get the path to the report-generator skill."""
        return project_root / "cli" / "skills" / "store" / "report-generator"

    def test_skill_manifest_is_valid(self, report_generator_skill_path):
        """Test that the skill.yaml manifest is valid."""
        manifest_path = report_generator_skill_path / "skill.yaml"
        assert manifest_path.exists(), "skill.yaml should exist"

        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest = yaml.safe_load(f)

        # Check required fields
        assert manifest["name"] == "report-generator"
        assert manifest["version"] == "3.1.0"
        assert "permissions" in manifest
        assert "commands" in manifest
        assert manifest["entrypoint"] == "main.py"

    def test_skill_entrypoint_exists(self, report_generator_skill_path):
        """Test that the main.py entry point exists."""
        main_path = report_generator_skill_path / "main.py"
        assert main_path.exists(), "main.py should exist"

    def test_skill_has_required_functions(self, report_generator_skill_path):
        """Test that the skill has required functions defined."""
        main_path = report_generator_skill_path / "main.py"
        content = main_path.read_text(encoding="utf-8")

        # Check for required functions
        assert "def generate_consulting_report" in content
        assert "def generate_demo_report" in content
        assert "def _validate_output_path" in content

    def test_skill_permissions_are_minimal(self, report_generator_skill_path):
        """Test that the skill requests minimal permissions."""
        manifest_path = report_generator_skill_path / "skill.yaml"
        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest = yaml.safe_load(f)

        permissions = manifest.get("permissions", [])

        # Should have file:write permission
        assert "file:write" in permissions
        # Should NOT need dangerous permissions
        assert "execute" not in permissions
        assert "network:internet" not in permissions

    def test_skill_certification_exists(self, report_generator_skill_path):
        """Test that certification.json exists."""
        cert_path = report_generator_skill_path / "certification.json"
        assert cert_path.exists(), "certification.json should exist"

        with open(cert_path, "r", encoding="utf-8") as f:
            cert = json.load(f)

        assert cert["skill_name"] == "report-generator"
        assert cert["certificate_id"] == "SKILL-RPT-003"


class TestSkillManifestModel:
    """Test SkillManifest model with report-generator skill."""

    @pytest.fixture
    def report_generator_manifest(self):
        """Load the report-generator manifest."""
        manifest_path = project_root / "cli" / "skills" / "store" / "report-generator" / "skill.yaml"
        with open(manifest_path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)

    def test_manifest_loads_into_model(self, report_generator_manifest):
        """Test that manifest can be loaded into SkillManifest model."""
        from cli.skills.models import SkillManifest

        manifest = SkillManifest(**report_generator_manifest)

        assert manifest.name == "report-generator"
        assert manifest.version == "3.1.0"
        assert manifest.category.value == "analytics"
        assert len(manifest.commands) >= 8

    def test_manifest_commands_are_valid(self, report_generator_manifest):
        """Test that commands in manifest are valid."""
        from cli.skills.models import SkillManifest, SkillCommand

        manifest = SkillManifest(**report_generator_manifest)

        # Check generate command
        generate_cmd = next((c for c in manifest.commands if c.name == "generate"), None)
        assert generate_cmd is not None
        assert generate_cmd.function == "generate_consulting_report"
        assert len(generate_cmd.arguments) >= 1

        # Check demo command
        demo_cmd = next((c for c in manifest.commands if c.name == "demo"), None)
        assert demo_cmd is not None
        assert demo_cmd.function == "generate_demo_report"

    def test_manifest_permissions_are_valid_enums(self, report_generator_manifest):
        """Test that permissions are valid SkillPermission enums."""
        from cli.skills.models import SkillManifest, SkillPermission

        manifest = SkillManifest(**report_generator_manifest)

        for perm in manifest.permissions:
            assert isinstance(perm, SkillPermission)


class TestPermissionEnforcement:
    """Test permission enforcement for the skill."""

    def test_permission_checker_allows_required_permissions(self):
        """Test that PermissionChecker allows the skill's required permissions."""
        from cli.skills.security import PermissionChecker

        checker = PermissionChecker()

        # Grant required permissions
        checker.grant_permission("report-generator", "file:write")
        checker.grant_permission("report-generator", "file:read")

        # Check permissions
        granted, missing = checker.check_permissions(
            "report-generator",
            ["file:write", "file:read"]
        )
        assert granted
        assert len(missing) == 0

    def test_permission_checker_denies_ungrated_permissions(self):
        """Test that PermissionChecker denies permissions that weren't granted."""
        from cli.skills.security import PermissionChecker

        checker = PermissionChecker()

        # Only grant file:read
        checker.grant_permission("report-generator", "file:read")

        # Check for file:write - should be missing
        granted, missing = checker.check_permissions(
            "report-generator",
            ["file:write", "file:read"]
        )
        # file:write is sensitive so it should be in missing
        assert "file:write" in missing


class TestSandboxEnforcement:
    """Test sandbox enforcement for the skill."""

    def test_filesystem_sandbox_allows_temp_directory(self):
        """Test that FileSystemSandbox allows writing to temp directory."""
        from cli.skills.sandbox import FileSystemSandbox

        with tempfile.TemporaryDirectory() as tmpdir:
            sandbox = FileSystemSandbox(
                skill_name="report-generator",
                allowed_paths={Path(tmpdir)},
                allow_read=True,
                allow_write=True,
            )

            with sandbox:
                # This should not raise an error
                test_file = Path(tmpdir) / "test.txt"
                test_file.write_text("test")
                assert test_file.exists()

    def test_filesystem_sandbox_blocks_unauthorized_access(self):
        """Test that FileSystemSandbox blocks access to unauthorized directories."""
        from cli.skills.sandbox import FileSystemSandbox, FileAccessDeniedError

        with tempfile.TemporaryDirectory() as allowed_dir:
            # Create a sandbox with NO default dirs and only our specific allowed dir
            sandbox = FileSystemSandbox(
                skill_name="report-generator-test",  # Different name to avoid default sandbox dir
                allowed_paths={Path(allowed_dir)},
                allow_read=True,
                allow_write=True,
            )
            # Clear default allowed paths for this test
            sandbox.allowed_paths = {Path(allowed_dir).resolve()}

            with sandbox:
                # Try to write to a path that's definitely not allowed
                # Use a path outside the allowed directory
                blocked_path = Path(allowed_dir).parent / "blocked_test_file.txt"
                with pytest.raises(FileAccessDeniedError):
                    with open(blocked_path, "w") as f:
                        f.write("should not work")


class TestHealthCheck:
    """Test health checking for the skill."""

    def test_skill_manifest_integrity(self):
        """Test that skill manifest passes integrity check."""
        from cli.skills.security import HashVerifier

        skill_path = project_root / "cli" / "skills" / "store" / "report-generator"
        manifest_path = skill_path / "skill.yaml"

        verifier = HashVerifier()
        # Read file content and compute hash
        content = manifest_path.read_bytes()
        manifest_hash = verifier.compute_hash(content, "sha256")

        # Hash should be a valid hex string
        assert manifest_hash is not None
        assert len(manifest_hash) == 64  # SHA-256 produces 64 hex characters

    def test_skill_health_checker_basic(self):
        """Test basic health check functionality."""
        from cli.skills.security import SkillHealthChecker, HealthCheckResult

        checker = SkillHealthChecker()

        # Create a mock result with correct API
        result = HealthCheckResult(
            skill_name="report-generator",
            status="healthy",
            checks={
                "manifest_exists": {"passed": True, "message": "OK"},
                "entrypoint_exists": {"passed": True, "message": "OK"},
                "permissions_valid": {"passed": True, "message": "OK"},
            },
        )

        assert result.is_healthy()
        assert result.skill_name == "report-generator"
        assert len(result.get_issues()) == 0


class TestFullExecutionFlow:
    """Test the full execution flow of the skill."""

    @pytest.fixture
    def skill_module(self):
        """Import skill module with sys.path management and cleanup."""
        skill_path = project_root / "cli" / "skills" / "store" / "report-generator"
        sys.path.insert(0, str(skill_path))
        try:
            import main as skill_main
            yield skill_main
        finally:
            sys.path.remove(str(skill_path))
            sys.modules.pop("main", None)

    def test_skill_module_can_be_imported(self, skill_module):
        """Test that the skill module can be imported."""
        assert hasattr(skill_module, "generate_consulting_report")
        assert hasattr(skill_module, "generate_demo_report")

    def test_skill_can_execute_generate_command(self, skill_module):
        """Test that the skill can execute the generate command."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = os.path.join(tmpdir, "test_report.md")
            result = skill_module.generate_consulting_report(
                topic="Test Business Analysis",
                output=output_path,
                context="comprehensive",
            )

            assert "generated" in result.lower()
            assert Path(output_path).exists()

    def test_skill_can_execute_demo_command(self, skill_module):
        """Test that the skill can execute the demo command."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = os.path.join(tmpdir, "demo_report.md")
            result = skill_module.generate_demo_report(output=output_path)

            assert "generated" in result.lower()
            assert Path(output_path).exists()

            # Verify demo content is in the report
            content = Path(output_path).read_text(encoding="utf-8")
            assert "新能源汽车" in content


# ---------------------------------------------------------------------------
# _install_local_skill — dev-mode local zip install
# ---------------------------------------------------------------------------


class TestInstallLocalSkill:
    """Tests for the _install_local_skill dev-mode installation path."""

    def _make_zip(self, tmp_path: Path, skill_name: str = "my-skill", extra_members: dict | None = None) -> Path:
        """Build a minimal valid skill zip and return its path."""
        zip_path = tmp_path / "skill.zip"
        manifest = {"name": skill_name, "version": "1.0.0", "description": "test skill"}
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("manifest.json", json.dumps(manifest))
            zf.writestr("main.py", "# entry")
            for name, content in (extra_members or {}).items():
                zf.writestr(name, content)
        return zip_path

    def _mock_registry(self, skills_root: Path, skill_name: str) -> MagicMock:
        mock = MagicMock()
        mock.is_installed.return_value = False
        mock.get_skill_path.return_value = skills_root / skill_name
        return mock

    def test_zip_slip_entry_is_blocked(self, tmp_path):
        """A zip containing a path-traversal entry (../) must be rejected before any extraction."""
        import typer
        zip_path = self._make_zip(tmp_path, extra_members={"../escape.txt": "evil"})
        mock_reg = self._mock_registry(tmp_path / "installed", "my-skill")

        from cli.commands.skills import _install_local_skill

        with patch("cli.skills.registry.SkillRegistry", return_value=mock_reg):
            with pytest.raises((typer.Exit, SystemExit)):
                _install_local_skill(str(zip_path))

        # The traversal target must not exist outside the skills directory
        assert not (tmp_path / "escape.txt").exists()

    def test_invalid_skill_name_in_manifest_is_blocked(self, tmp_path):
        """A manifest with a skill name that fails the allowlist regex must be rejected."""
        import typer
        # Name contains a space — fails r"[a-zA-Z0-9][a-zA-Z0-9_\-]{0,63}"
        zip_path = self._make_zip(tmp_path, skill_name="invalid name!")
        mock_reg = self._mock_registry(tmp_path / "installed", "invalid name!")
        mock_reg.is_installed.return_value = False  # don't block on already-installed

        from cli.commands.skills import _install_local_skill

        with patch("cli.skills.registry.SkillRegistry", return_value=mock_reg):
            with pytest.raises((typer.Exit, SystemExit)):
                _install_local_skill(str(zip_path))

    def test_missing_manifest_json_is_blocked(self, tmp_path):
        """A zip without manifest.json must be rejected immediately."""
        import typer
        zip_path = tmp_path / "no_manifest.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("main.py", "# entry")  # no manifest.json

        from cli.commands.skills import _install_local_skill

        with pytest.raises((typer.Exit, SystemExit)):
            _install_local_skill(str(zip_path))


class TestSkillManagerHashGate:
    """Tests for the mandatory hash-verification gate in SkillManager.install().

    CLAUDE.md: "签名验证不可跳过" — this class verifies the hash gate cannot
    be silently bypassed when the store fails to return integrity metadata.
    """

    @pytest.fixture
    def patched_manager(self, tmp_path):
        """SkillManager with all filesystem/network IO mocked."""
        from cli.skills.manager import SkillManager

        # Use MagicMock() instances (not the MagicMock class) so that calling
        # them inside __init__ (e.g. PermissionPrompter(console)) returns a plain
        # MagicMock rather than one spec'd to the constructor argument.
        with patch.multiple(
            "cli.skills.manager",
            SkillRegistry=MagicMock(),
            SignatureVerifier=MagicMock(),
            HashVerifier=MagicMock(),
            PermissionChecker=MagicMock(),
            PermissionStore=MagicMock(),
            PermissionPrompter=MagicMock(),
            RevocationListManager=MagicMock(),
            SecurityAuditLogger=MagicMock(),
        ):
            mgr = SkillManager()
            # Skill not yet installed — prevent early-exit in install()
            mgr.registry.get_installed.return_value = None
            mgr._store_client = MagicMock()
            skill_info = MagicMock()
            skill_info.version = "1.0.0"
            mgr._store_client.get_skill.return_value = skill_info

            # registry helpers return tmp_path locations
            mgr.registry.get_cache_path.return_value = tmp_path / "pkg.zip"
            skill_dir = tmp_path / "skills" / "test-skill"
            mgr.registry.get_skill_path.return_value = skill_dir
            yield mgr, tmp_path

    def test_install_aborts_when_download_info_raises_store_error(self, patched_manager):
        """If get_download_info raises StoreError, install() must raise SkillManagerError.

        This test documents the P0 security issue: when download_info is
        unavailable the code silently sets expected_hash="" and continues,
        effectively skipping the mandatory hash check.  The test SHOULD FAIL
        until the bug is fixed (raises SkillManagerError).
        """
        from cli.skills.manager import SkillManagerError
        from cli.skills.store_client import StoreError

        mgr, tmp_path = patched_manager
        mgr._store_client.get_download_info.side_effect = StoreError("Network unavailable")

        with pytest.raises(SkillManagerError, match="(?i)hash|integrity|download info|verification"):
            mgr.install("test-skill")

    def test_install_invalidates_validator_cache_after_success(self, patched_manager, tmp_path):
        """invalidate_cmd_tree() must be called after a successful install so the
        AI validator accepts commands for the newly installed skill immediately."""
        import io as _io
        from cli.skills.manager import SkillManagerError

        mgr, tmp_path = patched_manager

        # Provide valid download_info
        mgr._store_client.get_download_info.return_value = {
            "hash": "abc123",
            "signature": "sig",
        }

        # Build a minimal zip so the extraction step doesn't fail
        buf = _io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("skill.yaml", "name: test-skill\nversion: 1.0.0")
        pkg_bytes = buf.getvalue()
        mgr._store_client.download.return_value = pkg_bytes

        # hash_verifier and signature verifier succeed
        mgr.hash_verifier.verify_hash.return_value = True
        mgr.verifier.verify_manifest_signature.return_value = None
        mgr.revocation_manager.is_revoked.return_value = False
        # permission_prompter is MagicMock().return_value — no permissions needed
        mgr.permission_prompter.request_permissions.return_value = (True, [])

        # Write pkg bytes to cache path so zipfile can open it
        cache_path = tmp_path / "pkg.zip"
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_bytes(pkg_bytes)
        mgr.registry.get_cache_path.return_value = cache_path

        skill_dir = tmp_path / "skills" / "test-skill"
        skill_dir.mkdir(parents=True, exist_ok=True)
        mgr.registry.get_skill_path.return_value = skill_dir

        # Write a valid skill.yaml into the extracted dir so manifest loading works
        manifest_data = {
            "name": "test-skill",
            "version": "1.0.0",
            "description": "Test",
            "entrypoint": "main.py",
            "permissions": [],
            "dependencies": {"python": []},
        }
        (skill_dir / "skill.yaml").write_text(yaml.dump(manifest_data), encoding="utf-8")

        with patch("cli.ai.validator.invalidate_cmd_tree") as mock_invalidate:
            try:
                mgr.install("test-skill")
            except Exception:
                pass  # manifest parsing may fail for unrelated reasons
            mock_invalidate.assert_called_once()
