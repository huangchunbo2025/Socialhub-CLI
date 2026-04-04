"""Security and signature verification for skills.

This module provides cryptographic verification for skill packages,
including Ed25519 signature verification, hash validation, and
certificate management.
"""

import base64
import hashlib
import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from .models import SkillCertification, SkillManifest


class SecurityError(Exception):
    """Security verification error."""

    pass


class KeyManager:
    """Manage official public keys for signature verification.

    This class handles loading, caching, and updating the official
    SocialHub.AI public key used to verify skill signatures.
    """

    # Official SocialHub.AI Ed25519 public key (base64 encoded)
    # This is the production public key for verifying skill signatures
    OFFICIAL_PUBLIC_KEY_B64 = "MCowBQYDK2VwAyEAIvR8munSVGQJIVkhKmV6WQZwwhzUVto6KaSxGrpBAiQ="

    # Backup key URL for key rotation
    KEY_UPDATE_URL = "https://keys.socialhub.ai/v1/public_key"

    # Local key cache path
    KEY_CACHE_PATH = Path.home() / ".socialhub" / "security" / "public_key.pem"

    # Key fingerprint for verification (SHA256 of the public key)
    EXPECTED_KEY_FINGERPRINT = "sha256:9e5bd0f4cfcf487341eb582501b04587f62ac62de3303f56a2489f90cdae867b"

    def __init__(self):
        self._public_key: Ed25519PublicKey | None = None
        self._key_loaded_at: datetime | None = None
        self._logger = logging.getLogger(__name__)

    def load_public_key(self) -> Ed25519PublicKey:
        """Load the official public key for signature verification.

        Returns:
            Ed25519PublicKey: The loaded public key

        Raises:
            SecurityError: If the key cannot be loaded or is invalid
        """
        if self._public_key is not None:
            return self._public_key

        try:
            # Try to load from embedded key first (most secure)
            key_bytes = base64.b64decode(self.OFFICIAL_PUBLIC_KEY_B64)
            self._public_key = Ed25519PublicKey.from_public_bytes(key_bytes[12:])
            self._key_loaded_at = datetime.now()
            return self._public_key

        except Exception as e:
            self._logger.error("Failed to load public key: %s", e)
            raise SecurityError(
                "Failed to load official public key. "
                "Please ensure cryptography library is properly installed."
            ) from e

    def get_key_fingerprint(self) -> str:
        """Get the SHA256 fingerprint of the current public key.

        Returns:
            str: The key fingerprint in format 'sha256:xxxx...'
        """
        key = self.load_public_key()
        key_bytes = key.public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )
        fingerprint = hashlib.sha256(key_bytes).hexdigest()
        return f"sha256:{fingerprint}"

    def verify_key_integrity(self) -> bool:
        """Verify that the loaded key matches the expected fingerprint.

        Returns:
            bool: True if the key is valid
        """
        current_fingerprint = self.get_key_fingerprint()
        return current_fingerprint == self.EXPECTED_KEY_FINGERPRINT


class HashVerifier:
    """Verify package integrity using cryptographic hashes.

    Supports multiple hash algorithms for defense in depth.
    """

    SUPPORTED_ALGORITHMS = {"sha256", "sha384", "sha512"}
    DEFAULT_ALGORITHM = "sha256"

    def __init__(self):
        self._logger = logging.getLogger(__name__)

    def compute_hash(
        self,
        content: bytes,
        algorithm: str = "sha256",
    ) -> str:
        """Compute the hash of content.

        Args:
            content: The content to hash
            algorithm: Hash algorithm to use (sha256, sha384, sha512)

        Returns:
            str: The hex-encoded hash

        Raises:
            ValueError: If the algorithm is not supported
        """
        if algorithm not in self.SUPPORTED_ALGORITHMS:
            raise ValueError(
                f"Unsupported hash algorithm: {algorithm}. "
                f"Supported: {self.SUPPORTED_ALGORITHMS}"
            )

        hasher = hashlib.new(algorithm)
        hasher.update(content)
        return hasher.hexdigest()

    def verify_hash(
        self,
        content: bytes,
        expected_hash: str,
        algorithm: str = "sha256",
    ) -> bool:
        """Verify content against an expected hash.

        Args:
            content: The content to verify
            expected_hash: The expected hash value
            algorithm: Hash algorithm to use

        Returns:
            bool: True if the hash matches
        """
        actual_hash = self.compute_hash(content, algorithm)
        # Use constant-time comparison to prevent timing attacks
        return self._constant_time_compare(actual_hash, expected_hash)

    def verify_multiple_hashes(
        self,
        content: bytes,
        expected_hashes: dict[str, str],
    ) -> tuple[bool, list[str]]:
        """Verify content against multiple hash algorithms.

        Args:
            content: The content to verify
            expected_hashes: Dict mapping algorithm to expected hash

        Returns:
            Tuple of (all_valid, list of failed algorithms)
        """
        failed = []
        for algorithm, expected in expected_hashes.items():
            if algorithm not in self.SUPPORTED_ALGORITHMS:
                continue
            if not self.verify_hash(content, expected, algorithm):
                failed.append(algorithm)

        return len(failed) == 0, failed

    def _constant_time_compare(self, a: str, b: str) -> bool:
        """Constant-time string comparison to prevent timing attacks."""
        if len(a) != len(b):
            return False
        result = 0
        for x, y in zip(a.encode(), b.encode()):
            result |= x ^ y
        return result == 0


class SignatureVerifier:
    """Verify skill package signatures using Ed25519.

    This class handles cryptographic verification of skill packages
    to ensure they are authentically signed by SocialHub.AI.
    """

    # Trusted certificate authority
    TRUSTED_CA = "SocialHub.AI"

    # Signature data version for forward compatibility
    SIGNATURE_VERSION = "1"

    def __init__(self):
        self._key_manager = KeyManager()
        self._hash_verifier = HashVerifier()
        self._logger = logging.getLogger(__name__)

    def verify_manifest_signature(
        self,
        manifest: SkillManifest,
    ) -> bool:
        """Verify the signature in a skill manifest.

        Args:
            manifest: The skill manifest to verify

        Returns:
            bool: True if the signature is valid

        Raises:
            SecurityError: If verification fails
        """
        if not manifest.certification:
            raise SecurityError(
                f"Skill '{manifest.name}' is not certified - missing certification info"
            )

        cert = manifest.certification

        # Step 1: Check if certified by trusted authority
        if cert.certified_by != self.TRUSTED_CA:
            raise SecurityError(
                f"Skill '{manifest.name}' is not certified by trusted authority. "
                f"Expected: {self.TRUSTED_CA}, Got: {cert.certified_by}"
            )

        # Step 2: Check certificate expiration
        if cert.expires_at and cert.expires_at < datetime.now():
            raise SecurityError(
                f"Skill '{manifest.name}' certificate has expired at {cert.expires_at}. "
                "Please update to a newer version."
            )

        # Step 3: Verify signature is present
        if not cert.signature:
            raise SecurityError(
                f"Skill '{manifest.name}' is missing signature in certification"
            )

        # Step 4: Verify the Ed25519 signature
        return self._verify_ed25519_signature(
            manifest.name,
            manifest.version,
            cert,
        )

    def _verify_ed25519_signature(
        self,
        name: str,
        version: str,
        certification: SkillCertification,
    ) -> bool:
        """Verify Ed25519 signature cryptographically.

        Args:
            name: Skill name
            version: Skill version
            certification: Certification info containing signature

        Returns:
            bool: True if signature is valid

        Raises:
            SecurityError: If signature verification fails
        """
        try:
            # Load the official public key
            public_key = self._key_manager.load_public_key()

            # Decode the base64 signature
            try:
                signature_bytes = base64.b64decode(certification.signature)
            except Exception as e:
                raise SecurityError(
                    f"Invalid signature encoding for '{name}': {e}"
                ) from e

            # Build the signed data (canonical format)
            signed_data = self._build_signed_data(name, version, certification)

            # Verify the signature
            try:
                public_key.verify(signature_bytes, signed_data)
                self._logger.info(
                    f"Signature verified successfully for {name}@{version}"
                )
                return True

            except InvalidSignature:
                raise SecurityError(
                    f"Invalid signature for skill '{name}@{version}'. "
                    "The package may have been tampered with or is not from the official store."
                )

        except SecurityError:
            raise
        except Exception as e:
            self._logger.error("Signature verification error: %s", e)
            raise SecurityError(
                f"Signature verification failed for '{name}': {e}"
            ) from e

    def _build_signed_data(
        self,
        name: str,
        version: str,
        certification: SkillCertification,
    ) -> bytes:
        """Build the canonical data that was signed.

        The signed data format is a JSON object with sorted keys
        to ensure consistent serialization.

        Args:
            name: Skill name
            version: Skill version
            certification: Certification info

        Returns:
            bytes: The canonical signed data
        """
        data = {
            "v": self.SIGNATURE_VERSION,
            "name": name,
            "version": version,
            "certified_by": certification.certified_by,
            "certified_at": (
                certification.certified_at.isoformat()
                if certification.certified_at
                else None
            ),
            "certificate_id": certification.certificate_id,
        }

        # Canonical JSON: sorted keys, no whitespace
        canonical = json.dumps(data, sort_keys=True, separators=(",", ":"))
        return canonical.encode("utf-8")

    def verify_package_hash(
        self,
        package_content: bytes,
        expected_hash: str,
        algorithm: str = "sha256",
    ) -> bool:
        """Verify package content hash.

        Args:
            package_content: The package bytes
            expected_hash: Expected hash value
            algorithm: Hash algorithm (default: sha256)

        Returns:
            bool: True if hash matches

        Raises:
            SecurityError: If hash verification fails
        """
        if not self._hash_verifier.verify_hash(
            package_content, expected_hash, algorithm
        ):
            raise SecurityError(
                f"Package hash verification failed. Expected: {expected_hash[:16]}..., "
                f"The package may have been corrupted or tampered with."
            )
        return True

    def verify_package_integrity(
        self,
        package_path: Path,
        expected_hash: str,
        algorithm: str = "sha256",
    ) -> bool:
        """Verify package file integrity.

        Args:
            package_path: Path to the package file
            expected_hash: Expected hash value
            algorithm: Hash algorithm

        Returns:
            bool: True if integrity check passes

        Raises:
            SecurityError: If integrity check fails
        """
        try:
            with open(package_path, "rb") as f:
                content = f.read()
            return self.verify_package_hash(content, expected_hash, algorithm)
        except FileNotFoundError:
            raise SecurityError(f"Package file not found: {package_path}")
        except PermissionError:
            raise SecurityError(f"Permission denied reading package: {package_path}")


def _crl_integrity_hash(payload: str) -> str:
    """Compute an HMAC-style integrity hash for CRL cache content.

    Uses the CRL URL as a fixed salt so that a tampered file without the
    correct hash (or a hash computed without this salt) is rejected.
    Not a substitute for server-side signatures, but prevents casual tampering.
    """
    salt = b"socialhub-crl-v1:" + RevocationListManager.CRL_URL.encode()
    return hashlib.sha256(salt + payload.encode()).hexdigest()


class RevocationListManager:
    """Manage certificate revocation list (CRL).

    Maintains a list of revoked skills and certificates that
    should not be installed or executed.
    """

    CRL_URL = "https://skills.socialhub.ai/api/v1/security/crl"
    LOCAL_CRL_PATH = Path.home() / ".socialhub" / "security" / "crl.json"
    UPDATE_INTERVAL = timedelta(hours=1)

    def __init__(self):
        self._revoked_skills: set[str] = set()
        self._revoked_certificates: set[str] = set()
        self._last_update: datetime | None = None
        # True once CRL data has been successfully loaded (from server or cache).
        # False means we have no data — is_revoked() will raise rather than silently pass.
        self._data_loaded: bool = False
        self._logger = logging.getLogger(__name__)

    def is_revoked(self, skill_name: str, certificate_id: str | None = None) -> bool:
        """Check if a skill or certificate is revoked.

        Args:
            skill_name: Name of the skill
            certificate_id: Optional certificate ID

        Returns:
            bool: True if revoked

        Raises:
            SecurityError: If CRL data could not be loaded (no network + no local cache).
                           Callers must not silently swallow this — installation must be blocked.
        """
        self._maybe_update()

        if not self._data_loaded:
            raise SecurityError(
                "Cannot verify revocation status: CRL data unavailable "
                "(no network access and no local cache). "
                "Ensure network connectivity to install skills."
            )

        if skill_name in self._revoked_skills:
            return True

        if certificate_id and certificate_id in self._revoked_certificates:
            return True

        return False

    def get_revocation_reason(self, skill_name: str) -> str | None:
        """Get the reason a skill was revoked.

        Args:
            skill_name: Name of the skill

        Returns:
            Optional reason string
        """
        # This would be fetched from the CRL data
        return None

    def update(self) -> bool:
        """Update the revocation list from the server.

        Returns:
            bool: True if update succeeded
        """
        try:
            import httpx

            response = httpx.get(self.CRL_URL, timeout=10)
            if response.status_code == 200:
                data = response.json()
                self._revoked_skills = set(data.get("revoked_skills", []))
                self._revoked_certificates = set(data.get("revoked_certificates", []))
                self._last_update = datetime.now()
                self._data_loaded = True
                self._save_local_cache()
                return True
            return False

        except Exception as e:
            self._logger.warning("Failed to update CRL: %s", e)
            # Fall back to local cache
            self._load_local_cache()
            return False

    def _maybe_update(self) -> None:
        """Update CRL if needed."""
        if self._last_update is None:
            self._load_local_cache()

        if self._should_update():
            self.update()

    def _should_update(self) -> bool:
        """Check if CRL should be updated."""
        if self._last_update is None:
            return True
        return datetime.now() - self._last_update > self.UPDATE_INTERVAL

    def _save_local_cache(self) -> None:
        """Save CRL to local cache with integrity hash."""
        try:
            self.LOCAL_CRL_PATH.parent.mkdir(parents=True, exist_ok=True)
            payload = {
                "revoked_skills": sorted(self._revoked_skills),
                "revoked_certificates": sorted(self._revoked_certificates),
                "updated_at": self._last_update.isoformat() if self._last_update else None,
            }
            payload_str = json.dumps(payload, sort_keys=True)
            data = json.loads(payload_str)
            data["_integrity"] = _crl_integrity_hash(payload_str)
            self.LOCAL_CRL_PATH.write_text(json.dumps(data))
        except Exception as e:
            self._logger.warning("Failed to save CRL cache: %s", e)

    def _load_local_cache(self) -> None:
        """Load CRL from local cache, verifying integrity hash."""
        try:
            if not self.LOCAL_CRL_PATH.exists():
                return
            raw = self.LOCAL_CRL_PATH.read_text()
            data = json.loads(raw)
            stored_hash = data.pop("_integrity", None)
            # Recompute integrity over the content fields only (without _integrity key)
            payload_str = json.dumps(
                {k: v for k, v in data.items()},
                sort_keys=True,
            )
            if stored_hash is None or stored_hash != _crl_integrity_hash(payload_str):
                self._logger.warning(
                    "CRL cache integrity check failed — ignoring potentially tampered file: %s",
                    self.LOCAL_CRL_PATH,
                )
                return
            self._revoked_skills = set(data.get("revoked_skills", []))
            self._revoked_certificates = set(data.get("revoked_certificates", []))
            if data.get("updated_at"):
                self._last_update = datetime.fromisoformat(data["updated_at"])
            self._data_loaded = True
        except Exception as e:
            self._logger.warning("Failed to load CRL cache: %s", e)


class SecurityAuditLogger:
    """Log security-related events for auditing.

    Provides structured logging for security events to enable
    monitoring and incident response.
    """

    LOG_PATH = Path.home() / ".socialhub" / "logs" / "security_audit.log"

    def __init__(self):
        self._logger = self._setup_logger()

    def _setup_logger(self) -> logging.Logger:
        """Set up the audit logger."""
        logger = logging.getLogger("socialhub.security.audit")
        logger.setLevel(logging.INFO)
        if logger.handlers:
            return logger

        # Create log directory if needed
        self.LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

        # File handler with rotation
        handler = logging.FileHandler(self.LOG_PATH)
        handler.setFormatter(
            logging.Formatter(
                "%(asctime)s | %(levelname)s | %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )
        )
        logger.addHandler(handler)
        return logger

    def log_signature_verified(self, skill_name: str, version: str) -> None:
        """Log successful signature verification."""
        self._logger.info(
            f"SIGNATURE_VERIFIED | skill={skill_name} | version={version}"
        )

    def log_signature_failed(
        self, skill_name: str, version: str, reason: str
    ) -> None:
        """Log failed signature verification."""
        self._logger.warning(
            f"SIGNATURE_FAILED | skill={skill_name} | version={version} | reason={reason}"
        )

    def log_permission_granted(
        self, skill_name: str, permission: str, granted_by: str = "user"
    ) -> None:
        """Log permission grant."""
        self._logger.info(
            f"PERMISSION_GRANTED | skill={skill_name} | "
            f"permission={permission} | granted_by={granted_by}"
        )

    def log_permission_denied(
        self, skill_name: str, permission: str, reason: str
    ) -> None:
        """Log permission denial."""
        self._logger.warning(
            f"PERMISSION_DENIED | skill={skill_name} | "
            f"permission={permission} | reason={reason}"
        )

    def log_security_violation(
        self, skill_name: str, violation_type: str, details: str
    ) -> None:
        """Log security violation."""
        self._logger.error(
            f"SECURITY_VIOLATION | skill={skill_name} | "
            f"type={violation_type} | details={details}"
        )

    def log_install_blocked(self, skill_name: str, reason: str) -> None:
        """Log blocked installation."""
        self._logger.warning(
            f"INSTALL_BLOCKED | skill={skill_name} | reason={reason}"
        )


class PermissionChecker:
    """Check and enforce skill permissions.

    Manages the permission model for skills, tracking granted
    permissions and enforcing access control.
    """

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

    # Permission descriptions for user display
    PERMISSION_DESCRIPTIONS = {
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

    # Risk levels for permissions
    PERMISSION_RISK_LEVELS = {
        "file:read": "low",
        "file:write": "medium",
        "network:local": "medium",
        "network:internet": "high",
        "data:read": "low",
        "data:write": "high",
        "config:read": "low",
        "config:write": "medium",
        "execute": "high",
    }

    def __init__(self):
        self._granted_permissions: dict[str, set[str]] = {}
        self._audit_logger = SecurityAuditLogger()

    def check_permissions(
        self,
        skill_name: str,
        required_permissions: list[str],
    ) -> tuple[bool, list[str]]:
        """Check if skill has required permissions.

        Args:
            skill_name: Name of the skill
            required_permissions: List of required permission strings

        Returns:
            Tuple of (all_granted, missing_permissions)
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
        """Grant a permission to a skill.

        Args:
            skill_name: Name of the skill
            permission: Permission to grant
        """
        if skill_name not in self._granted_permissions:
            self._granted_permissions[skill_name] = set()
        self._granted_permissions[skill_name].add(permission)
        self._audit_logger.log_permission_granted(skill_name, permission)

    def revoke_permission(self, skill_name: str, permission: str) -> None:
        """Revoke a permission from a skill.

        Args:
            skill_name: Name of the skill
            permission: Permission to revoke
        """
        if skill_name in self._granted_permissions:
            self._granted_permissions[skill_name].discard(permission)

    def revoke_all_permissions(self, skill_name: str) -> None:
        """Revoke all permissions from a skill.

        Args:
            skill_name: Name of the skill
        """
        self._granted_permissions.pop(skill_name, None)

    def get_granted_permissions(self, skill_name: str) -> set[str]:
        """Get all granted permissions for a skill.

        Args:
            skill_name: Name of the skill

        Returns:
            Set of granted permission strings
        """
        return self._granted_permissions.get(skill_name, set()).copy()

    def is_sensitive(self, permission: str) -> bool:
        """Check if a permission is sensitive.

        Args:
            permission: Permission string to check

        Returns:
            bool: True if the permission requires explicit user consent
        """
        return permission in self.SENSITIVE_PERMISSIONS

    def get_risk_level(self, permission: str) -> str:
        """Get the risk level of a permission.

        Args:
            permission: Permission string

        Returns:
            Risk level: 'low', 'medium', or 'high'
        """
        return self.PERMISSION_RISK_LEVELS.get(permission, "medium")

    def format_permission_request(
        self,
        skill_name: str,
        permissions: list[str],
    ) -> str:
        """Format permission request for user display.

        Args:
            skill_name: Name of the skill
            permissions: List of requested permissions

        Returns:
            Formatted string for display
        """
        lines = [f"Skill '{skill_name}' requests the following permissions:\n"]

        for perm in permissions:
            desc = self.PERMISSION_DESCRIPTIONS.get(perm, perm)
            risk = self.get_risk_level(perm)
            risk_indicator = {"low": "", "medium": " [MEDIUM RISK]", "high": " [HIGH RISK]"}
            sensitive = risk_indicator.get(risk, "")
            lines.append(f"  - {perm}: {desc}{sensitive}")

        return "\n".join(lines)


def validate_skill_source(source_url: str) -> bool:
    """Validate that skill source is from official store.

    This is a critical security function that ensures skills
    can only be installed from the official SocialHub.AI Skills Store.

    Args:
        source_url: The URL to validate

    Returns:
        bool: True if the URL is from an allowed source
    """
    allowed_hosts = [
        "skills.socialhub.ai",
        "store.socialhub.ai",
    ]

    try:
        parsed = urlparse(source_url)
        return parsed.hostname in allowed_hosts and parsed.scheme == "https"
    except Exception:
        return False


class PermissionStore:
    """Persistent storage for permission grants.

    Stores permission authorizations in a JSON file so they persist
    across CLI sessions.
    """

    PERMISSIONS_FILE = Path.home() / ".socialhub" / "security" / "permissions.json"

    def __init__(self):
        self._permissions: dict[str, dict] = {}
        self._logger = logging.getLogger(__name__)
        self._load()

    def _load(self) -> None:
        """Load permissions from disk."""
        try:
            if self.PERMISSIONS_FILE.exists():
                data = json.loads(self.PERMISSIONS_FILE.read_text(encoding="utf-8"))
                self._permissions = data.get("skills", {})
        except Exception as e:
            self._logger.warning("Failed to load permissions: %s", e)
            self._permissions = {}

    def _save(self) -> None:
        """Save permissions to disk."""
        try:
            self.PERMISSIONS_FILE.parent.mkdir(parents=True, exist_ok=True)
            data = {
                "version": "1.0",
                "updated_at": datetime.now().isoformat(),
                "skills": self._permissions,
            }
            self.PERMISSIONS_FILE.write_text(
                json.dumps(data, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        except Exception as e:
            self._logger.warning("Failed to save permissions: %s", e)

    def get_permissions(self, skill_name: str, version: str = "") -> set[str]:
        """Get granted permissions for a skill.

        If version is provided and differs from the stored version,
        returns an empty set — the user must re-approve permissions
        after an upgrade.

        Args:
            skill_name: Name of the skill
            version: If provided, compare against stored version

        Returns:
            Set of permission strings
        """
        skill_data = self._permissions.get(skill_name, {})
        if version and skill_data.get("version") and skill_data["version"] != version:
            return set()  # Version mismatch — permissions invalidated
        return set(skill_data.get("permissions", []))

    def grant_permissions(
        self,
        skill_name: str,
        permissions: list[str],
        version: str = "",
    ) -> None:
        """Grant permissions to a skill.

        Args:
            skill_name: Name of the skill
            permissions: List of permissions to grant
            version: Skill version (for tracking)
        """
        if skill_name not in self._permissions:
            self._permissions[skill_name] = {
                "permissions": [],
                "granted_at": None,
                "version": "",
            }

        current = set(self._permissions[skill_name]["permissions"])
        current.update(permissions)
        self._permissions[skill_name]["permissions"] = list(current)
        self._permissions[skill_name]["granted_at"] = datetime.now().isoformat()
        self._permissions[skill_name]["version"] = version
        self._save()

    def revoke_permissions(self, skill_name: str, permissions: list[str]) -> None:
        """Revoke specific permissions from a skill.

        Args:
            skill_name: Name of the skill
            permissions: List of permissions to revoke
        """
        if skill_name in self._permissions:
            current = set(self._permissions[skill_name]["permissions"])
            current -= set(permissions)
            self._permissions[skill_name]["permissions"] = list(current)
            self._save()

    def revoke_all(self, skill_name: str) -> None:
        """Revoke all permissions from a skill.

        Args:
            skill_name: Name of the skill
        """
        if skill_name in self._permissions:
            del self._permissions[skill_name]
            self._save()

    def has_permission(self, skill_name: str, permission: str) -> bool:
        """Check if a skill has a specific permission.

        Args:
            skill_name: Name of the skill
            permission: Permission to check

        Returns:
            bool: True if permission is granted
        """
        return permission in self.get_permissions(skill_name)

    def list_all_grants(self) -> dict[str, set[str]]:
        """List all permission grants.

        Returns:
            Dict mapping skill names to sets of permissions
        """
        return {
            name: set(data.get("permissions", []))
            for name, data in self._permissions.items()
        }


class PermissionPrompter:
    """Interactive permission request handler.

    Displays permission requests to users and collects their consent
    for sensitive permissions.
    """

    # Risk level colors and icons
    RISK_STYLES = {
        "low": {"color": "green", "icon": "●"},
        "medium": {"color": "yellow", "icon": "▲"},
        "high": {"color": "red", "icon": "◆"},
    }

    def __init__(self, console: Optional["Console"] = None):
        from rich.console import Console
        self._console = console or Console()
        self._audit_logger = SecurityAuditLogger()

    def request_permissions(
        self,
        skill_name: str,
        permissions: list[str],
        skill_version: str = "",
        auto_approve_safe: bool = True,
    ) -> tuple[bool, list[str]]:
        """Request user approval for permissions.

        Args:
            skill_name: Name of the skill
            permissions: List of requested permissions
            skill_version: Version of the skill
            auto_approve_safe: Auto-approve safe permissions

        Returns:
            Tuple of (all_approved, list of approved permissions)
        """
        from rich.prompt import Confirm

        # Categorize permissions
        safe_perms = []
        sensitive_perms = []

        for perm in permissions:
            if perm in PermissionChecker.SAFE_PERMISSIONS:
                safe_perms.append(perm)
            else:
                sensitive_perms.append(perm)

        approved = []

        # Auto-approve safe permissions
        if auto_approve_safe:
            approved.extend(safe_perms)

        # If no sensitive permissions, we're done
        if not sensitive_perms:
            return True, approved

        # Display permission request panel
        self._display_permission_panel(skill_name, skill_version, sensitive_perms)

        # Request approval for each sensitive permission
        self._console.print()
        for perm in sensitive_perms:
            risk = PermissionChecker.PERMISSION_RISK_LEVELS.get(perm, "medium")
            desc = PermissionChecker.PERMISSION_DESCRIPTIONS.get(perm, perm)
            style = self.RISK_STYLES.get(risk, self.RISK_STYLES["medium"])

            prompt_text = (
                f"[{style['color']}]{style['icon']}[/{style['color']}] "
                f"Allow [bold]{perm}[/bold] ({desc})?"
            )

            try:
                if Confirm.ask(prompt_text, default=False):
                    approved.append(perm)
                    self._audit_logger.log_permission_granted(skill_name, perm, "user")
                else:
                    self._audit_logger.log_permission_denied(
                        skill_name, perm, "user_rejected"
                    )
            except KeyboardInterrupt:
                self._console.print("\n[yellow]Permission request cancelled[/yellow]")
                return False, []

        # Check if all required sensitive permissions were granted
        all_approved = len(approved) == len(permissions)

        if not all_approved:
            missing = set(sensitive_perms) - set(approved)
            self._console.print(
                f"\n[yellow]Warning: Skill may not function correctly without: "
                f"{', '.join(missing)}[/yellow]"
            )

        return all_approved, approved

    def _display_permission_panel(
        self,
        skill_name: str,
        skill_version: str,
        permissions: list[str],
    ) -> None:
        """Display the permission request panel.

        Args:
            skill_name: Name of the skill
            skill_version: Version string
            permissions: List of sensitive permissions
        """
        from rich.panel import Panel
        from rich.table import Table
        from rich.text import Text

        # Build permission table
        table = Table(show_header=True, header_style="bold", box=None)
        table.add_column("Risk", width=6)
        table.add_column("Permission", width=20)
        table.add_column("Description", width=40)

        for perm in permissions:
            risk = PermissionChecker.PERMISSION_RISK_LEVELS.get(perm, "medium")
            desc = PermissionChecker.PERMISSION_DESCRIPTIONS.get(perm, perm)
            style = self.RISK_STYLES.get(risk, self.RISK_STYLES["medium"])

            risk_text = Text(f"{style['icon']} {risk.upper()}", style=style["color"])
            table.add_row(risk_text, perm, desc)

        # Create panel
        version_str = f" v{skill_version}" if skill_version else ""
        title = f"Permission Request: {skill_name}{version_str}"

        panel_content = Text()
        panel_content.append(
            "This skill requests the following sensitive permissions:\n\n",
            style="dim",
        )

        self._console.print()
        self._console.print(Panel(table, title=title, border_style="yellow"))
        self._console.print(
            "[dim]Review each permission carefully. "
            "Only grant permissions you trust.[/dim]"
        )

    def request_single_permission(
        self,
        skill_name: str,
        permission: str,
        reason: str = "",
    ) -> bool:
        """Request approval for a single permission at runtime.

        Args:
            skill_name: Name of the skill
            permission: Permission being requested
            reason: Optional reason for the request

        Returns:
            bool: True if approved
        """
        from rich.prompt import Confirm

        risk = PermissionChecker.PERMISSION_RISK_LEVELS.get(permission, "medium")
        desc = PermissionChecker.PERMISSION_DESCRIPTIONS.get(permission, permission)
        style = self.RISK_STYLES.get(risk, self.RISK_STYLES["medium"])

        self._console.print()
        self._console.print(
            f"[bold]Runtime Permission Request[/bold] from [cyan]{skill_name}[/cyan]"
        )
        if reason:
            self._console.print(f"[dim]Reason: {reason}[/dim]")

        prompt_text = (
            f"[{style['color']}]{style['icon']}[/{style['color']}] "
            f"Allow [bold]{permission}[/bold] ({desc})?"
        )

        try:
            result = Confirm.ask(prompt_text, default=False)
            if result:
                self._audit_logger.log_permission_granted(skill_name, permission, "runtime")
            else:
                self._audit_logger.log_permission_denied(
                    skill_name, permission, "runtime_rejected"
                )
            return result
        except KeyboardInterrupt:
            self._console.print("\n[yellow]Request cancelled[/yellow]")
            return False


class PermissionContext:
    """Runtime permission enforcement context.

    Provides a context manager that enforces permissions during
    skill execution by intercepting sensitive operations.
    """

    def __init__(
        self,
        skill_name: str,
        granted_permissions: set[str],
        permission_store: PermissionStore | None = None,
        prompter: PermissionPrompter | None = None,
    ):
        self.skill_name = skill_name
        self.granted_permissions = granted_permissions
        self._store = permission_store or PermissionStore()
        self._prompter = prompter
        self._audit_logger = SecurityAuditLogger()
        self._active = False

    def __enter__(self):
        """Enter the permission context."""
        self._active = True
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Exit the permission context."""
        self._active = False
        return False

    def check_permission(
        self,
        permission: str,
        operation: str = "",
        prompt_if_missing: bool = False,
    ) -> bool:
        """Check if an operation is permitted.

        Args:
            permission: Required permission
            operation: Description of the operation
            prompt_if_missing: Whether to prompt user if permission is missing

        Returns:
            bool: True if permitted

        Raises:
            PermissionDeniedError: If permission is denied
        """
        # Safe permissions are always allowed
        if permission in PermissionChecker.SAFE_PERMISSIONS:
            return True

        # Check if already granted
        if permission in self.granted_permissions:
            return True

        # Check persistent store
        if self._store.has_permission(self.skill_name, permission):
            self.granted_permissions.add(permission)
            return True

        # Optionally prompt for permission
        if prompt_if_missing and self._prompter:
            reason = f"Operation: {operation}" if operation else ""
            if self._prompter.request_single_permission(
                self.skill_name, permission, reason
            ):
                self.granted_permissions.add(permission)
                self._store.grant_permissions(
                    self.skill_name, [permission]
                )
                return True

        # Permission denied
        self._audit_logger.log_security_violation(
            self.skill_name,
            "permission_denied",
            f"Attempted {operation or permission} without permission",
        )
        return False

    def require_permission(
        self,
        permission: str,
        operation: str = "",
    ) -> None:
        """Require a permission, raising an error if not granted.

        Args:
            permission: Required permission
            operation: Description of the operation

        Raises:
            PermissionDeniedError: If permission is not granted
        """
        if not self.check_permission(permission, operation):
            raise PermissionDeniedError(
                f"Skill '{self.skill_name}' does not have permission '{permission}' "
                f"required for: {operation or 'this operation'}"
            )

    def is_active(self) -> bool:
        """Check if the context is currently active."""
        return self._active


class PermissionDeniedError(SecurityError):
    """Raised when a permission is denied."""

    pass


class SecurityEventReporter:
    """Report security events to the central server.

    Collects and reports security-related events for monitoring
    and incident response purposes.
    """

    REPORT_URL = "https://skills.socialhub.ai/api/v1/security/events"
    LOCAL_QUEUE_PATH = Path.home() / ".socialhub" / "security" / "event_queue.json"
    MAX_QUEUE_SIZE = 100

    def __init__(self):
        self._event_queue: list[dict] = []
        self._logger = logging.getLogger(__name__)
        self._load_queue()

    def _load_queue(self) -> None:
        """Load pending events from disk."""
        try:
            if self.LOCAL_QUEUE_PATH.exists():
                data = json.loads(self.LOCAL_QUEUE_PATH.read_text(encoding="utf-8"))
                self._event_queue = data.get("events", [])
        except Exception as e:
            self._logger.warning("Failed to load event queue: %s", e)
            self._event_queue = []

    def _save_queue(self) -> None:
        """Save pending events to disk."""
        try:
            self.LOCAL_QUEUE_PATH.parent.mkdir(parents=True, exist_ok=True)
            data = {
                "version": "1.0",
                "events": self._event_queue[-self.MAX_QUEUE_SIZE:],
            }
            self.LOCAL_QUEUE_PATH.write_text(
                json.dumps(data, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        except Exception as e:
            self._logger.warning("Failed to save event queue: %s", e)

    def report_event(
        self,
        event_type: str,
        skill_name: str,
        details: dict,
        severity: str = "info",
    ) -> None:
        """Report a security event.

        Args:
            event_type: Type of event (e.g., 'signature_failure', 'permission_violation')
            skill_name: Name of the affected skill
            details: Additional event details
            severity: Event severity ('info', 'warning', 'error', 'critical')
        """
        event = {
            "type": event_type,
            "skill_name": skill_name,
            "details": details,
            "severity": severity,
            "timestamp": datetime.now().isoformat(),
            "reported": False,
        }

        self._event_queue.append(event)
        self._save_queue()

        # Try to report immediately
        self._try_report()

    def report_signature_failure(
        self,
        skill_name: str,
        version: str,
        reason: str,
    ) -> None:
        """Report a signature verification failure."""
        self.report_event(
            event_type="signature_failure",
            skill_name=skill_name,
            details={"version": version, "reason": reason},
            severity="error",
        )

    def report_permission_violation(
        self,
        skill_name: str,
        permission: str,
        operation: str,
    ) -> None:
        """Report a permission violation."""
        self.report_event(
            event_type="permission_violation",
            skill_name=skill_name,
            details={"permission": permission, "operation": operation},
            severity="warning",
        )

    def report_sandbox_violation(
        self,
        skill_name: str,
        sandbox_type: str,
        details: str,
    ) -> None:
        """Report a sandbox violation."""
        self.report_event(
            event_type="sandbox_violation",
            skill_name=skill_name,
            details={"sandbox_type": sandbox_type, "details": details},
            severity="error",
        )

    def report_revoked_skill_attempt(
        self,
        skill_name: str,
        certificate_id: str,
    ) -> None:
        """Report an attempt to use a revoked skill."""
        self.report_event(
            event_type="revoked_skill_attempt",
            skill_name=skill_name,
            details={"certificate_id": certificate_id},
            severity="critical",
        )

    def _try_report(self) -> bool:
        """Try to report pending events to the server.

        Returns:
            bool: True if all events were reported successfully
        """
        unreported = [e for e in self._event_queue if not e.get("reported")]
        if not unreported:
            return True

        try:
            import httpx

            response = httpx.post(
                self.REPORT_URL,
                json={"events": unreported},
                timeout=10,
            )

            if response.status_code == 200:
                for event in unreported:
                    event["reported"] = True
                self._save_queue()
                return True

        except Exception as e:
            self._logger.debug("Failed to report events: %s", e)

        return False

    def get_pending_count(self) -> int:
        """Get the number of pending events."""
        return len([e for e in self._event_queue if not e.get("reported")])

    def clear_reported(self) -> None:
        """Clear reported events from the queue."""
        self._event_queue = [e for e in self._event_queue if not e.get("reported")]
        self._save_queue()


class HealthCheckResult:
    """Result of a skill health check."""

    def __init__(
        self,
        skill_name: str,
        status: str,
        checks: dict[str, dict],
    ):
        self.skill_name = skill_name
        self.status = status  # 'healthy', 'warning', 'critical'
        self.checks = checks
        self.checked_at = datetime.now()

    def is_healthy(self) -> bool:
        """Check if the skill is healthy."""
        return self.status == "healthy"

    def get_issues(self) -> list[str]:
        """Get list of issues found."""
        issues = []
        for check_name, result in self.checks.items():
            if not result.get("passed"):
                issues.append(f"{check_name}: {result.get('message', 'Failed')}")
        return issues

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "skill_name": self.skill_name,
            "status": self.status,
            "checks": self.checks,
            "checked_at": self.checked_at.isoformat(),
            "issues": self.get_issues(),
        }


class SkillHealthChecker:
    """Check health status of installed skills.

    Performs various checks including certificate expiration,
    revocation status, file integrity, and update availability.
    """

    # Warning threshold for certificate expiration (days)
    CERT_EXPIRY_WARNING_DAYS = 30

    def __init__(self):
        self._registry = None  # Lazy load to avoid circular imports
        self._revocation_manager = RevocationListManager()
        self._verifier = SignatureVerifier()
        self._logger = logging.getLogger(__name__)

    @property
    def registry(self):
        """Lazy load registry to avoid circular imports."""
        if self._registry is None:
            from .registry import SkillRegistry
            self._registry = SkillRegistry()
        return self._registry

    def check_all(self) -> list[HealthCheckResult]:
        """Check health of all installed skills.

        Returns:
            List of HealthCheckResult objects
        """
        results = []
        for skill in self.registry.list_installed():
            result = self.check_skill(skill.name)
            results.append(result)
        return results

    def check_skill(self, skill_name: str) -> HealthCheckResult:
        """Check health of a specific skill.

        Args:
            skill_name: Name of the skill to check

        Returns:
            HealthCheckResult object
        """
        checks = {}

        # Get installed skill info
        installed = self.registry.get_installed(skill_name)
        if not installed:
            return HealthCheckResult(
                skill_name=skill_name,
                status="critical",
                checks={"installed": {"passed": False, "message": "Skill not installed"}},
            )

        # Check 1: Certificate expiration
        checks["certificate"] = self._check_certificate(installed)

        # Check 2: Revocation status
        checks["revocation"] = self._check_revocation(installed)

        # Check 3: File integrity
        checks["integrity"] = self._check_integrity(installed)

        # Check 4: Enabled status
        checks["enabled"] = self._check_enabled(installed)

        # Check 5: Update availability
        checks["updates"] = self._check_updates(installed)

        # Determine overall status
        status = self._determine_status(checks)

        return HealthCheckResult(
            skill_name=skill_name,
            status=status,
            checks=checks,
        )

    def _check_certificate(self, installed) -> dict:
        """Check certificate status."""
        manifest = installed.manifest
        if not manifest or not manifest.certification:
            return {
                "passed": False,
                "message": "No certification information",
                "severity": "warning",
            }

        cert = manifest.certification

        # Check expiration
        if cert.expires_at:
            days_until_expiry = (cert.expires_at - datetime.now()).days

            if days_until_expiry < 0:
                return {
                    "passed": False,
                    "message": f"Certificate expired {-days_until_expiry} days ago",
                    "severity": "critical",
                }

            if days_until_expiry < self.CERT_EXPIRY_WARNING_DAYS:
                return {
                    "passed": True,
                    "message": f"Certificate expires in {days_until_expiry} days",
                    "severity": "warning",
                }

        return {
            "passed": True,
            "message": "Certificate is valid",
            "severity": "info",
        }

    def _check_revocation(self, installed) -> dict:
        """Check revocation status."""
        cert_id = None
        if installed.manifest and installed.manifest.certification:
            cert_id = installed.manifest.certification.certificate_id

        if self._revocation_manager.is_revoked(installed.name, cert_id):
            return {
                "passed": False,
                "message": "Skill has been revoked",
                "severity": "critical",
            }

        return {
            "passed": True,
            "message": "Not revoked",
            "severity": "info",
        }

    def _check_integrity(self, installed) -> dict:
        """Check file integrity."""
        try:
            skill_path = Path(installed.path)

            # Check manifest exists
            manifest_path = skill_path / "skill.yaml"
            if not manifest_path.exists():
                return {
                    "passed": False,
                    "message": "Manifest file missing",
                    "severity": "critical",
                }

            # Check entrypoint exists
            if installed.manifest:
                entrypoint = skill_path / installed.manifest.entrypoint
                if not entrypoint.exists():
                    return {
                        "passed": False,
                        "message": f"Entrypoint '{installed.manifest.entrypoint}' missing",
                        "severity": "critical",
                    }

            return {
                "passed": True,
                "message": "Files intact",
                "severity": "info",
            }

        except Exception as e:
            return {
                "passed": False,
                "message": f"Integrity check failed: {e}",
                "severity": "error",
            }

    def _check_enabled(self, installed) -> dict:
        """Check if skill is enabled."""
        if installed.enabled:
            return {
                "passed": True,
                "message": "Enabled",
                "severity": "info",
            }
        return {
            "passed": True,
            "message": "Disabled by user",
            "severity": "info",
        }

    def _check_updates(self, installed) -> dict:
        """Check for available updates."""
        try:
            from .store_client import SkillsStoreClient

            client = SkillsStoreClient()
            skill_info = client.get_skill(installed.name)

            if skill_info.version != installed.version:
                return {
                    "passed": True,
                    "message": f"Update available: {installed.version} -> {skill_info.version}",
                    "severity": "info",
                    "update_available": True,
                    "latest_version": skill_info.version,
                }

            return {
                "passed": True,
                "message": "Up to date",
                "severity": "info",
            }

        except Exception:
            return {
                "passed": True,
                "message": "Could not check for updates",
                "severity": "info",
            }

    def _determine_status(self, checks: dict) -> str:
        """Determine overall health status from checks."""
        has_critical = False
        has_warning = False

        for check in checks.values():
            if not check.get("passed"):
                severity = check.get("severity", "warning")
                if severity == "critical":
                    has_critical = True
                elif severity in ("warning", "error"):
                    has_warning = True

        if has_critical:
            return "critical"
        if has_warning:
            return "warning"
        return "healthy"

    def get_summary(self, results: list[HealthCheckResult]) -> dict:
        """Get summary of health check results.

        Args:
            results: List of health check results

        Returns:
            Summary dictionary
        """
        summary = {
            "total": len(results),
            "healthy": 0,
            "warning": 0,
            "critical": 0,
            "skills": {},
        }

        for result in results:
            summary[result.status] += 1
            summary["skills"][result.skill_name] = {
                "status": result.status,
                "issues": result.get_issues(),
            }

        return summary
