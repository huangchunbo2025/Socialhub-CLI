"""Configuration management for SocialHub CLI."""

import json
import os
from importlib.resources import files
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
    app_id: str = Field(default="", description="App ID for API authentication")
    app_secret: str = Field(default="", description="App Secret for API authentication")
    timeout: int = Field(default=30, description="Request timeout in seconds")


class LocalConfig(BaseModel):
    """Local mode configuration."""

    data_dir: str = Field(default="./data", description="Local data directory")


class AIConfig(BaseModel):
    """AI configuration for Azure OpenAI."""

    provider: str = Field(default="azure", description="AI provider: 'azure' or 'openai'")
    azure_endpoint: str = Field(default="https://socialhub-openai-service.openai.azure.com", description="Azure OpenAI endpoint")
    azure_api_key: str = Field(default="", description="Azure OpenAI API key")
    azure_deployment: str = Field(default="gpt-4o", description="Azure deployment name")
    azure_api_version: str = Field(default="2024-08-01-preview", description="Azure API version")
    openai_api_key: str = Field(default="", description="OpenAI API key (if using OpenAI)")
    openai_model: str = Field(default="gpt-3.5-turbo", description="OpenAI model name")


class MCPConfig(BaseModel):
    """MCP (Model Context Protocol) configuration.

    SECURITY: These values can be overridden via environment variables:
    - MCP_SSE_URL
    - MCP_POST_URL
    - MCP_TENANT_ID
    - MCP_DATABASE
    """

    sse_url: str = Field(
        default_factory=lambda: os.environ.get("MCP_SSE_URL", ""),
        description="MCP SSE endpoint (or set MCP_SSE_URL env var)"
    )
    post_url: str = Field(
        default_factory=lambda: os.environ.get("MCP_POST_URL", ""),
        description="MCP message endpoint (or set MCP_POST_URL env var)"
    )
    tenant_id: str = Field(
        default_factory=lambda: os.environ.get("MCP_TENANT_ID", ""),
        description="MCP tenant ID (or set MCP_TENANT_ID env var)"
    )
    database: str = Field(
        default_factory=lambda: os.environ.get("MCP_DATABASE", ""),
        description="Default database name (or set MCP_DATABASE env var)"
    )


class OAuthConfig(BaseModel):
    """OAuth2 ROPC authentication configuration."""

    enabled: bool = Field(default=False, description="Enable OAuth2 auth gate")
    token_url: str = Field(default="", description="OAuth2 token endpoint URL")
    client_id: str = Field(default="", description="OAuth2 client ID")
    scopes: str = Field(default="", description="Space-separated OAuth2 scopes")


class Config(BaseModel):
    """Main configuration model."""

    mode: str = Field(default="mcp", description="Operation mode: 'api', 'local', or 'mcp'")
    api: APIConfig = Field(default_factory=APIConfig)
    local: LocalConfig = Field(default_factory=LocalConfig)
    ai: AIConfig = Field(default_factory=AIConfig)
    mcp: MCPConfig = Field(default_factory=MCPConfig)
    oauth: OAuthConfig = Field(default_factory=OAuthConfig)
    default_format: str = Field(default="table", description="Default output format")
    page_size: int = Field(default=50, description="Default page size for list commands")


def ensure_config_dir() -> None:
    """Ensure configuration directory exists."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)


def _load_bundled_defaults() -> dict:
    """Load bundled defaults.json shipped with the package."""
    try:
        text = files("cli").joinpath("defaults.json").read_text(encoding="utf-8")
        return json.loads(text)
    except Exception:
        return {}


def load_config() -> Config:
    """Load configuration from file, falling back to bundled defaults."""
    if not CONFIG_FILE.exists():
        defaults = _load_bundled_defaults()
        return Config(**defaults) if defaults else Config()

    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return Config(**data)
    except Exception as e:
        console.print(f"[yellow]Warning: Failed to load config: {e}[/yellow]")
        defaults = _load_bundled_defaults()
        return Config(**defaults) if defaults else Config()


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
        "app_id": os.getenv("SOCIALHUB_APP_ID"),
        "app_secret": os.getenv("SOCIALHUB_APP_SECRET"),
        "mode": os.getenv("SOCIALHUB_MODE"),
    }
