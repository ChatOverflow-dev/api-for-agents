from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    supabase_url: str
    supabase_service_key: str
    llm_api_key: str | None = None
    llm_base_url: str | None = None
    llm_api_version: str | None = None
    llm_default_headers: dict[str, str] | None = None
    embedding_model: str = "text-embedding-3-small"

    class Config:
        env_file = ".env"
        extra = "ignore"  # Ignore extra fields in .env


settings = Settings()
