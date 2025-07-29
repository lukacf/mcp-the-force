"""Unified configuration management using YAML with environment overlay."""

import os
import yaml
import logging
from pathlib import Path
from functools import lru_cache
from typing import Optional, Dict, Any, Tuple
from pydantic import BaseModel, Field, field_validator
from pydantic.fields import FieldInfo
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)

# Configuration file paths
CONFIG_FILE = Path("config.yaml")
SECRETS_FILE = Path("secrets.yaml")


class DeveloperLoggingConfig(BaseModel):
    """Developer logging settings."""

    enabled: bool = Field(False, description="Enable developer logging mode")
    port: int = Field(4711, description="ZMQ logging port")
    db_path: str = Field(".mcp_logs.sqlite3", description="SQLite database path")
    batch_size: int = Field(100, description="Batch size for database writes")
    batch_timeout: float = Field(1.0, description="Batch timeout in seconds")
    max_db_size_mb: int = Field(1000, description="Max database size before rotation")


class LoggingConfig(BaseModel):
    """Logging configuration."""

    level: str = Field("INFO", description="Logging level")
    developer_mode: DeveloperLoggingConfig = Field(
        default_factory=DeveloperLoggingConfig
    )
    victoria_logs_url: str = Field(
        "http://localhost:9428", description="Victoria Logs URL"
    )
    victoria_logs_enabled: bool = Field(True, description="Enable Victoria Logs")
    loki_app_tag: str = Field("mcp-the-force", description="Loki app tag")
    project_path: Optional[str] = Field(None, description="Project path for logging")

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
    adc_credentials_path: Optional[str] = Field(
        None, description="Path to Application Default Credentials JSON file"
    )
    max_output_tokens: int = Field(
        default=65536, description="Default max output tokens"
    )
    max_function_calls: Optional[int] = Field(
        default=500,
        description="Maximum function call rounds (agentic systems do many calls)",
    )
    max_parallel_tool_exec: int = Field(
        default=8,
        description="Maximum parallel tool executions for OpenAI",
    )


class MCPConfig(BaseModel):
    """MCP server configuration."""

    host: str = Field("127.0.0.1", description="Server host")
    port: int = Field(8000, description="Server port", ge=1, le=65535)
    context_percentage: float = Field(
        0.85, description="Percentage of model context to use", ge=0.1, le=0.95
    )
    default_temperature: float = Field(
        1.0, description="Default temperature for AI models", ge=0.0, le=2.0
    )
    thread_pool_workers: int = Field(
        10, description="Max workers for shared thread pool", ge=1, le=100
    )
    default_vector_store_provider: str = Field(
        "openai", description="Default provider for vector stores"
    )


class SessionConfig(BaseModel):
    """Session management configuration."""

    ttl_seconds: int = Field(
        15552000, description="Session TTL in seconds (default: 6 months)", ge=60
    )
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


class ToolsConfig(BaseModel):
    """Configuration for built-in local service tools."""

    default_summarization_model: str = Field(
        "chat_with_gemini25_flash",
        description="The default model used by describe_session for summarization.",
    )


class FeaturesConfig(BaseModel):
    """Feature flags configuration."""

    # No feature flags currently - the stable inline list is now always enabled
    pass


class BackupConfig(BaseModel):
    """Configuration for backup scripts."""

    path: str = Field(
        default_factory=lambda: str(Path.home() / ".mcp_backups"),
        description="Directory for database backups",
    )


class SecurityConfig(BaseModel):
    """Security configuration."""

    path_blacklist: list[str] = Field(
        default_factory=lambda: [
            "/etc",
            "/usr",
            "/bin",
            "/sbin",
            "/boot",
            "/sys",
            "/proc",
            "/dev",
            "/root",
            # macOS specific
            "/System",
            "/private/etc",
            # Note: /private/var excluded to allow temp files in tests
            # Block sensitive Library subdirectories but allow iCloud Drive
            "~/Library/Keychains",
            "~/Library/Cookies",
            "~/Library/Mail",
            "~/Library/Messages",
            "~/Library/Safari",
            "~/Library/Accounts",
            "~/Library/Autosave Information",
            "~/Library/IdentityServices",
            "~/Library/PersonalizationPortrait",
            # Windows specific (will be ignored on Unix)
            "C:\\Windows",
            "C:\\Program Files",
            "C:\\Program Files (x86)",
        ],
        description="Paths that are blocked from access",
    )


class ServicesConfig(BaseModel):
    """External services configuration."""

    loiter_killer_host: str = Field(
        "localhost", description="Loiter killer service host"
    )
    loiter_killer_port: int = Field(9876, description="Loiter killer service port")

    @property
    def loiter_killer_url(self) -> str:
        """Construct loiter killer URL from host and port."""
        return f"http://{self.loiter_killer_host}:{self.loiter_killer_port}"


class DevConfig(BaseModel):
    """Development and testing configuration."""

    adapter_mock: bool = Field(False, description="Use mock adapters for testing")
    ci_e2e: bool = Field(False, description="Running in CI E2E test environment")


class Settings(BaseSettings):
    """Unified settings for mcp-the-force server."""

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
    gemini: ProviderConfig = Field(default_factory=ProviderConfig)
    anthropic: ProviderConfig = Field(default_factory=ProviderConfig)
    xai: ProviderConfig = Field(default_factory=ProviderConfig)
    litellm: ProviderConfig = Field(default_factory=ProviderConfig)

    # Feature configs
    session: SessionConfig = Field(default_factory=SessionConfig)
    memory: MemoryConfig = Field(default_factory=MemoryConfig)
    tools: ToolsConfig = Field(default_factory=ToolsConfig)
    features: FeaturesConfig = Field(default_factory=FeaturesConfig)
    backup: BackupConfig = Field(default_factory=BackupConfig)
    security: SecurityConfig = Field(default_factory=SecurityConfig)
    services: ServicesConfig = Field(default_factory=ServicesConfig)
    dev: DevConfig = Field(default_factory=DevConfig)

    # Testing - backward compatibility alias
    @property
    def adapter_mock(self) -> bool:
        """Backward compatibility for adapter_mock."""
        return self.dev.adapter_mock

    def __init__(self, **kwargs):
        """Initialize settings and set up ADC if configured."""
        super().__init__(**kwargs)

        # Store config path for debugging
        self._config_path = None

        # Set GOOGLE_APPLICATION_CREDENTIALS if adc_credentials_path is configured
        if self.vertex.adc_credentials_path:
            # Resolve path relative to config file location
            config_file = Path(os.getenv("MCP_CONFIG_FILE", str(CONFIG_FILE))).resolve()
            config_dir = config_file.parent

            adc_path = Path(self.vertex.adc_credentials_path).expanduser()
            if not adc_path.is_absolute():
                abs_path = (config_dir / adc_path).resolve()
            else:
                abs_path = adc_path.resolve()

            if not abs_path.exists():
                logger.warning(
                    f"ADC credentials file not found at {abs_path}. GOOGLE_APPLICATION_CREDENTIALS will not be set."
                )
                return
            if not os.access(str(abs_path), os.R_OK):
                raise PermissionError(f"ADC credentials file not readable: {abs_path}")

            os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = str(abs_path)
            logger.debug(f"Set GOOGLE_APPLICATION_CREDENTIALS to {abs_path}")

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
                self, field: FieldInfo, field_name: str
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
                self, field: FieldInfo, field_name: str
            ) -> Tuple[Any, str, bool]:
                data = self()
                if field_name in data:
                    return data[field_name], field_name, True
                return None, field_name, False

            def __call__(self) -> Dict[str, Any]:
                return cls._legacy_env_source()

        # Precedence (left to right - first source wins):
        # env_settings > legacy_env > yaml > defaults
        # This means env vars (including those from MCP JSON) override YAML
        return (
            init_settings,
            env_settings,  # Standard nested env vars (e.g., OPENAI__API_KEY) - highest priority
            LegacyEnvVars(settings_cls),  # Flat legacy env vars (e.g., OPENAI_API_KEY)
            YamlConfigSource(settings_cls),  # YAML files (lower priority)
            file_secret_settings,
        )

    @classmethod
    def _yaml_config_source(cls) -> Dict[str, Any]:
        """Load configuration from YAML files."""
        import sys

        config_data: Dict[str, Any] = {}

        # Automatic test isolation: When running under pytest and the caller has not
        # explicitly provided MCP_CONFIG_FILE/MCP_SECRETS_FILE, skip the default
        # config.yaml/secrets.yaml so tests cannot be polluted by real configuration
        if (
            "pytest" in sys.modules
            and "MCP_CONFIG_FILE" not in os.environ
            and "MCP_SECRETS_FILE" not in os.environ
        ):
            return {}  # Nothing to merge, stay with defaults

        # Get file paths from environment
        config_file = Path(os.getenv("MCP_CONFIG_FILE", str(CONFIG_FILE)))
        secrets_file = Path(os.getenv("MCP_SECRETS_FILE", str(SECRETS_FILE)))

        # Load main config file
        if config_file.exists():
            try:
                with open(config_file) as f:
                    config_data = yaml.safe_load(f) or {}
                logger.debug(f"Loaded configuration from {config_file}")
                # Store the path for later use
                cls._last_config_path = str(config_file)
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

        # Handle None values from YAML (e.g., "features:" with no content)
        for key in list(config_data.keys()):
            if config_data[key] is None:
                config_data[key] = {}

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
            "GEMINI_API_KEY": ("gemini", "api_key"),
            "ANTHROPIC_API_KEY": ("anthropic", "api_key"),
            "XAI_API_KEY": ("xai", "api_key"),
            # MCP settings
            "HOST": ("mcp", "host"),
            "PORT": ("mcp", "port"),
            "CONTEXT_PERCENTAGE": ("mcp", "context_percentage"),
            "DEFAULT_TEMPERATURE": ("mcp", "default_temperature"),
            # Logging
            "LOG_LEVEL": ("logging", "level"),
            "VICTORIA_LOGS_URL": ("logging", "victoria_logs_url"),
            "DISABLE_VICTORIA_LOGS": (
                "logging",
                "victoria_logs_enabled",
            ),  # Note: inverted logic
            "LOKI_APP_TAG": ("logging", "loki_app_tag"),
            "MCP_PROJECT_PATH": ("logging", "project_path"),
            # Session settings
            "SESSION_TTL_SECONDS": ("session", "ttl_seconds"),
            "SESSION_DB_PATH": ("session", "db_path"),
            "STABLE_LIST_DB_PATH": ("session", "db_path"),  # Use same DB as sessions
            "SESSION_CLEANUP_PROBABILITY": ("session", "cleanup_probability"),
            # Memory settings
            "MEMORY_ENABLED": ("memory", "enabled"),
            "MEMORY_ROLLOVER_LIMIT": ("memory", "rollover_limit"),
            "MEMORY_SESSION_CUTOFF_HOURS": ("memory", "session_cutoff_hours"),
            "MEMORY_SUMMARY_CHAR_LIMIT": ("memory", "summary_char_limit"),
            "MEMORY_MAX_FILES_PER_COMMIT": ("memory", "max_files_per_commit"),
            # Services
            "LOITER_KILLER_HOST": ("services", "loiter_killer_host"),
            "LOITER_KILLER_PORT": ("services", "loiter_killer_port"),
            # Dev/Testing
            "MCP_ADAPTER_MOCK": ("dev", "adapter_mock"),
            "CI_E2E": ("dev", "ci_e2e"),
            # OpenAI specific
            "MAX_PARALLEL_TOOL_EXEC": ("openai", "max_parallel_tool_exec"),
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
                # Special handling for inverted boolean flags
                if env_key == "DISABLE_VICTORIA_LOGS":
                    # Invert the boolean value
                    current[path[-1]] = value.lower() not in ("1", "true", "yes")
                else:
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
            # Logging extras
            "VICTORIA_LOGS_URL": self.logging.victoria_logs_url,
            "VICTORIA_LOGS_ENABLED": str(self.logging.victoria_logs_enabled).lower(),
            "LOKI_APP_TAG": self.logging.loki_app_tag,
            "MCP_PROJECT_PATH": self.logging.project_path or "",
            # Services
            "LOITER_KILLER_URL": self.services.loiter_killer_url,
            # Testing/Dev
            "MCP_ADAPTER_MOCK": str(self.dev.adapter_mock).lower(),
            "CI_E2E": str(self.dev.ci_e2e).lower(),
            # OpenAI specific
            "MAX_PARALLEL_TOOL_EXEC": str(self.openai.max_parallel_tool_exec),
        }

        # Filter out empty values
        return {k: v for k, v in env_vars.items() if v}

    def export_mcp_config(self) -> Dict[str, Any]:
        """Export settings as mcp-config.json format."""
        env_vars = self.export_env()

        return {
            "mcpServers": {
                "the-force": {
                    "command": "uv",
                    "args": ["run", "--", "mcp-the-force"],
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
