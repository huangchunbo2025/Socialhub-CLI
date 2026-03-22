from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class RegisterRequest(BaseModel):
    email: str
    password: str = Field(min_length=8)
    name: str = Field(min_length=1, max_length=200)


class LoginRequest(BaseModel):
    email: str
    password: str = Field(min_length=8)


class UpdateProfileRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    bio: str | None = Field(default=None, max_length=5000)
    website: str | None = Field(default=None, max_length=255)


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    name: str
    role: str
    status: str
    bio: str | None
    website: str | None
    saved_skills: list[str] = []


class SavedSkillsRequest(BaseModel):
    skill_names: list[str] = []


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserResponse
