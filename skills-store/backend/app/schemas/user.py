from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class UserRegisterRequest(BaseModel):
    email: str
    password: str = Field(min_length=8)
    name: str = Field(min_length=1, max_length=200)


class UserLoginRequest(BaseModel):
    email: str
    password: str = Field(min_length=8)


class StorefrontUserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    name: str
    status: str


class UserSkillUpsertRequest(BaseModel):
    version: str | None = Field(default=None, max_length=50)


class UserSkillToggleRequest(BaseModel):
    enabled: bool


class UserSkillItemResponse(BaseModel):
    skill_name: str
    display_name: str
    version: str
    category: str
    is_enabled: bool
    downloaded_at: str
    description: str
    package_hash: str | None = None
