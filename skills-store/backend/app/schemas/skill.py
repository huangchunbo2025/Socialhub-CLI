from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class CreateSkillRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    display_name: str = Field(min_length=1, max_length=160)
    summary: str = Field(min_length=1)
    description: str = Field(min_length=1)
    category: str
    tags: list[str] = Field(default_factory=list)
    icon_url: str | None = None


class SkillResponse(BaseModel):
    id: int
    name: str
    display_name: str
    summary: str
    description: str
    license_name: str | None = None
    license_url: str | None = None
    homepage_url: str | None = None
    category: str
    status: str
    featured: bool
    tags: list[str]
    runtime_requirements: list[dict] = Field(default_factory=list)
    install_guidance: list[dict] = Field(default_factory=list)
    security_review: list[dict] = Field(default_factory=list)
    docs_sections: list[dict] = Field(default_factory=list)
    download_count: int
    latest_version: str | None = None
    developer: dict[str, str | int] | None = None


class SkillVersionResponse(BaseModel):
    id: int
    version: str
    status: str
    package_hash: str
    package_size: int
    release_notes: str | None
    submitted_at: datetime | None
    published_at: datetime | None


class DownloadInfoResponse(BaseModel):
    skill_name: str
    version: str
    package_hash: str
    package_size: int
    signature: str | None
    certificate_serial: str | None
    public_key_id: str | None
    download_url: str


class CheckUpdatesRequest(BaseModel):
    skills: list[dict[str, str]]
