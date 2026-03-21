from __future__ import annotations

from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlalchemy import Select, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..models import (
    Developer,
    ReviewStatus,
    Skill,
    SkillCategory,
    SkillCertification,
    SkillReview,
    SkillStatus,
    SkillVersion,
    VersionStatus,
)
from .certificates import issue_certificate

PUBLIC_VISIBLE_VERSION_STATUSES = {
    VersionStatus.PUBLISHED,
    VersionStatus.DEPRECATED,
    VersionStatus.REVOKED,
}


def _error(code: str, message: str, http_status: int) -> HTTPException:
    return HTTPException(
        status_code=http_status,
        detail={"error": {"code": code, "message": message}},
    )


def _normalize_skill_name(name: str) -> str:
    return name.strip().lower().replace(" ", "-")


def _latest_public_version(versions: list[SkillVersion]) -> SkillVersion | None:
    visible = [v for v in versions if v.status in PUBLIC_VISIBLE_VERSION_STATUSES]
    if not visible:
        return None
    return max(visible, key=lambda item: (item.published_at or datetime.min.replace(tzinfo=UTC), item.id))


def serialize_skill(skill: Skill) -> dict:
    latest_version = _latest_public_version(list(skill.versions))
    return {
        "id": skill.id,
        "name": skill.name,
        "display_name": skill.display_name,
        "summary": skill.summary,
        "description": skill.description,
        "category": skill.category.value,
        "status": skill.status.value,
        "featured": skill.featured,
        "tags": skill.tags,
        "download_count": skill.download_count,
        "latest_version": latest_version.version if latest_version else None,
        "developer": {
            "id": skill.developer.id,
            "name": skill.developer.name,
        }
        if skill.developer
        else None,
    }


def serialize_skill_version(version: SkillVersion) -> dict:
    return {
        "id": version.id,
        "version": version.version,
        "status": version.status.value,
        "package_hash": version.package_hash,
        "package_size": version.package_size,
        "release_notes": version.release_notes,
        "submitted_at": version.submitted_at,
        "published_at": version.published_at,
    }


def serialize_review(review: SkillReview) -> dict:
    return {
        "id": review.id,
        "status": review.status.value,
        "comment": review.comment,
        "started_at": review.started_at,
        "completed_at": review.completed_at,
        "scan_result_json": review.scan_result_json,
    }


async def list_public_skills(
    session: AsyncSession,
    *,
    search: str | None,
    category: str | None,
    page: int,
    limit: int,
    featured_only: bool = False,
) -> tuple[list[dict], int]:
    filters = [Skill.status == SkillStatus.ACTIVE]
    if category:
        try:
            filters.append(Skill.category == SkillCategory(category))
        except ValueError:
            return [], 0
    if featured_only:
        filters.append(Skill.featured.is_(True))
    if search:
        pattern = f"%{search.strip()}%"
        filters.append(
            or_(
                Skill.name.ilike(pattern),
                Skill.display_name.ilike(pattern),
                Skill.summary.ilike(pattern),
            )
        )

    count_stmt = select(func.count()).select_from(Skill).where(*filters)
    total = int((await session.execute(count_stmt)).scalar_one())

    stmt: Select[tuple[Skill]] = (
        select(Skill)
        .where(*filters)
        .options(selectinload(Skill.developer), selectinload(Skill.versions))
        .order_by(Skill.featured.desc(), Skill.download_count.desc(), Skill.id.desc())
        .offset((page - 1) * limit)
        .limit(limit)
    )
    result = await session.execute(stmt)
    skills = result.scalars().unique().all()
    return [serialize_skill(skill) for skill in skills], total


async def get_skill_by_name(session: AsyncSession, name: str) -> Skill | None:
    stmt: Select[tuple[Skill]] = (
        select(Skill)
        .where(Skill.name == _normalize_skill_name(name))
        .options(selectinload(Skill.developer), selectinload(Skill.versions))
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def get_public_skill_or_404(session: AsyncSession, name: str) -> Skill:
    skill = await get_skill_by_name(session, name)
    if skill is None or skill.status != SkillStatus.ACTIVE:
        raise _error("SKILL_NOT_FOUND", "Skill not found", status.HTTP_404_NOT_FOUND)
    return skill


async def list_public_versions(session: AsyncSession, name: str) -> list[dict]:
    skill = await get_public_skill_or_404(session, name)
    visible_versions = [
        serialize_skill_version(version)
        for version in sorted(skill.versions, key=lambda item: item.id, reverse=True)
        if version.status in PUBLIC_VISIBLE_VERSION_STATUSES
    ]
    return visible_versions


async def create_skill(
    session: AsyncSession,
    *,
    developer: Developer,
    name: str,
    display_name: str,
    summary: str,
    description: str,
    category: str,
    tags: list[str],
    icon_url: str | None,
) -> Skill:
    normalized_name = _normalize_skill_name(name)
    existing = await get_skill_by_name(session, normalized_name)
    if existing is not None:
        raise _error("INVALID_REQUEST", "Skill name already exists", status.HTTP_409_CONFLICT)

    try:
        category_enum = SkillCategory(category)
    except ValueError as exc:
        raise _error("INVALID_REQUEST", "Unsupported skill category", status.HTTP_422_UNPROCESSABLE_ENTITY) from exc

    skill = Skill(
        developer_id=developer.id,
        name=normalized_name,
        display_name=display_name.strip(),
        summary=summary.strip(),
        description=description.strip(),
        category=category_enum,
        status=SkillStatus.ACTIVE,
        featured=False,
        tags=[tag.strip() for tag in tags if tag.strip()],
        icon_url=icon_url.strip() if icon_url else None,
        download_count=0,
    )
    session.add(skill)
    await session.commit()
    refreshed = await get_skill_by_name(session, normalized_name)
    if refreshed is None:
        raise _error("INVALID_REQUEST", "Failed to create skill", status.HTTP_500_INTERNAL_SERVER_ERROR)
    return refreshed


async def list_developer_skills(session: AsyncSession, developer: Developer) -> list[dict]:
    stmt: Select[tuple[Skill]] = (
        select(Skill)
        .where(Skill.developer_id == developer.id)
        .options(selectinload(Skill.developer), selectinload(Skill.versions))
        .order_by(Skill.id.desc())
    )
    result = await session.execute(stmt)
    skills = result.scalars().unique().all()
    return [serialize_skill(skill) for skill in skills]


async def get_developer_skill_or_404(session: AsyncSession, developer: Developer, name: str) -> Skill:
    skill = await get_skill_by_name(session, name)
    if skill is None or skill.developer_id != developer.id:
        raise _error("SKILL_NOT_FOUND", "Skill not found", status.HTTP_404_NOT_FOUND)
    return skill


async def create_skill_version(
    session: AsyncSession,
    *,
    skill: Skill,
    version: str,
    package_filename: str,
    package_path: str,
    package_size: int,
    package_hash: str,
    manifest_json: dict,
    scan_summary: dict,
    scan_detail: dict,
    release_notes: str | None,
) -> SkillVersion:
    existing_stmt: Select[tuple[SkillVersion]] = select(SkillVersion).where(
        SkillVersion.skill_id == skill.id,
        SkillVersion.version == version,
    )
    existing = (await session.execute(existing_stmt)).scalar_one_or_none()
    if existing is not None:
        raise _error("DUPLICATE_VERSION", "Version already exists", status.HTTP_409_CONFLICT)

    now = datetime.now(UTC)
    skill_version = SkillVersion(
        skill_id=skill.id,
        version=version,
        status=VersionStatus.REVIEWING,
        package_filename=package_filename,
        package_path=package_path,
        package_size=package_size,
        package_hash=package_hash,
        manifest_json=manifest_json,
        scan_summary=scan_summary,
        release_notes=release_notes.strip() if release_notes else None,
        submitted_at=now,
    )
    session.add(skill_version)
    await session.flush()

    review = SkillReview(
        skill_version_id=skill_version.id,
        reviewer_id=None,
        status=ReviewStatus.PENDING,
        comment=None,
        scan_result_json=scan_detail,
    )
    session.add(review)
    await session.commit()
    await session.refresh(skill_version)
    return skill_version


async def get_latest_downloadable_version(session: AsyncSession, name: str, version: str | None = None) -> tuple[Skill, SkillVersion, SkillCertification | None]:
    skill = await get_public_skill_or_404(session, name)
    candidates = [item for item in skill.versions if item.status == VersionStatus.PUBLISHED]
    if version:
        candidates = [item for item in candidates if item.version == version]
    if not candidates:
        raise _error("VERSION_NOT_FOUND", "Version not found", status.HTTP_404_NOT_FOUND)

    chosen = max(candidates, key=lambda item: (item.published_at or datetime.min.replace(tzinfo=UTC), item.id))
    cert_stmt: Select[tuple[SkillCertification]] = select(SkillCertification).where(
        SkillCertification.skill_version_id == chosen.id
    )
    certification = (await session.execute(cert_stmt)).scalar_one_or_none()
    return skill, chosen, certification


async def list_reviews(
    session: AsyncSession,
    *,
    status_filter: str | None,
    page: int,
    limit: int,
) -> tuple[list[dict], int]:
    filters = []
    if status_filter:
        try:
            filters.append(SkillReview.status == ReviewStatus(status_filter))
        except ValueError:
            return [], 0

    count_stmt = select(func.count()).select_from(SkillReview).where(*filters)
    total = int((await session.execute(count_stmt)).scalar_one())

    stmt: Select[tuple[SkillReview]] = (
        select(SkillReview)
        .where(*filters)
        .options(
            selectinload(SkillReview.skill_version).selectinload(SkillVersion.skill).selectinload(Skill.developer)
        )
        .order_by(SkillReview.created_at.desc(), SkillReview.id.desc())
        .offset((page - 1) * limit)
        .limit(limit)
    )
    result = await session.execute(stmt)
    reviews = result.scalars().unique().all()
    data = []
    for review in reviews:
        version = review.skill_version
        skill = version.skill
        data.append(
            {
                **serialize_review(review),
                "skill_name": skill.name,
                "display_name": skill.display_name,
                "version": version.version,
                "version_status": version.status.value,
                "developer": {
                    "id": skill.developer.id,
                    "name": skill.developer.name,
                },
                "scan_summary": version.scan_summary,
            }
        )
    return data, total


async def get_review_or_404(session: AsyncSession, review_id: int) -> SkillReview:
    stmt: Select[tuple[SkillReview]] = (
        select(SkillReview)
        .where(SkillReview.id == review_id)
        .options(selectinload(SkillReview.skill_version).selectinload(SkillVersion.skill))
    )
    review = (await session.execute(stmt)).scalar_one_or_none()
    if review is None:
        raise _error("REVIEW_NOT_FOUND", "Review not found", status.HTTP_404_NOT_FOUND)
    return review


async def start_review(session: AsyncSession, review_id: int, reviewer: Developer) -> SkillReview:
    review = await get_review_or_404(session, review_id)
    if review.status not in {ReviewStatus.PENDING, ReviewStatus.IN_REVIEW}:
        raise _error("INVALID_REQUEST", "Review cannot be started", status.HTTP_409_CONFLICT)

    review.status = ReviewStatus.IN_REVIEW
    review.reviewer_id = reviewer.id
    review.started_at = datetime.now(UTC)
    await session.commit()
    await session.refresh(review)
    return review


async def approve_review(session: AsyncSession, review_id: int, reviewer: Developer, comment: str | None) -> SkillReview:
    review = await get_review_or_404(session, review_id)
    if review.status not in {ReviewStatus.PENDING, ReviewStatus.IN_REVIEW}:
        raise _error("INVALID_REQUEST", "Review cannot be approved", status.HTTP_409_CONFLICT)
    if (review.skill_version.scan_summary or {}).get("status") != "passed":
        raise _error("SCAN_REJECTED", "Skill version scan did not pass", status.HTTP_409_CONFLICT)
    existing_cert_stmt: Select[tuple[SkillCertification]] = select(SkillCertification).where(
        SkillCertification.skill_version_id == review.skill_version.id
    )
    existing_cert = (await session.execute(existing_cert_stmt)).scalar_one_or_none()
    if existing_cert is not None:
        raise _error("INVALID_REQUEST", "Certificate already issued for this version", status.HTTP_409_CONFLICT)

    review.status = ReviewStatus.APPROVED
    review.reviewer_id = reviewer.id
    review.comment = comment.strip() if comment else None
    review.started_at = review.started_at or datetime.now(UTC)
    review.completed_at = datetime.now(UTC)
    review.skill_version.status = VersionStatus.PUBLISHED
    review.skill_version.published_at = datetime.now(UTC)
    certification = issue_certificate(review.skill_version, reviewer)
    session.add(certification)
    await session.commit()
    await session.refresh(review)
    return review


async def reject_review(session: AsyncSession, review_id: int, reviewer: Developer, comment: str | None) -> SkillReview:
    review = await get_review_or_404(session, review_id)
    if review.status not in {ReviewStatus.PENDING, ReviewStatus.IN_REVIEW}:
        raise _error("INVALID_REQUEST", "Review cannot be rejected", status.HTTP_409_CONFLICT)

    review.status = ReviewStatus.REJECTED
    review.reviewer_id = reviewer.id
    review.comment = comment.strip() if comment else None
    review.started_at = review.started_at or datetime.now(UTC)
    review.completed_at = datetime.now(UTC)
    review.skill_version.status = VersionStatus.REJECTED
    await session.commit()
    await session.refresh(review)
    return review


async def get_admin_stats(session: AsyncSession) -> dict[str, int]:
    skills_total = int((await session.execute(select(func.count()).select_from(Skill))).scalar_one())
    published_versions_total = int(
        (
            await session.execute(
                select(func.count()).select_from(SkillVersion).where(SkillVersion.status == VersionStatus.PUBLISHED)
            )
        ).scalar_one()
    )
    reviews_pending = int(
        (
            await session.execute(
                select(func.count()).select_from(SkillReview).where(SkillReview.status == ReviewStatus.PENDING)
            )
        ).scalar_one()
    )
    certificates_revoked = int(
        (
            await session.execute(
                select(func.count()).select_from(SkillCertification).where(SkillCertification.revoked_at.is_not(None))
            )
        ).scalar_one()
    )
    return {
        "skills_total": skills_total,
        "published_versions_total": published_versions_total,
        "reviews_pending": reviews_pending,
        "certificates_revoked": certificates_revoked,
    }


async def revoke_certificate(
    session: AsyncSession,
    *,
    certificate_serial: str,
    reviewer: Developer,
    reason: str | None,
) -> SkillCertification:
    stmt: Select[tuple[SkillCertification]] = (
        select(SkillCertification)
        .where(SkillCertification.certificate_serial == certificate_serial)
        .options(selectinload(SkillCertification.skill_version))
    )
    certification = (await session.execute(stmt)).scalar_one_or_none()
    if certification is None:
        raise _error("CERT_NOT_FOUND", "Certificate not found", status.HTTP_404_NOT_FOUND)
    if certification.revoked_at is not None:
        raise _error("CERT_ALREADY_REVOKED", "Certificate already revoked", status.HTTP_409_CONFLICT)

    certification.revoked_at = datetime.now(UTC)
    certification.revoke_reason = reason.strip() if reason else None
    certification.issued_by = reviewer.id
    certification.skill_version.status = VersionStatus.REVOKED
    await session.commit()
    await session.refresh(certification)
    return certification


def build_verify_payload(skill_version: SkillVersion, certification: SkillCertification) -> dict[str, str]:
    issued_at = certification.issued_at.astimezone(UTC).isoformat()
    return {
        "skill_name": str(skill_version.manifest_json.get("name", "")),
        "version": skill_version.version,
        "hash": skill_version.package_hash,
        "issued_at": issued_at,
    }
