"""Constants for the simulation and the API. Everything tunable lives here."""

import math
import os
from functools import lru_cache
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv
from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = BACKEND_ROOT.parent

load_dotenv(BACKEND_ROOT / ".env")

# Durations: whole days, one timeline per run.
DURATION_MIN_DAYS = 1
DURATION_MAX_DAYS = 30
DURATION_DEFAULT_DAYS = 7

# Integration.
DT_SECONDS = 600  # 10 min Euler step
FRAME_INTERVAL_SECONDS = 3600  # one recorded sample per hour

# Collectors and request limits.
DEFAULT_COLLECTOR_RADIUS_M = 10_000.0
MAX_LITTER_PLACEMENTS = 50
MAX_COLLECTORS = 20
MAX_DISTINCT_BOXES = 8  # snapshot boxes (areas) one request may need

# Snapshot box.
# Slicing a box from the open Copernicus handle takes 5-12 s at any size up to 25 deg (measured),
# so the cap sits just above the 30-day formula value (24.5) and never cuts a box short.
HALF_WIDTH_CAP_DEG = 25.0
# Boxes with more cells than this are not cached in Tiger: a 25 deg box is ~360,000 rows (tens of MB,
# about a minute to upload) while refetching it takes seconds. 60,000 covers boxes up to 10 deg.
SNAPSHOT_STORE_MAX_CELLS = 60_000
CACHE_KEEP_HOURS = 2  # in-memory snapshots older than this (by slice hour) are dropped
CENTRE_ROUND_DEG = 0.5
GRID_RESOLUTION_DEG = 1 / 12

# Which current components are summed into u_total / v_total.
APPLY_STOKES = True
APPLY_TIDE = False  # frozen tidal phase is wrong for days-long drift; on with multi-slice

# Per litter type drift multiplier. Identical until documented otherwise.
LITTER_TYPES = ("bottle", "bag", "foam")
DRIFT_FACTOR = {"bottle": 1.0, "bag": 1.0, "foam": 1.0}

# Copernicus.
COPERNICUS_DATASET_ID = "cmems_mod_glo_phy_anfc_merged-uv_PT1H-i"
COPERNICUS_TIMEOUT_S = 30  # a slice takes 5-12 s, plus ~8 s if the handle must be (re)opened
COPERNICUS_REOPEN_S = 6 * 3600  # reopen the dataset handle this often to see newly published hours
SYNTHETIC_RETRY_S = 60  # a fallback field is reused this long before Copernicus is tried again
DATABASE_RETRY_S = 60  # after a database error the database is skipped this long

# Arrows returned by /currents: roughly this many per side.
CURRENT_ARROWS_PER_SIDE = 20

ATTRIBUTION_SOURCE = "Copernicus Marine Service, Global Ocean Physics Analysis and Forecast"
SYNTHETIC_SOURCE = "Synthetic rotating gyre (Copernicus data unavailable)"
LIMITATIONS = [
    "Single frozen time slice",
    "No tide in MVP",
    "No wind, sinking or breakdown",
    "About 9 km grid",
]

CORS_ORIGINS = [o.strip() for o in os.getenv("CORS_ORIGIN", "http://localhost:5173").split(",") if o.strip()]
DATABASE_URL = os.getenv("DATABASE_URL")


def half_width_deg(duration_days: int) -> float:
    """Box half-width: room for about a 1 m/s current (0.8 degrees a day), rounded up to half a
    degree, capped at HALF_WIDTH_CAP_DEG (see the fetch timings there)."""
    raw = 0.5 + 0.8 * duration_days
    return min(HALF_WIDTH_CAP_DEG, math.ceil(raw * 2) / 2)


class Settings(BaseSettings):
    """Story, retrieval, and narration configuration."""

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
