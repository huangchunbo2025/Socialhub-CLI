from datetime import datetime

from sqlalchemy import DateTime, Enum, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base
from .enums import DeveloperRole, DeveloperStatus, enum_values
from .mixins import TimestampMixin


class Developer(TimestampMixin, Base):
    __tablename__ = "developers"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String(200), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    role: Mapped[DeveloperRole] = mapped_column(
        Enum(DeveloperRole, name="developer_role", values_callable=enum_values),
        nullable=False,
    )
    status: Mapped[DeveloperStatus] = mapped_column(
        Enum(DeveloperStatus, name="developer_status", values_callable=enum_values),
        nullable=False,
        default=DeveloperStatus.ACTIVE,
    )
    bio: Mapped[str | None] = mapped_column(Text(), nullable=True)
    website: Mapped[str | None] = mapped_column(String(255), nullable=True)
    saved_skills: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    skills = relationship("Skill", back_populates="developer")
