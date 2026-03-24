"""Tests for the Version Manager module."""

import json
import tempfile
from pathlib import Path

import pytest

import sys
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "socialhub"))

from cli.skills.version_manager import (
    VersionInfo,
    ChangelogEntry,
    SkillVersionRecord,
    VersionManager,
)


class TestVersionInfo:
    """Test VersionInfo class."""

    def test_parse_simple_version(self):
        """Test parsing simple version string."""
        v = VersionInfo.parse("1.2.3")
        assert v.major == 1
        assert v.minor == 2
        assert v.patch == 3
        assert v.prerelease == ""
        assert v.build == ""

    def test_parse_version_with_prerelease(self):
        """Test parsing version with prerelease."""
        v = VersionInfo.parse("2.0.0-beta.1")
        assert v.major == 2
        assert v.minor == 0
        assert v.patch == 0
        assert v.prerelease == "beta.1"

    def test_parse_version_with_build(self):
        """Test parsing version with build metadata."""
        v = VersionInfo.parse("1.0.0+build.123")
        assert v.major == 1
        assert v.build == "build.123"

    def test_parse_full_version(self):
        """Test parsing full semantic version."""
        v = VersionInfo.parse("3.2.1-alpha.2+build.456")
        assert v.major == 3
        assert v.minor == 2
        assert v.patch == 1
        assert v.prerelease == "alpha.2"
        assert v.build == "build.456"

    def test_parse_invalid_version(self):
        """Test parsing invalid version raises error."""
        with pytest.raises(ValueError):
            VersionInfo.parse("invalid")

        with pytest.raises(ValueError):
            VersionInfo.parse("1.2")

        with pytest.raises(ValueError):
            VersionInfo.parse("v1.2.3")  # No 'v' prefix allowed

    def test_version_str(self):
        """Test version string representation."""
        v = VersionInfo(1, 2, 3)
        assert str(v) == "1.2.3"

        v = VersionInfo(2, 0, 0, "beta.1")
        assert str(v) == "2.0.0-beta.1"

        v = VersionInfo(1, 0, 0, "rc.1", "build.100")
        assert str(v) == "1.0.0-rc.1+build.100"

    def test_version_comparison_lt(self):
        """Test version less than comparison."""
        assert VersionInfo.parse("1.0.0") < VersionInfo.parse("2.0.0")
        assert VersionInfo.parse("1.0.0") < VersionInfo.parse("1.1.0")
        assert VersionInfo.parse("1.0.0") < VersionInfo.parse("1.0.1")
        assert VersionInfo.parse("1.0.0-alpha") < VersionInfo.parse("1.0.0")
        assert VersionInfo.parse("1.0.0-alpha") < VersionInfo.parse("1.0.0-beta")

    def test_version_comparison_eq(self):
        """Test version equality comparison."""
        assert VersionInfo.parse("1.0.0") == VersionInfo.parse("1.0.0")
        assert VersionInfo.parse("2.1.3-beta") == VersionInfo.parse("2.1.3-beta")
        assert VersionInfo.parse("1.0.0") != VersionInfo.parse("1.0.1")

    def test_version_comparison_gt(self):
        """Test version greater than comparison."""
        assert VersionInfo.parse("2.0.0") > VersionInfo.parse("1.0.0")
        assert VersionInfo.parse("1.0.0") > VersionInfo.parse("1.0.0-beta")

    def test_version_compatibility(self):
        """Test version compatibility check."""
        v1 = VersionInfo.parse("1.0.0")
        v2 = VersionInfo.parse("1.5.0")
        v3 = VersionInfo.parse("2.0.0")

        assert v1.is_compatible_with(v2)
        assert not v1.is_compatible_with(v3)


class TestChangelogEntry:
    """Test ChangelogEntry class."""

    def test_changelog_entry_creation(self):
        """Test creating a changelog entry."""
        entry = ChangelogEntry(
            version="2.0.0",
            date="2024-03-20",
            changes=["New feature", "Bug fix"],
            breaking_changes=["API change"],
            deprecations=["Old method deprecated"],
        )

        assert entry.version == "2.0.0"
        assert len(entry.changes) == 2
        assert len(entry.breaking_changes) == 1
        assert len(entry.deprecations) == 1

    def test_changelog_to_dict(self):
        """Test converting changelog entry to dict."""
        entry = ChangelogEntry(
            version="1.0.0",
            date="2024-01-01",
            changes=["Initial release"],
        )

        d = entry.to_dict()
        assert d["version"] == "1.0.0"
        assert d["date"] == "2024-01-01"
        assert d["changes"] == ["Initial release"]

    def test_changelog_from_dict(self):
        """Test creating changelog entry from dict."""
        data = {
            "version": "1.5.0",
            "date": "2024-02-15",
            "changes": ["Feature A", "Feature B"],
            "breaking_changes": [],
            "deprecations": [],
        }

        entry = ChangelogEntry.from_dict(data)
        assert entry.version == "1.5.0"
        assert len(entry.changes) == 2


class TestSkillVersionRecord:
    """Test SkillVersionRecord class."""

    def test_version_record_creation(self):
        """Test creating a version record."""
        record = SkillVersionRecord(
            name="test-skill",
            version="1.0.0",
            display_name="Test Skill",
            description="A test skill",
            release_date="2024-03-20",
            is_latest=True,
        )

        assert record.name == "test-skill"
        assert record.version == "1.0.0"
        assert record.is_latest

    def test_version_record_to_dict(self):
        """Test converting version record to dict."""
        record = SkillVersionRecord(
            name="test-skill",
            version="2.0.0",
            display_name="Test Skill",
            description="Description",
            release_date="2024-03-20",
        )

        d = record.to_dict()
        assert d["name"] == "test-skill"
        assert d["version"] == "2.0.0"

    def test_version_record_from_dict(self):
        """Test creating version record from dict."""
        data = {
            "name": "my-skill",
            "version": "1.5.0",
            "display_name": "My Skill",
            "description": "My description",
            "release_date": "2024-02-01",
            "is_latest": True,
        }

        record = SkillVersionRecord.from_dict(data)
        assert record.name == "my-skill"
        assert record.is_latest


class TestVersionManager:
    """Test VersionManager class."""

    @pytest.fixture
    def temp_version_manager(self, tmp_path):
        """Create a version manager with temporary storage."""
        manager = VersionManager()
        manager.VERSION_INDEX_PATH = tmp_path / "version_index.json"
        manager._version_index = {}
        return manager

    def test_register_version(self, temp_version_manager):
        """Test registering a new version."""
        manager = temp_version_manager

        record = SkillVersionRecord(
            name="test-skill",
            version="1.0.0",
            display_name="Test",
            description="Test",
            release_date="2024-03-20",
            is_latest=True,
        )

        manager.register_version(record)

        assert "test-skill" in manager._version_index
        assert "1.0.0" in manager._version_index["test-skill"]

    def test_get_version(self, temp_version_manager):
        """Test getting a specific version."""
        manager = temp_version_manager

        record = SkillVersionRecord(
            name="test-skill",
            version="1.0.0",
            display_name="Test",
            description="Test",
            release_date="2024-03-20",
        )
        manager.register_version(record)

        result = manager.get_version("test-skill", "1.0.0")
        assert result is not None
        assert result.version == "1.0.0"

        result = manager.get_version("test-skill", "2.0.0")
        assert result is None

    def test_get_latest_version(self, temp_version_manager):
        """Test getting the latest version."""
        manager = temp_version_manager

        manager.register_version(SkillVersionRecord(
            name="test-skill",
            version="1.0.0",
            display_name="Test",
            description="Test",
            release_date="2024-03-20",
        ))

        manager.register_version(SkillVersionRecord(
            name="test-skill",
            version="2.0.0",
            display_name="Test",
            description="Test",
            release_date="2024-03-21",
            is_latest=True,
        ))

        latest = manager.get_latest_version("test-skill")
        assert latest is not None
        assert latest.version == "2.0.0"

    def test_list_versions(self, temp_version_manager):
        """Test listing all versions."""
        manager = temp_version_manager

        for version in ["1.0.0", "1.1.0", "2.0.0"]:
            manager.register_version(SkillVersionRecord(
                name="test-skill",
                version=version,
                display_name="Test",
                description="Test",
                release_date="2024-03-20",
            ))

        versions = manager.list_versions("test-skill")
        assert len(versions) == 3
        # Should be sorted newest first
        assert versions[0].version == "2.0.0"
        assert versions[1].version == "1.1.0"
        assert versions[2].version == "1.0.0"

    def test_check_update_available(self, temp_version_manager):
        """Test checking for updates."""
        manager = temp_version_manager

        manager.register_version(SkillVersionRecord(
            name="test-skill",
            version="2.0.0",
            display_name="Test",
            description="Test",
            release_date="2024-03-20",
            is_latest=True,
        ))

        # Update available
        update = manager.check_update_available("test-skill", "1.0.0")
        assert update is not None
        assert update.version == "2.0.0"

        # No update available
        update = manager.check_update_available("test-skill", "2.0.0")
        assert update is None

    def test_get_upgrade_path(self, temp_version_manager):
        """Test getting upgrade path."""
        manager = temp_version_manager

        for version in ["1.0.0", "1.1.0", "1.2.0", "2.0.0"]:
            manager.register_version(SkillVersionRecord(
                name="test-skill",
                version=version,
                display_name="Test",
                description="Test",
                release_date="2024-03-20",
                is_latest=(version == "2.0.0"),
            ))

        path = manager.get_upgrade_path("test-skill", "1.0.0", "2.0.0")
        assert len(path) == 3
        assert path[0].version == "1.1.0"
        assert path[1].version == "1.2.0"
        assert path[2].version == "2.0.0"

    def test_deprecate_version(self, temp_version_manager):
        """Test deprecating a version."""
        manager = temp_version_manager

        manager.register_version(SkillVersionRecord(
            name="test-skill",
            version="1.0.0",
            display_name="Test",
            description="Test",
            release_date="2024-03-20",
        ))

        result = manager.deprecate_version(
            "test-skill",
            "1.0.0",
            "Security vulnerability found"
        )
        assert result

        record = manager.get_version("test-skill", "1.0.0")
        assert record.is_deprecated
        assert record.deprecation_message == "Security vulnerability found"

    def test_compare_versions(self, temp_version_manager):
        """Test version comparison."""
        manager = temp_version_manager

        assert manager.compare_versions("1.0.0", "2.0.0") == -1
        assert manager.compare_versions("2.0.0", "1.0.0") == 1
        assert manager.compare_versions("1.0.0", "1.0.0") == 0

    def test_format_version_table(self, temp_version_manager):
        """Test formatting version table."""
        manager = temp_version_manager

        manager.register_version(SkillVersionRecord(
            name="test-skill",
            version="1.0.0",
            display_name="Test",
            description="Test",
            release_date="2024-03-01",
        ))

        manager.register_version(SkillVersionRecord(
            name="test-skill",
            version="2.0.0",
            display_name="Test",
            description="Test",
            release_date="2024-03-20",
            is_latest=True,
        ))

        table = manager.format_version_table("test-skill")
        assert "test-skill" in table
        assert "1.0.0" in table
        assert "2.0.0" in table
        assert "LATEST" in table

    def test_persistence(self, tmp_path):
        """Test that versions are persisted to disk."""
        # Create manager and register a version
        manager1 = VersionManager()
        manager1.VERSION_INDEX_PATH = tmp_path / "version_index.json"
        manager1._version_index = {}

        manager1.register_version(SkillVersionRecord(
            name="test-skill",
            version="1.0.0",
            display_name="Test",
            description="Test",
            release_date="2024-03-20",
        ))

        # Create new manager and verify it loads the version
        manager2 = VersionManager()
        manager2.VERSION_INDEX_PATH = tmp_path / "version_index.json"
        manager2._version_index = {}
        manager2._load_index()

        result = manager2.get_version("test-skill", "1.0.0")
        assert result is not None
        assert result.version == "1.0.0"


class TestHasBreakingChanges:
    """Test breaking changes detection."""

    @pytest.fixture
    def manager(self, tmp_path):
        """Create a version manager with temporary storage."""
        manager = VersionManager()
        manager.VERSION_INDEX_PATH = tmp_path / "version_index.json"
        manager._version_index = {}
        return manager

    def test_major_version_bump_is_breaking(self, manager):
        """Test that major version bump is considered breaking."""
        has_breaking, changes = manager.has_breaking_changes(
            "test-skill", "1.0.0", "2.0.0"
        )
        assert has_breaking
        assert len(changes) > 0
        assert "Major version" in changes[0]

    def test_minor_version_bump_not_breaking(self, manager):
        """Test that minor version bump is not breaking."""
        has_breaking, changes = manager.has_breaking_changes(
            "test-skill", "1.0.0", "1.1.0"
        )
        assert not has_breaking
        assert len(changes) == 0

    def test_patch_version_bump_not_breaking(self, manager):
        """Test that patch version bump is not breaking."""
        has_breaking, changes = manager.has_breaking_changes(
            "test-skill", "1.0.0", "1.0.1"
        )
        assert not has_breaking
