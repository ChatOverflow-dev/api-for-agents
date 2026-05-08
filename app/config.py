import json

from pydantic import field_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    supabase_url: str
    supabase_service_key: str
    llm_api_key: str | None = None
    llm_base_url: str | None = None
    llm_api_version: str | None = None
    llm_default_headers: dict[str, str] | None = None
    embedding_model: str = "text-embedding-3-small"

    @field_validator("llm_default_headers", mode="before")
    @classmethod
    def parse_headers(cls, v):
        if isinstance(v, str):
            try:
                return json.loads(v)
            except json.JSONDecodeError:
                # dotenv stripped inner quotes — try to recover
                # e.g. {Key:Value} -> {"Key":"Value"}
                import re
                pairs = re.findall(r'([\w-]+)\s*:\s*([^,}]+)', v.strip('{}'))
                if pairs:
                    return {k.strip(): v.strip() for k, v in pairs}
        return v

    class Config:
        env_file = ".env"
        extra = "ignore"  # Ignore extra fields in .env


settings = Settings()
