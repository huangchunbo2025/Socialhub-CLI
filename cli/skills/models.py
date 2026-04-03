"""Skill data models and specifications."""

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class SkillCategory(str, Enum):
    """Skill category enumeration."""

    DATA = "data"
    MARKETING = "marketing"
    ANALYTICS = "analytics"
    INTEGRATION = "integration"
    UTILITY = "utility"


class SkillPermission(str, Enum):
    """Skill permission enumeration."""

    FILE_READ = "file:read"
    FILE_WRITE = "file:write"
    NETWORK_LOCAL = "network:local"
    NETWORK_INTERNET = "network:internet"
    DATA_READ = "data:read"
    DATA_WRITE = "data:write"
    CONFIG_READ = "config:read"
    CONFIG_WRITE = "config:write"
    EXECUTE = "execute"


class SkillStatus(str, Enum):
    """Skill status enumeration."""

    DRAFT = "draft"
    REVIEW = "review"
    PUBLISHED = "published"
    SUSPENDED = "suspended"
    DEPRECATED = "deprecated"


class SkillCommand(BaseModel):
    """Skill command definition."""

    name: str = Field(..., description="Command name")
    description: str = Field("", description="Command description")
    function: str = Field(..., description="Function to call")
    arguments: list[dict[str, Any]] = Field(default_factory=list, description="Command arguments")


class SkillCompatibility(BaseModel):
    """Skill compatibility requirements."""

    cli_version: str = Field(">=0.1.0", description="Minimum CLI version")
    python_version: str = Field(">=3.10", description="Minimum Python version")


class SkillDependencies(BaseModel):
    """Skill dependencies."""

    python: list[str] = Field(default_factory=list, description="Python package dependencies")
    skills: list[str] = Field(default_factory=list, description="Skill dependencies")


class SkillCertification(BaseModel):
    """Skill certification information."""

    certified_at: datetime | None = None
    certified_by: str = "SocialHub.AI"
    signature: str = ""
    certificate_id: str = ""
    expires_at: datetime | None = None


class SkillManifest(BaseModel):
    """Skill manifest (skill.yaml content)."""

    # Basic info
    name: str = Field(..., description="Skill name (unique identifier)")
    version: str = Field(..., description="Semantic version")
    display_name: str = Field("", description="Display name")
    description: str = Field("", description="Skill description")
    author: str = Field("", description="Author name")
    license: str = Field("MIT", description="License type")
    homepage: str = Field("", description="Homepage URL")

    # Classification
    category: SkillCategory = Field(SkillCategory.UTILITY, description="Skill category")
    tags: list[str] = Field(default_factory=list, description="Tags")

    # Compatibility
    compatibility: SkillCompatibility = Field(default_factory=SkillCompatibility)

    # Dependencies
    dependencies: SkillDependencies = Field(default_factory=SkillDependencies)

    # Permissions
    permissions: list[SkillPermission] = Field(default_factory=list)

    # Entry point
    entrypoint: str = Field("main.py", description="Main entry file")
    commands: list[SkillCommand] = Field(default_factory=list)

    # Certification
    certification: SkillCertification | None = None


class InstalledSkill(BaseModel):
    """Installed skill record."""

    name: str
    version: str
    display_name: str = ""
    description: str = ""
    category: SkillCategory = SkillCategory.UTILITY
    installed_at: datetime = Field(default_factory=datetime.now)
    path: str = ""
    enabled: bool = True
    manifest: SkillManifest | None = None


class SkillSearchResult(BaseModel):
    """Skill search result from store."""

    name: str
    display_name: str
    description: str
    version: str
    author: str
    category: SkillCategory
    downloads: int = 0
    rating: float = 0.0
    tags: list[str] = Field(default_factory=list)
    certified: bool = True


class SkillDetail(BaseModel):
    """Detailed skill information."""

    name: str
    display_name: str
    description: str
    version: str
    author: str
    license: str
    homepage: str
    category: SkillCategory
    tags: list[str] = Field(default_factory=list)
    downloads: int = 0
    rating: float = 0.0
    permissions: list[SkillPermission] = Field(default_factory=list)
    dependencies: SkillDependencies = Field(default_factory=SkillDependencies)
    commands: list[SkillCommand] = Field(default_factory=list)
    versions: list[str] = Field(default_factory=list)
    certified: bool = True
    certification: SkillCertification | None = None
    readme: str = ""
    changelog: str = ""
