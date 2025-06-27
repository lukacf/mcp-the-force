from functools import lru_cache
from pydantic import Field, PositiveInt
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    host: str = Field(default="127.0.0.1", validation_alias="HOST")
    port: PositiveInt = Field(default=8000, validation_alias="PORT")
    openai_api_key: str = Field(default="", validation_alias="OPENAI_API_KEY")
    vertex_project: str = Field(default="", validation_alias="VERTEX_PROJECT")
    vertex_location: str = Field(default="", validation_alias="VERTEX_LOCATION")
    context_percentage: float = Field(
        default=0.85, validation_alias="CONTEXT_PERCENTAGE", ge=0.1, le=0.95
    )  # Use 10-95% of model context
    default_temperature: float = Field(
        default=0.2, validation_alias="DEFAULT_TEMPERATURE"
    )

    # Memory configuration
    memory_enabled: bool = Field(default=True, validation_alias="MEMORY_ENABLED")
    memory_rollover_limit: PositiveInt = Field(
        default=9500, validation_alias="MEMORY_ROLLOVER_LIMIT"
    )
    memory_session_cutoff_hours: PositiveInt = Field(
        default=2, validation_alias="MEMORY_SESSION_CUTOFF_HOURS"
    )
    memory_summary_char_limit: PositiveInt = Field(
        default=200000, validation_alias="MEMORY_SUMMARY_CHAR_LIMIT"
    )  # ~50k tokens
    memory_max_files_per_commit: PositiveInt = Field(
        default=50, validation_alias="MEMORY_MAX_FILES_PER_COMMIT"
    )
    session_db_path: str = Field(
        default=".mcp_sessions.sqlite3", validation_alias="SESSION_DB_PATH"
    )

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def vertex_endpoint(self) -> str:
        return f"projects/{self.vertex_project}/locations/{self.vertex_location}"


@lru_cache
def get_settings() -> Settings:
    return Settings()
