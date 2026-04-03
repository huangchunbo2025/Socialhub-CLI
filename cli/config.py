"""Configuration management for SocialHub CLI."""

import json
import logging as _logging
import os
from importlib.resources import files
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator

_cfg_logger = _logging.getLogger(__name__)

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


def _validate_http_url(v: str) -> str:
    """Validate that a URL uses http:// or https:// scheme (SSRF protection)."""
    if v and not (v.startswith("https://") or v.startswith("http://")):
        raise ValueError(f"URL must start with https:// or http://, got: {v!r}")
    return v


class AIConfig(BaseModel):
    """AI configuration for Azure OpenAI."""

    provider: str = Field(default="azure", description="AI provider: 'azure' or 'openai'")

    @field_validator("provider")
    @classmethod
    def _validate_provider(cls, v: str) -> str:
        if v not in ("azure", "openai"):
            raise ValueError(f"provider must be 'azure' or 'openai', got '{v}'")
        return v

    @field_validator("azure_endpoint")
    @classmethod
    def _validate_azure_endpoint(cls, v: str) -> str:
        return _validate_http_url(v)

    azure_endpoint: str = Field(default="https://socialhub-openai-service.openai.azure.com", description="Azure OpenAI endpoint")
    azure_api_key: str = Field(default="", description="Azure OpenAI API key")
    azure_deployment: str = Field(default="gpt-4o", description="Azure deployment name")
    azure_api_version: str = Field(default="2024-08-01-preview", description="Azure API version")
    openai_api_key: str = Field(default="", description="OpenAI API key (if using OpenAI)")
    openai_model: str = Field(default="gpt-4o-mini", description="OpenAI model name")
    max_tokens: int = Field(default=2048, ge=1, description="Max tokens per AI response")
    temperature: float = Field(default=0.7, description="Sampling temperature (0.0–2.0)")
    ai_timeout_s: int = Field(default=60, description="AI API request timeout in seconds")

    @field_validator("temperature")
    @classmethod
    def _validate_temperature(cls, v: float) -> float:
        if not 0.0 <= v <= 2.0:
            raise ValueError(f"temperature must be between 0.0 and 2.0, got {v}")
        return v


class MCPConfig(BaseModel):
    """MCP (Model Context Protocol) configuration.

    SECURITY: These values can be overridden via environment variables:
    - MCP_SSE_URL
    - MCP_POST_URL
    - MCP_TENANT_ID
    - MCP_DATABASE
    - MCP_API_KEY   (sent as Authorization: Bearer <token>)
    """

    @field_validator("sse_url", "post_url")
    @classmethod
    def _validate_url(cls, v: str) -> str:
        return _validate_http_url(v)

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
    api_key: str = Field(
        default_factory=lambda: os.environ.get("MCP_API_KEY", ""),
        description="MCP API key sent as Authorization: Bearer (or set MCP_API_KEY env var)"
    )


class SessionConfig(BaseModel):
    """AI session (multi-turn conversation) configuration."""

    ttl_hours: int = Field(default=24, description="Session TTL in hours (default 24h, covers cross-day analysis)")
    max_history: int = Field(default=10, description="Maximum conversation turns kept in context")
    sessions_dir: str = Field(
        default_factory=lambda: str(Path.home() / ".socialhub" / "sessions"),
        description="Directory for session files",
    )


class TraceConfig(BaseModel):
    """AI decision trace/observability configuration."""

    enabled: bool = Field(default=True, description="Enable AI decision tracing")
    pii_masking: bool = Field(default=True, description="Mask PII (phone, email, ID) in trace logs")
    order_id_min_digits: int = Field(default=16, description="Minimum digit length to treat as order ID for masking")
    max_file_size_mb: int = Field(default=10, description="Max trace file size before rotation (MB)")
    backup_count: int = Field(default=3, description="Number of rotated trace log backups to keep")
    trace_dir: str = Field(
        default_factory=lambda: str(Path.home() / ".socialhub"),
        description="Directory for trace log files",
    )


class NetworkConfig(BaseModel):
    """Enterprise network configuration (proxy, CA certificates)."""

    http_proxy: str = Field(
        default_factory=lambda: os.environ.get("HTTP_PROXY", os.environ.get("http_proxy", "")),
        description="HTTP proxy URL (or set HTTP_PROXY env var)",
    )
    https_proxy: str = Field(
        default_factory=lambda: os.environ.get("HTTPS_PROXY", os.environ.get("https_proxy", "")),
        description="HTTPS proxy URL (or set HTTPS_PROXY env var)",
    )
    no_proxy: str = Field(
        default_factory=lambda: os.environ.get("NO_PROXY", os.environ.get("no_proxy", "")),
        description="Comma-separated list of hosts to bypass proxy",
    )
    ca_bundle: str = Field(default="", description="Path to custom CA certificate bundle (.pem or .crt)")
    ssl_verify: bool = Field(default=True, description="Verify SSL certificates (set False only for testing)")
    request_timeout: int = Field(default=30, description="HTTP request timeout in seconds (enterprise proxy may need higher value)")


class SnowflakeConfig(BaseModel):
    """Snowflake sync configuration (read from environment variables)."""

    account: str = Field(
        default_factory=lambda: os.environ.get("SNOWFLAKE_ACCOUNT", ""),
        description="Snowflake account identifier",
    )
    account_locator: str = Field(
        default_factory=lambda: os.environ.get("SNOWFLAKE_ACCOUNT_LOCATOR", ""),
        description="Snowflake account locator (optional)",
    )
    host: str = Field(
        default_factory=lambda: os.environ.get("SNOWFLAKE_HOST", ""),
        description="Snowflake host override (optional)",
    )
    user: str = Field(
        default_factory=lambda: os.environ.get("SNOWFLAKE_USER", ""),
        description="Snowflake username",
    )
    password: str = Field(
        default_factory=lambda: os.environ.get("SNOWFLAKE_PASSWORD", ""),
        description="Snowflake password",
    )
    authenticator: str = Field(
        default_factory=lambda: os.environ.get("SNOWFLAKE_AUTHENTICATOR", ""),
        description="Snowflake authenticator (e.g. 'externalbrowser')",
    )
    warehouse: str = Field(
        default_factory=lambda: os.environ.get("SNOWFLAKE_WAREHOUSE", ""),
        description="Snowflake warehouse name",
    )
    database: str = Field(
        default_factory=lambda: os.environ.get("SNOWFLAKE_DATABASE", ""),
        description="Snowflake database name",
    )
    schema_name: str = Field(
        default_factory=lambda: os.environ.get("SNOWFLAKE_SCHEMA", ""),
        description="Snowflake schema name",
    )
    table: str = Field(
        default_factory=lambda: os.environ.get(
            "SNOWFLAKE_SYNC_TABLE", os.environ.get("SNOWFLAKE_TABLE", "MEMBERS_MVP")
        ),
        description="Snowflake source table name",
    )
    role: str = Field(
        default_factory=lambda: os.environ.get("SNOWFLAKE_ROLE", ""),
        description="Snowflake role",
    )
    sort_by: str = Field(
        default_factory=lambda: os.environ.get("SNOWFLAKE_SYNC_SORT_BY", ""),
        description="Column to sort sync output by",
    )


class OAuthConfig(BaseModel):
    """SocialHub OAuth2 authentication configuration."""

    enabled: bool = Field(default=False, description="Enable OAuth2 auth gate")
    auth_url: str = Field(default="", description="Auth API base URL")

    @field_validator("auth_url")
    @classmethod
    def _validate_auth_url(cls, v: str) -> str:
        return _validate_http_url(v)


class MemoryConfig(BaseModel):
    """Memory system configuration."""

    enabled: bool = Field(default=True, description="Enable persistent memory system")
    memory_dir: str = Field(
        default_factory=lambda: str(Path.home() / ".socialhub" / "memory"),
        description="Root directory for memory files",
    )
    max_insights: int = Field(default=200, description="Max stored insights")
    max_summaries: int = Field(default=60, description="Max stored session summaries")
    insight_ttl_days: int = Field(default=90, description="Insight TTL in days")
    summary_ttl_days: int = Field(default=30, description="Session summary TTL in days")
    inject_max_tokens: int = Field(default=4000, description="Max token budget for memory injection")
    inject_recent_insights: int = Field(default=5, description="Max recent insights to inject")
    inject_recent_summaries: int = Field(default=3, description="Max recent summaries to inject")
    extractor_timeout_s: int = Field(default=30, description="LLM extractor timeout in seconds")


class Config(BaseModel):
    """Main configuration model."""

    mode: str = Field(default="mcp", description="Operation mode: 'api', 'local', or 'mcp'")

    @field_validator("mode")
    @classmethod
    def _validate_mode(cls, v: str) -> str:
        if v not in ("api", "local", "mcp"):
            raise ValueError(f"mode must be 'api', 'local', or 'mcp', got '{v}'")
        return v
    api: APIConfig = Field(default_factory=APIConfig)
    local: LocalConfig = Field(default_factory=LocalConfig)
    ai: AIConfig = Field(default_factory=AIConfig)
    mcp: MCPConfig = Field(default_factory=MCPConfig)
    oauth: OAuthConfig = Field(default_factory=OAuthConfig)
    session: SessionConfig = Field(default_factory=SessionConfig)
    trace: TraceConfig = Field(default_factory=TraceConfig)
    memory: MemoryConfig = Field(default_factory=MemoryConfig)
    network: NetworkConfig = Field(default_factory=NetworkConfig)
    snowflake: SnowflakeConfig = Field(default_factory=SnowflakeConfig)
    default_format: str = Field(default="table", description="Default output format")
    page_size: int = Field(default=50, description="Default page size for list commands")

    @model_validator(mode="after")
    def _validate_cross_field(self) -> "Config":
        """Validate cross-field business constraints that individual validators cannot check."""
        if self.mode == "mcp" and not self.mcp.sse_url:
            # Warn via logging rather than hard-raising, so misconfigured envs don't
            # prevent CLI startup (user can run `sh config set mcp.sse_url ...`).
            import logging
            logging.getLogger(__name__).warning(
                "Config mode is 'mcp' but mcp.sse_url is empty. "
                "Set via 'sh config set mcp.sse_url <url>' or MCP_SSE_URL env var."
            )
        return self


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


def _apply_env_overrides(config: Config) -> Config:
    """Apply environment variable overrides (highest priority).

    Handles both MCP fields (MCP_SSE_URL / MCP_POST_URL / MCP_TENANT_ID / MCP_DATABASE)
    and AI fields (AI_PROVIDER / AZURE_OPENAI_ENDPOINT / AZURE_OPENAI_API_KEY /
    AZURE_OPENAI_DEPLOYMENT / AZURE_OPENAI_API_VERSION / OPENAI_API_KEY / OPENAI_MODEL).

    This is the single source of truth for env-var overrides; ai/client.py::get_ai_config()
    reads from config, not directly from os.environ.
    """
    # MCP fields
    mcp_env_map = {
        "MCP_SSE_URL": "sse_url",
        "MCP_POST_URL": "post_url",
        "MCP_TENANT_ID": "tenant_id",
        "MCP_DATABASE": "database",
        "MCP_API_KEY": "api_key",
    }
    mcp_overrides = {
        field: os.environ[env_var]
        for env_var, field in mcp_env_map.items()
        if os.environ.get(env_var)
    }

    # AI fields
    ai_env_map = {
        "AI_PROVIDER": "provider",
        "AZURE_OPENAI_ENDPOINT": "azure_endpoint",
        "AZURE_OPENAI_API_KEY": "azure_api_key",
        "AZURE_OPENAI_DEPLOYMENT": "azure_deployment",
        "AZURE_OPENAI_API_VERSION": "azure_api_version",
        "OPENAI_API_KEY": "openai_api_key",
        "OPENAI_MODEL": "openai_model",
    }
    ai_overrides = {
        field: os.environ[env_var]
        for env_var, field in ai_env_map.items()
        if os.environ.get(env_var)
    }

    # OAuth fields
    oauth_overrides: dict = {}
    if os.environ.get("SOCIALHUB_OAUTH_ENABLED"):
        val = os.environ["SOCIALHUB_OAUTH_ENABLED"].lower()
        oauth_overrides["enabled"] = val in ("1", "true", "yes")
    if os.environ.get("SOCIALHUB_OAUTH_AUTH_URL"):
        oauth_overrides["auth_url"] = os.environ["SOCIALHUB_OAUTH_AUTH_URL"]

    # Trace fields
    trace_overrides: dict = {}
    if os.environ.get("SOCIALHUB_TRACE_ENABLED"):
        val = os.environ["SOCIALHUB_TRACE_ENABLED"].lower()
        trace_overrides["enabled"] = val in ("1", "true", "yes")
    if os.environ.get("SOCIALHUB_TRACE_DIR"):
        trace_overrides["trace_dir"] = os.environ["SOCIALHUB_TRACE_DIR"]

    # Network fields
    network_overrides: dict = {}
    if os.environ.get("SOCIALHUB_CA_BUNDLE"):
        network_overrides["ca_bundle"] = os.environ["SOCIALHUB_CA_BUNDLE"]
    if os.environ.get("SOCIALHUB_SSL_VERIFY"):
        val = os.environ["SOCIALHUB_SSL_VERIFY"].lower()
        network_overrides["ssl_verify"] = val in ("1", "true", "yes")

    if not any([mcp_overrides, ai_overrides, oauth_overrides, trace_overrides, network_overrides]):
        return config

    base = config.model_dump()
    if mcp_overrides:
        base["mcp"].update(mcp_overrides)
    if ai_overrides:
        base["ai"].update(ai_overrides)
    if oauth_overrides:
        base["oauth"].update(oauth_overrides)
    if trace_overrides:
        base["trace"].update(trace_overrides)
    if network_overrides:
        base["network"].update(network_overrides)
    return Config(**base)


def load_config() -> Config:
    """Load configuration from file, falling back to bundled defaults.

    Priority (highest → lowest): environment variables > config file > bundled defaults.
    """
    if not CONFIG_FILE.exists():
        defaults = _load_bundled_defaults()
        config = Config(**defaults) if defaults else Config()
        return _apply_env_overrides(config)

    try:
        with open(CONFIG_FILE, encoding="utf-8") as f:
            data = json.load(f)
        return _apply_env_overrides(Config(**data))
    except Exception as e:
        _cfg_logger.warning("Failed to load config: %s", e)
        defaults = _load_bundled_defaults()
        config = Config(**defaults) if defaults else Config()
        return _apply_env_overrides(config)


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
        _cfg_logger.error("Error setting config: %s", e)
        return False


