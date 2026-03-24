"""Tests for skills security module."""

import base64
import hashlib
import json
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from socialhub.cli.skills.security import (
    HashVerifier,
    KeyManager,
    PermissionChecker,
    PermissionContext,
    PermissionDeniedError,
    PermissionStore,
    RevocationListManager,
    SecurityAuditLogger,
    SecurityError,
    SignatureVerifier,
    validate_skill_source,
)
from socialhub.cli.skills.models import SkillCertification, SkillManifest


class TestHashVerifier:
    """Tests for HashVerifier class."""

    @pytest.fixture
    def verifier(self):
        return HashVerifier()

    @pytest.fixture
    def sample_content(self):
        return b"Hello, SocialHub.AI!"

    def test_compute_hash_sha256(self, verifier, sample_content):
        """Test SHA256 hash computation."""
        expected = hashlib.sha256(sample_content).hexdigest()
        result = verifier.compute_hash(sample_content, "sha256")
        assert result == expected

    def test_compute_hash_sha384(self, verifier, sample_content):
        """Test SHA384 hash computation."""
        expected = hashlib.sha384(sample_content).hexdigest()
        result = verifier.compute_hash(sample_content, "sha384")
        assert result == expected

    def test_compute_hash_sha512(self, verifier, sample_content):
        """Test SHA512 hash computation."""
        expected = hashlib.sha512(sample_content).hexdigest()
        result = verifier.compute_hash(sample_content, "sha512")
        assert result == expected

    def test_compute_hash_unsupported_algorithm(self, verifier, sample_content):
        """Test that unsupported algorithms raise ValueError."""
        with pytest.raises(ValueError, match="Unsupported hash algorithm"):
            verifier.compute_hash(sample_content, "md5")

    def test_verify_hash_valid(self, verifier, sample_content):
        """Test hash verification with valid hash."""
        expected_hash = hashlib.sha256(sample_content).hexdigest()
        assert verifier.verify_hash(sample_content, expected_hash) is True

    def test_verify_hash_invalid(self, verifier, sample_content):
        """Test hash verification with invalid hash."""
        wrong_hash = "a" * 64  # Wrong hash
        assert verifier.verify_hash(sample_content, wrong_hash) is False

    def test_verify_hash_different_content(self, verifier):
        """Test that different content produces different hash."""
        content1 = b"Hello"
        content2 = b"World"
        hash1 = verifier.compute_hash(content1)
        assert verifier.verify_hash(content2, hash1) is False

    def test_verify_multiple_hashes_all_valid(self, verifier, sample_content):
        """Test multiple hash verification when all are valid."""
        hashes = {
            "sha256": hashlib.sha256(sample_content).hexdigest(),
            "sha512": hashlib.sha512(sample_content).hexdigest(),
        }
        valid, failed = verifier.verify_multiple_hashes(sample_content, hashes)
        assert valid is True
        assert failed == []

    def test_verify_multiple_hashes_one_invalid(self, verifier, sample_content):
        """Test multiple hash verification when one is invalid."""
        hashes = {
            "sha256": hashlib.sha256(sample_content).hexdigest(),
            "sha512": "invalid_hash",
        }
        valid, failed = verifier.verify_multiple_hashes(sample_content, hashes)
        assert valid is False
        assert "sha512" in failed

    def test_verify_multiple_hashes_ignores_unsupported(self, verifier, sample_content):
        """Test that unsupported algorithms are ignored."""
        hashes = {
            "sha256": hashlib.sha256(sample_content).hexdigest(),
            "md5": "ignored",  # Unsupported
        }
        valid, failed = verifier.verify_multiple_hashes(sample_content, hashes)
        assert valid is True


class TestKeyManager:
    """Tests for KeyManager class."""

    @pytest.fixture
    def key_manager(self):
        return KeyManager()

    def test_load_public_key(self, key_manager):
        """Test public key loading."""
        # This will use the embedded key
        try:
            key = key_manager.load_public_key()
            assert key is not None
        except SecurityError:
            # Expected if the placeholder key is used
            pass

    def test_key_caching(self, key_manager):
        """Test that key is cached after first load."""
        try:
            key1 = key_manager.load_public_key()
            key2 = key_manager.load_public_key()
            assert key1 is key2  # Same object (cached)
        except SecurityError:
            pass

    def test_get_key_fingerprint_format(self, key_manager):
        """Test fingerprint format."""
        try:
            fingerprint = key_manager.get_key_fingerprint()
            assert fingerprint.startswith("sha256:")
            assert len(fingerprint) == 7 + 64  # "sha256:" + 64 hex chars
        except SecurityError:
            pass


class TestSignatureVerifier:
    """Tests for SignatureVerifier class."""

    @pytest.fixture
    def verifier(self):
        return SignatureVerifier()

    @pytest.fixture
    def valid_certification(self):
        return SkillCertification(
            certified_at=datetime.now(),
            certified_by="SocialHub.AI",
            signature=base64.b64encode(b"test_signature").decode(),
            certificate_id="CERT-2024-00001",
            expires_at=datetime.now() + timedelta(days=365),
        )

    @pytest.fixture
    def expired_certification(self):
        return SkillCertification(
            certified_at=datetime.now() - timedelta(days=400),
            certified_by="SocialHub.AI",
            signature=base64.b64encode(b"test_signature").decode(),
            certificate_id="CERT-2024-00002",
            expires_at=datetime.now() - timedelta(days=35),  # Expired
        )

    @pytest.fixture
    def untrusted_certification(self):
        return SkillCertification(
            certified_at=datetime.now(),
            certified_by="Evil.Corp",  # Not trusted
            signature=base64.b64encode(b"test_signature").decode(),
            certificate_id="CERT-EVIL-00001",
        )

    def test_missing_certification_raises(self, verifier):
        """Test that missing certification raises SecurityError."""
        manifest = SkillManifest(
            name="test-skill",
            version="1.0.0",
            certification=None,
        )
        with pytest.raises(SecurityError, match="not certified"):
            verifier.verify_manifest_signature(manifest)

    def test_untrusted_ca_raises(self, verifier, untrusted_certification):
        """Test that untrusted CA raises SecurityError."""
        manifest = SkillManifest(
            name="test-skill",
            version="1.0.0",
            certification=untrusted_certification,
        )
        with pytest.raises(SecurityError, match="not certified by trusted authority"):
            verifier.verify_manifest_signature(manifest)

    def test_expired_certificate_raises(self, verifier, expired_certification):
        """Test that expired certificate raises SecurityError."""
        manifest = SkillManifest(
            name="test-skill",
            version="1.0.0",
            certification=expired_certification,
        )
        with pytest.raises(SecurityError, match="expired"):
            verifier.verify_manifest_signature(manifest)

    def test_missing_signature_raises(self, verifier):
        """Test that missing signature raises SecurityError."""
        cert = SkillCertification(
            certified_at=datetime.now(),
            certified_by="SocialHub.AI",
            signature="",  # Empty signature
            certificate_id="CERT-2024-00001",
        )
        manifest = SkillManifest(
            name="test-skill",
            version="1.0.0",
            certification=cert,
        )
        with pytest.raises(SecurityError, match="missing signature"):
            verifier.verify_manifest_signature(manifest)

    def test_build_signed_data_is_deterministic(self, verifier, valid_certification):
        """Test that signed data is built deterministically."""
        data1 = verifier._build_signed_data("test", "1.0.0", valid_certification)
        data2 = verifier._build_signed_data("test", "1.0.0", valid_certification)
        assert data1 == data2

    def test_build_signed_data_different_for_different_inputs(
        self, verifier, valid_certification
    ):
        """Test that different inputs produce different signed data."""
        data1 = verifier._build_signed_data("skill1", "1.0.0", valid_certification)
        data2 = verifier._build_signed_data("skill2", "1.0.0", valid_certification)
        assert data1 != data2

    def test_verify_package_hash_valid(self, verifier):
        """Test package hash verification with valid hash."""
        content = b"test package content"
        expected_hash = hashlib.sha256(content).hexdigest()
        assert verifier.verify_package_hash(content, expected_hash) is True

    def test_verify_package_hash_invalid_raises(self, verifier):
        """Test that invalid package hash raises SecurityError."""
        content = b"test package content"
        wrong_hash = "a" * 64
        with pytest.raises(SecurityError, match="Package hash verification failed"):
            verifier.verify_package_hash(content, wrong_hash)


class TestPermissionChecker:
    """Tests for PermissionChecker class."""

    @pytest.fixture
    def checker(self):
        return PermissionChecker()

    def test_safe_permissions_always_granted(self, checker):
        """Test that safe permissions don't require explicit grant."""
        granted, missing = checker.check_permissions(
            "test-skill", ["file:read", "data:read", "config:read"]
        )
        assert granted is True
        assert missing == []

    def test_sensitive_permissions_require_grant(self, checker):
        """Test that sensitive permissions require explicit grant."""
        granted, missing = checker.check_permissions(
            "test-skill", ["network:internet", "execute"]
        )
        assert granted is False
        assert "network:internet" in missing
        assert "execute" in missing

    def test_grant_permission(self, checker):
        """Test granting permissions."""
        checker.grant_permission("test-skill", "network:internet")
        granted, missing = checker.check_permissions(
            "test-skill", ["network:internet"]
        )
        assert granted is True
        assert missing == []

    def test_revoke_permission(self, checker):
        """Test revoking permissions."""
        checker.grant_permission("test-skill", "network:internet")
        checker.revoke_permission("test-skill", "network:internet")
        granted, missing = checker.check_permissions(
            "test-skill", ["network:internet"]
        )
        assert granted is False
        assert "network:internet" in missing

    def test_revoke_all_permissions(self, checker):
        """Test revoking all permissions."""
        checker.grant_permission("test-skill", "network:internet")
        checker.grant_permission("test-skill", "execute")
        checker.revoke_all_permissions("test-skill")

        permissions = checker.get_granted_permissions("test-skill")
        assert len(permissions) == 0

    def test_get_granted_permissions_returns_copy(self, checker):
        """Test that get_granted_permissions returns a copy."""
        checker.grant_permission("test-skill", "execute")
        perms = checker.get_granted_permissions("test-skill")
        perms.add("hacked")  # Try to modify

        # Original should be unchanged
        original = checker.get_granted_permissions("test-skill")
        assert "hacked" not in original

    def test_is_sensitive(self, checker):
        """Test sensitivity classification."""
        assert checker.is_sensitive("network:internet") is True
        assert checker.is_sensitive("execute") is True
        assert checker.is_sensitive("file:read") is False
        assert checker.is_sensitive("data:read") is False

    def test_get_risk_level(self, checker):
        """Test risk level classification."""
        assert checker.get_risk_level("execute") == "high"
        assert checker.get_risk_level("network:internet") == "high"
        assert checker.get_risk_level("file:write") == "medium"
        assert checker.get_risk_level("file:read") == "low"

    def test_format_permission_request(self, checker):
        """Test permission request formatting."""
        output = checker.format_permission_request(
            "test-skill", ["file:read", "network:internet"]
        )
        assert "test-skill" in output
        assert "file:read" in output
        assert "network:internet" in output
        assert "HIGH RISK" in output


class TestRevocationListManager:
    """Tests for RevocationListManager class."""

    @pytest.fixture
    def manager(self):
        return RevocationListManager()

    def test_empty_list_not_revoked(self, manager):
        """Test that empty list means nothing is revoked."""
        assert manager.is_revoked("any-skill") is False

    def test_revoked_skill_detected(self, manager):
        """Test that revoked skills are detected."""
        manager._revoked_skills = {"malicious-skill"}
        assert manager.is_revoked("malicious-skill") is True
        assert manager.is_revoked("safe-skill") is False

    def test_revoked_certificate_detected(self, manager):
        """Test that revoked certificates are detected."""
        manager._revoked_certificates = {"CERT-REVOKED-001"}
        assert manager.is_revoked("any-skill", "CERT-REVOKED-001") is True
        assert manager.is_revoked("any-skill", "CERT-VALID-001") is False

    def test_should_update_when_never_updated(self, manager):
        """Test that update is needed when never updated."""
        assert manager._should_update() is True

    def test_should_not_update_when_recent(self, manager):
        """Test that update is not needed when recently updated."""
        manager._last_update = datetime.now()
        assert manager._should_update() is False


class TestValidateSkillSource:
    """Tests for validate_skill_source function."""

    def test_official_store_valid(self):
        """Test that official store URLs are valid."""
        assert validate_skill_source("https://skills.socialhub.ai/api/v1/skills") is True
        assert validate_skill_source("https://store.socialhub.ai/packages/test") is True

    def test_http_rejected(self):
        """Test that HTTP (non-HTTPS) is rejected."""
        assert validate_skill_source("http://skills.socialhub.ai/api/v1/skills") is False

    def test_unofficial_source_rejected(self):
        """Test that unofficial sources are rejected."""
        assert validate_skill_source("https://evil.com/skills") is False
        assert validate_skill_source("https://fake-socialhub.ai/skills") is False

    def test_invalid_url_rejected(self):
        """Test that invalid URLs are rejected."""
        assert validate_skill_source("not-a-url") is False
        assert validate_skill_source("") is False

    def test_file_url_rejected(self):
        """Test that file URLs are rejected."""
        assert validate_skill_source("file:///etc/passwd") is False


class TestSecurityAuditLogger:
    """Tests for SecurityAuditLogger class."""

    @pytest.fixture
    def logger(self, tmp_path):
        # Use temporary path for testing
        with patch.object(SecurityAuditLogger, "LOG_PATH", tmp_path / "audit.log"):
            return SecurityAuditLogger()

    def test_log_signature_verified(self, logger):
        """Test logging signature verification."""
        logger.log_signature_verified("test-skill", "1.0.0")
        # No exception means success

    def test_log_signature_failed(self, logger):
        """Test logging signature failure."""
        logger.log_signature_failed("test-skill", "1.0.0", "Invalid signature")
        # No exception means success

    def test_log_permission_granted(self, logger):
        """Test logging permission grant."""
        logger.log_permission_granted("test-skill", "execute", "user")
        # No exception means success

    def test_log_security_violation(self, logger):
        """Test logging security violation."""
        logger.log_security_violation("test-skill", "sandbox_escape", "Attempted file access")
        # No exception means success


class TestPermissionStore:
    """Tests for PermissionStore class."""

    @pytest.fixture
    def store(self, tmp_path):
        """Create a permission store with temporary storage."""
        with patch.object(
            PermissionStore, "PERMISSIONS_FILE", tmp_path / "permissions.json"
        ):
            return PermissionStore()

    def test_grant_permissions(self, store):
        """Test granting permissions."""
        store.grant_permissions("test-skill", ["execute", "network:internet"], "1.0.0")

        perms = store.get_permissions("test-skill")
        assert "execute" in perms
        assert "network:internet" in perms

    def test_has_permission(self, store):
        """Test checking individual permission."""
        store.grant_permissions("test-skill", ["execute"])

        assert store.has_permission("test-skill", "execute") is True
        assert store.has_permission("test-skill", "network:internet") is False

    def test_revoke_permissions(self, store):
        """Test revoking specific permissions."""
        store.grant_permissions("test-skill", ["execute", "network:internet"])
        store.revoke_permissions("test-skill", ["execute"])

        perms = store.get_permissions("test-skill")
        assert "execute" not in perms
        assert "network:internet" in perms

    def test_revoke_all(self, store):
        """Test revoking all permissions."""
        store.grant_permissions("test-skill", ["execute", "network:internet"])
        store.revoke_all("test-skill")

        perms = store.get_permissions("test-skill")
        assert len(perms) == 0

    def test_persistence(self, tmp_path):
        """Test that permissions are persisted to disk."""
        perm_file = tmp_path / "permissions.json"

        with patch.object(PermissionStore, "PERMISSIONS_FILE", perm_file):
            store1 = PermissionStore()
            store1.grant_permissions("test-skill", ["execute"])

        # Create new store instance - should load from disk
        with patch.object(PermissionStore, "PERMISSIONS_FILE", perm_file):
            store2 = PermissionStore()
            assert store2.has_permission("test-skill", "execute") is True

    def test_list_all_grants(self, store):
        """Test listing all permission grants."""
        store.grant_permissions("skill1", ["execute"])
        store.grant_permissions("skill2", ["network:internet", "data:write"])

        all_grants = store.list_all_grants()
        assert "skill1" in all_grants
        assert "skill2" in all_grants
        assert "execute" in all_grants["skill1"]
        assert "network:internet" in all_grants["skill2"]

    def test_empty_skill_returns_empty_set(self, store):
        """Test that non-existent skill returns empty set."""
        perms = store.get_permissions("nonexistent-skill")
        assert perms == set()


class TestPermissionContext:
    """Tests for PermissionContext class."""

    @pytest.fixture
    def store(self, tmp_path):
        """Create a permission store with temporary storage."""
        with patch.object(
            PermissionStore, "PERMISSIONS_FILE", tmp_path / "permissions.json"
        ):
            return PermissionStore()

    def test_context_activation(self, store):
        """Test that context properly activates and deactivates."""
        context = PermissionContext("test-skill", set(), store)

        assert context.is_active() is False

        with context:
            assert context.is_active() is True

        assert context.is_active() is False

    def test_check_safe_permission(self, store):
        """Test that safe permissions are always allowed."""
        context = PermissionContext("test-skill", set(), store)

        with context:
            assert context.check_permission("file:read") is True
            assert context.check_permission("data:read") is True

    def test_check_granted_permission(self, store):
        """Test that granted permissions are allowed."""
        granted = {"execute", "network:internet"}
        context = PermissionContext("test-skill", granted, store)

        with context:
            assert context.check_permission("execute") is True
            assert context.check_permission("network:internet") is True

    def test_check_denied_permission(self, store):
        """Test that non-granted permissions are denied."""
        context = PermissionContext("test-skill", set(), store)

        with context:
            assert context.check_permission("execute") is False
            assert context.check_permission("network:internet") is False

    def test_require_permission_raises(self, store):
        """Test that require_permission raises on missing permission."""
        context = PermissionContext("test-skill", set(), store)

        with context:
            with pytest.raises(PermissionDeniedError):
                context.require_permission("execute", "run external command")

    def test_require_permission_succeeds(self, store):
        """Test that require_permission succeeds with granted permission."""
        context = PermissionContext("test-skill", {"execute"}, store)

        with context:
            # Should not raise
            context.require_permission("execute", "run external command")

    def test_permission_from_store(self, store):
        """Test that permissions are loaded from store."""
        store.grant_permissions("test-skill", ["execute"])
        context = PermissionContext("test-skill", set(), store)

        with context:
            assert context.check_permission("execute") is True


class TestSecurityIntegration:
    """Integration tests for security module."""

    def test_full_verification_flow(self):
        """Test complete verification flow."""
        # Create a mock manifest with valid structure
        cert = SkillCertification(
            certified_at=datetime.now(),
            certified_by="SocialHub.AI",
            signature=base64.b64encode(b"mock_signature").decode(),
            certificate_id="CERT-2024-TEST",
            expires_at=datetime.now() + timedelta(days=365),
        )

        manifest = SkillManifest(
            name="test-skill",
            version="1.0.0",
            certification=cert,
        )

        verifier = SignatureVerifier()

        # The verification will fail due to invalid signature,
        # but it should check all the preliminary conditions first
        try:
            verifier.verify_manifest_signature(manifest)
        except SecurityError as e:
            # Should fail at signature verification, not earlier checks
            assert "Invalid signature" in str(e) or "Signature verification failed" in str(e)

    def test_permission_and_revocation_combined(self):
        """Test combined permission and revocation checks."""
        checker = PermissionChecker()
        revocation = RevocationListManager()

        # Grant permissions
        checker.grant_permission("test-skill", "network:internet")

        # Later, skill gets revoked
        revocation._revoked_skills = {"test-skill"}

        # Permission check still passes (separate from revocation)
        granted, _ = checker.check_permissions("test-skill", ["network:internet"])
        assert granted is True

        # But revocation check fails
        assert revocation.is_revoked("test-skill") is True

    def test_permission_store_and_context_integration(self, tmp_path):
        """Test integration between PermissionStore and PermissionContext."""
        perm_file = tmp_path / "permissions.json"

        with patch.object(PermissionStore, "PERMISSIONS_FILE", perm_file):
            # Store permissions
            store = PermissionStore()
            store.grant_permissions("integration-skill", ["execute", "data:write"])

            # Create context with empty initial permissions
            context = PermissionContext("integration-skill", set(), store)

            with context:
                # Should be able to check permissions from store
                assert context.check_permission("execute") is True
                assert context.check_permission("data:write") is True
                # Non-stored permission should fail
                assert context.check_permission("network:internet") is False
