from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Developer, DeveloperRole, DeveloperStatus

PBKDF2_ITERATIONS = 600_000
PBKDF2_ALGORITHM = "sha256"
PBKDF2_PREFIX = "pbkdf2_sha256"


def _auth_error(code: str, message: str, http_status: int) -> HTTPException:
    return HTTPException(
        status_code=http_status,
        detail={"error": {"code": code, "message": message}},
    )


def normalize_email(email: str) -> str:
    return email.strip().lower()


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac(
        PBKDF2_ALGORITHM,
        password.encode("utf-8"),
        salt,
        PBKDF2_ITERATIONS,
    )
    salt_b64 = base64.b64encode(salt).decode("ascii")
    digest_b64 = base64.b64encode(digest).decode("ascii")
    return f"{PBKDF2_PREFIX}${PBKDF2_ITERATIONS}${salt_b64}${digest_b64}"


def verify_password(password: str, password_hash: str) -> bool:
    try:
        scheme, iterations_text, salt_b64, digest_b64 = password_hash.split("$", 3)
        if scheme != PBKDF2_PREFIX:
            return False
        iterations = int(iterations_text)
        salt = base64.b64decode(salt_b64.encode("ascii"))
        expected_digest = base64.b64decode(digest_b64.encode("ascii"))
    except (TypeError, ValueError):
        return False

    actual_digest = hashlib.pbkdf2_hmac(
        PBKDF2_ALGORITHM,
        password.encode("utf-8"),
        salt,
        iterations,
    )
    return hmac.compare_digest(actual_digest, expected_digest)


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


async def update_saved_skills(
    session: AsyncSession,
    developer: Developer,
    skill_names: list[str],
) -> Developer:
    normalized = [name.strip() for name in skill_names if name and name.strip()]
    developer.saved_skills = sorted(set(normalized))
    await session.commit()
    await session.refresh(developer)
    return developer
