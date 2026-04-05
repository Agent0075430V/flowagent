from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "FlowAgent API"
    env: str = "dev"
    host: str = "0.0.0.0"
    port: int = 8080

    gcp_project_id: str = "woven-answer-492218-v6"
    firestore_database: str = "(default)"
    enable_local_fallback_store: bool = True
    local_fallback_store_file: str = ".flowagent_local_store.json"

    google_client_id: str = ""
    google_client_secret: str = ""
    google_redirect_uri: str = "http://localhost:8080/auth/callback"

    # JWT settings for user authentication.
    jwt_secret: str = ""
    jwt_algorithm: str = "HS256"
    jwt_expires_minutes: int = 1440

    # Gemini/Vertex AI fallback settings for intent classification.
    use_gemini_intent_fallback: bool = True
    gemini_project_id: str = ""
    gemini_location: str = "asia-south1"
    gemini_model: str = "gemini-1.5-flash"

    default_timezone: str = "Asia/Kolkata"
    default_work_start: str = "09:00"
    default_work_end: str = "19:00"

    # Use a strong random value in production for signing ephemeral state payloads.
    state_secret: str = ""
    oauth_state_ttl_seconds: int = 600

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


@lru_cache
def get_settings() -> Settings:
    return Settings()
