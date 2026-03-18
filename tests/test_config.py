"""Tests for configuration management."""

import json
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from socialhub.cli.config import (
    Config,
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

    with patch("socialhub.cli.config.CONFIG_DIR", config_dir):
        with patch("socialhub.cli.config.CONFIG_FILE", config_file):
            yield config_dir, config_file


def test_default_config():
    """Test default configuration values."""
    config = Config()

    assert config.mode == "api"
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
    assert config.mode == "api"


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

    assert get_config_value("mode") == "api"
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
