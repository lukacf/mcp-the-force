from functools import lru_cache
from pydantic import Field, PositiveInt
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    host: str = Field("127.0.0.1", env="HOST")
    port: PositiveInt = Field(8000, env="PORT")
    openai_api_key: str = Field("", env="OPENAI_API_KEY")
    vertex_project: str = Field("", env="VERTEX_PROJECT")
    vertex_location: str = Field("", env="VERTEX_LOCATION")
    max_inline_tokens: PositiveInt = Field(12000, env="MAX_INLINE_TOKENS")
    default_temperature: float = Field(0.2, env="DEFAULT_TEMPERATURE")
    
    class Config:
        env_file = ".env"
    
    @property
    def vertex_endpoint(self) -> str:
        return f"projects/{self.vertex_project}/locations/{self.vertex_location}"

@lru_cache
def get_settings() -> Settings:
    return Settings()
