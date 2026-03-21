from __future__ import annotations

from datetime import UTC, datetime, timedelta

from jose import JWTError, jwt

from ..config import settings

ALGORITHM = "HS256"


def create_access_token(user_id: int, email: str, role: str) -> tuple[str, int]:
    expires_delta = timedelta(hours=settings.jwt_expire_hours)
    now = datetime.now(UTC)
    expire_at = now + expires_delta
    payload = {
        "sub": str(user_id),
        "email": email,
        "role": role,
        "iat": int(now.timestamp()),
        "exp": int(expire_at.timestamp()),
    }
    token = jwt.encode(payload, settings.jwt_secret, algorithm=ALGORITHM)
    return token, int(expires_delta.total_seconds())


def decode_access_token(token: str) -> dict:
    try:
        return jwt.decode(token, settings.jwt_secret, algorithms=[ALGORITHM])
    except JWTError as exc:
        raise ValueError("Invalid access token") from exc
