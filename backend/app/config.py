import os
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Groq gives free API access (no credit card) to fast open models via an
    # OpenAI-compatible endpoint - see https://console.groq.com/keys
    groq_api_key: str = ""
    groq_model: str = "llama-3.3-70b-versatile"
    groq_base_url: str = "https://api.groq.com/openai/v1"
    jwt_secret: str = "dev-secret-change-me"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 1440
    database_url: str = "sqlite:///./study_companion.db"
    upload_dir: str = "./uploads"


settings = Settings()
os.makedirs(settings.upload_dir, exist_ok=True)
