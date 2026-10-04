"""Pydantic models: the API contract with the frontend.

JSON is camelCase to match src/types.ts; Python attributes stay snake_case.
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from pydantic.alias_generators import to_camel

from app import config

LitterType = Literal["bottle", "bag", "foam"]
PlacementType = Literal["bottle", "bag", "foam", "collector"]
ParticleStatus = Literal["floating", "captured", "beached", "outside"]
SnapshotSource = Literal["copernicus", "synthetic"]
Coordinates = tuple[float, float]  # [lon, lat]


class ApiModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


# ---- requests ---------------------------------------------------------------


class Placement(ApiModel):
    id: str = Field(min_length=1, max_length=64)
    type: PlacementType
    coordinates: Coordinates
    placed_at_seconds: int = Field(default=0, ge=0)

    @field_validator("coordinates")
    @classmethod
    def _in_range(cls, value: Coordinates) -> Coordinates:
        lon, lat = value
        if not (-180.0 <= lon <= 180.0 and -90.0 <= lat <= 90.0):
            raise ValueError("coordinates must be [lon, lat] within [-180, 180] and [-90, 90]")
        return value

    @field_validator("placed_at_seconds", mode="before")
    @classmethod
    def _whole_seconds(cls, value):
        if isinstance(value, bool):
            raise ValueError("placement time must be a whole number of seconds")
        return value


class SimulateRequest(ApiModel):
    placements: list[Placement]
    duration_days: int = Field(
        default=config.DURATION_DEFAULT_DAYS, ge=config.DURATION_MIN_DAYS, le=config.DURATION_MAX_DAYS
    )
    collector_radius_m: float = Field(default=config.DEFAULT_COLLECTOR_RADIUS_M, gt=0, le=200_000)
    # Collectors are placed and reported either way; they only capture litter when this is true.
    # Off by default for now; /compare always runs both ways.
    honour_collectors: bool = False

    @field_validator("placements")
    @classmethod
    def _check_placements(cls, value: list[Placement]) -> list[Placement]:
        litter = [p for p in value if p.type != "collector"]
        if not litter:
            raise ValueError("at least one litter placement is required")
        if len(litter) > config.MAX_LITTER_PLACEMENTS:
            raise ValueError(f"at most {config.MAX_LITTER_PLACEMENTS} litter placements")
        if len(value) - len(litter) > config.MAX_COLLECTORS:
            raise ValueError(f"at most {config.MAX_COLLECTORS} collectors")
        ids = [p.id for p in value]
        if len(ids) != len(set(ids)):
            raise ValueError("placement ids must be unique")
        return value

    @model_validator(mode="after")
    def _placement_times_within_run(self):
        total_seconds = self.duration_days * 24 * 3600
        for placement in self.placements:
            if placement.placed_at_seconds > total_seconds:
                raise ValueError(f"{placement.id}: placement time exceeds the experiment duration")
        return self


# ---- simulate response ------------------------------------------------------


class TrajectorySample(ApiModel):
    time_seconds: int
    coordinates: Coordinates
    status: ParticleStatus


class ParticleTrajectory(ApiModel):
    id: str
    type: LitterType
    samples: list[TrajectorySample]


class ItemResult(ApiModel):
    id: str
    type: LitterType
    final_status: ParticleStatus
    captured_by: str | None = None
    status_changed_at_seconds: int | None = None


class CollectorResult(ApiModel):
    id: str
    coordinates: Coordinates
    radius_m: float
    captured_count: int


class Summary(ApiModel):
    floating: int = 0
    captured: int = 0
    beached: int = 0
    outside: int = 0


class SnapshotInfo(ApiModel):
    snapshot_id: str
    source: SnapshotSource
    slice_time: datetime
    n_slices: int


class Attribution(ApiModel):
    source: str
    dataset: str
    limitations: list[str]


class SimulateResponse(ApiModel):
    run_id: str
    duration_days: int
    total_seconds: int
    sample_interval_seconds: int
    trajectories: list[ParticleTrajectory]
    items: list[ItemResult]
    collectors: list[CollectorResult]
    summary: Summary
    snapshots: list[SnapshotInfo]
    attribution: Attribution
    persisted: bool


class CompareResponse(ApiModel):
    """Keys match the frontend's ComparisonMode. delta = with minus without."""

    without: SimulateResponse
    with_: SimulateResponse = Field(alias="with")
    delta: Summary


# ---- other endpoints --------------------------------------------------------


class CurrentArrow(ApiModel):
    coordinates: Coordinates
    u: float  # m/s east
    v: float  # m/s north
    speed: float  # m/s
    bearing: float  # degrees clockwise from north


class CurrentsResponse(ApiModel):
    snapshot: SnapshotInfo
    bounds: tuple[Coordinates, Coordinates]  # [[west, south], [east, north]]
    arrows: list[CurrentArrow]
    attribution: Attribution


class TimelineBucket(ApiModel):
    time_seconds: int
    floating: int
    captured: int
    beached: int
    outside: int


class TimelineResponse(ApiModel):
    run_id: str
    bucket_seconds: int
    buckets: list[TimelineBucket]


class DurationRange(ApiModel):
    min: int
    max: int
    default: int


class MetaDefaults(ApiModel):
    collector_radius_m: float
    sample_interval_seconds: int
    integration_step_seconds: int
    max_litter_placements: int
    max_collectors: int = config.MAX_COLLECTORS
    max_distinct_areas: int = config.MAX_DISTINCT_BOXES


class MetaResponse(ApiModel):
    duration_days: DurationRange
    defaults: MetaDefaults
    litter_types: list[LitterType]
    attribution: Attribution


class HealthResponse(ApiModel):
    ok: bool
    db: bool


class ErrorResponse(ApiModel):
    code: str
    message: str
    placement_id: str | None = None
