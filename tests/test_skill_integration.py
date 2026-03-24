"""Integration tests for the Skills system with report-generator skill."""

import json
import os
import shutil
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

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
        assert manifest["version"] == "1.0.0"
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
        assert "def generate_report" in content
        assert "def preview_report" in content
        assert "def _validate_output_path" in content

    def test_skill_permissions_are_minimal(self, report_generator_skill_path):
        """Test that the skill requests minimal permissions."""
        manifest_path = report_generator_skill_path / "skill.yaml"
        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest = yaml.safe_load(f)

        permissions = manifest.get("permissions", [])

        # Should only need file:write and optionally file:read
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
        assert cert["certificate_id"] == "SKILL-RPT-001"


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
        assert manifest.version == "1.0.0"
        assert manifest.category.value == "analytics"
        assert len(manifest.commands) == 2

    def test_manifest_commands_are_valid(self, report_generator_manifest):
        """Test that commands in manifest are valid."""
        from cli.skills.models import SkillManifest, SkillCommand

        manifest = SkillManifest(**report_generator_manifest)

        # Check generate command
        generate_cmd = next((c for c in manifest.commands if c.name == "generate"), None)
        assert generate_cmd is not None
        assert generate_cmd.function == "generate_report"
        assert len(generate_cmd.arguments) >= 1

        # Check preview command
        preview_cmd = next((c for c in manifest.commands if c.name == "preview"), None)
        assert preview_cmd is not None
        assert preview_cmd.function == "preview_report"

    def test_manifest_permissions_are_valid_enums(self, report_generator_manifest):
        """Test that permissions are valid SkillPermission enums."""
        from cli.skills.models import SkillManifest, SkillPermission

        manifest = SkillManifest(**report_generator_manifest)

        for perm in manifest.permissions:
            assert isinstance(perm, SkillPermission)
            assert perm.value in ["file:read", "file:write"]


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

    def test_skill_module_can_be_imported(self):
        """Test that the skill module can be imported."""
        skill_path = project_root / "cli" / "skills" / "store" / "report-generator"
        sys.path.insert(0, str(skill_path))

        try:
            import main as skill_main
            assert hasattr(skill_main, "generate_report")
            assert hasattr(skill_main, "preview_report")
        finally:
            sys.path.remove(str(skill_path))

    def test_skill_can_execute_generate_command(self):
        """Test that the skill can execute the generate command."""
        skill_path = project_root / "cli" / "skills" / "store" / "report-generator"
        sys.path.insert(0, str(skill_path))

        try:
            import main as skill_main

            with tempfile.TemporaryDirectory() as tmpdir:
                output_path = os.path.join(tmpdir, "test_report.html")
                result = skill_main.generate_report(
                    output=output_path,
                    title="Test Report",
                    report_data={"overview": {"total_customers": 100}},
                )

                assert "Report generated successfully" in result
                assert Path(output_path).exists()
        finally:
            sys.path.remove(str(skill_path))

    def test_skill_can_execute_preview_command(self):
        """Test that the skill can execute the preview command."""
        skill_path = project_root / "cli" / "skills" / "store" / "report-generator"
        sys.path.insert(0, str(skill_path))

        try:
            import main as skill_main

            with tempfile.TemporaryDirectory() as tmpdir:
                output_path = os.path.join(tmpdir, "preview_report.html")
                result = skill_main.preview_report(output=output_path)

                assert "Report generated successfully" in result
                assert Path(output_path).exists()

                # Verify demo data is in the report
                content = Path(output_path).read_text(encoding="utf-8")
                assert "Alice Wang" in content
                assert "SocialHub.AI Demo Report" in content
        finally:
            sys.path.remove(str(skill_path))
