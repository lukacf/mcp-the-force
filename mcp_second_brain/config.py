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

    class Config:
        env_file = ".env"
        extra = "ignore"  # Ignore extra fields in .env file

    @property
    def vertex_endpoint(self) -> str:
        return f"projects/{self.vertex_project}/locations/{self.vertex_location}"


@lru_cache
def get_settings() -> Settings:
    return Settings()
