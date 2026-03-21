from __future__ import annotations

import base64
from datetime import UTC, datetime, timedelta
import hashlib
import json
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from fastapi import HTTPException, status

from ..config import settings
from ..models import Developer, SkillCertification, SkillVersion


def _error(code: str, message: str, http_status: int) -> HTTPException:
    return HTTPException(
        status_code=http_status,
        detail={"error": {"code": code, "message": message}},
    )


def _ensure_private_key(path: Path) -> Ed25519PrivateKey:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        key = Ed25519PrivateKey.generate()
        path.write_bytes(
            key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.PKCS8,
                encryption_algorithm=serialization.NoEncryption(),
            )
        )
        return key

    return serialization.load_pem_private_key(path.read_bytes(), password=None)


def load_private_key() -> Ed25519PrivateKey:
    return _ensure_private_key(settings.ed25519_private_key_path)


def load_public_key_bytes() -> bytes:
    private_key = load_private_key()
    public_key: Ed25519PublicKey = private_key.public_key()
    return public_key.public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )


def build_sign_payload(skill_version: SkillVersion, issued_at: datetime) -> dict[str, str]:
    return {
        "skill_name": str(skill_version.manifest_json.get("name", "")),
        "version": skill_version.version,
        "hash": skill_version.package_hash,
        "issued_at": issued_at.astimezone(UTC).isoformat(),
    }


def canonicalize_payload(payload: dict[str, str]) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sign_payload(payload: dict[str, str]) -> tuple[str, str]:
    private_key = load_private_key()
    payload_bytes = canonicalize_payload(payload)
    signature = private_key.sign(payload_bytes)
    payload_hash = hashlib.sha256(payload_bytes).hexdigest()
    return base64.b64encode(signature).decode("utf-8"), f"sha256:{payload_hash}"


def verify_signature(payload: dict[str, str], signature: str) -> bool:
    public_key = Ed25519PublicKey.from_public_bytes(load_public_key_bytes())
    payload_bytes = canonicalize_payload(payload)
    try:
        public_key.verify(base64.b64decode(signature), payload_bytes)
        return True
    except Exception:
        return False


def issue_certificate(skill_version: SkillVersion, reviewer: Developer) -> SkillCertification:
    if skill_version.id is None:
        raise _error("INVALID_REQUEST", "Skill version must be persisted before signing", status.HTTP_400_BAD_REQUEST)

    issued_at = datetime.now(UTC)
    payload = build_sign_payload(skill_version, issued_at)
    signature, payload_hash = sign_payload(payload)
    serial_suffix = hashlib.sha256(f"{skill_version.id}:{skill_version.version}:{payload_hash}".encode("utf-8")).hexdigest()[:16]
    return SkillCertification(
        skill_version_id=skill_version.id,
        certificate_serial=f"cert-{issued_at.strftime('%Y%m%d')}-{serial_suffix}",
        signature=signature,
        payload_hash=payload_hash,
        public_key_id=settings.ed25519_public_key_id,
        issued_by=reviewer.id,
        issued_at=issued_at,
        expires_at=issued_at + timedelta(days=365),
    )
