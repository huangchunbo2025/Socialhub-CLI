from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base
from .enums import VersionStatus, enum_values
from .mixins import TimestampMixin


class SkillVersion(TimestampMixin, Base):
    __tablename__ = "skill_versions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    skill_id: Mapped[int] = mapped_column(ForeignKey("skills.id", ondelete="CASCADE"), nullable=False)
    version: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[VersionStatus] = mapped_column(
        Enum(VersionStatus, name="version_status", values_callable=enum_values),
        nullable=False,
        default=VersionStatus.DRAFT,
    )
    package_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    package_path: Mapped[str] = mapped_column(String(500), nullable=False)
    package_size: Mapped[int] = mapped_column(nullable=False)
    package_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    manifest_json: Mapped[dict] = mapped_column(JSONB, nullable=False)
    scan_summary: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    release_notes: Mapped[str | None] = mapped_column(Text(), nullable=True)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    skill = relationship("Skill", back_populates="versions")
    certification = relationship("SkillCertification", back_populates="skill_version", uselist=False)
    reviews = relationship("SkillReview", back_populates="skill_version")
