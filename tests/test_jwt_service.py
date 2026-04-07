"""Unit tests for jwt_service."""
import time
import pytest
from unittest.mock import patch

from mcp_server.services.jwt_service import create_token, verify_token


def test_create_and_verify_roundtrip():
    """create_token + verify_token returns original tenant_id."""
    token = create_token("tenant-abc")
    assert isinstance(token, str)
    assert token.count(".") == 2  # header.payload.sig
    tenant_id = verify_token(token)
    assert tenant_id == "tenant-abc"


def test_verify_expired_token():
    """verify_token returns None for expired token."""
    token = create_token("tenant-abc")
    with patch("mcp_server.services.jwt_service._now", return_value=int(time.time()) + 99999):
        result = verify_token(token)
    assert result is None


def test_verify_tampered_token():
    """verify_token returns None for tampered payload."""
    import base64, json
    token = create_token("tenant-abc")
    parts = token.split(".")
    bad_payload = base64.urlsafe_b64encode(
        json.dumps({"sub": "hacker", "exp": int(time.time()) + 9999}).encode()
    ).rstrip(b"=").decode()
    tampered = f"{parts[0]}.{bad_payload}.{parts[2]}"
    assert verify_token(tampered) is None


def test_verify_invalid_format():
    """verify_token returns None for garbage input."""
    assert verify_token("not.a.token") is None
    assert verify_token("") is None
    assert verify_token("only-one-part") is None
