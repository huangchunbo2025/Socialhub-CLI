from __future__ import annotations

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth.dependencies import get_current_storefront_user
from ..database import get_db_session
from ..models import User
from ..schemas.user import UserSkillToggleRequest, UserSkillUpsertRequest
from ..services.skills import (
    add_skill_to_user_library,
    list_user_library,
    remove_skill_from_user_library,
    toggle_user_skill,
)

router = APIRouter(tags=["user-skills"])


@router.get("/users/me/skills")
async def get_user_skills(
    current_user: User = Depends(get_current_storefront_user),
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, dict]:
    items = await list_user_library(session, current_user)
    return {"data": {"items": items, "total": len(items)}}


@router.post("/users/me/skills/{skill_name}")
async def add_user_skill(
    skill_name: str,
    payload: UserSkillUpsertRequest,
    current_user: User = Depends(get_current_storefront_user),
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, dict]:
    item = await add_skill_to_user_library(session, current_user, skill_name, payload.version)
    return {"data": item}


@router.delete("/users/me/skills/{skill_name}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user_skill(
    skill_name: str,
    current_user: User = Depends(get_current_storefront_user),
    session: AsyncSession = Depends(get_db_session),
) -> Response:
    await remove_skill_from_user_library(session, current_user, skill_name)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.patch("/users/me/skills/{skill_name}/toggle")
async def patch_user_skill_toggle(
    skill_name: str,
    payload: UserSkillToggleRequest,
    current_user: User = Depends(get_current_storefront_user),
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, dict]:
    item = await toggle_user_skill(session, current_user, skill_name, payload.enabled)
    return {"data": item}
