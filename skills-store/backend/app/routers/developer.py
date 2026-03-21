from fastapi import APIRouter, Depends, File, Form, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth.dependencies import get_current_user
from ..database import get_db_session
from ..models import Developer
from ..schemas.skill import CreateSkillRequest
from ..services.skills import (
    create_skill,
    create_skill_version,
    get_developer_skill_or_404,
    list_developer_skills,
    serialize_skill,
    serialize_skill_version,
)
from ..utils.packages import validate_and_store_package

router = APIRouter(prefix="/developer", tags=["developer"], dependencies=[Depends(get_current_user)])


@router.get("/skills")
async def list_own_skills(
    current_user: Developer = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, list[dict]]:
    return {"data": await list_developer_skills(session, current_user)}


@router.post("/skills")
async def create_skill_route(
    payload: CreateSkillRequest,
    current_user: Developer = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, dict]:
    skill = await create_skill(
        session,
        developer=current_user,
        name=payload.name,
        display_name=payload.display_name,
        summary=payload.summary,
        description=payload.description,
        category=payload.category,
        tags=payload.tags,
        icon_url=payload.icon_url,
    )
    return {"data": serialize_skill(skill)}


@router.get("/skills/{name}")
async def get_own_skill(
    name: str,
    current_user: Developer = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, dict]:
    skill = await get_developer_skill_or_404(session, current_user, name)
    return {"data": serialize_skill(skill)}


@router.post("/skills/{name}/versions")
async def create_skill_version_route(
    name: str,
    version: str = Form(...),
    release_notes: str | None = Form(default=None),
    package: UploadFile = File(...),
    current_user: Developer = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, dict]:
    skill = await get_developer_skill_or_404(session, current_user, name)
    package_info = await validate_and_store_package(skill.name, version.strip(), package)
    skill_version = await create_skill_version(
        session,
        skill=skill,
        version=version.strip(),
        package_filename=package_info["package_filename"],
        package_path=package_info["package_path"],
        package_size=package_info["package_size"],
        package_hash=package_info["package_hash"],
        manifest_json=package_info["manifest_json"],
        scan_summary=package_info["scan_summary"],
        scan_detail=package_info["scan_detail"],
        release_notes=release_notes,
    )
    return {
        "data": {
            "skill_name": skill.name,
            **serialize_skill_version(skill_version),
        }
    }
