from functools import lru_cache
from pydantic import Field, PositiveInt
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    host: str = Field("127.0.0.1", env="HOST")
    port: PositiveInt = Field(8000, env="PORT")
    openai_api_key: str = Field("", env="OPENAI_API_KEY")
    vertex_project: str = Field("", env="VERTEX_PROJECT")
    vertex_location: str = Field("", env="VERTEX_LOCATION")
    context_percentage: float = Field(
        0.85, env="CONTEXT_PERCENTAGE", ge=0.1, le=0.95
    )  # Use 10-95% of model context
    default_temperature: float = Field(0.2, env="DEFAULT_TEMPERATURE")

    # Memory configuration
    memory_enabled: bool = Field(True, env="MEMORY_ENABLED")
    memory_rollover_limit: PositiveInt = Field(9500, env="MEMORY_ROLLOVER_LIMIT")
    memory_session_cutoff_hours: PositiveInt = Field(
        2, env="MEMORY_SESSION_CUTOFF_HOURS"
    )
    memory_summary_char_limit: PositiveInt = Field(500, env="MEMORY_SUMMARY_CHAR_LIMIT")
    memory_max_files_per_commit: PositiveInt = Field(
        50, env="MEMORY_MAX_FILES_PER_COMMIT"
    )
    session_db_path: str = Field(".mcp_sessions.sqlite3", env="SESSION_DB_PATH")

    class Config:
        env_file = ".env"
        extra = "ignore"  # Ignore extra fields in .env file

    @property
    def vertex_endpoint(self) -> str:
        return f"projects/{self.vertex_project}/locations/{self.vertex_location}"


@lru_cache
def get_settings() -> Settings:
    return Settings()
