"""Configuration management for SocialHub CLI."""

import json
import os
from pathlib import Path
from typing import Any, Optional

from pydantic import BaseModel, Field
from rich.console import Console

console = Console()

# Default config directory
CONFIG_DIR = Path.home() / ".socialhub"
CONFIG_FILE = CONFIG_DIR / "config.json"


class APIConfig(BaseModel):
    """API connection configuration."""

    url: str = Field(default="https://api.socialhub.ai", description="API base URL")
    key: str = Field(default="", description="API key for authentication")
    timeout: int = Field(default=30, description="Request timeout in seconds")


class LocalConfig(BaseModel):
    """Local mode configuration."""

    data_dir: str = Field(default="./data", description="Local data directory")


class Config(BaseModel):
    """Main configuration model."""

    mode: str = Field(default="api", description="Operation mode: 'api' or 'local'")
    api: APIConfig = Field(default_factory=APIConfig)
    local: LocalConfig = Field(default_factory=LocalConfig)
    default_format: str = Field(default="table", description="Default output format")
    page_size: int = Field(default=50, description="Default page size for list commands")


def ensure_config_dir() -> None:
    """Ensure configuration directory exists."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)


def load_config() -> Config:
    """Load configuration from file."""
    if not CONFIG_FILE.exists():
        return Config()

    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return Config(**data)
    except (json.JSONDecodeError, Exception) as e:
        console.print(f"[yellow]Warning: Failed to load config: {e}[/yellow]")
        return Config()


def save_config(config: Config) -> None:
    """Save configuration to file."""
    ensure_config_dir()
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config.model_dump(), f, indent=2, ensure_ascii=False)


def get_config_value(key: str) -> Any:
    """Get a configuration value by dot-notation key."""
    config = load_config()
    parts = key.split(".")

    value: Any = config.model_dump()
    for part in parts:
        if isinstance(value, dict) and part in value:
            value = value[part]
        else:
            return None
    return value


def set_config_value(key: str, value: str) -> bool:
    """Set a configuration value by dot-notation key."""
    config = load_config()
    data = config.model_dump()
    parts = key.split(".")

    # Navigate to parent
    current = data
    for part in parts[:-1]:
        if part not in current:
            current[part] = {}
        current = current[part]

    # Set value (try to parse as int/bool if applicable)
    final_key = parts[-1]
    if value.lower() == "true":
        current[final_key] = True
    elif value.lower() == "false":
        current[final_key] = False
    elif value.isdigit():
        current[final_key] = int(value)
    else:
        current[final_key] = value

    # Save
    try:
        new_config = Config(**data)
        save_config(new_config)
        return True
    except Exception as e:
        console.print(f"[red]Error setting config: {e}[/red]")
        return False


def get_env_config() -> dict:
    """Get configuration from environment variables."""
    return {
        "api_url": os.getenv("SOCIALHUB_API_URL"),
        "api_key": os.getenv("SOCIALHUB_API_KEY"),
        "mode": os.getenv("SOCIALHUB_MODE"),
    }
