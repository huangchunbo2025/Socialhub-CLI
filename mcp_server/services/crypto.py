"""Fernet symmetric encryption for Service Account JSON.

Environment variables:
    CREDENTIAL_ENCRYPT_KEY: Fernet key (base64-urlsafe, 32 bytes).
                            Generate with: Fernet.generate_key().decode()
"""

from __future__ import annotations

import os

from cryptography.fernet import Fernet


def _get_fernet() -> Fernet:
    key = os.environ.get("CREDENTIAL_ENCRYPT_KEY", "")
    if not key:
        raise RuntimeError(
            "CREDENTIAL_ENCRYPT_KEY environment variable is not set. "
            "Generate one with: python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\""
        )
    return Fernet(key.encode() if isinstance(key, str) else key)


def encrypt(plaintext: str) -> str:
    """Encrypt a plaintext string. Returns base64-urlsafe ciphertext string."""
    return _get_fernet().encrypt(plaintext.encode()).decode()


def decrypt(ciphertext: str) -> str:
    """Decrypt a ciphertext string produced by encrypt(). Returns original plaintext."""
    return _get_fernet().decrypt(ciphertext.encode()).decode()
