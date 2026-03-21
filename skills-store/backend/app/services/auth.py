from __future__ import annotations

from datetime import UTC, datetime

from fastapi import HTTPException, status
from passlib.context import CryptContext
from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Developer, DeveloperRole, DeveloperStatus

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def _auth_error(code: str, message: str, http_status: int) -> HTTPException:
    return HTTPException(
        status_code=http_status,
        detail={"error": {"code": code, "message": message}},
    )


def normalize_email(email: str) -> str:
    return email.strip().lower()


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    return pwd_context.verify(password, password_hash)


async def get_developer_by_email(session: AsyncSession, email: str) -> Developer | None:
    stmt: Select[tuple[Developer]] = select(Developer).where(Developer.email == normalize_email(email))
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def get_developer_by_id(session: AsyncSession, developer_id: int) -> Developer | None:
    stmt: Select[tuple[Developer]] = select(Developer).where(Developer.id == developer_id)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def create_developer(session: AsyncSession, email: str, password: str, name: str) -> Developer:
    existing = await get_developer_by_email(session, email)
    if existing is not None:
        raise _auth_error("DUPLICATE_EMAIL", "Email is already registered", status.HTTP_409_CONFLICT)

    developer = Developer(
        email=normalize_email(email),
        password_hash=hash_password(password),
        name=name.strip(),
        role=DeveloperRole.DEVELOPER,
        status=DeveloperStatus.ACTIVE,
    )
    session.add(developer)
    await session.commit()
    await session.refresh(developer)
    return developer


async def authenticate_developer(session: AsyncSession, email: str, password: str) -> Developer:
    developer = await get_developer_by_email(session, email)
    if developer is None or not verify_password(password, developer.password_hash):
        raise _auth_error(
            "INVALID_CREDENTIALS",
            "Invalid email or password",
            status.HTTP_401_UNAUTHORIZED,
        )

    if developer.status != DeveloperStatus.ACTIVE:
        raise _auth_error("FORBIDDEN", "Account is not active", status.HTTP_403_FORBIDDEN)

    developer.last_login_at = datetime.now(UTC)
    await session.commit()
    await session.refresh(developer)
    return developer


async def update_developer_profile(
    session: AsyncSession,
    developer: Developer,
    *,
    name: str | None,
    bio: str | None,
    website: str | None,
) -> Developer:
    if name is not None:
        developer.name = name.strip()
    if bio is not None:
        developer.bio = bio.strip() or None
    if website is not None:
        developer.website = website.strip() or None

    await session.commit()
    await session.refresh(developer)
    return developer
