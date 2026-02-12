from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    supabase_url: str
    supabase_service_key: str

    class Config:
        env_file = ".env"
        extra = "ignore"  # Ignore extra fields in .env


settings = Settings()
