"""Application settings loaded from environment variables / .env file."""
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent.parent  # backend/


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(BASE_DIR / ".env"), env_file_encoding="utf-8", extra="ignore"
    )

    APP_ENV: str = "development"  # development | test | production
    APP_NAME: str = "Shijie Learning Platform API"
    API_V1_PREFIX: str = "/api/v1"
    LOG_LEVEL: str = "INFO"

    BACKEND_HOST: str = "0.0.0.0"
    BACKEND_PORT: int = 8000

    # SQLite for development/test; PostgreSQL in production (DATABASE_URL=postgresql+psycopg://...)
    DATABASE_URL: str = f"sqlite:///{BASE_DIR / 'data' / 'app.db'}"

    REDIS_URL: str = "redis://localhost:6379/0"  # reserved for production; not required in dev

    JWT_SECRET: str = "dev-only-secret-change-me"
    ACCESS_TOKEN_TTL_MINUTES: int = 30
    REFRESH_TOKEN_TTL_DAYS: int = 14

    CORS_ORIGINS: str = "http://localhost:5173,http://127.0.0.1:5173"

    # Providers -------------------------------------------------
    LLM_PROVIDER: str = "mock"  # mock | openrouter
    OPENROUTER_API_KEY: str = ""
    OPENROUTER_BASE_URL: str = "https://openrouter.ai/api/v1"
    LLM_DEFAULT_MODEL: str = ""
    LLM_FALLBACK_MODELS: str = ""
    LLM_TIMEOUT_SECONDS: int = 60

    ASR_PROVIDER: str = "mock"  # mock | funasr | openai_compatible
    ASR_BASE_URL: str = "http://localhost:8100"
    ASR_MODEL: str = "paraformer-zh"
    ASR_API_KEY: str = ""  # openai_compatible 云识别（硅基流动/Groq 等）需要
    ASR_TRUST_ENV: bool = False  # False=绕过系统代理直连(国内云 API 直连更稳)；代理上网可设 true

    OCR_PROVIDER: str = "mock"  # mock | paddleocr

    EMBEDDING_PROVIDER: str = "lexical"  # lexical | bge (bge requires model runtime)
    EMBEDDING_MODEL: str = "bge-m3"
    EMBEDDING_DIMENSION: int = 1024

    RERANKER_PROVIDER: str = "none"  # none | bge-reranker
    RERANKER_MODEL: str = ""

    EXERCISE_SOURCE: str = "local_bank"

    STORAGE_PROVIDER: str = "local"  # local | s3-compatible (MinIO in production)
    STORAGE_ENDPOINT: str = ""
    STORAGE_BUCKET: str = "shijie"
    STORAGE_ACCESS_KEY: str = ""
    STORAGE_SECRET_KEY: str = ""
    STORAGE_LOCAL_DIR: str = str(BASE_DIR / "data" / "uploads")

    # Review scheduler ------------------------------------------
    SCHEDULER_VERSION: str = "fsrs45-baseline+planner-v1"
    DAILY_REVIEW_DEFAULT_MINUTES: int = 20

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
