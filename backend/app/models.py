from __future__ import annotations

import re
from enum import Enum
from typing import Literal

from pydantic import AnyHttpUrl, BaseModel, ConfigDict, Field, field_validator, model_validator


SAFE_ID = r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$"
SAFE_SLUG = r"^[a-z0-9][a-z0-9_-]{0,63}$"


class FinalStatus(str, Enum):
    floating = "floating"
    beached = "beached"
    captured = "captured"
    outside_domain = "outside_domain"
    missing_data = "missing_data"


class Coordinate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    lon: float = Field(ge=-180, le=180)
    lat: float = Field(ge=-90, le=90)


class PlaceContext(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    coordinates: Coordinate
    label: str = Field(min_length=1, max_length=120)
    ocean: str | None = Field(default=None, min_length=1, max_length=80)
    sea: str | None = Field(default=None, min_length=1, max_length=80)
    country: str | None = Field(default=None, min_length=1, max_length=80)
    coast: str | None = Field(default=None, min_length=1, max_length=120)

    @field_validator("label", "ocean", "sea", "country", "coast")
    @classmethod
    def reject_control_characters(cls, value: str | None) -> str | None:
        if value is not None and any(ord(character) < 32 for character in value):
            raise ValueError("place text cannot contain control characters")
        return value


class RouteGeography(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    start: PlaceContext
    end: PlaceContext
    traversed_regions: list[str] = Field(default_factory=list, max_length=12)
    landfall: PlaceContext | None = None

    @field_validator("traversed_regions")
    @classmethod
    def validate_regions(cls, values: list[str]) -> list[str]:
        cleaned: list[str] = []
        for value in values:
            value = value.strip()
            if not value or len(value) > 120:
                raise ValueError("regions must be between 1 and 120 characters")
            if any(ord(character) < 32 for character in value):
                raise ValueError("regions cannot contain control characters")
            if value not in cleaned:
                cleaned.append(value)
        return cleaned


class SimulationEvent(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    elapsed_hours: float = Field(ge=0, le=8760)
    type: str = Field(pattern=SAFE_SLUG)
    location: str | None = Field(default=None, min_length=1, max_length=120)
    coordinates: Coordinate | None = None

    @field_validator("location")
    @classmethod
    def reject_control_characters(cls, value: str | None) -> str | None:
        if value is not None and any(ord(character) < 32 for character in value):
            raise ValueError("location cannot contain control characters")
        return value


class SimulationSummary(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    simulation_id: str = Field(pattern=SAFE_ID)
    litter_type: str = Field(pattern=SAFE_SLUG)
    particle_id: str = Field(pattern=SAFE_ID)
    duration_hours: float = Field(gt=0, le=8760)
    events: list[SimulationEvent] = Field(min_length=1, max_length=20)
    final_status: FinalStatus
    assumptions: list[str] = Field(default_factory=list, max_length=20)
    geography: RouteGeography | None = None

    @field_validator("assumptions")
    @classmethod
    def validate_assumptions(cls, values: list[str]) -> list[str]:
        cleaned: list[str] = []
        for value in values:
            value = value.strip()
            if not value or len(value) > 200:
                raise ValueError("assumptions must be between 1 and 200 characters")
            if any(ord(character) < 32 for character in value):
                raise ValueError("assumptions cannot contain control characters")
            cleaned.append(value)
        return cleaned

    @model_validator(mode="after")
    def validate_event_timeline(self) -> "SimulationSummary":
        previous = -1.0
        for event in self.events:
            if event.elapsed_hours > self.duration_hours:
                raise ValueError("event elapsed_hours cannot exceed duration_hours")
            if event.elapsed_hours < previous:
                raise ValueError("events must be ordered by elapsed_hours")
            previous = event.elapsed_hours
        return self


def story_word_count(script: str) -> int:
    return len(re.findall(r"\b[\w’'-]+\b", script, flags=re.UNICODE))


class StoryDraft(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    title: str = Field(min_length=1, max_length=80)
    script: str

    @field_validator("script")
    @classmethod
    def validate_script(cls, value: str) -> str:
        count = story_word_count(value)
        if count < 50 or count > 80:
            raise ValueError(f"story must contain 50 to 80 words; received {count}")
        disclosure_phrases = (
            "possible journey",
            "possible path",
            "finn's map",
            "finn’s map",
            "ocean map",
            "imagined journey",
            "modelled journey",
            "simulated journey",
            "simulation",
        )
        if not any(phrase in value.lower() for phrase in disclosure_phrases):
            raise ValueError("story must identify the journey as a map-based possibility")
        return value


class StorySource(BaseModel):
    document_id: str
    title: str
    url: AnyHttpUrl


class StoryResponse(BaseModel):
    story_id: str
    simulation_id: str
    particle_id: str
    title: str
    script: str
    sources: list[StorySource]
    generation_mode: Literal["live", "fallback"]
    retrieval_mode: Literal["tidb", "local"]


class AudioResponse(BaseModel):
    story_id: str
    audio_url: str
    content_type: str
    script: str
    voice_id: str
    model_id: str
    cached: bool


class StoryForRunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    particle_id: str = Field(pattern=SAFE_ID)
