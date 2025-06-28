"""Unified configuration management using YAML with environment overlay."""

import os
import yaml
import logging
from pathlib import Path
from functools import lru_cache
from typing import Optional, Dict, Any, Tuple
from pydantic import BaseModel, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)

# Configuration file paths
CONFIG_FILE = Path("config.yaml")
SECRETS_FILE = Path("secrets.yaml")


class LoggingConfig(BaseModel):
    """Logging configuration."""

    level: str = Field("INFO", description="Logging level")

    @field_validator("level")
    @classmethod
    def validate_level(cls, v: str) -> str:
        valid_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        if v.upper() not in valid_levels:
            raise ValueError(f"Invalid log level: {v}")
        return v.upper()


class ProviderConfig(BaseModel):
    """Provider configuration for AI models."""

    enabled: bool = True
    api_key: Optional[str] = None
    project: Optional[str] = None
    location: Optional[str] = None
    # OAuth configuration for Vertex AI (CI/CD environments)
    oauth_client_id: Optional[str] = None
    oauth_client_secret: Optional[str] = None
    user_refresh_token: Optional[str] = None
    max_output_tokens: int = Field(
        default=65536, description="Default max output tokens"
    )
    max_function_calls: Optional[int] = Field(
        default=500,
        description="Maximum function call rounds (agentic systems do many calls)",
    )


class MCPConfig(BaseModel):
    """MCP server configuration."""

    host: str = Field("127.0.0.1", description="Server host")
    port: int = Field(8000, description="Server port", ge=1, le=65535)
    context_percentage: float = Field(
        0.85, description="Percentage of model context to use", ge=0.1, le=0.95
    )
    default_temperature: float = Field(
        0.2, description="Default temperature for AI models", ge=0.0, le=2.0
    )
    thread_pool_workers: int = Field(
        10, description="Max workers for shared thread pool", ge=1, le=100
    )


class SessionConfig(BaseModel):
    """Session management configuration."""

    ttl_seconds: int = Field(3600, description="Session TTL in seconds", ge=60)
    db_path: str = Field(".mcp_sessions.sqlite3", description="Session database path")
    cleanup_probability: float = Field(
        0.01, description="Cleanup probability", ge=0.0, le=1.0
    )


class MemoryConfig(BaseModel):
    """Memory system configuration."""

    enabled: bool = Field(True, description="Enable memory system")
    rollover_limit: int = Field(
        9500, description="Rollover limit for memory stores", ge=10
    )
    session_cutoff_hours: int = Field(2, description="Session cutoff in hours", ge=1)
    summary_char_limit: int = Field(
        200000, description="Summary character limit", ge=100
    )
    max_files_per_commit: int = Field(50, description="Max files per commit", ge=1)


class Settings(BaseSettings):
    """Unified settings for mcp-second-brain server."""

    # Top-level configs
    mcp: MCPConfig = Field(default_factory=MCPConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)

    # Provider configs with legacy environment variable support
    openai: ProviderConfig = Field(
        default_factory=lambda: ProviderConfig(max_output_tokens=65536)
    )
    vertex: ProviderConfig = Field(
        default_factory=lambda: ProviderConfig(max_output_tokens=65536)
    )
    anthropic: ProviderConfig = Field(default_factory=ProviderConfig)

    # Feature configs
    session: SessionConfig = Field(default_factory=SessionConfig)
    memory: MemoryConfig = Field(default_factory=MemoryConfig)

    # Testing
    adapter_mock: bool = Field(False, description="Use mock adapters for testing")

    model_config = SettingsConfigDict(
        env_nested_delimiter="__",  # Allows OPENAI__API_KEY env var
        # .env file support is now removed in favor of explicit YAML configuration
        extra="ignore",
        validate_default=True,
    )

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls,
        init_settings,
        env_settings,
        dotenv_settings,
        file_secret_settings,
    ):
        """Customize settings sources to include YAML files and legacy env vars."""
        from pydantic_settings.sources import PydanticBaseSettingsSource

        class YamlConfigSource(PydanticBaseSettingsSource):
            """Load settings from YAML files."""

            def get_field_value(
                self, field_name: str, field_info
            ) -> Tuple[Any, str, bool]:
                data = self()
                if field_name in data:
                    return data[field_name], field_name, True
                return None, field_name, False

            def __call__(self) -> Dict[str, Any]:
                return cls._yaml_config_source()

        class LegacyEnvVars(PydanticBaseSettingsSource):
            """Load legacy flat environment variables."""

            def get_field_value(
                self, field_name: str, field_info
            ) -> Tuple[Any, str, bool]:
                data = self()
                if field_name in data:
                    return data[field_name], field_name, True
                return None, field_name, False

            def __call__(self) -> Dict[str, Any]:
                return cls._legacy_env_source()

        # Precedence (right to left): file_secrets > env_settings > legacy_env > yaml > init
        # .env files are no longer supported.
        return (
            init_settings,
            YamlConfigSource(settings_cls),
            LegacyEnvVars(settings_cls),
            env_settings,
            file_secret_settings,
        )

    @classmethod
    def _yaml_config_source(cls) -> Dict[str, Any]:
        """Load configuration from YAML files."""
        config_data: Dict[str, Any] = {}

        # Get file paths from environment
        config_file = Path(os.getenv("MCP_CONFIG_FILE", str(CONFIG_FILE)))
        secrets_file = Path(os.getenv("MCP_SECRETS_FILE", str(SECRETS_FILE)))

        # Load main config file
        if config_file.exists():
            try:
                with open(config_file) as f:
                    config_data = yaml.safe_load(f) or {}
                logger.debug(f"Loaded configuration from {config_file}")
            except Exception as e:
                logger.warning(f"Failed to load {config_file}: {e}")

        # Load and merge secrets file
        if secrets_file.exists():
            try:
                with open(secrets_file) as f:
                    secrets_data = yaml.safe_load(f) or {}
                config_data = _deep_merge(config_data, secrets_data)
                logger.debug(f"Loaded secrets from {secrets_file}")
            except Exception as e:
                logger.warning(f"Failed to load {secrets_file}: {e}")

        if "providers" in config_data:
            providers = config_data.pop("providers")
            if isinstance(providers, dict):
                for provider_name, provider_config in providers.items():
                    if provider_name in config_data:
                        config_data[provider_name] = _deep_merge(
                            config_data[provider_name], provider_config or {}
                        )
                    else:
                        config_data[provider_name] = provider_config or {}

        return config_data

    @classmethod
    def _legacy_env_source(cls) -> Dict[str, Any]:
        """Support legacy flat environment variables."""
        config_data: Dict[str, Any] = {}

        # Map legacy environment variables to nested structure
        legacy_mappings = {
            # Provider API keys
            "OPENAI_API_KEY": ("openai", "api_key"),
            "VERTEX_PROJECT": ("vertex", "project"),
            "VERTEX_LOCATION": ("vertex", "location"),
            "GCLOUD_OAUTH_CLIENT_ID": ("vertex", "oauth_client_id"),
            "GCLOUD_OAUTH_CLIENT_SECRET": ("vertex", "oauth_client_secret"),
            "GCLOUD_USER_REFRESH_TOKEN": ("vertex", "user_refresh_token"),
            "ANTHROPIC_API_KEY": ("anthropic", "api_key"),
            # MCP settings
            "HOST": ("mcp", "host"),
            "PORT": ("mcp", "port"),
            "CONTEXT_PERCENTAGE": ("mcp", "context_percentage"),
            "DEFAULT_TEMPERATURE": ("mcp", "default_temperature"),
            # Logging
            "LOG_LEVEL": ("logging", "level"),
            # Session settings
            "SESSION_TTL_SECONDS": ("session", "ttl_seconds"),
            "SESSION_DB_PATH": ("session", "db_path"),
            "SESSION_CLEANUP_PROBABILITY": ("session", "cleanup_probability"),
            # Memory settings
            "MEMORY_ENABLED": ("memory", "enabled"),
            "MEMORY_ROLLOVER_LIMIT": ("memory", "rollover_limit"),
            "MEMORY_SESSION_CUTOFF_HOURS": ("memory", "session_cutoff_hours"),
            "MEMORY_SUMMARY_CHAR_LIMIT": ("memory", "summary_char_limit"),
            "MEMORY_MAX_FILES_PER_COMMIT": ("memory", "max_files_per_commit"),
            # Testing
            "MCP_ADAPTER_MOCK": ("adapter_mock",),
        }

        # Check both uppercase and lowercase versions for case insensitivity
        for env_key, path in legacy_mappings.items():
            value = os.getenv(env_key)
            if value is None:
                # Try lowercase version
                value = os.getenv(env_key.lower())

            if value is not None:
                # Navigate/create the nested structure
                current = config_data
                for key in path[:-1]:
                    if key not in current:
                        current[key] = {}
                    current = current[key]

                # Set the final value
                current[path[-1]] = value

        return config_data

    # Backward compatibility properties
    @property
    def host(self) -> str:
        return self.mcp.host

    @property
    def port(self) -> int:
        return self.mcp.port

    @property
    def openai_api_key(self) -> Optional[str]:
        return self.openai.api_key

    @property
    def vertex_project(self) -> Optional[str]:
        return self.vertex.project

    @property
    def vertex_location(self) -> Optional[str]:
        return self.vertex.location

    @property
    def context_percentage(self) -> float:
        return self.mcp.context_percentage

    @property
    def default_temperature(self) -> float:
        return self.mcp.default_temperature

    # Session properties
    @property
    def session_ttl_seconds(self) -> int:
        return self.session.ttl_seconds

    @property
    def session_db_path(self) -> str:
        return self.session.db_path

    @property
    def session_cleanup_probability(self) -> float:
        return self.session.cleanup_probability

    # Memory properties
    @property
    def memory_enabled(self) -> bool:
        return self.memory.enabled

    @property
    def memory_rollover_limit(self) -> int:
        return self.memory.rollover_limit

    @property
    def memory_session_cutoff_hours(self) -> int:
        return self.memory.session_cutoff_hours

    @property
    def memory_summary_char_limit(self) -> int:
        return self.memory.summary_char_limit

    @property
    def memory_max_files_per_commit(self) -> int:
        return self.memory.max_files_per_commit

    @property
    def vertex_endpoint(self) -> str:
        """Vertex AI endpoint URL."""
        return f"projects/{self.vertex.project}/locations/{self.vertex.location}"

    def export_env(self) -> Dict[str, str]:
        """Export settings as environment variables for .env file."""
        env_vars = {
            # MCP settings
            "HOST": self.mcp.host,
            "PORT": str(self.mcp.port),
            "CONTEXT_PERCENTAGE": str(self.mcp.context_percentage),
            "DEFAULT_TEMPERATURE": str(self.mcp.default_temperature),
            # Logging
            "LOG_LEVEL": self.logging.level,
            # Providers
            "OPENAI_API_KEY": self.openai.api_key or "",
            "VERTEX_PROJECT": self.vertex.project or "",
            "VERTEX_LOCATION": self.vertex.location or "",
            "GCLOUD_OAUTH_CLIENT_ID": self.vertex.oauth_client_id or "",
            "GCLOUD_OAUTH_CLIENT_SECRET": self.vertex.oauth_client_secret or "",
            "GCLOUD_USER_REFRESH_TOKEN": self.vertex.user_refresh_token or "",
            "ANTHROPIC_API_KEY": self.anthropic.api_key or "",
            # Session
            "SESSION_TTL_SECONDS": str(self.session.ttl_seconds),
            "SESSION_DB_PATH": self.session.db_path,
            "SESSION_CLEANUP_PROBABILITY": str(self.session.cleanup_probability),
            # Memory
            "MEMORY_ENABLED": str(self.memory.enabled).lower(),
            "MEMORY_ROLLOVER_LIMIT": str(self.memory.rollover_limit),
            "MEMORY_SESSION_CUTOFF_HOURS": str(self.memory.session_cutoff_hours),
            "MEMORY_SUMMARY_CHAR_LIMIT": str(self.memory.summary_char_limit),
            "MEMORY_MAX_FILES_PER_COMMIT": str(self.memory.max_files_per_commit),
            # Testing
            "MCP_ADAPTER_MOCK": str(self.adapter_mock).lower(),
        }

        # Filter out empty values
        return {k: v for k, v in env_vars.items() if v}

    def export_mcp_config(self) -> Dict[str, Any]:
        """Export settings as mcp-config.json format."""
        env_vars = self.export_env()

        return {
            "mcpServers": {
                "second-brain": {
                    "command": "uv",
                    "args": ["run", "--", "mcp-second-brain"],
                    "env": env_vars,
                    "timeout": 3600000,  # 1 hour in milliseconds
                }
            }
        }


def _deep_merge(a: Dict[str, Any], b: Dict[str, Any]) -> Dict[str, Any]:
    """Deep merge two dictionaries, with b taking precedence."""
    result = a.copy()

    for key, value in b.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value

    return result


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
