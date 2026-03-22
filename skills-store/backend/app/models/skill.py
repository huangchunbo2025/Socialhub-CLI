from sqlalchemy import Boolean, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base
from .enums import SkillCategory, SkillStatus, enum_values
from .mixins import TimestampMixin


class Skill(TimestampMixin, Base):
    __tablename__ = "skills"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    developer_id: Mapped[int] = mapped_column(ForeignKey("developers.id", ondelete="RESTRICT"), nullable=False)
    name: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    display_name: Mapped[str] = mapped_column(String(160), nullable=False)
    summary: Mapped[str] = mapped_column(Text(), nullable=False)
    description: Mapped[str] = mapped_column(Text(), nullable=False)
    license_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    license_url: Mapped[str | None] = mapped_column(String(255), nullable=True)
    homepage_url: Mapped[str | None] = mapped_column(String(255), nullable=True)
    category: Mapped[SkillCategory] = mapped_column(
        Enum(SkillCategory, name="skill_category", values_callable=enum_values),
        nullable=False,
    )
    status: Mapped[SkillStatus] = mapped_column(
        Enum(SkillStatus, name="skill_status", values_callable=enum_values),
        nullable=False,
        default=SkillStatus.ACTIVE,
    )
    featured: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    icon_url: Mapped[str | None] = mapped_column(String(255), nullable=True)
    tags: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    runtime_requirements: Mapped[list[dict] | None] = mapped_column(JSONB, nullable=True)
    install_guidance: Mapped[list[dict] | None] = mapped_column(JSONB, nullable=True)
    security_review: Mapped[list[dict] | None] = mapped_column(JSONB, nullable=True)
    docs_sections: Mapped[list[dict] | None] = mapped_column(JSONB, nullable=True)
    download_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    developer = relationship("Developer", back_populates="skills")
    versions = relationship("SkillVersion", back_populates="skill")
