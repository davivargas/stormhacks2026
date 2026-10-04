from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


BACKEND_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = BACKEND_ROOT.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(PROJECT_ROOT / ".env", PROJECT_ROOT / ".env.local", BACKEND_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    retrieval_mode: Literal["local", "tidb"] = "local"
    story_prompt_version: str = "2026-10-03-v1"
    retrieval_version: str = "ocean-education-v1"

    gemini_api_key: SecretStr | None = None
    gemini_model: str = "gemini-3.8-flash"
    embedding_model: str = "gemini-embedding-2"
    embedding_dimensions: int = Field(default=768, ge=128, le=3072)

    tidb_database_url: SecretStr | None = None

    elevenlabs_api_key: SecretStr | None = None
    elevenlabs_voice_id: str = ""
    elevenlabs_model_id: str = "eleven_v4"
    elevenlabs_output_format: str = "mp3_44100_128"

    provider_timeout_seconds: float = Field(default=20.0, ge=1.0, le=120.0)
    provider_max_attempts: int = Field(default=2, ge=1, le=4)
    cache_dir: Path = BACKEND_ROOT / ".data"
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    @field_validator("embedding_dimensions")
    @classmethod
    def supported_embedding_dimensions(cls, value: int) -> int:
        if value not in {768, 1536, 3072}:
            raise ValueError("use a Gemini-supported dimension: 768, 1536, or 3072")
        return value

    @property
    def allowed_origins(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
