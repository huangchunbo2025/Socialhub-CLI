from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth.dependencies import get_current_user
from ..auth.jwt import create_access_token
from ..database import get_db_session
from ..models import Developer
from ..schemas.auth import LoginRequest, RegisterRequest, UpdateProfileRequest, UserResponse
from ..services.auth import authenticate_developer, create_developer, update_developer_profile

router = APIRouter(tags=["auth"])


def _serialize_user(user: Developer) -> UserResponse:
    return UserResponse(
        id=user.id,
        email=user.email,
        name=user.name,
        role=user.role.value,
        status=user.status.value,
        bio=user.bio,
        website=user.website,
    )


@router.post("/auth/register")
async def register(
    payload: RegisterRequest,
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, UserResponse]:
    developer = await create_developer(session, payload.email, payload.password, payload.name)
    return {"data": _serialize_user(developer)}


@router.post("/auth/login")
async def login(
    payload: LoginRequest,
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, dict[str, object]]:
    developer = await authenticate_developer(session, payload.email, payload.password)
    access_token, expires_in = create_access_token(
        developer.id,
        developer.email,
        developer.role.value,
    )
    return {
        "data": {
            "access_token": access_token,
            "token_type": "bearer",
            "expires_in": expires_in,
            "user": _serialize_user(developer).model_dump(),
        }
    }


@router.get("/auth/me")
async def me(current_user: Developer = Depends(get_current_user)) -> dict[str, UserResponse]:
    return {"data": _serialize_user(current_user)}


@router.patch("/auth/me")
async def update_me(
    payload: UpdateProfileRequest,
    current_user: Developer = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, UserResponse]:
    developer = await update_developer_profile(
        session,
        current_user,
        name=payload.name,
        bio=payload.bio,
        website=payload.website,
    )
    return {"data": _serialize_user(developer)}
