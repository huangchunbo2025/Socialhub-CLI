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
        detail_payload = {
            "description": (
                "Sales Daily Brief turns CRM pipeline activity into a concise operating brief for revenue leaders. "
                "It highlights movement by stage, identifies risk concentration, and surfaces the follow-up actions "
                "that should happen in the next business cycle."
            ),
            "license_name": "MIT",
            "license_url": "https://opensource.org/licenses/MIT",
            "homepage_url": "https://socialhub.ai/skills/sales-daily-brief",
            "runtime_requirements": [
                {
                    "title": "Required environment",
                    "items": [
                        "SocialHub CLI with store access enabled",
                        "A connected CRM or pipeline data source",
                        "An operator account with permission to run reporting workflows",
                    ],
                },
                {
                    "title": "Operational expectations",
                    "items": [
                        "Pipeline fields should be normalized before the brief is generated",
                        "Teams should validate which stage definitions are used in the report",
                    ],
                },
            ],
            "install_guidance": [
                {
                    "title": "Install latest",
                    "command": "socialhub skills install sales-daily-brief",
                    "body": "Use the latest published build when your team wants the current approved release.",
                },
                {
                    "title": "Install a pinned version",
                    "command": "socialhub skills install sales-daily-brief@1.0.0",
                    "body": "Pin a version for controlled rollout, auditability, or reproducible test environments.",
                },
            ],
            "security_review": [
                {
                    "title": "Review posture",
                    "body": "This demo release is treated as a reviewed analytics skill with package metadata and release lineage visible through the store APIs.",
                },
                {
                    "title": "Trust signals",
                    "items": [
                        "Publisher identity is stable across the catalog and review flow",
                        "Release package metadata is available before installation",
                        "Version history can be reviewed before operators install the skill",
                    ],
                },
            ],
            "docs_sections": [
                {
                    "title": "What it does",
                    "body": "Produces a morning-ready summary of pipeline movement, deal risk, and next actions for sales leadership.",
                },
                {
                    "title": "Expected files",
                    "items": [
                        "Skill manifest",
                        "Release archive",
                        "Version-specific release notes",
                    ],
                },
            ],
        }
        if existing_skill is not None:
            existing_skill.description = detail_payload["description"]
            existing_skill.license_name = detail_payload["license_name"]
            existing_skill.license_url = detail_payload["license_url"]
            existing_skill.homepage_url = detail_payload["homepage_url"]
            existing_skill.runtime_requirements = detail_payload["runtime_requirements"]
            existing_skill.install_guidance = detail_payload["install_guidance"]
            existing_skill.security_review = detail_payload["security_review"]
            existing_skill.docs_sections = detail_payload["docs_sections"]
            await session.commit()
            return

        skill = Skill(
            developer_id=developer.id,
            name="sales-daily-brief",
            display_name="Sales Daily Brief",
            summary="Generates a structured sales brief from CRM pipeline data.",
            description=detail_payload["description"],
            license_name=detail_payload["license_name"],
            license_url=detail_payload["license_url"],
            homepage_url=detail_payload["homepage_url"],
            category=SkillCategory.ANALYTICS,
            status=SkillStatus.ACTIVE,
            featured=True,
            icon_url=None,
            tags=["sales", "crm", "briefing"],
            runtime_requirements=detail_payload["runtime_requirements"],
            install_guidance=detail_payload["install_guidance"],
            security_review=detail_payload["security_review"],
            docs_sections=detail_payload["docs_sections"],
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
