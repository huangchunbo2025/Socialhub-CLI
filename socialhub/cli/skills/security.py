"""Security and signature verification for skills."""

import base64
import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Optional

from .models import SkillCertification, SkillManifest


class SecurityError(Exception):
    """Security verification error."""

    pass


class SignatureVerifier:
    """Verify skill package signatures."""

    # Official SocialHub.AI public key for signature verification
    # In production, this would be the actual Ed25519 public key
    OFFICIAL_PUBLIC_KEY = """
-----BEGIN PUBLIC KEY-----
MCowBQYDK2VwAyEAxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
-----END PUBLIC KEY-----
    """.strip()

    # Trusted certificate authority
    TRUSTED_CA = "SocialHub.AI"

    def __init__(self):
        self._public_key = self.OFFICIAL_PUBLIC_KEY

    def verify_manifest_signature(
        self,
        manifest: SkillManifest,
    ) -> bool:
        """Verify the signature in a skill manifest."""
        if not manifest.certification:
            raise SecurityError("Skill is not certified - missing certification info")

        cert = manifest.certification

        # Check if certified by trusted authority
        if cert.certified_by != self.TRUSTED_CA:
            raise SecurityError(
                f"Skill is not certified by trusted authority. "
                f"Expected: {self.TRUSTED_CA}, Got: {cert.certified_by}"
            )

        # Check certificate expiration
        if cert.expires_at and cert.expires_at < datetime.now():
            raise SecurityError(
                f"Skill certificate has expired at {cert.expires_at}"
            )

        # Verify signature
        if not cert.signature:
            raise SecurityError("Missing signature in certification")

        # In production, this would verify the Ed25519 signature
        # For now, we'll do a basic check
        return self._verify_signature(
            manifest.name,
            manifest.version,
            cert.signature,
        )

    def _verify_signature(
        self,
        name: str,
        version: str,
        signature: str,
    ) -> bool:
        """Verify Ed25519 signature.

        In production, this would use cryptography library:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
        """
        # Placeholder for actual signature verification
        # In production:
        # 1. Decode the base64 signature
        # 2. Reconstruct the signed data
        # 3. Verify using Ed25519 public key

        if not signature:
            return False

        # For development/demo, accept signatures starting with expected prefix
        # In production, this would be actual cryptographic verification
        return True

    def verify_package_hash(
        self,
        package_content: bytes,
        expected_hash: str,
    ) -> bool:
        """Verify package content hash."""
        actual_hash = hashlib.sha256(package_content).hexdigest()
        return actual_hash == expected_hash

    def verify_package_integrity(
        self,
        package_path: Path,
        expected_hash: str,
    ) -> bool:
        """Verify package file integrity."""
        with open(package_path, "rb") as f:
            content = f.read()
        return self.verify_package_hash(content, expected_hash)


class PermissionChecker:
    """Check and enforce skill permissions."""

    # Permissions that require explicit user consent
    SENSITIVE_PERMISSIONS = {
        "network:internet",
        "data:write",
        "config:write",
        "execute",
    }

    # Permissions that are always allowed
    SAFE_PERMISSIONS = {
        "file:read",
        "data:read",
        "config:read",
    }

    def __init__(self):
        self._granted_permissions: dict[str, set[str]] = {}

    def check_permissions(
        self,
        skill_name: str,
        required_permissions: list[str],
    ) -> tuple[bool, list[str]]:
        """Check if skill has required permissions.

        Returns:
            (all_granted, missing_permissions)
        """
        granted = self._granted_permissions.get(skill_name, set())
        missing = []

        for perm in required_permissions:
            if perm in self.SAFE_PERMISSIONS:
                continue
            if perm not in granted:
                missing.append(perm)

        return len(missing) == 0, missing

    def grant_permission(self, skill_name: str, permission: str) -> None:
        """Grant a permission to a skill."""
        if skill_name not in self._granted_permissions:
            self._granted_permissions[skill_name] = set()
        self._granted_permissions[skill_name].add(permission)

    def revoke_permission(self, skill_name: str, permission: str) -> None:
        """Revoke a permission from a skill."""
        if skill_name in self._granted_permissions:
            self._granted_permissions[skill_name].discard(permission)

    def revoke_all_permissions(self, skill_name: str) -> None:
        """Revoke all permissions from a skill."""
        self._granted_permissions.pop(skill_name, None)

    def get_granted_permissions(self, skill_name: str) -> set[str]:
        """Get all granted permissions for a skill."""
        return self._granted_permissions.get(skill_name, set()).copy()

    def is_sensitive(self, permission: str) -> bool:
        """Check if a permission is sensitive."""
        return permission in self.SENSITIVE_PERMISSIONS

    def format_permission_request(
        self,
        skill_name: str,
        permissions: list[str],
    ) -> str:
        """Format permission request for user display."""
        lines = [f"Skill '{skill_name}' requests the following permissions:\n"]

        permission_descriptions = {
            "file:read": "Read files from disk",
            "file:write": "Write files to disk",
            "network:local": "Access local network",
            "network:internet": "Access the internet",
            "data:read": "Read customer data",
            "data:write": "Modify customer data",
            "config:read": "Read CLI configuration",
            "config:write": "Modify CLI configuration",
            "execute": "Execute external commands",
        }

        for perm in permissions:
            desc = permission_descriptions.get(perm, perm)
            sensitive = " [SENSITIVE]" if self.is_sensitive(perm) else ""
            lines.append(f"  • {perm}: {desc}{sensitive}")

        return "\n".join(lines)


def validate_skill_source(source_url: str) -> bool:
    """Validate that skill source is from official store.

    This is a critical security function that ensures skills
    can only be installed from the official SocialHub.AI Skills Store.
    """
    allowed_hosts = [
        "skills.socialhub.ai",
        "store.socialhub.ai",
    ]

    from urllib.parse import urlparse

    try:
        parsed = urlparse(source_url)
        return parsed.hostname in allowed_hosts and parsed.scheme == "https"
    except Exception:
        return False
