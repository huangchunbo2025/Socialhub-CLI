import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db_session
from ..models import SkillCertification, SkillVersion
from ..models.enums import SkillCategory
from ..schemas.skill import CheckUpdatesRequest
from ..services.certificates import verify_signature
from ..services.skills import (
    build_verify_payload,
    get_latest_downloadable_version,
    get_public_skill_or_404,
    list_public_skills,
    list_public_versions,
    serialize_skill,
)

router = APIRouter(tags=["public"])
logger = logging.getLogger(__name__)


@router.get("/categories")
async def get_categories() -> dict[str, list[dict[str, str]]]:
    return {
        "data": [{"key": item.value, "label": item.value.replace("_", " ").title()} for item in SkillCategory]
    }


@router.get("/skills/featured")
async def get_featured_skills(session: AsyncSession = Depends(get_db_session)) -> dict[str, list[dict]]:
    data, _ = await list_public_skills(
        session,
        search=None,
        category=None,
        page=1,
        limit=12,
        featured_only=True,
    )
    return {"data": data}


@router.get("/skills")
async def list_skills(
    search: str | None = Query(default=None),
    category: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, object]:
    try:
        data, total = await list_public_skills(
            session,
            search=search,
            category=category,
            page=page,
            limit=limit,
        )
        return {
            "data": data,
            "pagination": {
                "total": total,
                "page": page,
                "limit": limit,
            },
        }
    except Exception:
        logger.exception(
            "list_skills failed",
            extra={"search": search, "category": category, "page": page, "limit": limit},
        )
        raise


@router.post("/skills/verify")
async def verify_skill(
    payload: dict[str, str],
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, dict[str, bool | str | None]]:
    skill_name = payload.get("skill_name", "").strip().lower()
    signature = payload.get("signature")
    package_hash = payload.get("hash")
    if not skill_name or not signature or not package_hash:
        return {"data": {"valid": False, "certificate_serial": None, "revoked": False}}

    stmt: Select[tuple[SkillCertification, SkillVersion]] = (
        select(SkillCertification, SkillVersion)
        .join(SkillVersion, SkillCertification.skill_version_id == SkillVersion.id)
        .where(
            SkillVersion.package_hash == package_hash,
            SkillCertification.signature == signature,
        )
    )
    rows = (await session.execute(stmt)).all()
    for certification, version in rows:
        if version.manifest_json.get("name") == skill_name:
            canonical_payload = build_verify_payload(version, certification)
            signature_ok = verify_signature(canonical_payload, certification.signature)
            return {
                "data": {
                    "valid": signature_ok and certification.signature == signature,
                    "certificate_serial": certification.certificate_serial,
                    "revoked": certification.revoked_at is not None,
                }
            }

    return {"data": {"valid": False, "certificate_serial": None, "revoked": False}}


@router.post("/skills/check-updates")
async def check_updates(
    payload: CheckUpdatesRequest,
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, list[dict[str, object]]]:
    results: list[dict[str, object]] = []
    for item in payload.skills:
        name = item.get("name", "").strip().lower()
        current_version = item.get("version")
        if not name:
            continue
        try:
            _, latest_version, _ = await get_latest_downloadable_version(session, name)
        except HTTPException:
            continue
        results.append(
            {
                "name": name,
                "current_version": current_version,
                "latest_version": latest_version.version,
                "has_update": current_version != latest_version.version,
            }
        )
    return {"data": results}


@router.get("/skills/{name}")
async def get_skill(name: str, session: AsyncSession = Depends(get_db_session)) -> dict[str, dict]:
    skill = await get_public_skill_or_404(session, name)
    return {"data": serialize_skill(skill)}


@router.get("/skills/{name}/versions")
async def get_skill_versions(name: str, session: AsyncSession = Depends(get_db_session)) -> dict[str, list[dict]]:
    return {"data": await list_public_versions(session, name)}


@router.get("/skills/{name}/download")
async def download_skill(
    name: str,
    version: str | None = Query(default=None),
    session: AsyncSession = Depends(get_db_session),
) -> FileResponse:
    skill, selected_version, _ = await get_latest_downloadable_version(session, name, version)
    skill.download_count += 1
    await session.commit()
    return FileResponse(
        selected_version.package_path,
        media_type="application/zip",
        filename=f"{skill.name}-{selected_version.version}.zip",
    )


@router.get("/skills/{name}/download-info")
async def get_download_info(
    name: str,
    version: str | None = Query(default=None),
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, dict[str, object]]:
    skill, selected_version, certification = await get_latest_downloadable_version(session, name, version)
    return {
        "data": {
            "skill_name": skill.name,
            "version": selected_version.version,
            "package_hash": selected_version.package_hash,
            "package_size": selected_version.package_size,
            "signature": certification.signature if certification else None,
            "certificate_serial": certification.certificate_serial if certification else None,
            "public_key_id": certification.public_key_id if certification else None,
            "download_url": f"/api/v1/skills/{skill.name}/download?version={selected_version.version}",
        }
    }


@router.get("/crl")
async def get_crl(session: AsyncSession = Depends(get_db_session)) -> dict[str, dict[str, object]]:
    stmt: Select[tuple[SkillCertification]] = select(SkillCertification).where(
        SkillCertification.revoked_at.is_not(None)
    )
    revoked = (await session.execute(stmt)).scalars().all()
    return {
        "data": {
            "issued_at": None,
            "revoked_certificates": [
                {
                    "certificate_serial": item.certificate_serial,
                    "revoked_at": item.revoked_at,
                    "reason": item.revoke_reason,
                }
                for item in revoked
            ],
        }
    }
