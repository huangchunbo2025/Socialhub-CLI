from __future__ import annotations

from pydantic import BaseModel, Field


class ReviewActionRequest(BaseModel):
    comment: str | None = Field(default=None, max_length=5000)
