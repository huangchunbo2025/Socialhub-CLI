from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class SkillCertification(Base):
    __tablename__ = "skill_certifications"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    skill_version_id: Mapped[int] = mapped_column(
        ForeignKey("skill_versions.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )
    certificate_serial: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    signature: Mapped[str] = mapped_column(Text(), nullable=False)
    payload_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    public_key_id: Mapped[str] = mapped_column(String(120), nullable=False)
    issued_by: Mapped[int] = mapped_column(ForeignKey("developers.id", ondelete="RESTRICT"), nullable=False)
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoke_reason: Mapped[str | None] = mapped_column(Text(), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    skill_version = relationship("SkillVersion", back_populates="certification")
