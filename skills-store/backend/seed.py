from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from sqlalchemy import select

from app.database import SessionLocal
from app.models import (
    Developer,
    DeveloperRole,
    DeveloperStatus,
    ReviewStatus,
    Skill,
    SkillCategory,
    SkillReview,
    SkillStatus,
    SkillVersion,
    VersionStatus,
)
from app.services.auth import hash_password, normalize_email


async def ensure_developer(
    *,
    email: str,
    password: str,
    name: str,
    role: DeveloperRole,
) -> Developer:
    async with SessionLocal() as session:
        result = await session.execute(
            select(Developer).where(Developer.email == normalize_email(email))
        )
        existing = result.scalar_one_or_none()
        if existing is not None:
            return existing

        developer = Developer(
            email=normalize_email(email),
            password_hash=hash_password(password),
            name=name,
            role=role,
            status=DeveloperStatus.ACTIVE,
        )
        session.add(developer)
        await session.commit()
        await session.refresh(developer)
        return developer


async def seed_demo_data() -> None:
    admin = await ensure_developer(
        email="admin@skills-store.local",
        password="Admin123!",
        name="Store Admin",
        role=DeveloperRole.STORE_ADMIN,
    )
    developer = await ensure_developer(
        email="developer@skills-store.local",
        password="Developer123!",
        name="Demo Developer",
        role=DeveloperRole.DEVELOPER,
    )

    async with SessionLocal() as session:
        result = await session.execute(select(Skill).where(Skill.name == "sales-daily-brief"))
        existing_skill = result.scalar_one_or_none()
        if existing_skill is not None:
            return

        skill = Skill(
            developer_id=developer.id,
            name="sales-daily-brief",
            display_name="Sales Daily Brief",
            summary="Generates a structured sales brief from CRM pipeline data.",
            description="Summarizes pipeline movement, key risks, and next actions for sales leaders.",
            category=SkillCategory.ANALYTICS,
            status=SkillStatus.ACTIVE,
            featured=True,
            icon_url=None,
            tags=["sales", "crm", "briefing"],
            download_count=42,
        )
        session.add(skill)
        await session.flush()

        version = SkillVersion(
            skill_id=skill.id,
            version="1.0.0",
            status=VersionStatus.PUBLISHED,
            package_filename="sales-daily-brief-1.0.0.zip",
            package_path="./data/packages/demo/sales-daily-brief-1.0.0.zip",
            package_size=10240,
            package_hash="demo-sales-daily-brief-hash",
            manifest_json={
                "name": "sales-daily-brief",
                "version": "1.0.0",
                "display_name": "Sales Daily Brief",
            },
            scan_summary={"status": "passed", "risk_level": "low", "issues": []},
            release_notes="Initial demo release",
            submitted_at=datetime.now(UTC),
            published_at=datetime.now(UTC),
        )
        session.add(version)
        await session.flush()

        review = SkillReview(
            skill_version_id=version.id,
            reviewer_id=admin.id,
            status=ReviewStatus.APPROVED,
            comment="Approved as demo seed data",
            scan_result_json={"status": "passed", "issues": []},
            started_at=datetime.now(UTC),
            completed_at=datetime.now(UTC),
        )
        session.add(review)
        await session.commit()


if __name__ == "__main__":
    asyncio.run(seed_demo_data())
