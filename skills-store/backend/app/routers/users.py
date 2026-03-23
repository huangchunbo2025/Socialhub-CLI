from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth.dependencies import get_current_storefront_user
from ..auth.jwt import create_access_token
from ..database import get_db_session
from ..models import User
from ..schemas.user import StorefrontUserResponse, UserLoginRequest, UserRegisterRequest
from ..services.auth import authenticate_storefront_user, create_storefront_user

router = APIRouter(tags=["users"])


def _serialize_user(user: User) -> StorefrontUserResponse:
    return StorefrontUserResponse(
        id=user.id,
        email=user.email,
        name=user.name,
        status=user.status,
    )


@router.post("/users/register")
async def register_storefront_user(
    payload: UserRegisterRequest,
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, StorefrontUserResponse]:
    user = await create_storefront_user(session, payload.email, payload.password, payload.name)
    return {"data": _serialize_user(user)}


@router.post("/users/login")
async def login_storefront_user(
    payload: UserLoginRequest,
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, dict[str, object]]:
    user = await authenticate_storefront_user(session, payload.email, payload.password)
    access_token, expires_in = create_access_token(
        user.id,
        user.email,
        None,
        principal_type="user",
    )
    return {
        "data": {
            "access_token": access_token,
            "expires_in": expires_in,
            "user": _serialize_user(user).model_dump(),
        }
    }


@router.get("/users/me")
async def get_storefront_me(
    current_user: User = Depends(get_current_storefront_user),
) -> dict[str, StorefrontUserResponse]:
    return {"data": _serialize_user(current_user)}
