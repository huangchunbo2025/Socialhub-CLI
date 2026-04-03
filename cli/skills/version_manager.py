"""Skill Version Manager for SocialHub.AI CLI.

This module provides version management functionality for skills,
including version comparison, upgrade/downgrade, and changelog tracking.
"""

import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml


@dataclass
class VersionInfo:
    """Version information for a skill."""

    major: int
    minor: int
    patch: int
    prerelease: str = ""
    build: str = ""

    @classmethod
    def parse(cls, version_string: str) -> "VersionInfo":
        """Parse a semantic version string.

        Args:
            version_string: Version string like "1.2.3", "2.0.0-beta.1"

        Returns:
            VersionInfo instance
        """
        # Regex for semantic versioning
        pattern = r"^(\d+)\.(\d+)\.(\d+)(?:-([a-zA-Z0-9.]+))?(?:\+([a-zA-Z0-9.]+))?$"
        match = re.match(pattern, version_string.strip())

        if not match:
            raise ValueError(f"Invalid version format: {version_string}")

        return cls(
            major=int(match.group(1)),
            minor=int(match.group(2)),
            patch=int(match.group(3)),
            prerelease=match.group(4) or "",
            build=match.group(5) or "",
        )

    def __str__(self) -> str:
        """Convert to string representation."""
        version = f"{self.major}.{self.minor}.{self.patch}"
        if self.prerelease:
            version += f"-{self.prerelease}"
        if self.build:
            version += f"+{self.build}"
        return version

    def __lt__(self, other: "VersionInfo") -> bool:
        """Compare versions for less than."""
        if (self.major, self.minor, self.patch) != (other.major, other.minor, other.patch):
            return (self.major, self.minor, self.patch) < (other.major, other.minor, other.patch)
        # Prerelease versions are less than release versions
        if self.prerelease and not other.prerelease:
            return True
        if not self.prerelease and other.prerelease:
            return False
        return self.prerelease < other.prerelease

    def __eq__(self, other: object) -> bool:
        """Compare versions for equality."""
        if not isinstance(other, VersionInfo):
            return False
        return (
            self.major == other.major
            and self.minor == other.minor
            and self.patch == other.patch
            and self.prerelease == other.prerelease
        )

    def __le__(self, other: "VersionInfo") -> bool:
        return self < other or self == other

    def __gt__(self, other: "VersionInfo") -> bool:
        return not self <= other

    def __ge__(self, other: "VersionInfo") -> bool:
        return not self < other

    def is_compatible_with(self, other: "VersionInfo") -> bool:
        """Check if this version is compatible with another (same major version)."""
        return self.major == other.major


@dataclass
class ChangelogEntry:
    """A single changelog entry."""

    version: str
    date: str
    changes: list[str]
    breaking_changes: list[str] = field(default_factory=list)
    deprecations: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "version": self.version,
            "date": self.date,
            "changes": self.changes,
            "breaking_changes": self.breaking_changes,
            "deprecations": self.deprecations,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ChangelogEntry":
        """Create from dictionary."""
        return cls(
            version=data["version"],
            date=data["date"],
            changes=data.get("changes", []),
            breaking_changes=data.get("breaking_changes", []),
            deprecations=data.get("deprecations", []),
        )


@dataclass
class SkillVersionRecord:
    """Record of a skill version in the store."""

    name: str
    version: str
    display_name: str
    description: str
    release_date: str
    download_url: str = ""
    checksum: str = ""
    size_bytes: int = 0
    changelog: list[str] = field(default_factory=list)
    min_cli_version: str = "0.1.0"
    is_latest: bool = False
    is_deprecated: bool = False
    deprecation_message: str = ""

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "name": self.name,
            "version": self.version,
            "display_name": self.display_name,
            "description": self.description,
            "release_date": self.release_date,
            "download_url": self.download_url,
            "checksum": self.checksum,
            "size_bytes": self.size_bytes,
            "changelog": self.changelog,
            "min_cli_version": self.min_cli_version,
            "is_latest": self.is_latest,
            "is_deprecated": self.is_deprecated,
            "deprecation_message": self.deprecation_message,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "SkillVersionRecord":
        """Create from dictionary."""
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


class VersionManager:
    """Manage skill versions in the store."""

    # Path to version index
    VERSION_INDEX_PATH = Path.home() / ".socialhub" / "skills" / "version_index.json"

    def __init__(self):
        self._logger = logging.getLogger(__name__)
        self._version_index: dict[str, dict[str, SkillVersionRecord]] = {}
        self._load_index()

    def _load_index(self) -> None:
        """Load version index from disk."""
        if self.VERSION_INDEX_PATH.exists():
            try:
                with open(self.VERSION_INDEX_PATH, encoding="utf-8") as f:
                    data = json.load(f)
                for skill_name, versions in data.items():
                    self._version_index[skill_name] = {
                        v: SkillVersionRecord.from_dict(info)
                        for v, info in versions.items()
                    }
            except Exception as e:
                self._logger.warning("Failed to load version index: %s", e)
                self._version_index = {}

    def _save_index(self) -> None:
        """Save version index to disk."""
        self.VERSION_INDEX_PATH.parent.mkdir(parents=True, exist_ok=True)
        data = {
            skill: {v: record.to_dict() for v, record in versions.items()}
            for skill, versions in self._version_index.items()
        }
        with open(self.VERSION_INDEX_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def register_version(self, record: SkillVersionRecord) -> None:
        """Register a new skill version.

        Args:
            record: Version record to register
        """
        if record.name not in self._version_index:
            self._version_index[record.name] = {}

        # Update latest flag
        if record.is_latest:
            for v in self._version_index[record.name].values():
                v.is_latest = False

        self._version_index[record.name][record.version] = record
        self._save_index()
        self._logger.info("Registered %s v%s", record.name, record.version)

    def get_version(self, skill_name: str, version: str) -> SkillVersionRecord | None:
        """Get a specific version record.

        Args:
            skill_name: Skill name
            version: Version string

        Returns:
            SkillVersionRecord or None
        """
        return self._version_index.get(skill_name, {}).get(version)

    def get_latest_version(self, skill_name: str) -> SkillVersionRecord | None:
        """Get the latest version of a skill.

        Args:
            skill_name: Skill name

        Returns:
            Latest SkillVersionRecord or None
        """
        versions = self._version_index.get(skill_name, {})
        if not versions:
            return None

        # Find the one marked as latest
        for record in versions.values():
            if record.is_latest:
                return record

        # Fall back to highest version number
        sorted_versions = sorted(
            versions.keys(),
            key=lambda v: VersionInfo.parse(v),
            reverse=True
        )
        return versions[sorted_versions[0]] if sorted_versions else None

    def list_versions(
        self,
        skill_name: str,
        include_deprecated: bool = False
    ) -> list[SkillVersionRecord]:
        """List all versions of a skill.

        Args:
            skill_name: Skill name
            include_deprecated: Whether to include deprecated versions

        Returns:
            List of version records, sorted newest first
        """
        versions = self._version_index.get(skill_name, {})
        records = list(versions.values())

        if not include_deprecated:
            records = [r for r in records if not r.is_deprecated]

        # Sort by version number, newest first
        records.sort(key=lambda r: VersionInfo.parse(r.version), reverse=True)
        return records

    def check_update_available(
        self,
        skill_name: str,
        current_version: str
    ) -> SkillVersionRecord | None:
        """Check if an update is available for a skill.

        Args:
            skill_name: Skill name
            current_version: Currently installed version

        Returns:
            SkillVersionRecord of newer version if available, None otherwise
        """
        latest = self.get_latest_version(skill_name)
        if not latest:
            return None

        current = VersionInfo.parse(current_version)
        latest_v = VersionInfo.parse(latest.version)

        if latest_v > current:
            return latest
        return None

    def get_upgrade_path(
        self,
        skill_name: str,
        from_version: str,
        to_version: str = None
    ) -> list[SkillVersionRecord]:
        """Get the upgrade path between two versions.

        Args:
            skill_name: Skill name
            from_version: Starting version
            to_version: Target version (default: latest)

        Returns:
            List of version records in upgrade order
        """
        if to_version is None:
            latest = self.get_latest_version(skill_name)
            if not latest:
                return []
            to_version = latest.version

        from_v = VersionInfo.parse(from_version)
        to_v = VersionInfo.parse(to_version)

        if from_v >= to_v:
            return []

        versions = self.list_versions(skill_name, include_deprecated=False)
        upgrade_path = []

        for record in reversed(versions):
            record_v = VersionInfo.parse(record.version)
            if from_v < record_v <= to_v:
                upgrade_path.append(record)

        return upgrade_path

    def has_breaking_changes(
        self,
        skill_name: str,
        from_version: str,
        to_version: str
    ) -> tuple[bool, list[str]]:
        """Check if there are breaking changes between versions.

        Args:
            skill_name: Skill name
            from_version: Starting version
            to_version: Target version

        Returns:
            Tuple of (has_breaking_changes, list of breaking change descriptions)
        """
        from_v = VersionInfo.parse(from_version)
        to_v = VersionInfo.parse(to_version)

        # Major version change indicates breaking changes
        if from_v.major != to_v.major:
            return True, [f"Major version upgrade from {from_v.major} to {to_v.major}"]

        # Check changelog for breaking changes
        upgrade_path = self.get_upgrade_path(skill_name, from_version, to_version)
        breaking_changes = []

        for record in upgrade_path:
            # This would check the actual changelog
            # For now, we just check if it's a major version bump
            pass

        return len(breaking_changes) > 0, breaking_changes

    def deprecate_version(
        self,
        skill_name: str,
        version: str,
        message: str = ""
    ) -> bool:
        """Mark a version as deprecated.

        Args:
            skill_name: Skill name
            version: Version to deprecate
            message: Deprecation message

        Returns:
            True if successful
        """
        record = self.get_version(skill_name, version)
        if not record:
            return False

        record.is_deprecated = True
        record.deprecation_message = message
        self._save_index()
        return True

    def compare_versions(self, version1: str, version2: str) -> int:
        """Compare two version strings.

        Args:
            version1: First version
            version2: Second version

        Returns:
            -1 if v1 < v2, 0 if equal, 1 if v1 > v2
        """
        v1 = VersionInfo.parse(version1)
        v2 = VersionInfo.parse(version2)

        if v1 < v2:
            return -1
        elif v1 > v2:
            return 1
        return 0

    def format_version_table(self, skill_name: str) -> str:
        """Format version information as a table.

        Args:
            skill_name: Skill name

        Returns:
            Formatted table string
        """
        versions = self.list_versions(skill_name, include_deprecated=True)
        if not versions:
            return f"No versions found for skill: {skill_name}"

        lines = [
            f"Versions for {skill_name}:",
            "-" * 60,
            f"{'Version':<12} {'Release Date':<15} {'Status':<15} {'Notes'}",
            "-" * 60,
        ]

        for record in versions:
            status = "LATEST" if record.is_latest else ("DEPRECATED" if record.is_deprecated else "")
            notes = record.deprecation_message if record.is_deprecated else ""
            lines.append(
                f"{record.version:<12} {record.release_date:<15} {status:<15} {notes}"
            )

        return "\n".join(lines)


def load_skill_versions_from_manifest(skill_path: Path) -> list[ChangelogEntry]:
    """Load version changelog from skill manifest.

    Args:
        skill_path: Path to skill directory

    Returns:
        List of changelog entries
    """
    manifest_path = skill_path / "skill.yaml"
    if not manifest_path.exists():
        return []

    with open(manifest_path, encoding="utf-8") as f:
        manifest = yaml.safe_load(f)

    changelog_data = manifest.get("changelog", [])
    entries = []

    for entry in changelog_data:
        if isinstance(entry, dict):
            entries.append(ChangelogEntry(
                version=entry.get("version", ""),
                date=entry.get("date", ""),
                changes=entry.get("changes", []),
                breaking_changes=entry.get("breaking_changes", []),
                deprecations=entry.get("deprecations", []),
            ))

    return entries
