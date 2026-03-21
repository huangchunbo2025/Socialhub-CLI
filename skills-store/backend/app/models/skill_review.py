from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base
from .enums import ReviewStatus


class SkillReview(Base):
    __tablename__ = "skill_reviews"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    skill_version_id: Mapped[int] = mapped_column(ForeignKey("skill_versions.id", ondelete="CASCADE"), nullable=False)
    reviewer_id: Mapped[int | None] = mapped_column(ForeignKey("developers.id", ondelete="RESTRICT"), nullable=True)
    status: Mapped[ReviewStatus] = mapped_column(
        Enum(ReviewStatus, name="review_status"),
        nullable=False,
        default=ReviewStatus.PENDING,
    )
    comment: Mapped[str | None] = mapped_column(Text(), nullable=True)
    scan_result_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    skill_version = relationship("SkillVersion", back_populates="reviews")
