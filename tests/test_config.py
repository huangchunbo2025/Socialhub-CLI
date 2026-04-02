"""Tests for configuration management."""

import json
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from cli.config import (
    Config,
    _apply_env_overrides,
    get_config_value,
    load_config,
    save_config,
    set_config_value,
)


@pytest.fixture
def temp_config_dir(tmp_path):
    """Create temporary config directory."""
    config_dir = tmp_path / ".socialhub"
    config_dir.mkdir()
    config_file = config_dir / "config.json"

    with patch("cli.config.CONFIG_DIR", config_dir):
        with patch("cli.config.CONFIG_FILE", config_file):
            yield config_dir, config_file


def test_default_config():
    """Test default configuration values."""
    config = Config()

    assert config.mode == "mcp"
    assert config.api.url == "https://api.socialhub.ai"
    assert config.api.key == ""
    assert config.api.timeout == 30
    assert config.local.data_dir == "./data"
    assert config.default_format == "table"
    assert config.page_size == 50


def test_load_config_missing_file(temp_config_dir):
    """Test loading config when file doesn't exist."""
    config_dir, config_file = temp_config_dir

    config = load_config()
    assert config.mode == "mcp"


def test_save_and_load_config(temp_config_dir):
    """Test saving and loading configuration."""
    config_dir, config_file = temp_config_dir

    # Create custom config
    config = Config()
    config.mode = "local"
    config.api.url = "https://test.api.com"
    config.api.key = "test-key-123"

    # Save
    save_config(config)
    assert config_file.exists()

    # Load
    loaded = load_config()
    assert loaded.mode == "local"
    assert loaded.api.url == "https://test.api.com"
    assert loaded.api.key == "test-key-123"


def test_get_config_value(temp_config_dir):
    """Test getting config values by dot notation."""
    config_dir, config_file = temp_config_dir

    config = Config()
    config.api.url = "https://custom.api.com"
    save_config(config)

    assert get_config_value("mode") == "mcp"
    assert get_config_value("api.url") == "https://custom.api.com"
    assert get_config_value("api.timeout") == 30
    assert get_config_value("nonexistent") is None
    assert get_config_value("api.nonexistent") is None


def test_set_config_value(temp_config_dir):
    """Test setting config values by dot notation."""
    config_dir, config_file = temp_config_dir

    # Initialize config
    save_config(Config())

    # Set string value
    assert set_config_value("api.url", "https://new.api.com")
    assert get_config_value("api.url") == "https://new.api.com"

    # Set integer value
    assert set_config_value("api.timeout", "60")
    assert get_config_value("api.timeout") == 60

    # Set mode
    assert set_config_value("mode", "local")
    assert get_config_value("mode") == "local"


def test_apply_env_overrides_mcp_fields(monkeypatch):
    """Env vars override MCP config fields at highest priority."""
    monkeypatch.setenv("MCP_SSE_URL", "https://sse.example.com")
    monkeypatch.setenv("MCP_POST_URL", "https://post.example.com")
    monkeypatch.setenv("MCP_TENANT_ID", "tenant-99")
    monkeypatch.setenv("MCP_DATABASE", "db_override")

    config = Config()
    result = _apply_env_overrides(config)

    assert result.mcp.sse_url == "https://sse.example.com"
    assert result.mcp.post_url == "https://post.example.com"
    assert result.mcp.tenant_id == "tenant-99"
    assert result.mcp.database == "db_override"


def test_apply_env_overrides_no_env_vars(monkeypatch):
    """When no MCP env vars are set, config is returned unchanged."""
    for var in ("MCP_SSE_URL", "MCP_POST_URL", "MCP_TENANT_ID", "MCP_DATABASE"):
        monkeypatch.delenv(var, raising=False)

    config = Config()
    config.mcp.tenant_id = "original-tenant"
    result = _apply_env_overrides(config)

    assert result.mcp.tenant_id == "original-tenant"


def test_apply_env_overrides_ai_fields(monkeypatch):
    """Env vars override AI config fields at highest priority."""
    monkeypatch.setenv("AI_PROVIDER", "openai")
    monkeypatch.setenv("AZURE_OPENAI_ENDPOINT", "https://myendpoint.openai.azure.com")
    monkeypatch.setenv("AZURE_OPENAI_API_KEY", "test-azure-key")
    monkeypatch.setenv("AZURE_OPENAI_DEPLOYMENT", "gpt-4o-deploy")
    monkeypatch.setenv("AZURE_OPENAI_API_VERSION", "2025-01-01")
    monkeypatch.setenv("OPENAI_API_KEY", "test-openai-key")
    monkeypatch.setenv("OPENAI_MODEL", "gpt-4o-mini")

    config = Config()
    result = _apply_env_overrides(config)

    assert result.ai.provider == "openai"
    assert result.ai.azure_endpoint == "https://myendpoint.openai.azure.com"
    assert result.ai.azure_api_key == "test-azure-key"
    assert result.ai.azure_deployment == "gpt-4o-deploy"
    assert result.ai.azure_api_version == "2025-01-01"
    assert result.ai.openai_api_key == "test-openai-key"
    assert result.ai.openai_model == "gpt-4o-mini"


def test_apply_env_overrides_ai_partial(monkeypatch):
    """Only set AI env vars are overridden; unset fields keep their config values."""
    for var in ("AI_PROVIDER", "AZURE_OPENAI_ENDPOINT", "AZURE_OPENAI_API_KEY",
                "AZURE_OPENAI_DEPLOYMENT", "AZURE_OPENAI_API_VERSION",
                "OPENAI_API_KEY", "OPENAI_MODEL"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "partial-key")

    config = Config()
    config.ai.azure_deployment = "original-deploy"
    result = _apply_env_overrides(config)

    assert result.ai.openai_api_key == "partial-key"
    assert result.ai.azure_deployment == "original-deploy"


def test_apply_env_overrides_empty_string_ai_ignored(monkeypatch):
    """Setting an AI env var to empty string does not override config (falsy guard)."""
    monkeypatch.setenv("OPENAI_API_KEY", "")

    config = Config()
    config.ai.openai_api_key = "existing-key"
    result = _apply_env_overrides(config)

    assert result.ai.openai_api_key == "existing-key"
