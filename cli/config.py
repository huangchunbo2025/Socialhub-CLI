"""Configuration management for SocialHub CLI."""

import json
import logging as _logging
import os
import stat
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

    @field_validator("openai_base_url")
    @classmethod
    def _validate_openai_base_url(cls, v: str) -> str:
        return _validate_http_url(v)

    azure_endpoint: str = Field(default="https://socialhub-openai-service.openai.azure.com", description="Azure OpenAI endpoint")
    azure_api_key: str = Field(default="", description="Azure OpenAI API key")
    azure_deployment: str = Field(default="gpt-4o", description="Azure deployment name")
    azure_api_version: str = Field(default="2024-08-01-preview", description="Azure API version")
    openai_api_key: str = Field(default="", description="OpenAI API key (if using OpenAI)")
    openai_base_url: str = Field(default="https://api.openai.com/v1", description="OpenAI API base URL (for compatible services)")
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

    sse_url: str = Field(default="", description="MCP SSE endpoint (or set MCP_SSE_URL env var)")
    post_url: str = Field(default="", description="MCP message endpoint (or set MCP_POST_URL env var)")
    tenant_id: str = Field(default="", description="MCP tenant ID (or set MCP_TENANT_ID env var)")
    database: str = Field(default="", description="Default database name (or set MCP_DATABASE env var)")
    api_key: str = Field(default="", description="MCP API key sent as Authorization: Bearer (or set MCP_API_KEY env var)")


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

    http_proxy: str = Field(default="", description="HTTP proxy URL (or set HTTP_PROXY env var)")
    https_proxy: str = Field(default="", description="HTTPS proxy URL (or set HTTPS_PROXY env var)")
    no_proxy: str = Field(default="", description="Comma-separated list of hosts to bypass proxy")
    ca_bundle: str = Field(default="", description="Path to custom CA certificate bundle (.pem or .crt)")
    ssl_verify: bool = Field(default=True, description="Verify SSL certificates (set False only for testing)")
    request_timeout: int = Field(default=30, description="HTTP request timeout in seconds (enterprise proxy may need higher value)")


class SnowflakeConfig(BaseModel):
    """Snowflake sync configuration (read from environment variables)."""

    account: str = Field(default="", description="Snowflake account identifier")
    account_locator: str = Field(default="", description="Snowflake account locator (optional)")
    host: str = Field(default="", description="Snowflake host override (optional)")
    user: str = Field(default="", description="Snowflake username")
    password: str = Field(default="", description="Snowflake password")
    authenticator: str = Field(default="", description="Snowflake authenticator (e.g. 'externalbrowser')")
    warehouse: str = Field(default="", description="Snowflake warehouse name")
    database: str = Field(default="", description="Snowflake database name")
    schema_name: str = Field(default="", description="Snowflake schema name")
    table: str = Field(default="MEMBERS_MVP", description="Snowflake source table name")
    role: str = Field(default="", description="Snowflake role")
    sort_by: str = Field(default="", description="Column to sort sync output by")


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




class StarRocksConfig(BaseModel):
    """StarRocks database connection configuration."""

    host: str = Field(
        default_factory=lambda: os.environ.get("STARROCKS_HOST", "localhost"),
        description="StarRocks host (or set STARROCKS_HOST env var)",
    )
    port: int = Field(
        default_factory=lambda: int(os.environ.get("STARROCKS_HTTP_PORT", "8030")),
        description="StarRocks HTTP port (or set STARROCKS_HTTP_PORT env var)",
    )
    user: str = Field(
        default_factory=lambda: os.environ.get("STARROCKS_USER", "root"),
        description="StarRocks user (or set STARROCKS_USER env var)",
    )
    password: str = Field(
        default_factory=lambda: os.environ.get("STARROCKS_PASSWORD", ""),
        description="StarRocks password (or set STARROCKS_PASSWORD env var)",
    )
    db_prefix: str = Field(
        default_factory=lambda: os.environ.get("STARROCKS_DB_PREFIX", "socialhub"),
        description="StarRocks database prefix (or set STARROCKS_DB_PREFIX env var)",
    )


class Config(BaseModel):
    """Main configuration model."""

    config_version: int = Field(default=1, description="Config schema version (reserved for future migration logic)")
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
    starrocks: StarRocksConfig = Field(default_factory=StarRocksConfig)
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
        "OPENAI_BASE_URL": "openai_base_url",
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
    if os.environ.get("HTTP_PROXY") or os.environ.get("http_proxy"):
        network_overrides["http_proxy"] = os.environ.get("HTTP_PROXY", os.environ.get("http_proxy", ""))
    if os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy"):
        network_overrides["https_proxy"] = os.environ.get("HTTPS_PROXY", os.environ.get("https_proxy", ""))
    if os.environ.get("NO_PROXY") or os.environ.get("no_proxy"):
        network_overrides["no_proxy"] = os.environ.get("NO_PROXY", os.environ.get("no_proxy", ""))

    # Snowflake fields
    snowflake_env_map = {
        "SNOWFLAKE_ACCOUNT": "account",
        "SNOWFLAKE_ACCOUNT_LOCATOR": "account_locator",
        "SNOWFLAKE_HOST": "host",
        "SNOWFLAKE_USER": "user",
        "SNOWFLAKE_PASSWORD": "password",
        "SNOWFLAKE_AUTHENTICATOR": "authenticator",
        "SNOWFLAKE_WAREHOUSE": "warehouse",
        "SNOWFLAKE_DATABASE": "database",
        "SNOWFLAKE_SCHEMA": "schema_name",
        "SNOWFLAKE_ROLE": "role",
        "SNOWFLAKE_SYNC_SORT_BY": "sort_by",
    }
    snowflake_overrides = {
        field: os.environ[env_var]
        for env_var, field in snowflake_env_map.items()
        if os.environ.get(env_var)
    }
    # Special case: SNOWFLAKE_SYNC_TABLE / SNOWFLAKE_TABLE
    _sf_table = os.environ.get("SNOWFLAKE_SYNC_TABLE", os.environ.get("SNOWFLAKE_TABLE", ""))
    if _sf_table:
        snowflake_overrides["table"] = _sf_table

    if not any([mcp_overrides, ai_overrides, oauth_overrides, trace_overrides, network_overrides, snowflake_overrides]):
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
    if snowflake_overrides:
        base["snowflake"].update(snowflake_overrides)
    return Config(**base)


_config_cache: Config | None = None
_config_cache_mtime: float = 0.0


def load_config() -> Config:
    """Load configuration with in-process caching.

    Priority (highest → lowest): environment variables > config file > bundled defaults.
    """
    global _config_cache, _config_cache_mtime

    try:
        current_mtime = CONFIG_FILE.stat().st_mtime if CONFIG_FILE.exists() else 0.0
    except OSError:
        current_mtime = 0.0

    if _config_cache is not None and current_mtime == _config_cache_mtime:
        return _config_cache

    if not CONFIG_FILE.exists():
        defaults = _load_bundled_defaults()
        result = Config(**defaults) if defaults else Config()
        result = _apply_env_overrides(result)
    else:
        try:
            with open(CONFIG_FILE, encoding="utf-8") as f:
                data = json.load(f)
            result = _apply_env_overrides(Config(**data))
        except Exception as e:
            _cfg_logger.warning("Failed to load config: %s", e)
            defaults = _load_bundled_defaults()
            result = Config(**defaults) if defaults else Config()
            result = _apply_env_overrides(result)

    _config_cache = result
    _config_cache_mtime = current_mtime
    return result


def save_config(config: Config) -> None:
    """Save configuration to file."""
    global _config_cache
    ensure_config_dir()
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config.model_dump(), f, indent=2, ensure_ascii=False)
    try:
        CONFIG_FILE.chmod(stat.S_IRUSR | stat.S_IWUSR)
    except OSError:
        _cfg_logger.debug("chmod 0600 failed (expected on Windows)")
    _config_cache = None


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

    # Set value with type coercion
    final_key = parts[-1]
    if value.lower() == "true":
        current[final_key] = True
    elif value.lower() == "false":
        current[final_key] = False
    else:
        # Try int, then float, then string
        try:
            current[final_key] = int(value)
        except ValueError:
            try:
                current[final_key] = float(value)
            except ValueError:
                current[final_key] = value

    # Save
    try:
        new_config = Config(**data)
        save_config(new_config)
        return True
    except Exception as e:
        _cfg_logger.error("Error setting config: %s", e)
        return False


