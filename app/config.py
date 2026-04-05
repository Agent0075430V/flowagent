from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "FlowAgent API"
    env: str = "dev"
    host: str = "0.0.0.0"
    port: int = 8080

    gcp_project_id: str = "woven-answer-492218-v6"
    firestore_database: str = "(default)"

    google_client_id: str = ""
    google_client_secret: str = ""
    google_redirect_uri: str = "http://localhost:8080/auth/callback"

    default_timezone: str = "Asia/Kolkata"
    default_work_start: str = "09:00"
    default_work_end: str = "19:00"

    # Use a strong random value in production for signing ephemeral state payloads.
    state_secret: str = "change-me"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


@lru_cache
def get_settings() -> Settings:
    return Settings()
