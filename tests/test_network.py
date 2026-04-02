"""Tests for cli.network — proxy/CA utilities."""

import pytest
import httpx

from cli.config import NetworkConfig
from cli.network import build_httpx_kwargs, build_httpx_client


def test_no_proxy_no_ca():
    """Default config produces no proxy/verify/timeout overrides in build_httpx_kwargs."""
    config = NetworkConfig(http_proxy="", https_proxy="", no_proxy="", ca_bundle="", ssl_verify=True)
    kwargs = build_httpx_kwargs(config)
    assert "proxies" not in kwargs
    assert "verify" not in kwargs
    assert "timeout" not in kwargs  # timeout is set only by build_httpx_client


def test_custom_timeout():
    """build_httpx_client applies request_timeout as default timeout across all phases."""
    config = NetworkConfig(http_proxy="", https_proxy="", no_proxy="", ca_bundle="", ssl_verify=True, request_timeout=60)
    client = build_httpx_client(config)
    assert client.timeout == httpx.Timeout(60)
    client.close()


def test_http_proxy():
    config = NetworkConfig(http_proxy="http://proxy.corp:8080", https_proxy="", no_proxy="", ca_bundle="", ssl_verify=True)
    kwargs = build_httpx_kwargs(config)
    assert "mounts" in kwargs
    assert "http://" in kwargs["mounts"]


def test_https_proxy():
    config = NetworkConfig(http_proxy="", https_proxy="https://proxy.corp:8080", no_proxy="", ca_bundle="", ssl_verify=True)
    kwargs = build_httpx_kwargs(config)
    assert "mounts" in kwargs
    assert "https://" in kwargs["mounts"]


def test_ssl_verify_false():
    config = NetworkConfig(http_proxy="", https_proxy="", no_proxy="", ca_bundle="", ssl_verify=False)
    kwargs = build_httpx_kwargs(config)
    assert kwargs["verify"] is False


def test_ca_bundle(tmp_path):
    ca_file = tmp_path / "ca.pem"
    ca_file.write_text("fake-ca")
    config = NetworkConfig(http_proxy="", https_proxy="", no_proxy="", ca_bundle=str(ca_file), ssl_verify=True)
    kwargs = build_httpx_kwargs(config)
    assert kwargs["verify"] == str(ca_file)


def test_ssl_verify_false_takes_priority_over_ca_bundle(tmp_path):
    ca_file = tmp_path / "ca.pem"
    ca_file.write_text("fake-ca")
    config = NetworkConfig(http_proxy="", https_proxy="", no_proxy="", ca_bundle=str(ca_file), ssl_verify=False)
    kwargs = build_httpx_kwargs(config)
    assert kwargs["verify"] is False


def test_no_proxy_produces_no_mounts():
    config = NetworkConfig(http_proxy="", https_proxy="", no_proxy="", ca_bundle="", ssl_verify=True)
    kwargs = build_httpx_kwargs(config)
    assert "mounts" not in kwargs


def test_build_httpx_client_returns_client():
    config = NetworkConfig(http_proxy="", https_proxy="", no_proxy="", ca_bundle="", ssl_verify=True)
    client = build_httpx_client(config)
    assert isinstance(client, httpx.Client)
    client.close()


def test_build_httpx_client_mounts_proxy():
    """build_httpx_client with http_proxy creates an HTTPTransport mount."""
    config = NetworkConfig(http_proxy="http://proxy.corp:8080", https_proxy="", no_proxy="", ca_bundle="", ssl_verify=True)
    client = build_httpx_client(config)
    mount_patterns = [k.pattern for k in client._mounts]
    assert "http://" in mount_patterns
    transport_types = [type(v).__name__ for v in client._mounts.values()]
    assert "HTTPTransport" in transport_types
    client.close()


def test_env_proxy_override(monkeypatch):
    """NetworkConfig picks up env vars at construction time."""
    monkeypatch.setenv("HTTP_PROXY", "http://env-proxy:3128")
    config = NetworkConfig()  # reads env at default_factory time
    # The env var should be reflected
    assert config.http_proxy == "http://env-proxy:3128"
