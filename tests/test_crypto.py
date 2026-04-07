"""Tests for Fernet encryption service."""
import os
from unittest.mock import patch

import pytest
from cryptography.fernet import Fernet


@pytest.fixture
def test_key():
    return Fernet.generate_key().decode()


def test_encrypt_returns_string(test_key):
    """encrypt() 返回字符串（不是原文）。"""
    with patch.dict(os.environ, {"CREDENTIAL_ENCRYPT_KEY": test_key}):
        from mcp_server.services import crypto
        import importlib; importlib.reload(crypto)
        result = crypto.encrypt("hello world")
        assert isinstance(result, str)
        assert result != "hello world"


def test_decrypt_roundtrip(test_key):
    """encrypt → decrypt 还原原文。"""
    with patch.dict(os.environ, {"CREDENTIAL_ENCRYPT_KEY": test_key}):
        from mcp_server.services import crypto
        import importlib; importlib.reload(crypto)
        original = '{"type": "service_account", "project_id": "test"}'
        encrypted = crypto.encrypt(original)
        decrypted = crypto.decrypt(encrypted)
        assert decrypted == original


def test_encrypt_different_each_time(test_key):
    """相同明文每次加密结果不同（Fernet IV 随机）。"""
    with patch.dict(os.environ, {"CREDENTIAL_ENCRYPT_KEY": test_key}):
        from mcp_server.services import crypto
        import importlib; importlib.reload(crypto)
        e1 = crypto.encrypt("same text")
        e2 = crypto.encrypt("same text")
        assert e1 != e2


def test_missing_key_raises():
    """未设置 CREDENTIAL_ENCRYPT_KEY 时 encrypt 抛出 RuntimeError。"""
    with patch.dict(os.environ, {}, clear=True):
        if "CREDENTIAL_ENCRYPT_KEY" in os.environ:
            del os.environ["CREDENTIAL_ENCRYPT_KEY"]
        from mcp_server.services import crypto
        import importlib; importlib.reload(crypto)
        with pytest.raises(RuntimeError, match="CREDENTIAL_ENCRYPT_KEY"):
            crypto.encrypt("test")
