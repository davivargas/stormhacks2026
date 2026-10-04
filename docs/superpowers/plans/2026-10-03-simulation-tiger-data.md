# Simulation and Tiger Data (Stream 3) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A FastAPI backend that turns litter placements anywhere on the ocean into stored, replayable drift trajectories using one frozen Copernicus current snapshot per item, persisted in Tiger Data.

**Architecture:** A pure NumPy engine advects each item through a `Field` (a small lon/lat box of currents). A service layer resolves one `Field` per item (memory cache, then Tiger, then Copernicus, then a synthetic fallback), runs the engine, and maps results to the frontend's existing `ParticleTrajectory` JSON. Tiger Data stores snapshots and run positions in hypertables and serves replay and a `time_bucket` timeline.

**Tech Stack:** Python 3.12+/3.13, FastAPI, Pydantic v2, NumPy, psycopg 3 with psycopg_pool, `copernicusmarine` toolbox, pytest. No SciPy, no Shapely.

**Spec:** `docs/superpowers/specs/2026-10-03-simulation-tiger-data-design.md`

**Branch:** `feature/simulation-tiger-data`. All commands run from `backend/` unless stated. On Windows Git Bash activate the venv with `source .venv/Scripts/activate`.

## Global Constraints

- Durations: integer days, 1 to 30, default 7. One duration and one timeline per run; every item starts at second zero.
- Integration step 600 s. Samples recorded every 3600 s. `timeSeconds` is elapsed seconds from run start.
- Statuses are exactly `floating`, `captured`, `beached`, `outside` (the frontend's `ParticleStatus`).
- Coordinates are always `[longitude, latitude]`.
- JSON keys are camelCase; Python and SQL are snake_case.
- Box half-width: `min(8.0, ceil((1.0 + 0.4 * days) * 2) / 2)` degrees. Box centre: drop point rounded to 0.5 degrees.
- Dataset id: `cmems_mod_glo_phy_anfc_merged-uv_PT1H-i`. MVP uses `uo + ustokes`, `vo + vstokes`. Tide is stored, not applied (`USE_TIDE = False`).
- Land is where `uo` is NaN.
- Default collector radius 10 000 m. Maximum 50 litter placements per run.
- Copernicus fetch budget 20 s, then synthetic fallback with `source: "synthetic"`. Never fail a simulate request because of the network or the database.
- Secrets live only in `backend/.env` (gitignored). Tests never touch the network or a real database.
- Deviations from the spec, deliberate: `requirements.txt` instead of `pyproject.toml` (pip only, no uv on the dev machine); the fetch lives in `app/sim/copernicus.py` beside `snapshot.py`; an `app/service.py` keeps routes thin; status checks run in the order outside, beached, captured (an out-of-box position must not be read as a clipped land cell); `runs.start_time` (the slice hour) anchors `positions.time`.

## Review Focus

1. **Empty or collector-only placements.** A run with no litter must return HTTP 200 with empty `trajectories` and all-zero `summary`, not crash. Test in Task 4.
2. **Item dropped inside a collector's radius.** It is captured at second zero, counted once, and never moves. Test in Task 3.
3. **Bad coordinates and duplicate ids.** Latitude beyond 90, longitude beyond 180, or two placements with one id are rejected with 422 before any work. Tests in Task 1.
4. **Drop near the antimeridian or a pole.** The box is clamped to valid lon/lat instead of wrapping; an item reaching the clamp edge becomes `outside`. Test in Task 2.
5. **Coastal cells with a mix of land and water corners.** Sampling treats land corners as zero velocity and never returns NaN, so a position can never become NaN. Test in Task 2.

## File Structure

```
backend/
  requirements.txt            pinned floor versions; copernicusmarine added in Task 5
  .env.example                already committed
  app/
    __init__.py
    main.py                   app factory, CORS, lifespan (db pool from Task 6)
    config.py                 every constant and the two box helpers
    schemas.py                Pydantic models: the JSON contract
    routes.py                 thin HTTP handlers only
    service.py                resolve fields, validate land, run engine, build responses, persist
    db.py                     Tiger Data access: pool, snapshots, runs, timeline
    sim/
      __init__.py
      geo.py                  haversine and metres-per-degree constants
      snapshot.py             Field, SnapshotKey, box_bounds, build_field, synthetic_field
      engine.py               run(): time loop and status machine
      copernicus.py           fetch_field(): the only code that talks to Copernicus
  scripts/
    make_fixture.py           writes fixtures/simulate_response.json
    fixtures/simulate_response.json
    schema.sql
    init_db.py
    smoke.py                  manual end-to-end check against a running server
  tests/
    conftest.py
    test_schemas.py
    test_snapshot.py
    test_engine.py
    test_api.py
    test_copernicus.py
    test_db_offline.py
  Dockerfile
  README.md
```

---

### Task 1: Scaffold and JSON contract (Phase 0, unblocks the other three streams)

**Files:**
- Create: `backend/requirements.txt`, `backend/app/__init__.py`, `backend/app/sim/__init__.py`, `backend/app/config.py`, `backend/app/schemas.py`, `backend/app/routes.py`, `backend/app/main.py`, `backend/scripts/make_fixture.py`, `backend/scripts/fixtures/simulate_response.json` (generated), `backend/tests/conftest.py`
- Test: `backend/tests/test_schemas.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `config`: `MIN_DAYS=1`, `MAX_DAYS=30`, `DEFAULT_DAYS=7`, `DT_SECONDS=600`, `SAMPLE_INTERVAL_SECONDS=3600`, `DEFAULT_COLLECTOR_RADIUS_M=10000.0`, `MAX_LITTER=50`, `MAX_HALF_WIDTH_DEG=8.0`, `CENTRE_ROUND_DEG=0.5`, `GRID_STEP_DEG=1/12`, `USE_TIDE=False`, `FETCH_TIMEOUT_S=20`, `DATASET_ID`, `DRIFT_FACTOR: dict[str, float]`, `DATABASE_URL: str`, `CORS_ORIGIN: str`, `ATTRIBUTION_SOURCE: str`, `LIMITATIONS: list[str]`, `half_width_deg(duration_days: int) -> float`, `round_centre(x: float) -> float`.
  - `schemas`: `Placement`, `SimulateRequest`, `TrajectorySample`, `ParticleTrajectory`, `ItemSummary`, `CollectorSummary`, `StatusCounts`, `SnapshotInfo`, `Attribution`, `SimulateResponse`, `CompareResponse`, `Arrow`, `CurrentsResponse`, `MetaResponse`, `TimelinePoint`, `TimelineResponse`. Field names exactly as in the code below.
  - `main.app` (FastAPI) and `routes.router` with `GET /api/health`, `GET /api/meta`.

- [ ] **Step 1: Create the environment**

```bash
cd backend
python -m venv .venv
source .venv/Scripts/activate
```

Create `backend/requirements.txt`:

```
fastapi>=0.115
uvicorn[standard]>=0.32
pydantic>=2.9
numpy>=2.1
psycopg[binary,pool]>=3.2
python-dotenv>=1.0
pytest>=8.3
httpx>=0.27
```

```bash
pip install -r requirements.txt
```

Add `.venv` and `__pycache__` to the repo root `.gitignore` (append two lines: `.venv` and `__pycache__`).

- [ ] **Step 2: Write the failing tests**

Create `backend/tests/conftest.py`:

```python
import os

# Tests never touch a real database. Set before any app import;
# load_dotenv does not override variables that already exist.
os.environ["DATABASE_URL"] = ""
```

Create `backend/tests/test_schemas.py`:

```python
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app import config
from app.main import app
from app.schemas import CompareResponse, SimulateRequest, SimulateResponse, StatusCounts

FIXTURE = Path(__file__).resolve().parents[1] / "scripts" / "fixtures" / "simulate_response.json"


@pytest.mark.parametrize("days,expected", [(1, 1.5), (7, 4.0), (17, 8.0), (30, 8.0)])
def test_half_width_formula(days, expected):
    assert config.half_width_deg(days) == expected


def test_round_centre_to_half_degree():
    assert config.round_centre(-125.3) == -125.5
    assert config.round_centre(48.9) == 49.0


def test_request_accepts_frontend_placements():
    req = SimulateRequest.model_validate({
        "placements": [
            {"id": "bottle-1", "type": "bottle", "coordinates": [-125.3, 48.9]},
            {"id": "collector-1", "type": "collector", "coordinates": [-125.0, 48.8]},
        ],
        "durationDays": 3,
    })
    assert req.duration_days == 3
    assert req.collector_radius_m == 10000.0
    assert req.placements[0].coordinates == (-125.3, 48.9)


def test_request_defaults_to_seven_days():
    assert SimulateRequest.model_validate({"placements": []}).duration_days == 7


@pytest.mark.parametrize("days", [0, 31, 1.5])
def test_duration_must_be_integer_between_1_and_30(days):
    with pytest.raises(ValidationError):
        SimulateRequest.model_validate({"placements": [], "durationDays": days})


def test_duplicate_ids_rejected():
    with pytest.raises(ValidationError):
        SimulateRequest.model_validate({"placements": [
            {"id": "a", "type": "bottle", "coordinates": [0, 0]},
            {"id": "a", "type": "bag", "coordinates": [1, 1]},
        ]})


@pytest.mark.parametrize("coords", [[181, 0], [-181, 0], [0, 91], [0, -91]])
def test_out_of_range_coordinates_rejected(coords):
    with pytest.raises(ValidationError):
        SimulateRequest.model_validate({"placements": [
            {"id": "a", "type": "bottle", "coordinates": coords},
        ]})


def test_more_than_fifty_litter_rejected():
    placements = [{"id": f"b{i}", "type": "bottle", "coordinates": [0, 0]} for i in range(51)]
    with pytest.raises(ValidationError):
        SimulateRequest.model_validate({"placements": placements})


def test_fixture_matches_contract_and_is_camel_case():
    raw = json.loads(FIXTURE.read_text())
    parsed = SimulateResponse.model_validate(raw)
    assert parsed.trajectories[0].samples[0].time_seconds == 0
    assert "timeSeconds" in raw["trajectories"][0]["samples"][0]
    assert set(raw["summary"]) == {"floating", "captured", "beached", "outside"}


def test_compare_response_serialises_with_key():
    one = SimulateResponse.model_validate(json.loads(FIXTURE.read_text()))
    body = CompareResponse(
        without=one, with_=one,
        delta=StatusCounts(floating=0, captured=0, beached=0, outside=0),
    ).model_dump(by_alias=True, mode="json")
    assert set(body) == {"without", "with", "delta"}


def test_health_and_meta_endpoints():
    client = TestClient(app)
    assert client.get("/api/health").json()["status"] == "ok"
    meta = client.get("/api/meta").json()
    assert meta["minDurationDays"] == 1
    assert meta["maxDurationDays"] == 30
    assert meta["defaultDurationDays"] == 7
    assert meta["litterTypes"] == ["bottle", "bag", "foam"]
    assert meta["attribution"]["dataset"] == config.DATASET_ID
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `python -m pytest tests/test_schemas.py -q`
Expected: collection error, `ModuleNotFoundError: No module named 'app'`.

- [ ] **Step 4: Implement config, schemas, routes, main**

Create empty `backend/app/__init__.py` and `backend/app/sim/__init__.py`.

Create `backend/app/config.py`:

```python
import math
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

MIN_DAYS = 1
MAX_DAYS = 30
DEFAULT_DAYS = 7
DT_SECONDS = 600
SAMPLE_INTERVAL_SECONDS = 3600
DEFAULT_COLLECTOR_RADIUS_M = 10_000.0
MAX_LITTER = 50
MAX_HALF_WIDTH_DEG = 8.0
CENTRE_ROUND_DEG = 0.5
GRID_STEP_DEG = 1.0 / 12.0
USE_TIDE = False
FETCH_TIMEOUT_S = 20
DATASET_ID = "cmems_mod_glo_phy_anfc_merged-uv_PT1H-i"
DRIFT_FACTOR = {"bottle": 1.0, "bag": 1.0, "foam": 1.0}

DATABASE_URL = os.getenv("DATABASE_URL", "")
CORS_ORIGIN = os.getenv("CORS_ORIGIN", "http://localhost:5173")

ATTRIBUTION_SOURCE = "Copernicus Marine Service, Global Ocean Physics Analysis and Forecast"
LIMITATIONS = [
    "Simplified simulation, not a validated real-world prediction",
    "Single frozen time slice of the currents",
    "No tide in this version",
    "No wind, sinking or breakdown",
    "About 9 km grid: small inlets and harbours are not resolved",
]


def half_width_deg(duration_days: int) -> float:
    """Box half-width in degrees, rounded up to a half degree, capped."""
    return min(MAX_HALF_WIDTH_DEG, math.ceil((1.0 + 0.4 * duration_days) * 2) / 2)


def round_centre(x: float) -> float:
    """Round a coordinate to the nearest CENTRE_ROUND_DEG for cache keys."""
    return round(x / CENTRE_ROUND_DEG) * CENTRE_ROUND_DEG
```

Create `backend/app/schemas.py`:

```python
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from pydantic.alias_generators import to_camel

from . import config

LitterType = Literal["bottle", "bag", "foam"]
PlacementType = Literal["bottle", "bag", "foam", "collector"]
Status = Literal["floating", "captured", "beached", "outside"]
Coordinates = tuple[float, float]  # (longitude, latitude)


class Camel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class Placement(Camel):
    id: str = Field(min_length=1)
    type: PlacementType
    coordinates: Coordinates

    @field_validator("coordinates")
    @classmethod
    def _in_range(cls, value: Coordinates) -> Coordinates:
        lon, lat = value
        if not -180.0 <= lon <= 180.0 or not -90.0 <= lat <= 90.0:
            raise ValueError("coordinates must be [longitude -180..180, latitude -90..90]")
        return value


class SimulateRequest(Camel):
    placements: list[Placement]
    duration_days: int = Field(default=config.DEFAULT_DAYS, ge=config.MIN_DAYS, le=config.MAX_DAYS)
    collector_radius_m: float = Field(default=config.DEFAULT_COLLECTOR_RADIUS_M, gt=0, le=200_000)

    @model_validator(mode="after")
    def _check_placements(self) -> "SimulateRequest":
        ids = [p.id for p in self.placements]
        if len(ids) != len(set(ids)):
            raise ValueError("placement ids must be unique")
        litter = sum(1 for p in self.placements if p.type != "collector")
        if litter > config.MAX_LITTER:
            raise ValueError(f"at most {config.MAX_LITTER} litter placements per run")
        return self


class TrajectorySample(Camel):
    time_seconds: int
    coordinates: Coordinates
    status: Status


class ParticleTrajectory(Camel):
    id: str
    type: LitterType
    samples: list[TrajectorySample]


class ItemSummary(Camel):
    id: str
    type: LitterType
    final_status: Status
    captured_by: str | None = None
    status_changed_at_seconds: int | None = None


class CollectorSummary(Camel):
    id: str
    coordinates: Coordinates
    radius_m: float
    captured_count: int


class StatusCounts(Camel):
    floating: int
    captured: int
    beached: int
    outside: int


class SnapshotInfo(Camel):
    snapshot_id: str
    source: Literal["copernicus", "synthetic"]
    slice_time: datetime
    n_slices: int


class Attribution(Camel):
    source: str
    dataset: str
    limitations: list[str]


class SimulateResponse(Camel):
    run_id: str
    duration_days: int
    total_seconds: int
    sample_interval_seconds: int
    trajectories: list[ParticleTrajectory]
    items: list[ItemSummary]
    collectors: list[CollectorSummary]
    summary: StatusCounts
    snapshots: list[SnapshotInfo]
    attribution: Attribution
    persisted: bool


class CompareResponse(Camel):
    without: SimulateResponse
    with_: SimulateResponse = Field(alias="with")
    delta: StatusCounts


class Arrow(Camel):
    coordinates: Coordinates
    u: float
    v: float
    speed: float
    bearing: float  # degrees clockwise from north


class CurrentsResponse(Camel):
    snapshot: SnapshotInfo
    bounds: tuple[Coordinates, Coordinates]  # [[west, south], [east, north]]
    arrows: list[Arrow]


class MetaResponse(Camel):
    min_duration_days: int
    max_duration_days: int
    default_duration_days: int
    sample_interval_seconds: int
    default_collector_radius_m: float
    litter_types: list[str]
    attribution: Attribution


class TimelinePoint(Camel):
    time_seconds: int
    floating: int
    captured: int
    beached: int
    outside: int


class TimelineResponse(Camel):
    run_id: str
    points: list[TimelinePoint]
```

Create `backend/app/routes.py`:

```python
from fastapi import APIRouter

from . import config
from .schemas import Attribution, MetaResponse

router = APIRouter()


def attribution() -> Attribution:
    return Attribution(
        source=config.ATTRIBUTION_SOURCE,
        dataset=config.DATASET_ID,
        limitations=config.LIMITATIONS,
    )


@router.get("/health")
def health() -> dict:
    return {"status": "ok", "db": False}


@router.get("/meta", response_model=MetaResponse)
def meta() -> MetaResponse:
    return MetaResponse(
        min_duration_days=config.MIN_DAYS,
        max_duration_days=config.MAX_DAYS,
        default_duration_days=config.DEFAULT_DAYS,
        sample_interval_seconds=config.SAMPLE_INTERVAL_SECONDS,
        default_collector_radius_m=config.DEFAULT_COLLECTOR_RADIUS_M,
        litter_types=list(config.DRIFT_FACTOR),
        attribution=attribution(),
    )
```

Create `backend/app/main.py`:

```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import config
from .routes import router


def create_app() -> FastAPI:
    app = FastAPI(title="PlasticPaths simulation API")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[config.CORS_ORIGIN],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(router, prefix="/api")
    return app


app = create_app()
```

- [ ] **Step 5: Generate the frontend fixture**

Create `backend/scripts/make_fixture.py`:

```python
"""Writes a canned /api/simulate response so the frontend can build before the engine exists.

Run from backend/:  python -m scripts.make_fixture
"""
import json
from datetime import datetime, timezone
from pathlib import Path

from app.routes import attribution
from app.schemas import (
    CollectorSummary, ItemSummary, ParticleTrajectory, SimulateResponse,
    SnapshotInfo, StatusCounts, TrajectorySample,
)

OUT = Path(__file__).resolve().parent / "fixtures" / "simulate_response.json"


def trajectory(pid: str, kind: str, lon: float, lat: float, dlon: float, dlat: float,
               end_status: str, end_index: int, hours: int = 24) -> ParticleTrajectory:
    samples = []
    for h in range(hours + 1):
        k = min(h, end_index)
        status = end_status if h >= end_index else "floating"
        samples.append(TrajectorySample(
            time_seconds=h * 3600,
            coordinates=(round(lon + dlon * k, 5), round(lat + dlat * k, 5)),
            status=status,
        ))
    return ParticleTrajectory(id=pid, type=kind, samples=samples)


def main() -> None:
    response = SimulateResponse(
        run_id="00000000-0000-0000-0000-000000000001",
        duration_days=1,
        total_seconds=86400,
        sample_interval_seconds=3600,
        trajectories=[
            trajectory("bottle-1", "bottle", -125.30, 48.90, 0.012, -0.004, "captured", 9),
            trajectory("bag-1", "bag", -125.60, 48.70, -0.010, 0.006, "beached", 15),
            trajectory("foam-1", "foam", -125.90, 48.50, 0.008, 0.003, "floating", 999),
        ],
        items=[
            ItemSummary(id="bottle-1", type="bottle", final_status="captured",
                        captured_by="collector-1", status_changed_at_seconds=9 * 3600),
            ItemSummary(id="bag-1", type="bag", final_status="beached",
                        status_changed_at_seconds=15 * 3600),
            ItemSummary(id="foam-1", type="foam", final_status="floating"),
        ],
        collectors=[CollectorSummary(id="collector-1", coordinates=(-125.19, 48.86),
                                     radius_m=10000.0, captured_count=1)],
        summary=StatusCounts(floating=1, captured=1, beached=1, outside=0),
        snapshots=[SnapshotInfo(snapshot_id="00000000-0000-0000-0000-0000000000aa",
                                source="synthetic",
                                slice_time=datetime(2026, 10, 3, 18, tzinfo=timezone.utc),
                                n_slices=1)],
        attribution=attribution(),
        persisted=False,
    )
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(response.model_dump(by_alias=True, mode="json"), indent=2))
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
```

Create empty `backend/scripts/__init__.py`, then run: `python -m scripts.make_fixture`
Expected: `wrote ...simulate_response.json`

- [ ] **Step 6: Run tests to verify they pass**

Run: `python -m pytest tests/test_schemas.py -q`
Expected: all pass (19 tests).

- [ ] **Step 7: Check the server starts**

Run: `python -m uvicorn app.main:app --port 8000` then open `http://localhost:8000/api/meta` and `http://localhost:8000/docs`. Stop the server.
Expected: JSON with `minDurationDays: 1`; the docs page lists the two endpoints.

- [ ] **Step 8: Commit and tell the team**

```bash
git add ../.gitignore requirements.txt app scripts tests
git commit -m "feat(backend): scaffold, JSON contract, meta endpoint and frontend fixture"
```

Tell Persons 1, 2 and 4 that `backend/scripts/fixtures/simulate_response.json` is the response shape and that `http://localhost:8000/docs` shows every model.

---

### Task 2: Current field, snapshot key, synthetic fallback

**Files:**
- Create: `backend/app/sim/geo.py`, `backend/app/sim/snapshot.py`, `backend/tests/__init__.py` (empty), `backend/tests/helpers.py`
- Test: `backend/tests/test_snapshot.py`

**Interfaces:**
- Consumes: `config.half_width_deg`, `config.round_centre`, `config.GRID_STEP_DEG`, `config.USE_TIDE`.
- Produces:
  - `geo.M_PER_DEG_LAT = 110_540.0`, `geo.M_PER_DEG_LON_EQUATOR = 111_320.0`, `geo.haversine_m(lon1, lat1, lon2, lat2) -> float`.
  - `snapshot.SnapshotKey(centre_lon, centre_lat, half_width_deg, slice_time, n_slices=1)` frozen dataclass (hashable).
  - `snapshot.key_for(lon: float, lat: float, duration_days: int, slice_time: datetime) -> SnapshotKey`.
  - `snapshot.box_bounds(key) -> tuple[float, float, float, float]` as `(west, south, east, north)`.
  - `snapshot.Field` dataclass: `lon` (nx,), `lat` (ny,), `u` and `v` (nt, ny, nx) float32 with NaN on land, `slice_time`, `source`, `snapshot_id: str`, `components: dict[str, np.ndarray]`. Methods `contains(lon, lat) -> bool`, `is_land(lon, lat) -> bool`, `sample(lon, lat, t_seconds=0.0) -> tuple[float, float]`.
  - `snapshot.COMPONENT_NAMES = ("uo", "vo", "utide", "vtide", "ustokes", "vstokes")`.
  - `snapshot.build_field(lon, lat, components, slice_time, source, snapshot_id=None) -> Field`.
  - `snapshot.synthetic_field(key: SnapshotKey) -> Field`.
  - `tests.helpers.uniform_field(u=0.0, v=0.0, lon0=0.0, lat0=0.0, size_deg=2.0, land_from_lon=None) -> Field` and `tests.helpers.T0` (a UTC datetime).

- [ ] **Step 1: Write the test helper and failing tests**

Create empty `backend/tests/__init__.py`.

Create `backend/tests/helpers.py`:

```python
from datetime import datetime, timezone

import numpy as np

from app import config
from app.sim.snapshot import Field

T0 = datetime(2026, 10, 3, 18, tzinfo=timezone.utc)


def uniform_field(u=0.0, v=0.0, lon0=0.0, lat0=0.0, size_deg=2.0, land_from_lon=None) -> Field:
    """A square box of constant current. Cells at or east of land_from_lon are land."""
    step = config.GRID_STEP_DEG
    n = int(round(size_deg / step)) + 1
    lon = lon0 + np.arange(n) * step
    lat = lat0 + np.arange(n) * step
    uu = np.full((1, n, n), u, dtype="float32")
    vv = np.full((1, n, n), v, dtype="float32")
    if land_from_lon is not None:
        land = lon >= land_from_lon
        uu[:, :, land] = np.nan
        vv[:, :, land] = np.nan
    return Field(lon=lon, lat=lat, u=uu, v=vv, slice_time=T0, source="synthetic")
```

Create `backend/tests/test_snapshot.py`:

```python
import math

import numpy as np
import pytest

from app import config
from app.sim import geo
from app.sim.snapshot import (
    COMPONENT_NAMES, SnapshotKey, box_bounds, build_field, key_for, synthetic_field,
)
from tests.helpers import T0, uniform_field

STEP = config.GRID_STEP_DEG


def test_haversine_one_degree_of_latitude():
    assert geo.haversine_m(0.0, 0.0, 0.0, 1.0) == pytest.approx(111_195, rel=1e-3)


def test_sample_uniform_field():
    f = uniform_field(u=0.5, v=-0.2)
    assert f.sample(1.0, 1.0) == pytest.approx((0.5, -0.2))


def test_sample_is_bilinear_between_cells():
    f = uniform_field()
    n = f.lon.size
    f.u[0] = np.arange(n, dtype="float32")[None, :]  # u equals the column index
    u, _ = f.sample(f.lon[0] + 2.5 * STEP, 1.0)
    assert u == pytest.approx(2.5, abs=1e-4)


def test_sample_ignores_time_when_single_slice():
    f = uniform_field(u=0.3)
    assert f.sample(1.0, 1.0, t_seconds=10 * 86400)[0] == pytest.approx(0.3)


def test_is_land_and_contains():
    f = uniform_field(u=0.5, land_from_lon=1.5)
    assert f.is_land(1.8, 1.0) is True
    assert f.is_land(0.5, 1.0) is False
    assert f.contains(0.5, 1.0) is True
    assert f.contains(2.5, 1.0) is False
    assert f.contains(0.5, -0.1) is False


def test_sample_next_to_land_is_never_nan():
    # Review Focus 5: land corners count as zero velocity.
    # 1.49 is deliberately off-grid so the cell at 1.5 is land despite float rounding.
    f = uniform_field(u=0.5, v=0.5, land_from_lon=1.49)
    u, v = f.sample(1.5 - STEP * 0.4, 1.0)  # 60% of the way from a water cell to a land cell
    assert not math.isnan(u) and not math.isnan(v)
    assert u == pytest.approx(0.2, abs=0.01)


def test_key_for_rounds_centre_and_sizes_box():
    key = key_for(-125.3, 48.9, 7, T0)
    assert key == SnapshotKey(-125.5, 49.0, 4.0, T0, 1)
    assert box_bounds(key) == (-129.5, 45.0, -121.5, 53.0)


def test_box_is_clamped_at_antimeridian_and_pole():
    # Review Focus 4: no wrapping; the box is cut at the edge of the map.
    west, south, east, north = box_bounds(key_for(179.9, 0.0, 7, T0))
    assert (west, east) == (176.0, 180.0)
    west, south, east, north = box_bounds(key_for(0.0, 89.8, 7, T0))
    assert (south, north) == (86.0, 89.0)


def test_synthetic_field_covers_box_and_moves_water():
    key = key_for(10.2, -20.1, 1, T0)
    f = synthetic_field(key)
    west, south, east, north = box_bounds(key)
    assert f.source == "synthetic"
    assert f.u.shape == (1, f.lat.size, f.lon.size)
    assert f.lon[0] == pytest.approx(west) and f.lon[-1] == pytest.approx(east, abs=STEP)
    assert not np.isnan(f.u).any()
    u, v = f.sample(10.2, -20.1)
    assert math.hypot(u, v) > 0.05


def test_build_field_sums_circulation_and_waves_but_not_tide():
    shape = (1, 3, 3)
    comps = {name: np.zeros(shape, dtype="float32") for name in COMPONENT_NAMES}
    comps["uo"][:] = 0.2
    comps["ustokes"][:] = 0.05
    comps["utide"][:] = 1.0
    comps["uo"][0, 0, 0] = np.nan  # one land cell
    lon = np.array([0.0, STEP, 2 * STEP])
    f = build_field(lon, lon.copy(), comps, T0, "copernicus")
    assert f.u[0, 1, 1] == pytest.approx(0.25)
    assert np.isnan(f.u[0, 0, 0]) and np.isnan(f.v[0, 0, 0])
    assert f.source == "copernicus"
    assert set(f.components) == set(COMPONENT_NAMES)


def test_build_field_flips_descending_latitude():
    shape = (1, 2, 2)
    comps = {name: np.zeros(shape, dtype="float32") for name in COMPONENT_NAMES}
    comps["uo"][0, 0, :] = 1.0  # first row belongs to the northern latitude
    f = build_field(np.array([0.0, STEP]), np.array([STEP, 0.0]), comps, T0, "copernicus")
    assert f.lat[0] < f.lat[1]
    assert f.u[0, 1, 0] == pytest.approx(1.0)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_snapshot.py -q`
Expected: collection error, `ModuleNotFoundError: No module named 'app.sim.snapshot'`.

- [ ] **Step 3: Implement geo and snapshot**

Create `backend/app/sim/geo.py`:

```python
import math

M_PER_DEG_LAT = 110_540.0
M_PER_DEG_LON_EQUATOR = 111_320.0
EARTH_RADIUS_M = 6_371_000.0


def haversine_m(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    """Great-circle distance in metres."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(a))
```

Create `backend/app/sim/snapshot.py`:

```python
import math
import uuid
from dataclasses import dataclass, field
from datetime import datetime

import numpy as np

from .. import config

COMPONENT_NAMES = ("uo", "vo", "utide", "vtide", "ustokes", "vstokes")


@dataclass(frozen=True)
class SnapshotKey:
    centre_lon: float
    centre_lat: float
    half_width_deg: float
    slice_time: datetime
    n_slices: int = 1


def key_for(lon: float, lat: float, duration_days: int, slice_time: datetime) -> SnapshotKey:
    return SnapshotKey(
        config.round_centre(lon),
        config.round_centre(lat),
        config.half_width_deg(duration_days),
        slice_time,
        1,
    )


def box_bounds(key: SnapshotKey) -> tuple[float, float, float, float]:
    """(west, south, east, north), clamped to the map. No antimeridian wrapping."""
    hw = key.half_width_deg
    return (
        max(-180.0, key.centre_lon - hw),
        max(-89.0, key.centre_lat - hw),
        min(180.0, key.centre_lon + hw),
        min(89.0, key.centre_lat + hw),
    )


@dataclass
class Field:
    """A regular lon/lat box of currents. u and v are (nt, ny, nx), NaN on land."""
    lon: np.ndarray
    lat: np.ndarray
    u: np.ndarray
    v: np.ndarray
    slice_time: datetime
    source: str
    snapshot_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    components: dict = field(default_factory=dict)

    def contains(self, lon: float, lat: float) -> bool:
        return bool(self.lon[0] <= lon <= self.lon[-1] and self.lat[0] <= lat <= self.lat[-1])

    def _frac(self, lon: float, lat: float) -> tuple[float, float]:
        fx = (lon - self.lon[0]) / (self.lon[1] - self.lon[0])
        fy = (lat - self.lat[0]) / (self.lat[1] - self.lat[0])
        return fx, fy

    def is_land(self, lon: float, lat: float) -> bool:
        fx, fy = self._frac(lon, lat)
        i = min(max(math.floor(fx + 0.5), 0), self.lon.size - 1)
        j = min(max(math.floor(fy + 0.5), 0), self.lat.size - 1)
        return bool(np.isnan(self.u[0, j, i]))

    def sample(self, lon: float, lat: float, t_seconds: float = 0.0) -> tuple[float, float]:
        """Velocity in m/s: bilinear in space, nearest slice in time, land corners = 0."""
        k = min(int(t_seconds // 3600), self.u.shape[0] - 1)
        fx, fy = self._frac(lon, lat)
        i0 = min(max(math.floor(fx), 0), self.lon.size - 2)
        j0 = min(max(math.floor(fy), 0), self.lat.size - 2)
        tx = min(max(fx - i0, 0.0), 1.0)
        ty = min(max(fy - j0, 0.0), 1.0)

        def interp(a: np.ndarray) -> float:
            c = np.nan_to_num(a[k, j0:j0 + 2, i0:i0 + 2], nan=0.0)
            south = c[0, 0] * (1 - tx) + c[0, 1] * tx
            north = c[1, 0] * (1 - tx) + c[1, 1] * tx
            return float(south * (1 - ty) + north * ty)

        return interp(self.u), interp(self.v)


def build_field(lon, lat, components: dict, slice_time: datetime, source: str,
                snapshot_id: str | None = None) -> Field:
    """Combine raw components into total u/v. Land is where uo is NaN."""
    lon = np.asarray(lon, dtype="float64")
    lat = np.asarray(lat, dtype="float64")
    comps = {name: np.asarray(components[name], dtype="float32") for name in COMPONENT_NAMES}
    if lat[0] > lat[-1]:
        lat = lat[::-1].copy()
        comps = {name: a[:, ::-1, :].copy() for name, a in comps.items()}
    land = np.isnan(comps["uo"])

    def clean(name: str) -> np.ndarray:
        return np.nan_to_num(comps[name], nan=0.0)

    u = clean("uo") + clean("ustokes")
    v = clean("vo") + clean("vstokes")
    if config.USE_TIDE:
        u = u + clean("utide")
        v = v + clean("vtide")
    u[land] = np.nan
    v[land] = np.nan
    extra = {"snapshot_id": snapshot_id} if snapshot_id else {}
    return Field(lon=lon, lat=lat, u=u, v=v, slice_time=slice_time, source=source,
                 components=comps, **extra)


def synthetic_field(key: SnapshotKey) -> Field:
    """A gentle rotating gyre plus an eastward drift. Used when Copernicus is unreachable."""
    west, south, east, north = box_bounds(key)
    step = config.GRID_STEP_DEG
    lon = west + np.arange(int(round((east - west) / step)) + 1) * step
    lat = south + np.arange(int(round((north - south) / step)) + 1) * step
    grid_lon, grid_lat = np.meshgrid(lon, lat)
    hw = key.half_width_deg
    zeros = np.zeros((1, lat.size, lon.size), dtype="float32")
    comps = {name: zeros.copy() for name in COMPONENT_NAMES}
    comps["uo"][0] = 0.1 - 0.3 * (grid_lat - key.centre_lat) / hw
    comps["vo"][0] = 0.3 * (grid_lon - key.centre_lon) / hw
    return build_field(lon, lat, comps, key.slice_time, "synthetic")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_snapshot.py -q`
Expected: 11 passed.

- [ ] **Step 5: Commit**

```bash
git add app/sim/geo.py app/sim/snapshot.py tests/__init__.py tests/helpers.py tests/test_snapshot.py
git commit -m "feat(backend): current field sampling, snapshot keys and synthetic fallback"
```

---

### Task 3: Simulation engine and status machine

**Files:**
- Create: `backend/app/sim/engine.py`
- Test: `backend/tests/test_engine.py`

**Interfaces:**
- Consumes: `Field.contains`, `Field.is_land`, `Field.sample`, `geo.haversine_m`, `geo.M_PER_DEG_LAT`, `geo.M_PER_DEG_LON_EQUATOR`, `config.DT_SECONDS`, `config.SAMPLE_INTERVAL_SECONDS`, `config.DRIFT_FACTOR`, `tests.helpers.uniform_field`.
- Produces:
  - `engine.Litter(id: str, type: str, lon: float, lat: float)`
  - `engine.Collector(id: str, lon: float, lat: float, radius_m: float)`
  - `engine.ItemResult(id, type, final_status, captured_by, status_changed_at_seconds, samples)` where `samples` is `list[tuple[int, float, float, str]]` as `(time_seconds, lon, lat, status)`.
  - `engine.RunResult(items: list[ItemResult], captured_counts: dict[str, int], summary: dict[str, int], total_seconds: int)`; `summary` always has the four status keys.
  - `engine.run(litter: list[Litter], collectors: list[Collector], duration_days: int, fields: dict[str, Field]) -> RunResult` where `fields` maps litter id to its `Field`.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_engine.py`:

```python
import math

import pytest

from app.sim.engine import Collector, Litter, run
from tests.helpers import uniform_field


def one(item, field, collectors=(), days=1):
    return run([item], list(collectors), days, {item.id: field})


def test_uniform_eastward_current_moves_item_the_expected_distance():
    result = one(Litter("a", "bottle", 0.5, 1.0), uniform_field(u=0.5))
    item = result.items[0]
    expected_lon = 0.5 + 0.5 * 86400 / (111_320 * math.cos(math.radians(1.0)))  # about 43 km
    t, lon, lat, status = item.samples[-1]
    assert t == 86400 and status == "floating"
    assert lon == pytest.approx(expected_lon, rel=1e-3)
    assert lat == pytest.approx(1.0)
    assert [s[0] for s in item.samples] == list(range(0, 86401, 3600))
    assert result.summary == {"floating": 1, "captured": 0, "beached": 0, "outside": 0}
    assert result.total_seconds == 86400


def test_item_beaches_on_land_and_freezes():
    field = uniform_field(u=0.5, land_from_lon=0.79)  # land cells start at lon 0.8333
    result = one(Litter("a", "bag", 0.5, 1.0), field, days=2)
    item = result.items[0]
    assert item.final_status == "beached"
    assert 0 < item.status_changed_at_seconds < 2 * 86400
    frozen = [s for s in item.samples if s[0] >= item.status_changed_at_seconds]
    assert len(frozen) > 1
    assert all(s[3] == "beached" for s in frozen)
    assert len({(s[1], s[2]) for s in frozen}) == 1
    assert result.summary["beached"] == 1


def test_item_is_captured_once_by_collector_in_its_path():
    collector = Collector("c1", 0.7, 1.0, 10_000.0)
    result = one(Litter("a", "foam", 0.5, 1.0), uniform_field(u=0.5), [collector])
    item = result.items[0]
    assert item.final_status == "captured"
    assert item.captured_by == "c1"
    assert result.captured_counts == {"c1": 1}
    assert result.summary == {"floating": 0, "captured": 1, "beached": 0, "outside": 0}
    frozen = [s for s in item.samples if s[0] >= item.status_changed_at_seconds]
    assert len({(s[1], s[2]) for s in frozen}) == 1


def test_item_dropped_inside_collector_is_captured_at_second_zero():
    # Review Focus 2.
    collector = Collector("c1", 0.5, 1.0, 10_000.0)
    result = one(Litter("a", "bottle", 0.51, 1.0), uniform_field(u=0.5), [collector])
    item = result.items[0]
    assert item.samples[0] == (0, 0.51, 1.0, "captured")
    assert item.status_changed_at_seconds == 0
    assert item.samples[-1][1:3] == (0.51, 1.0)
    assert result.captured_counts == {"c1": 1}


def test_item_leaving_the_box_becomes_outside():
    result = one(Litter("a", "bottle", 1.0, 1.9), uniform_field(v=0.5))
    item = result.items[0]
    assert item.final_status == "outside"
    assert item.status_changed_at_seconds < 86400


def test_all_items_share_one_timeline_but_follow_their_own_field():
    east = Litter("east", "bottle", 0.5, 1.0)
    north = Litter("north", "bag", 20.5, 31.0)
    fields = {"east": uniform_field(u=0.2), "north": uniform_field(v=0.2, lon0=20.0, lat0=30.0)}
    result = run([east, north], [], 1, fields)
    a, b = result.items
    assert [s[0] for s in a.samples] == [s[0] for s in b.samples]
    assert a.samples[-1][1] > 0.5 and a.samples[-1][2] == pytest.approx(1.0)
    assert b.samples[-1][2] > 31.0 and b.samples[-1][1] == pytest.approx(20.5)


def test_run_without_litter_returns_zero_counts():
    result = run([], [Collector("c1", 0.0, 0.0, 10_000.0)], 3, {})
    assert result.items == []
    assert result.summary == {"floating": 0, "captured": 0, "beached": 0, "outside": 0}
    assert result.captured_counts == {"c1": 0}
    assert result.total_seconds == 3 * 86400
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_engine.py -q`
Expected: collection error, `ModuleNotFoundError: No module named 'app.sim.engine'`.

- [ ] **Step 3: Implement the engine**

Create `backend/app/sim/engine.py`:

```python
import math
from dataclasses import dataclass

from .. import config
from . import geo
from .snapshot import Field

STATUSES = ("floating", "captured", "beached", "outside")


@dataclass
class Litter:
    id: str
    type: str
    lon: float
    lat: float


@dataclass
class Collector:
    id: str
    lon: float
    lat: float
    radius_m: float


@dataclass
class ItemResult:
    id: str
    type: str
    final_status: str
    captured_by: str | None
    status_changed_at_seconds: int | None
    samples: list  # (time_seconds, lon, lat, status)


@dataclass
class RunResult:
    items: list
    captured_counts: dict
    summary: dict
    total_seconds: int


def _classify(lon: float, lat: float, fld: Field, collectors: list) -> tuple:
    """Outside is checked first so an out-of-box point is never read as a clipped land cell."""
    if not fld.contains(lon, lat):
        return "outside", None
    if fld.is_land(lon, lat):
        return "beached", None
    for c in collectors:
        if geo.haversine_m(lon, lat, c.lon, c.lat) <= c.radius_m:
            return "captured", c.id
    return "floating", None


def run(litter: list, collectors: list, duration_days: int, fields: dict) -> RunResult:
    """Advect every item for the same duration, each through its own field. Deterministic."""
    dt = config.DT_SECONDS
    total_seconds = duration_days * 86400
    steps = total_seconds // dt
    sample_every = config.SAMPLE_INTERVAL_SECONDS // dt

    captured_counts = {c.id: 0 for c in collectors}
    summary = {status: 0 for status in STATUSES}
    items = []

    for item in litter:
        fld = fields[item.id]
        factor = config.DRIFT_FACTOR[item.type]
        lon, lat = item.lon, item.lat
        status, captured_by = _classify(lon, lat, fld, collectors)
        changed_at = 0 if status != "floating" else None
        samples = [(0, lon, lat, status)]

        for step in range(1, steps + 1):
            t = step * dt
            if status == "floating":
                u, v = fld.sample(lon, lat, t - dt)
                cos_lat = max(math.cos(math.radians(lat)), 0.01)
                lon = lon + u * factor * dt / (geo.M_PER_DEG_LON_EQUATOR * cos_lat)
                lat = lat + v * factor * dt / geo.M_PER_DEG_LAT
                status, captured_by = _classify(lon, lat, fld, collectors)
                if status != "floating":
                    changed_at = t
            if step % sample_every == 0:
                samples.append((t, lon, lat, status))

        if captured_by is not None:
            captured_counts[captured_by] += 1
        summary[status] += 1
        items.append(ItemResult(item.id, item.type, status, captured_by, changed_at, samples))

    return RunResult(items, captured_counts, summary, total_seconds)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_engine.py -q`
Expected: 7 passed.

- [ ] **Step 5: Run the whole suite and commit**

Run: `python -m pytest -q`
Expected: 37 passed.

```bash
git add app/sim/engine.py tests/test_engine.py
git commit -m "feat(backend): drift engine with beached, captured and outside states"
```

Known cost, accepted for the MVP: the loop is plain Python, about 30 microseconds per step per item. The worst case of 50 items for 30 days is roughly 6 seconds; a typical run of 5 items for 7 days is well under half a second. Vectorising across items is the upgrade if this ever matters.

---

### Task 4: Service layer and the simulate, compare and currents endpoints

After this task the frontend can integrate for real. Data is synthetic until Task 5.

**Files:**
- Create: `backend/app/service.py`
- Modify: `backend/app/routes.py` (add three endpoints and the on-land error response)
- Test: `backend/tests/test_api.py`

**Interfaces:**
- Consumes: everything produced by Tasks 1 to 3.
- Produces:
  - `service.OnLandError(placement_id: str)` with attribute `.placement_id`.
  - `service.current_slice_time() -> datetime` (UTC now floored to the hour).
  - `service.resolve_field(key: SnapshotKey) -> Field`. **This is the seam.** Task 4 returns a synthetic field; Tasks 5 and 6 replace its body. Tests monkeypatch it.
  - `service.resolve_fields(req: SimulateRequest, slice_time: datetime) -> dict[str, Field]` (raises `OnLandError`).
  - `service.persist(response, req, fields, slice_time, parent_run_id) -> bool`. Task 4 returns `False`; Task 6 replaces its body.
  - `service.simulate(req, *, use_collectors=True, fields=None, slice_time=None, parent_run_id=None) -> SimulateResponse`.
  - `service.compare(req) -> CompareResponse`.
  - `service.currents(lon: float, lat: float, duration_days: int) -> CurrentsResponse`.
  - `service.snapshot_info(fld: Field) -> SnapshotInfo`.
  - HTTP: `POST /api/simulate`, `POST /api/compare`, `GET /api/currents?lon=&lat=&durationDays=`.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_api.py`:

```python
import pytest
from fastapi.testclient import TestClient

from app import service
from app.main import app
from tests.helpers import uniform_field

client = TestClient(app)

BOTTLE = {"id": "bottle-1", "type": "bottle", "coordinates": [0.5, 1.0]}
COLLECTOR = {"id": "collector-1", "type": "collector", "coordinates": [0.7, 1.0]}


@pytest.fixture
def eastward(monkeypatch):
    fld = uniform_field(u=0.5)
    monkeypatch.setattr(service, "resolve_field", lambda key: fld)
    return fld


def test_simulate_returns_the_frontend_trajectory_shape():
    body = {"placements": [{"id": "bottle-1", "type": "bottle", "coordinates": [10.2, -20.1]}],
            "durationDays": 2}
    response = client.post("/api/simulate", json=body)
    assert response.status_code == 200
    data = response.json()
    assert data["durationDays"] == 2
    assert data["totalSeconds"] == 172800
    assert data["sampleIntervalSeconds"] == 3600
    trajectory = data["trajectories"][0]
    assert trajectory["id"] == "bottle-1" and trajectory["type"] == "bottle"
    assert len(trajectory["samples"]) == 49
    assert trajectory["samples"][0] == {"timeSeconds": 0, "coordinates": [10.2, -20.1], "status": "floating"}
    assert sum(data["summary"].values()) == 1
    assert data["snapshots"][0]["source"] == "synthetic"
    assert data["persisted"] is False
    assert data["attribution"]["limitations"]


@pytest.mark.parametrize("placements", [[], [COLLECTOR]])
def test_simulate_with_no_litter_returns_empty_result(placements):
    # Review Focus 1.
    response = client.post("/api/simulate", json={"placements": placements})
    assert response.status_code == 200
    data = response.json()
    assert data["trajectories"] == []
    assert data["summary"] == {"floating": 0, "captured": 0, "beached": 0, "outside": 0}
    assert data["snapshots"] == []


def test_drop_on_land_is_rejected_with_code(monkeypatch):
    fld = uniform_field(u=0.1, land_from_lon=1.49)
    monkeypatch.setattr(service, "resolve_field", lambda key: fld)
    body = {"placements": [{"id": "bag-9", "type": "bag", "coordinates": [1.8, 1.0]}]}
    response = client.post("/api/simulate", json=body)
    assert response.status_code == 422
    assert response.json() == {
        "code": "on_land",
        "message": "That spot is land. Try the water!",
        "placementId": "bag-9",
    }


def test_invalid_duration_is_rejected():
    response = client.post("/api/simulate", json={"placements": [BOTTLE], "durationDays": 31})
    assert response.status_code == 422


def test_simulate_is_deterministic(eastward):
    body = {"placements": [BOTTLE], "durationDays": 1}
    first = client.post("/api/simulate", json=body).json()
    second = client.post("/api/simulate", json=body).json()
    assert first["trajectories"] == second["trajectories"]
    assert first["runId"] != second["runId"]


def test_compare_runs_without_and_with_collectors_on_the_same_snapshot(eastward):
    body = {"placements": [BOTTLE, COLLECTOR], "durationDays": 1}
    response = client.post("/api/compare", json=body)
    assert response.status_code == 200
    data = response.json()
    assert data["without"]["summary"]["floating"] == 1
    assert data["without"]["collectors"] == []
    assert data["with"]["summary"]["captured"] == 1
    assert data["with"]["collectors"][0] == {
        "id": "collector-1", "coordinates": [0.7, 1.0], "radiusM": 10000.0, "capturedCount": 1,
    }
    assert data["delta"] == {"floating": -1, "captured": 1, "beached": 0, "outside": 0}
    assert data["without"]["snapshots"] == data["with"]["snapshots"]
    assert data["with"]["items"][0]["capturedBy"] == "collector-1"


def test_currents_returns_downsampled_arrows():
    response = client.get("/api/currents", params={"lon": 10.2, "lat": -20.1, "durationDays": 1})
    assert response.status_code == 200
    data = response.json()
    assert 0 < len(data["arrows"]) <= 400
    assert all(0.0 <= a["bearing"] < 360.0 for a in data["arrows"])
    assert data["bounds"][0] == pytest.approx([8.5, -21.5])
    assert data["bounds"][1] == pytest.approx([11.5, -18.5], abs=0.1)
    assert data["snapshot"]["source"] == "synthetic"


@pytest.mark.parametrize("u,v,bearing", [(0.5, 0.0, 90.0), (0.0, 0.5, 0.0), (-0.5, 0.0, 270.0)])
def test_arrow_bearing_is_degrees_clockwise_from_north(monkeypatch, u, v, bearing):
    fld = uniform_field(u=u, v=v)
    monkeypatch.setattr(service, "resolve_field", lambda key: fld)
    data = client.get("/api/currents", params={"lon": 1.0, "lat": 1.0}).json()
    assert data["arrows"][0]["bearing"] == pytest.approx(bearing)
    assert data["arrows"][0]["speed"] == pytest.approx(0.5)


def test_currents_rejects_out_of_range_coordinates():
    assert client.get("/api/currents", params={"lon": 200, "lat": 0}).status_code == 422
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_api.py -q`
Expected: `ImportError: cannot import name 'service' from 'app'`.

- [ ] **Step 3: Implement the service**

Create `backend/app/service.py`:

```python
import math
import uuid
from datetime import datetime, timezone

from . import config
from .schemas import (
    Arrow, Attribution, CollectorSummary, CompareResponse, CurrentsResponse, ItemSummary,
    ParticleTrajectory, SimulateRequest, SimulateResponse, SnapshotInfo, StatusCounts,
    TrajectorySample,
)
from .sim import engine
from .sim.snapshot import Field, SnapshotKey, key_for, synthetic_field

MAX_ARROWS_PER_SIDE = 16


class OnLandError(Exception):
    def __init__(self, placement_id: str):
        super().__init__(placement_id)
        self.placement_id = placement_id


def attribution() -> Attribution:
    return Attribution(source=config.ATTRIBUTION_SOURCE, dataset=config.DATASET_ID,
                       limitations=config.LIMITATIONS)


def current_slice_time() -> datetime:
    return datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)


def resolve_field(key: SnapshotKey) -> Field:
    """Return the currents for one box. Task 4: synthetic only."""
    return synthetic_field(key)


def resolve_fields(req: SimulateRequest, slice_time: datetime) -> dict:
    """One field per litter placement; placements that share a box share a field."""
    by_key: dict = {}
    fields: dict = {}
    for p in req.placements:
        if p.type == "collector":
            continue
        lon, lat = p.coordinates
        key = key_for(lon, lat, req.duration_days, slice_time)
        if key not in by_key:
            by_key[key] = resolve_field(key)
        fld = by_key[key]
        if fld.contains(lon, lat) and fld.is_land(lon, lat):
            raise OnLandError(p.id)
        fields[p.id] = fld
    return fields


def snapshot_info(fld: Field) -> SnapshotInfo:
    return SnapshotInfo(snapshot_id=fld.snapshot_id, source=fld.source,
                        slice_time=fld.slice_time, n_slices=int(fld.u.shape[0]))


def persist(response: SimulateResponse, req: SimulateRequest, fields: dict,
            slice_time: datetime, parent_run_id: str | None) -> bool:
    """Store the run. Task 4: no database yet."""
    return False


def simulate(req: SimulateRequest, *, use_collectors: bool = True, fields: dict | None = None,
             slice_time: datetime | None = None, parent_run_id: str | None = None) -> SimulateResponse:
    slice_time = slice_time or current_slice_time()
    if fields is None:
        fields = resolve_fields(req, slice_time)

    litter = [engine.Litter(p.id, p.type, p.coordinates[0], p.coordinates[1])
              for p in req.placements if p.type != "collector"]
    collectors = [engine.Collector(p.id, p.coordinates[0], p.coordinates[1], req.collector_radius_m)
                  for p in req.placements if p.type == "collector"] if use_collectors else []

    result = engine.run(litter, collectors, req.duration_days, fields)

    unique_fields = {fld.snapshot_id: fld for fld in fields.values()}
    response = SimulateResponse(
        run_id=str(uuid.uuid4()),
        duration_days=req.duration_days,
        total_seconds=result.total_seconds,
        sample_interval_seconds=config.SAMPLE_INTERVAL_SECONDS,
        trajectories=[
            ParticleTrajectory(id=item.id, type=item.type, samples=[
                TrajectorySample(time_seconds=t, coordinates=(round(lon, 5), round(lat, 5)), status=status)
                for t, lon, lat, status in item.samples
            ]) for item in result.items
        ],
        items=[ItemSummary(id=item.id, type=item.type, final_status=item.final_status,
                           captured_by=item.captured_by,
                           status_changed_at_seconds=item.status_changed_at_seconds)
               for item in result.items],
        collectors=[CollectorSummary(id=c.id, coordinates=(c.lon, c.lat), radius_m=c.radius_m,
                                     captured_count=result.captured_counts[c.id])
                    for c in collectors],
        summary=StatusCounts(**result.summary),
        snapshots=[snapshot_info(fld) for fld in unique_fields.values()],
        attribution=attribution(),
        persisted=False,
    )
    response.persisted = persist(response, req, fields, slice_time, parent_run_id)
    return response


def compare(req: SimulateRequest) -> CompareResponse:
    """Same placements, same snapshots: once ignoring collectors, once honouring them."""
    slice_time = current_slice_time()
    fields = resolve_fields(req, slice_time)
    without = simulate(req, use_collectors=False, fields=fields, slice_time=slice_time)
    with_ = simulate(req, use_collectors=True, fields=fields, slice_time=slice_time,
                     parent_run_id=without.run_id)
    delta = StatusCounts(**{
        status: getattr(with_.summary, status) - getattr(without.summary, status)
        for status in engine.STATUSES
    })
    return CompareResponse(without=without, with_=with_, delta=delta)


def currents(lon: float, lat: float, duration_days: int) -> CurrentsResponse:
    fld = resolve_field(key_for(lon, lat, duration_days, current_slice_time()))
    stride = max(1, math.ceil(max(fld.lon.size, fld.lat.size) / MAX_ARROWS_PER_SIDE))
    arrows = []
    for j in range(0, fld.lat.size, stride):
        for i in range(0, fld.lon.size, stride):
            u, v = float(fld.u[0, j, i]), float(fld.v[0, j, i])
            if math.isnan(u) or math.isnan(v):
                continue
            arrows.append(Arrow(
                coordinates=(round(float(fld.lon[i]), 4), round(float(fld.lat[j]), 4)),
                u=round(u, 4), v=round(v, 4),
                speed=round(math.hypot(u, v), 4),
                bearing=round(math.degrees(math.atan2(u, v)) % 360.0, 1) % 360.0,
            ))
    return CurrentsResponse(
        snapshot=snapshot_info(fld),
        bounds=((float(fld.lon[0]), float(fld.lat[0])), (float(fld.lon[-1]), float(fld.lat[-1]))),
        arrows=arrows,
    )
```

- [ ] **Step 4: Add the endpoints**

Replace `backend/app/routes.py` with:

```python
from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse

from . import config, service
from .schemas import (
    CompareResponse, CurrentsResponse, MetaResponse, SimulateRequest, SimulateResponse,
)

router = APIRouter()

# Kept as a module-level name because scripts/make_fixture.py imports it from here.
attribution = service.attribution


def on_land_response(err: service.OnLandError) -> JSONResponse:
    return JSONResponse(status_code=422, content={
        "code": "on_land",
        "message": "That spot is land. Try the water!",
        "placementId": err.placement_id,
    })


@router.get("/health")
def health() -> dict:
    return {"status": "ok", "db": False}


@router.get("/meta", response_model=MetaResponse)
def meta() -> MetaResponse:
    return MetaResponse(
        min_duration_days=config.MIN_DAYS,
        max_duration_days=config.MAX_DAYS,
        default_duration_days=config.DEFAULT_DAYS,
        sample_interval_seconds=config.SAMPLE_INTERVAL_SECONDS,
        default_collector_radius_m=config.DEFAULT_COLLECTOR_RADIUS_M,
        litter_types=list(config.DRIFT_FACTOR),
        attribution=service.attribution(),
    )


@router.get("/currents", response_model=CurrentsResponse)
def currents(
    lon: float = Query(ge=-180, le=180),
    lat: float = Query(ge=-90, le=90),
    duration_days: int = Query(config.DEFAULT_DAYS, alias="durationDays",
                               ge=config.MIN_DAYS, le=config.MAX_DAYS),
):
    return service.currents(lon, lat, duration_days)


@router.post("/simulate", response_model=SimulateResponse)
def simulate(req: SimulateRequest):
    try:
        return service.simulate(req)
    except service.OnLandError as err:
        return on_land_response(err)


@router.post("/compare", response_model=CompareResponse)
def compare(req: SimulateRequest):
    try:
        return service.compare(req)
    except service.OnLandError as err:
        return on_land_response(err)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest -q`
Expected: 49 passed.

- [ ] **Step 6: Try it by hand**

Run: `python -m uvicorn app.main:app --port 8000 --reload`, then in another terminal:

```bash
curl -s -X POST http://localhost:8000/api/compare -H "Content-Type: application/json" \
  -d '{"placements":[{"id":"bottle-1","type":"bottle","coordinates":[-140.2,32.1]},{"id":"collector-1","type":"collector","coordinates":[-140.0,32.1]}],"durationDays":7}' \
  | python -c "import sys,json; d=json.load(sys.stdin); print(d['delta'], d['with']['snapshots'])"
```

Expected: a delta object and one snapshot with `"source": "synthetic"`.

- [ ] **Step 7: Commit and tell Person 1**

```bash
git add app/service.py app/routes.py tests/test_api.py
git commit -m "feat(backend): simulate, compare and currents endpoints on synthetic currents"
```

Tell Person 1 the backend runs on `http://localhost:8000` and that `VITE_API_BASE_URL` should point there. `POST /api/simulate` returns `trajectories` in their `ParticleTrajectory[]` type.

---

### Task 5: Real currents from Copernicus Marine, with timeout and fallback

**Prerequisite (human):** `backend/.env` contains `COPERNICUSMARINE_SERVICE_USERNAME` and `COPERNICUSMARINE_SERVICE_PASSWORD`.

**Files:**
- Create: `backend/app/sim/copernicus.py`, `backend/scripts/smoke_copernicus.py`
- Modify: `backend/requirements.txt` (add one line), `backend/app/service.py` (replace `resolve_field`, add cache and timeout), `backend/tests/conftest.py` (block the network in every test)
- Test: `backend/tests/test_copernicus.py`

**Interfaces:**
- Consumes: `SnapshotKey`, `box_bounds`, `build_field`, `COMPONENT_NAMES`, `synthetic_field`, `config.DATASET_ID`, `config.FETCH_TIMEOUT_S`.
- Produces:
  - `copernicus.fetch_field(key: SnapshotKey) -> Field` (network; raises on any failure).
  - `copernicus.field_from_dataset(ds, key: SnapshotKey) -> Field` (pure; takes an xarray Dataset).
  - `service._memory: dict[SnapshotKey, Field]` (bounded in-process cache, real snapshots only).
  - `service.fetch_with_timeout(key) -> Field | None`.
  - `service.resolve_field(key)` now: memory, then Copernicus, then synthetic.

- [ ] **Step 1: Install the toolbox**

Append to `backend/requirements.txt`:

```
copernicusmarine>=2.0
```

Run: `pip install -r requirements.txt`
Expected: installs `copernicusmarine` and `xarray`. If the install fails on Python 3.13, recreate the venv with 3.12 (`py -3.12 -m venv .venv`), reinstall, and rerun the suite before continuing.

- [ ] **Step 2: Block the network in tests**

Replace `backend/tests/conftest.py` with:

```python
import os

import pytest

# Tests never touch a real database. Set before any app import;
# load_dotenv does not override variables that already exist.
os.environ["DATABASE_URL"] = ""


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    """No test may reach Copernicus. Fetches fail, so the service falls back to synthetic."""
    from app import service
    from app.sim import copernicus

    def refuse(key):
        raise RuntimeError("network disabled in tests")

    monkeypatch.setattr(copernicus, "fetch_field", refuse)
    service._memory.clear()
```

- [ ] **Step 3: Write the failing tests**

Create `backend/tests/test_copernicus.py`:

```python
import sys
import time
import types

import numpy as np
import pytest
import xarray as xr

from app import config, service
from app.sim import copernicus
from app.sim.copernicus import fetch_field as real_fetch_field  # captured before the autouse patch
from app.sim.snapshot import COMPONENT_NAMES, key_for
from tests.helpers import T0, uniform_field

KEY = key_for(10.2, -20.1, 1, T0)  # centre (10.0, -20.0), half-width 1.5


def fake_dataset() -> xr.Dataset:
    """Three hourly slices around T0, one depth level, latitude descending like some servers return."""
    times = np.array(["2026-10-03T17:00", "2026-10-03T18:00", "2026-10-03T19:00"], dtype="datetime64[ns]")
    lat = np.array([-19.0, -20.0, -21.0])
    lon = np.array([9.0, 10.0, 11.0])
    shape = (3, 1, 3, 3)
    data = {}
    for name in COMPONENT_NAMES:
        values = np.zeros(shape, dtype="float32")
        if name == "uo":
            values[0], values[1], values[2] = 0.1, 0.2, 0.3  # differs per time slice
            values[:, :, 0, 0] = np.nan                       # land at lat -19, lon 9
        if name == "ustokes":
            values[:] = 0.05
        if name == "utide":
            values[:] = 9.0
        data[name] = (("time", "depth", "latitude", "longitude"), values)
    return xr.Dataset(data, coords={"time": times, "depth": [0.49], "latitude": lat, "longitude": lon})


def test_field_from_dataset_picks_nearest_hour_and_combines_components():
    fld = copernicus.field_from_dataset(fake_dataset(), KEY)
    assert fld.source == "copernicus"
    assert fld.u.shape == (1, 3, 3)
    assert fld.lat[0] < fld.lat[-1]                    # flipped to ascending
    assert fld.u[0, 0, 1] == pytest.approx(0.25)       # 18:00 slice: uo 0.2 + stokes 0.05, tide ignored
    assert np.isnan(fld.u[0, 2, 0])                    # the land cell, now in the last row
    assert fld.slice_time == T0


def test_fetch_field_requests_the_box_and_dataset(monkeypatch):
    calls = {}

    def open_dataset(**kwargs):
        calls.update(kwargs)
        return fake_dataset()

    monkeypatch.setitem(sys.modules, "copernicusmarine", types.SimpleNamespace(open_dataset=open_dataset))
    fld = real_fetch_field(KEY)
    assert fld.source == "copernicus"
    assert calls["dataset_id"] == config.DATASET_ID
    assert calls["variables"] == list(COMPONENT_NAMES)
    assert (calls["minimum_longitude"], calls["maximum_longitude"]) == (8.5, 11.5)
    assert (calls["minimum_latitude"], calls["maximum_latitude"]) == (-21.5, -18.5)
    assert calls["start_datetime"] == "2026-10-03T17:00:00"
    assert calls["end_datetime"] == "2026-10-03T19:00:00"


def test_resolve_field_falls_back_to_synthetic_and_does_not_cache_it():
    fld = service.resolve_field(KEY)  # the autouse fixture makes the fetch fail
    assert fld.source == "synthetic"
    assert KEY not in service._memory


def test_resolve_field_caches_real_snapshots(monkeypatch):
    real = uniform_field(u=0.2)
    real.source = "copernicus"
    calls = []

    def fetch(key):
        calls.append(key)
        return real

    monkeypatch.setattr(copernicus, "fetch_field", fetch)
    assert service.resolve_field(KEY) is real
    assert service.resolve_field(KEY) is real
    assert len(calls) == 1


def test_slow_fetch_times_out_to_synthetic(monkeypatch):
    def slow(key):
        time.sleep(0.5)
        return uniform_field()

    monkeypatch.setattr(copernicus, "fetch_field", slow)
    monkeypatch.setattr(config, "FETCH_TIMEOUT_S", 0.05)
    started = time.monotonic()
    fld = service.resolve_field(KEY)
    assert fld.source == "synthetic"
    assert time.monotonic() - started < 0.4


def test_memory_cache_is_bounded(monkeypatch):
    monkeypatch.setattr(service, "MEMORY_CACHE_MAX", 2)

    def fetch(key):
        fld = uniform_field()
        fld.source = "copernicus"
        return fld

    monkeypatch.setattr(copernicus, "fetch_field", fetch)
    for lon in (0.0, 10.0, 20.0):
        service.resolve_field(key_for(lon, 0.0, 1, T0))
    assert len(service._memory) == 2
    assert key_for(0.0, 0.0, 1, T0) not in service._memory
```

- [ ] **Step 4: Run tests to verify they fail**

Run: `python -m pytest tests/test_copernicus.py -q`
Expected: `ModuleNotFoundError: No module named 'app.sim.copernicus'` (or an `AttributeError` on `service._memory` from the fixture).

- [ ] **Step 5: Implement the fetch**

Create `backend/app/sim/copernicus.py`:

```python
"""The only module that talks to Copernicus Marine."""
from datetime import timedelta

import numpy as np

from .. import config
from .snapshot import COMPONENT_NAMES, Field, SnapshotKey, box_bounds, build_field

TIME_FORMAT = "%Y-%m-%dT%H:%M:%S"


def field_from_dataset(ds, key: SnapshotKey) -> Field:
    """Turn an xarray Dataset covering the box into a single-slice Field."""
    if "depth" in ds.dims:
        ds = ds.isel(depth=0)
    target = np.datetime64(key.slice_time.replace(tzinfo=None))
    ds = ds.sel(time=target, method="nearest").load()
    components = {
        name: ds[name].transpose("latitude", "longitude").values[None, :, :]
        for name in COMPONENT_NAMES
    }
    return build_field(ds["longitude"].values, ds["latitude"].values, components,
                       key.slice_time, "copernicus")


def fetch_field(key: SnapshotKey) -> Field:
    """Download one box of surface currents. Credentials come from the environment."""
    import copernicusmarine  # lazy: heavy import, and unit tests replace it

    west, south, east, north = box_bounds(key)
    ds = copernicusmarine.open_dataset(
        dataset_id=config.DATASET_ID,
        variables=list(COMPONENT_NAMES),
        minimum_longitude=west,
        maximum_longitude=east,
        minimum_latitude=south,
        maximum_latitude=north,
        start_datetime=(key.slice_time - timedelta(hours=1)).strftime(TIME_FORMAT),
        end_datetime=(key.slice_time + timedelta(hours=1)).strftime(TIME_FORMAT),
    )
    return field_from_dataset(ds, key)
```

- [ ] **Step 6: Wire it into the service**

In `backend/app/service.py`, change the imports at the top to add:

```python
import logging
from concurrent.futures import ThreadPoolExecutor

from .sim import copernicus, engine
```

(remove the old `from .sim import engine` line), add below `MAX_ARROWS_PER_SIDE`:

```python
MEMORY_CACHE_MAX = 64

log = logging.getLogger("plasticpaths")
_memory: dict = {}  # SnapshotKey -> Field, real snapshots only
_fetch_pool = ThreadPoolExecutor(max_workers=4)
```

and replace the whole `resolve_field` function with:

```python
def fetch_with_timeout(key: SnapshotKey) -> Field | None:
    """Fetch from Copernicus within the time budget. Any failure returns None."""
    future = _fetch_pool.submit(copernicus.fetch_field, key)
    try:
        return future.result(timeout=config.FETCH_TIMEOUT_S)
    except Exception as err:  # includes the timeout
        log.warning("Copernicus fetch failed for %s: %r", key, err)
        return None


def remember(key: SnapshotKey, fld: Field) -> None:
    _memory[key] = fld
    while len(_memory) > MEMORY_CACHE_MAX:
        _memory.pop(next(iter(_memory)))  # drop the oldest entry


def resolve_field(key: SnapshotKey) -> Field:
    """Memory, then Copernicus, then a synthetic field. Synthetic fields are never cached,
    so the real source is retried on the next request."""
    if key in _memory:
        return _memory[key]
    fld = fetch_with_timeout(key)
    if fld is None:
        return synthetic_field(key)
    remember(key, fld)
    return fld
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `python -m pytest -q`
Expected: 55 passed.

- [ ] **Step 8: Smoke test against the real service**

Create `backend/scripts/smoke_copernicus.py`:

```python
"""Manual check that real currents arrive. Run from backend/:  python -m scripts.smoke_copernicus"""
import math
import time

import numpy as np

from app import service
from app.sim import copernicus
from app.sim.snapshot import key_for

POINTS = {"North Pacific": (-140.2, 32.1), "Bay of Bengal": (88.3, 15.2), "Off Vancouver Island": (-126.4, 48.6)}

for name, (lon, lat) in POINTS.items():
    key = key_for(lon, lat, 7, service.current_slice_time())
    started = time.monotonic()
    fld = copernicus.fetch_field(key)
    u, v = fld.sample(lon, lat)
    print(f"{name}: {time.monotonic() - started:.1f}s  grid {fld.u.shape}  "
          f"land {np.isnan(fld.u).mean():.0%}  speed {math.hypot(u, v):.2f} m/s")
```

Run: `python -m scripts.smoke_copernicus`
Expected: three lines, each a few seconds, grid about `(1, 97, 97)`, speed between 0 and 2 m/s. If a fetch takes longer than 20 s here, raise `FETCH_TIMEOUT_S` in `config.py` to 40 and note it. If it raises a credentials error, fix `backend/.env` first.

Then start the server and repeat the curl from Task 4 Step 6.
Expected: the snapshot now shows `"source": "copernicus"`.

- [ ] **Step 9: Commit**

```bash
git add requirements.txt app/sim/copernicus.py app/service.py scripts/smoke_copernicus.py tests/conftest.py tests/test_copernicus.py
git commit -m "feat(backend): fetch real surface currents from Copernicus with timeout fallback"
```

---

### Task 6: Tiger Data schema and database module

**Prerequisite (human):** a Tiger Cloud service exists and `backend/.env` has `DATABASE_URL` set to its direct (non-pooled) connection string with `sslmode=require`.

**Files:**
- Create: `backend/scripts/schema.sql`, `backend/scripts/init_db.py`, `backend/app/db.py`
- Test: `backend/tests/test_db_offline.py`

**Interfaces:**
- Consumes: `Field`, `SnapshotKey`, `build_field`, `COMPONENT_NAMES`, schema models, `config.DATABASE_URL`.
- Produces (all in `app.db`):
  - `init_pool() -> bool`, `close_pool() -> None`, `available() -> bool`, `ping() -> bool`, `apply_schema() -> None`.
  - `snapshot_rows(key: SnapshotKey, fld: Field)` generator of 12-tuples `(time, snapshot_id, ix, iy, lon, lat, uo, vo, utide, vtide, ustokes, vstokes)` with `None` for NaN. Pure.
  - `field_from_rows(key, snapshot_id: str, nx: int, ny: int, nt: int, rows) -> Field | None` where each row is `(time, ix, iy, lon, lat, uo, vo, utide, vtide, ustokes, vstokes)`. Returns `None` if the row count is wrong. Pure.
  - `timeline_points(start_time: datetime, rows) -> list[TimelinePoint]` where each row is `(bucket, status, count)`. Pure.
  - `save_snapshot(key, fld) -> None`, `load_snapshot(key) -> Field | None`.
  - `save_run(response: SimulateResponse, req: SimulateRequest, fields: dict, slice_time: datetime, parent_run_id: str | None) -> None`.
  - `load_run(run_id: str) -> SimulateResponse | None`, `timeline(run_id: str) -> list[TimelinePoint] | None`.

- [ ] **Step 1: Write the schema**

Create `backend/scripts/schema.sql`:

```sql
CREATE EXTENSION IF NOT EXISTS timescaledb;

CREATE TABLE IF NOT EXISTS snapshots (
  snapshot_id    UUID PRIMARY KEY,
  centre_lon     DOUBLE PRECISION NOT NULL,
  centre_lat     DOUBLE PRECISION NOT NULL,
  half_width_deg DOUBLE PRECISION NOT NULL,
  slice_time     TIMESTAMPTZ NOT NULL,
  n_slices       INT NOT NULL DEFAULT 1,
  source         TEXT NOT NULL,
  nx             INT NOT NULL,
  ny             INT NOT NULL,
  created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (centre_lon, centre_lat, half_width_deg, slice_time, n_slices)
);

-- One row per grid cell per time slice. ix/iy let the grid be rebuilt exactly.
CREATE TABLE IF NOT EXISTS current_samples (
  time        TIMESTAMPTZ NOT NULL,
  snapshot_id UUID NOT NULL,
  ix          INT NOT NULL,
  iy          INT NOT NULL,
  lon         DOUBLE PRECISION NOT NULL,
  lat         DOUBLE PRECISION NOT NULL,
  uo REAL, vo REAL, utide REAL, vtide REAL, ustokes REAL, vstokes REAL
);
SELECT create_hypertable('current_samples', by_range('time'), if_not_exists => TRUE);
CREATE INDEX IF NOT EXISTS current_samples_snapshot_idx ON current_samples (snapshot_id, time);

CREATE TABLE IF NOT EXISTS runs (
  run_id         UUID PRIMARY KEY,
  created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
  start_time     TIMESTAMPTZ NOT NULL,          -- the slice hour; positions.time = start_time + timeSeconds
  parent_run_id  UUID,                          -- links the "with" run to its "without" twin
  duration_days  INT NOT NULL CHECK (duration_days BETWEEN 1 AND 30),
  params         JSONB NOT NULL,
  summary        JSONB NOT NULL,
  snapshots      JSONB NOT NULL
);

CREATE TABLE IF NOT EXISTS run_items (
  run_id      UUID NOT NULL,
  item_id     TEXT NOT NULL,
  litter_type TEXT NOT NULL,
  start_lon   DOUBLE PRECISION NOT NULL,
  start_lat   DOUBLE PRECISION NOT NULL,
  snapshot_id UUID NOT NULL,
  final_status TEXT NOT NULL,
  captured_by TEXT,
  status_changed_at_seconds INT,
  PRIMARY KEY (run_id, item_id)
);

CREATE TABLE IF NOT EXISTS run_collection_points (
  run_id   UUID NOT NULL,
  cp_id    TEXT NOT NULL,
  lon      DOUBLE PRECISION NOT NULL,
  lat      DOUBLE PRECISION NOT NULL,
  radius_m DOUBLE PRECISION NOT NULL,
  captured_count INT NOT NULL DEFAULT 0,
  PRIMARY KEY (run_id, cp_id)
);

-- One row per item per recorded sample.
CREATE TABLE IF NOT EXISTS positions (
  time    TIMESTAMPTZ NOT NULL,
  run_id  UUID NOT NULL,
  item_id TEXT NOT NULL,
  lon     DOUBLE PRECISION NOT NULL,
  lat     DOUBLE PRECISION NOT NULL,
  status  TEXT NOT NULL
);
SELECT create_hypertable('positions', by_range('time'), if_not_exists => TRUE);
CREATE INDEX IF NOT EXISTS positions_run_idx ON positions (run_id, time);
```

`create_hypertable(..., if_not_exists => TRUE)` is used instead of the `WITH (timescaledb.hypertable)` clause so the script can be re-run safely on any TimescaleDB version.

- [ ] **Step 2: Write the failing tests for the pure helpers**

Create `backend/tests/test_db_offline.py`:

```python
from datetime import timedelta

import numpy as np

from app import db
from app.sim.snapshot import build_field, key_for, synthetic_field
from tests.helpers import T0

KEY = key_for(10.2, -20.1, 1, T0)


def field_with_land():
    base = synthetic_field(KEY)
    comps = {name: values.copy() for name, values in base.components.items()}
    comps["uo"][0, 0, 0] = np.nan
    comps["vo"][0, 0, 0] = np.nan
    return build_field(base.lon, base.lat, comps, T0, "copernicus")


def test_snapshot_rows_cover_every_cell_and_store_land_as_null():
    fld = field_with_land()
    rows = list(db.snapshot_rows(KEY, fld))
    assert len(rows) == fld.lon.size * fld.lat.size
    first = rows[0]
    assert first[0] == T0 and first[1] == fld.snapshot_id
    assert first[2:4] == (0, 0)
    assert first[6] is None and first[7] is None        # uo, vo on the land cell
    assert isinstance(rows[1][6], float)


def test_snapshot_survives_a_round_trip_through_rows():
    fld = field_with_land()
    stored = [(r[0], *r[2:]) for r in db.snapshot_rows(KEY, fld)]  # drop snapshot_id, as the SELECT does
    loaded = db.field_from_rows(KEY, fld.snapshot_id, fld.lon.size, fld.lat.size, 1, stored)
    assert loaded.snapshot_id == fld.snapshot_id
    assert loaded.source == "copernicus"
    np.testing.assert_allclose(loaded.lon, fld.lon)
    np.testing.assert_allclose(loaded.lat, fld.lat)
    np.testing.assert_array_equal(loaded.u, fld.u)      # NaN positions included
    np.testing.assert_array_equal(loaded.v, fld.v)


def test_field_from_rows_rejects_a_partial_snapshot():
    fld = field_with_land()
    stored = [(r[0], *r[2:]) for r in db.snapshot_rows(KEY, fld)][:-5]
    assert db.field_from_rows(KEY, fld.snapshot_id, fld.lon.size, fld.lat.size, 1, stored) is None


def test_timeline_points_fold_status_counts_per_hour():
    rows = [
        (T0, "floating", 3),
        (T0 + timedelta(hours=1), "floating", 2),
        (T0 + timedelta(hours=1), "captured", 1),
    ]
    points = db.timeline_points(T0, rows)
    assert [p.time_seconds for p in points] == [0, 3600]
    assert (points[0].floating, points[0].captured) == (3, 0)
    assert (points[1].floating, points[1].captured, points[1].beached, points[1].outside) == (2, 1, 0, 0)


def test_database_is_unavailable_without_a_url():
    assert db.init_pool() is False
    assert db.available() is False
    assert db.ping() is False
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `python -m pytest tests/test_db_offline.py -q`
Expected: `ImportError: cannot import name 'db' from 'app'`.

- [ ] **Step 4: Implement the database module**

Create `backend/app/db.py`:

```python
"""Tiger Data (TimescaleDB) access. Callers check available() first and catch exceptions."""
import logging
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
from psycopg.types.json import Jsonb
from psycopg_pool import ConnectionPool

from . import config
from .schemas import (
    Attribution, CollectorSummary, ItemSummary, ParticleTrajectory, SimulateRequest,
    SimulateResponse, SnapshotInfo, StatusCounts, TimelinePoint, TrajectorySample,
)
from .sim.snapshot import COMPONENT_NAMES, Field, SnapshotKey, build_field

log = logging.getLogger("plasticpaths")
SCHEMA_PATH = Path(__file__).resolve().parents[1] / "scripts" / "schema.sql"
STATUSES = ("floating", "captured", "beached", "outside")

_pool: ConnectionPool | None = None


# ---------- connection ----------

def init_pool() -> bool:
    """Open the pool. Returns False (and stays unavailable) if there is no URL or no connection."""
    global _pool
    if not config.DATABASE_URL:
        return False
    try:
        pool = ConnectionPool(config.DATABASE_URL, min_size=1, max_size=4, open=False, timeout=5)
        pool.open(wait=True, timeout=10)
        _pool = pool
        return True
    except Exception as err:
        log.warning("Tiger Data unavailable: %r", err)
        _pool = None
        return False


def close_pool() -> None:
    global _pool
    if _pool is not None:
        _pool.close()
        _pool = None


def available() -> bool:
    return _pool is not None


def ping() -> bool:
    if _pool is None:
        return False
    try:
        with _pool.connection() as conn:
            conn.execute("SELECT 1")
        return True
    except Exception:
        return False


def apply_schema() -> None:
    with _pool.connection() as conn:
        conn.execute(SCHEMA_PATH.read_text())


# ---------- pure helpers (unit tested without a database) ----------

def snapshot_rows(key: SnapshotKey, fld: Field):
    """Yield one current_samples row per grid cell per slice. NaN becomes None."""
    lon = fld.lon.tolist()
    lat = fld.lat.tolist()
    for k in range(fld.u.shape[0]):
        t = key.slice_time + timedelta(hours=k)
        layers = [fld.components[name][k].tolist() for name in COMPONENT_NAMES]
        for j, la in enumerate(lat):
            for i, lo in enumerate(lon):
                values = [layer[j][i] for layer in layers]
                yield (t, fld.snapshot_id, i, j, lo, la, *[None if v != v else v for v in values])


def field_from_rows(key: SnapshotKey, snapshot_id: str, nx: int, ny: int, nt: int, rows) -> Field | None:
    """Rebuild a Field from current_samples rows. None if the snapshot is incomplete."""
    if len(rows) != nx * ny * nt:
        return None
    lon = np.zeros(nx)
    lat = np.zeros(ny)
    comps = {name: np.full((nt, ny, nx), np.nan, dtype="float32") for name in COMPONENT_NAMES}
    for time, ix, iy, lo, la, *values in rows:
        k = int((time - key.slice_time).total_seconds() // 3600)
        lon[ix] = lo
        lat[iy] = la
        for name, value in zip(COMPONENT_NAMES, values):
            if value is not None:
                comps[name][k, iy, ix] = value
    return build_field(lon, lat, comps, key.slice_time, "copernicus", snapshot_id=str(snapshot_id))


def timeline_points(start_time: datetime, rows) -> list:
    """Fold (bucket, status, count) rows into one TimelinePoint per bucket."""
    buckets: dict = {}
    for bucket, status, count in rows:
        seconds = int((bucket - start_time).total_seconds())
        buckets.setdefault(seconds, dict.fromkeys(STATUSES, 0))[status] = count
    return [TimelinePoint(time_seconds=seconds, **counts) for seconds, counts in sorted(buckets.items())]


# ---------- snapshots ----------

def save_snapshot(key: SnapshotKey, fld: Field) -> None:
    with _pool.connection() as conn:
        inserted = conn.execute(
            """INSERT INTO snapshots (snapshot_id, centre_lon, centre_lat, half_width_deg,
                                      slice_time, n_slices, source, nx, ny)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
               ON CONFLICT DO NOTHING RETURNING snapshot_id""",
            (fld.snapshot_id, key.centre_lon, key.centre_lat, key.half_width_deg,
             key.slice_time, key.n_slices, fld.source, fld.lon.size, fld.lat.size),
        ).fetchone()
        if inserted is None:
            return  # another request stored this box first
        with conn.cursor() as cur:
            with cur.copy(
                """COPY current_samples (time, snapshot_id, ix, iy, lon, lat,
                                         uo, vo, utide, vtide, ustokes, vstokes) FROM STDIN"""
            ) as copy:
                for row in snapshot_rows(key, fld):
                    copy.write_row(row)


def load_snapshot(key: SnapshotKey) -> Field | None:
    with _pool.connection() as conn:
        head = conn.execute(
            """SELECT snapshot_id, nx, ny, n_slices FROM snapshots
               WHERE centre_lon = %s AND centre_lat = %s AND half_width_deg = %s
                 AND slice_time = %s AND n_slices = %s""",
            (key.centre_lon, key.centre_lat, key.half_width_deg, key.slice_time, key.n_slices),
        ).fetchone()
        if head is None:
            return None
        snapshot_id, nx, ny, nt = head
        rows = conn.execute(
            """SELECT time, ix, iy, lon, lat, uo, vo, utide, vtide, ustokes, vstokes
               FROM current_samples WHERE snapshot_id = %s""",
            (snapshot_id,),
        ).fetchall()
    return field_from_rows(key, str(snapshot_id), nx, ny, nt, rows)


# ---------- runs ----------

def save_run(response: SimulateResponse, req: SimulateRequest, fields: dict,
             slice_time: datetime, parent_run_id: str | None) -> None:
    run_id = response.run_id
    starts = {t.id: t.samples[0].coordinates for t in response.trajectories}
    with _pool.connection() as conn:  # one transaction
        conn.execute(
            """INSERT INTO runs (run_id, start_time, parent_run_id, duration_days, params, summary, snapshots)
               VALUES (%s, %s, %s, %s, %s, %s, %s)""",
            (run_id, slice_time, parent_run_id, response.duration_days,
             Jsonb(req.model_dump(by_alias=True, mode="json")),
             Jsonb(response.summary.model_dump()),
             Jsonb([s.model_dump(by_alias=True, mode="json") for s in response.snapshots])),
        )
        with conn.cursor() as cur:
            cur.executemany(
                """INSERT INTO run_items (run_id, item_id, litter_type, start_lon, start_lat, snapshot_id,
                                          final_status, captured_by, status_changed_at_seconds)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                [(run_id, item.id, item.type, starts[item.id][0], starts[item.id][1],
                  fields[item.id].snapshot_id, item.final_status, item.captured_by,
                  item.status_changed_at_seconds) for item in response.items],
            )
            cur.executemany(
                """INSERT INTO run_collection_points (run_id, cp_id, lon, lat, radius_m, captured_count)
                   VALUES (%s, %s, %s, %s, %s, %s)""",
                [(run_id, c.id, c.coordinates[0], c.coordinates[1], c.radius_m, c.captured_count)
                 for c in response.collectors],
            )
            with cur.copy("COPY positions (time, run_id, item_id, lon, lat, status) FROM STDIN") as copy:
                for trajectory in response.trajectories:
                    for sample in trajectory.samples:
                        copy.write_row((slice_time + timedelta(seconds=sample.time_seconds), run_id,
                                        trajectory.id, sample.coordinates[0], sample.coordinates[1],
                                        sample.status))


def load_run(run_id: str) -> SimulateResponse | None:
    with _pool.connection() as conn:
        run = conn.execute(
            "SELECT start_time, duration_days, summary, snapshots FROM runs WHERE run_id = %s", (run_id,),
        ).fetchone()
        if run is None:
            return None
        start_time, duration_days, summary, snapshots = run
        items = conn.execute(
            """SELECT item_id, litter_type, final_status, captured_by, status_changed_at_seconds
               FROM run_items WHERE run_id = %s ORDER BY item_id""", (run_id,),
        ).fetchall()
        collectors = conn.execute(
            """SELECT cp_id, lon, lat, radius_m, captured_count
               FROM run_collection_points WHERE run_id = %s ORDER BY cp_id""", (run_id,),
        ).fetchall()
        positions = conn.execute(
            """SELECT item_id, time, lon, lat, status FROM positions
               WHERE run_id = %s ORDER BY item_id, time""", (run_id,),
        ).fetchall()

    samples: dict = {}
    for item_id, time, lon, lat, status in positions:
        samples.setdefault(item_id, []).append(TrajectorySample(
            time_seconds=int((time - start_time).total_seconds()), coordinates=(lon, lat), status=status))

    return SimulateResponse(
        run_id=str(run_id),
        duration_days=duration_days,
        total_seconds=duration_days * 86400,
        sample_interval_seconds=config.SAMPLE_INTERVAL_SECONDS,
        trajectories=[ParticleTrajectory(id=i[0], type=i[1], samples=samples.get(i[0], [])) for i in items],
        items=[ItemSummary(id=i[0], type=i[1], final_status=i[2], captured_by=i[3],
                           status_changed_at_seconds=i[4]) for i in items],
        collectors=[CollectorSummary(id=c[0], coordinates=(c[1], c[2]), radius_m=c[3], captured_count=c[4])
                    for c in collectors],
        summary=StatusCounts(**summary),
        snapshots=[SnapshotInfo.model_validate(s) for s in snapshots],
        attribution=Attribution(source=config.ATTRIBUTION_SOURCE, dataset=config.DATASET_ID,
                                limitations=config.LIMITATIONS),
        persisted=True,
    )


def timeline(run_id: str) -> list | None:
    """Status counts per hour, computed in the database with time_bucket."""
    with _pool.connection() as conn:
        run = conn.execute("SELECT start_time FROM runs WHERE run_id = %s", (run_id,)).fetchone()
        if run is None:
            return None
        rows = conn.execute(
            """SELECT time_bucket('1 hour', time) AS bucket, status, count(*)
               FROM positions WHERE run_id = %s
               GROUP BY bucket, status ORDER BY bucket""", (run_id,),
        ).fetchall()
    return timeline_points(run[0], rows)
```

Create `backend/scripts/init_db.py`:

```python
"""Create the Tiger Data schema. Safe to re-run. Run from backend/:  python -m scripts.init_db"""
import sys

from app import db

if not db.init_pool():
    sys.exit("Could not connect. Check DATABASE_URL in backend/.env")
db.apply_schema()
with db._pool.connection() as conn:
    tables = conn.execute("SELECT hypertable_name FROM timescaledb_information.hypertables ORDER BY 1").fetchall()
print("hypertables:", [t[0] for t in tables])
db.close_pool()
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest -q`
Expected: 60 passed.

- [ ] **Step 6: Create the schema on the real service**

Run: `python -m scripts.init_db`
Expected: `hypertables: ['current_samples', 'positions']`. Run it a second time; the output must be identical with no error.

- [ ] **Step 7: Commit**

```bash
git add scripts/schema.sql scripts/init_db.py app/db.py tests/test_db_offline.py
git commit -m "feat(backend): Tiger Data schema and database module with hypertables"
```

---

### Task 7: Persist runs, cache snapshots in Tiger, replay and timeline endpoints

**Files:**
- Modify: `backend/app/service.py` (`resolve_field`, `persist`), `backend/app/routes.py` (health, two run endpoints), `backend/app/main.py` (lifespan)
- Create: `backend/scripts/smoke.py`
- Test: `backend/tests/test_persistence.py`

**Interfaces:**
- Consumes: every `db` function from Task 6; `service.fetch_with_timeout`, `service.remember`, `service._memory` from Task 5.
- Produces:
  - `service.resolve_field(key)` order: memory, Tiger, Copernicus (then stored in Tiger), synthetic.
  - `service.persist(...)` returns `True` only when `db.save_run` succeeded.
  - HTTP: `GET /api/runs/{run_id}` (200, 404, 503), `GET /api/runs/{run_id}/timeline` (200, 404, 503), `GET /api/health` now reports the real `db` flag.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_persistence.py`:

```python
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import db, service
from app.main import app
from app.schemas import SimulateResponse, TimelinePoint
from app.sim import copernicus
from app.sim.snapshot import key_for
from tests.helpers import T0, uniform_field

client = TestClient(app)  # no "with": the lifespan does not run, so no real pool is opened

RUN_ID = "00000000-0000-0000-0000-000000000001"
KEY = key_for(10.2, -20.1, 1, T0)
BODY = {"placements": [
    {"id": "bottle-1", "type": "bottle", "coordinates": [10.2, -20.1]},
    {"id": "collector-1", "type": "collector", "coordinates": [10.4, -20.1]},
], "durationDays": 1}
FIXTURE = Path(__file__).resolve().parents[1] / "scripts" / "fixtures" / "simulate_response.json"


def real_field():
    fld = uniform_field(u=0.2)
    fld.source = "copernicus"
    return fld


@pytest.fixture
def fake_db(monkeypatch):
    """Pretend Tiger is connected and record what the service asks of it."""
    calls = {"runs": [], "snapshots": [], "lookups": []}
    monkeypatch.setattr(db, "available", lambda: True)
    monkeypatch.setattr(db, "ping", lambda: True)
    monkeypatch.setattr(db, "load_snapshot", lambda key: calls["lookups"].append(key))
    monkeypatch.setattr(db, "save_snapshot", lambda key, fld: calls["snapshots"].append(key))
    monkeypatch.setattr(db, "save_run",
                        lambda response, req, fields, slice_time, parent_run_id:
                        calls["runs"].append((response.run_id, parent_run_id)))
    return calls


@pytest.mark.parametrize("path", [f"/api/runs/{RUN_ID}", f"/api/runs/{RUN_ID}/timeline"])
def test_run_endpoints_return_503_without_a_database(path):
    assert client.get(path).status_code == 503


def test_health_reports_database_state(fake_db):
    assert client.get("/api/health").json() == {"status": "ok", "db": True}


def test_simulate_without_database_still_succeeds_unpersisted():
    data = client.post("/api/simulate", json=BODY).json()
    assert data["persisted"] is False
    assert len(data["trajectories"]) == 1


def test_simulate_persists_when_database_is_available(fake_db):
    data = client.post("/api/simulate", json=BODY).json()
    assert data["persisted"] is True
    assert fake_db["runs"] == [(data["runId"], None)]


def test_compare_links_the_with_run_to_the_without_run(fake_db):
    data = client.post("/api/compare", json=BODY).json()
    assert fake_db["runs"] == [
        (data["without"]["runId"], None),
        (data["with"]["runId"], data["without"]["runId"]),
    ]


def test_database_failure_during_save_does_not_fail_the_request(fake_db, monkeypatch):
    def boom(*args):
        raise RuntimeError("connection lost")

    monkeypatch.setattr(db, "save_run", boom)
    response = client.post("/api/simulate", json=BODY)
    assert response.status_code == 200
    assert response.json()["persisted"] is False


def test_stored_snapshot_is_used_before_copernicus(fake_db, monkeypatch):
    stored = real_field()
    fetches = []
    monkeypatch.setattr(db, "load_snapshot", lambda key: stored)
    monkeypatch.setattr(copernicus, "fetch_field", lambda key: fetches.append(key))
    assert service.resolve_field(KEY) is stored
    assert fetches == []
    assert service._memory[KEY] is stored


def test_fetched_snapshot_is_stored_in_tiger(fake_db, monkeypatch):
    fetched = real_field()
    monkeypatch.setattr(copernicus, "fetch_field", lambda key: fetched)
    assert service.resolve_field(KEY) is fetched
    assert fake_db["lookups"] == [KEY]
    assert fake_db["snapshots"] == [KEY]


def test_synthetic_fallback_is_never_stored(fake_db):
    assert service.resolve_field(KEY).source == "synthetic"  # the autouse fixture blocks the fetch
    assert fake_db["snapshots"] == []


def test_snapshot_lookup_failure_falls_through_to_copernicus(fake_db, monkeypatch):
    def boom(key):
        raise RuntimeError("connection lost")

    fetched = real_field()
    monkeypatch.setattr(db, "load_snapshot", boom)
    monkeypatch.setattr(copernicus, "fetch_field", lambda key: fetched)
    assert service.resolve_field(KEY) is fetched


def test_get_run_returns_the_stored_run(fake_db, monkeypatch):
    stored = SimulateResponse.model_validate(json.loads(FIXTURE.read_text()))
    monkeypatch.setattr(db, "load_run", lambda run_id: stored)
    response = client.get(f"/api/runs/{RUN_ID}")
    assert response.status_code == 200
    assert response.json()["runId"] == stored.run_id
    assert response.json()["trajectories"][0]["samples"][0]["timeSeconds"] == 0


@pytest.mark.parametrize("run_id", [RUN_ID, "not-a-uuid"])
def test_get_run_returns_404_for_unknown_or_malformed_id(fake_db, monkeypatch, run_id):
    monkeypatch.setattr(db, "load_run", lambda run_id: None)
    assert client.get(f"/api/runs/{run_id}").status_code == 404


def test_timeline_returns_points(fake_db, monkeypatch):
    points = [TimelinePoint(time_seconds=0, floating=2, captured=0, beached=0, outside=0),
              TimelinePoint(time_seconds=3600, floating=1, captured=1, beached=0, outside=0)]
    monkeypatch.setattr(db, "timeline", lambda run_id: points)
    data = client.get(f"/api/runs/{RUN_ID}/timeline").json()
    assert data["runId"] == RUN_ID
    assert data["points"][1] == {"timeSeconds": 3600, "floating": 1, "captured": 1, "beached": 0, "outside": 0}


def test_timeline_returns_404_for_unknown_run(fake_db, monkeypatch):
    monkeypatch.setattr(db, "timeline", lambda run_id: None)
    assert client.get(f"/api/runs/{RUN_ID}/timeline").status_code == 404
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_persistence.py -q`
Expected: failures. The run endpoints return 404 (route missing) instead of 503, `persisted` is `False`, and nothing is recorded in `fake_db`.

- [ ] **Step 3: Wire the database into the service**

In `backend/app/service.py`, change `from . import config` to:

```python
from . import config, db
```

Replace the `resolve_field` function with these three functions:

```python
def load_stored(key: SnapshotKey) -> Field | None:
    if not db.available():
        return None
    try:
        return db.load_snapshot(key)
    except Exception as err:
        log.warning("Snapshot lookup failed for %s: %r", key, err)
        return None


def store(key: SnapshotKey, fld: Field) -> None:
    if not db.available():
        return
    try:
        db.save_snapshot(key, fld)
    except Exception as err:
        log.warning("Snapshot save failed for %s: %r", key, err)


def resolve_field(key: SnapshotKey) -> Field:
    """Memory, then Tiger, then Copernicus, then a synthetic field.
    Only real snapshots are cached or stored, so the real source is retried next time."""
    if key in _memory:
        return _memory[key]
    fld = load_stored(key)
    if fld is None:
        fld = fetch_with_timeout(key)
        if fld is None:
            return synthetic_field(key)
        store(key, fld)
    remember(key, fld)
    return fld
```

Replace the `persist` function with:

```python
def persist(response: SimulateResponse, req: SimulateRequest, fields: dict,
            slice_time: datetime, parent_run_id: str | None) -> bool:
    """Store the run in Tiger. A database problem never fails the request."""
    if not db.available():
        return False
    try:
        db.save_run(response, req, fields, slice_time, parent_run_id)
        return True
    except Exception as err:
        log.warning("Run save failed for %s: %r", response.run_id, err)
        return False
```

- [ ] **Step 4: Add the endpoints and the lifespan**

In `backend/app/routes.py`, change the imports to:

```python
import uuid

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse

from . import config, db, service
from .schemas import (
    CompareResponse, CurrentsResponse, MetaResponse, SimulateRequest, SimulateResponse,
    TimelineResponse,
)
```

Replace the `health` function with:

```python
@router.get("/health")
def health() -> dict:
    return {"status": "ok", "db": db.ping()}
```

Append to the end of the file:

```python
def checked_run_id(run_id: str) -> str:
    if not db.available():
        raise HTTPException(status_code=503, detail="database unavailable")
    try:
        return str(uuid.UUID(run_id))
    except ValueError:
        raise HTTPException(status_code=404, detail="run not found")


@router.get("/runs/{run_id}", response_model=SimulateResponse)
def get_run(run_id: str):
    run_id = checked_run_id(run_id)
    try:
        run = db.load_run(run_id)
    except Exception:
        raise HTTPException(status_code=503, detail="database unavailable")
    if run is None:
        raise HTTPException(status_code=404, detail="run not found")
    return run


@router.get("/runs/{run_id}/timeline", response_model=TimelineResponse)
def get_timeline(run_id: str):
    run_id = checked_run_id(run_id)
    try:
        points = db.timeline(run_id)
    except Exception:
        raise HTTPException(status_code=503, detail="database unavailable")
    if points is None:
        raise HTTPException(status_code=404, detail="run not found")
    return TimelineResponse(run_id=run_id, points=points)
```

Replace `backend/app/main.py` with:

```python
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import config, db
from .routes import router


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_pool()  # returns False and carries on if Tiger is unreachable
    yield
    db.close_pool()


def create_app() -> FastAPI:
    app = FastAPI(title="PlasticPaths simulation API", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[config.CORS_ORIGIN],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(router, prefix="/api")
    return app


app = create_app()
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest -q`
Expected: 77 passed.

- [ ] **Step 6: End-to-end smoke test against real Copernicus and real Tiger**

Create `backend/scripts/smoke.py`:

```python
"""Manual end-to-end check against a running server.
Start the server, then from backend/:  python -m scripts.smoke [base_url]"""
import sys
import time

import httpx

base = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000"
client = httpx.Client(base_url=base, timeout=180)
body = {"placements": [
    {"id": "bag-1", "type": "bag", "coordinates": [-140.6, 32.4]},
    {"id": "bottle-1", "type": "bottle", "coordinates": [-140.2, 32.1]},
    {"id": "collector-1", "type": "collector", "coordinates": [-140.1, 32.1]},
], "durationDays": 7}

health = client.get("/api/health").json()
print("health:", health)
assert health["db"] is True, "database not connected"

started = time.monotonic()
compared = client.post("/api/compare", json=body).json()
print(f"compare: {time.monotonic() - started:.1f}s  delta {compared['delta']}")
run = compared["with"]
print("source:", [s["source"] for s in run["snapshots"]], " persisted:", run["persisted"])
assert run["persisted"] is True, "run was not stored"
assert all(s["source"] == "copernicus" for s in run["snapshots"]), "fell back to synthetic currents"

replay = client.get(f"/api/runs/{run['runId']}").json()
assert replay["trajectories"] == run["trajectories"], "replay differs from the original run"
assert replay["summary"] == run["summary"]

timeline = client.get(f"/api/runs/{run['runId']}/timeline").json()["points"]
assert len(timeline) == 7 * 24 + 1, f"expected 169 hourly points, got {len(timeline)}"
assert all(sum(p[k] for k in ("floating", "captured", "beached", "outside")) == 2 for p in timeline)

started = time.monotonic()
client.post("/api/simulate", json=body)
print(f"second run (snapshots cached): {time.monotonic() - started:.1f}s")
print("PASS")
```

Run the server (`python -m uvicorn app.main:app --port 8000`), then `python -m scripts.smoke`.
Expected: `health: {'status': 'ok', 'db': True}`, a compare time of a few seconds, `source: ['copernicus', ...]`, `persisted: True`, a second run clearly faster than the first, and `PASS`.

Then restart the server and run the smoke script again within the same clock hour.
Expected: `PASS`, and the first compare is fast this time because the snapshots load from Tiger instead of Copernicus. Snapshots are keyed by the hour, so after the hour rolls over a fresh fetch is correct behaviour.

- [ ] **Step 7: Commit**

```bash
git add app/service.py app/routes.py app/main.py scripts/smoke.py tests/test_persistence.py
git commit -m "feat(backend): persist runs and snapshots in Tiger Data, replay and timeline endpoints"
```

---

### Task 8: Handoff, container and Tiger polish (Phase 4)

**Files:**
- Create: `backend/README.md`, `backend/Dockerfile`, `backend/.dockerignore`, `backend/scripts/compression.sql`

**Interfaces:**
- Consumes: the running API from Tasks 1 to 7.
- Produces: a container image that serves the API on `$PORT`, and the document the other streams integrate from.

- [ ] **Step 1: Write the backend README**

Create `backend/README.md`:

````markdown
# PlasticPaths backend (stream 3)

FastAPI service that simulates floating litter drifting on real ocean currents and stores every run in Tiger Data.

## Run locally

```bash
cd backend
python -m venv .venv && source .venv/Scripts/activate   # Windows Git Bash
pip install -r requirements.txt
cp .env.example .env        # fill in Copernicus and Tiger credentials
python -m scripts.init_db   # once, creates the tables and hypertables
python -m uvicorn app.main:app --port 8000 --reload
```

Interactive docs: http://localhost:8000/docs. Tests: `python -m pytest -q` (no network or database needed).

The server works with no credentials at all: it falls back to synthetic currents (`"source": "synthetic"`) and skips storage (`"persisted": false`).

## Endpoints

| Method and path | Purpose |
|---|---|
| GET /api/health | liveness and database flag |
| GET /api/meta | duration limits, defaults, litter types, attribution and limitations |
| GET /api/currents?lon&lat&durationDays | arrows for the map: `coordinates`, `u`, `v`, `speed`, `bearing` (degrees clockwise from north) |
| POST /api/simulate | run one experiment, returns `trajectories` as the frontend's `ParticleTrajectory[]` |
| POST /api/compare | same placements without and with collectors: `{without, with, delta}` |
| GET /api/runs/{runId} | replay a stored run |
| GET /api/runs/{runId}/timeline | status counts per hour |

Request body for simulate and compare is the frontend's `Placement[]` plus an optional duration:

```json
{"placements": [{"id": "bottle-1", "type": "bottle", "coordinates": [-140.2, 32.1]}], "durationDays": 7}
```

A drop on land returns HTTP 422 with `{"code": "on_land", "message": "...", "placementId": "..."}`.

## Frontend integration

Set `VITE_API_BASE_URL=http://localhost:8000`, then replace `buildTrajectories()` in `src/simulation.ts`:

```ts
export async function fetchTrajectories(placements: Placement[], durationDays = 7) {
  const response = await fetch(`${import.meta.env.VITE_API_BASE_URL}/api/simulate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ placements, durationDays }),
  });
  const data = await response.json();
  if (!response.ok) throw data;            // data.code === "on_land" for a drop on land
  return data;                             // data.trajectories is ParticleTrajectory[]
}
```

Use `data.totalSeconds` for the timeline length instead of the fixed `DURATION_SECONDS`. `interpolateFrame`, `trailGeoJson` and `particleGeoJson` work unchanged.

## How the simulation works

- When items are dropped, the backend fetches one hourly snapshot of surface currents for a box around each item from Copernicus Marine (`cmems_mod_glo_phy_anfc_merged-uv_PT1H-i`, about 9 km grid).
- Every item drifts through its own frozen snapshot for the same number of days (1 to 30) in 10-minute steps; positions are recorded hourly.
- An item stops when it reaches land (`beached`), enters a collector's radius (`captured`), or leaves its box (`outside`).
- Simplifications: one frozen time slice, no tide, no wind, no sinking or breakdown, all litter types drift alike.

## Tiger Data

Two hypertables do real work: `current_samples` caches every fetched snapshot (drops in the same area and hour reuse it, even across restarts), and `positions` stores every recorded sample of every run. The timeline endpoint is one `time_bucket` query:

```sql
SELECT time_bucket('1 hour', time) AS bucket, status, count(*)
FROM positions WHERE run_id = $1 GROUP BY bucket, status ORDER BY bucket;
```

Where each item started and ended, using Timescale's `first` and `last`:

```sql
SELECT item_id, first(lon, time), first(lat, time), last(lon, time), last(lat, time), last(status, time)
FROM positions WHERE run_id = $1 GROUP BY item_id;
```
````

- [ ] **Step 2: Add the container files**

Create `backend/Dockerfile`:

```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
COPY scripts ./scripts
ENV PORT=8000
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT}"]
```

Create `backend/.dockerignore`:

```
.venv
.env
__pycache__
tests
.pytest_cache
```

- [ ] **Step 3: Verify the container**

```bash
docker build -t plasticpaths-backend .
docker run --rm -p 8000:8000 --env-file .env plasticpaths-backend
```

In another terminal run: `python -m scripts.smoke`
Expected: `PASS`. If Docker is not installed on this machine, skip this step, say so in the commit message, and verify on the deployment host instead.

- [ ] **Step 4: Add the compression policy**

Create `backend/scripts/compression.sql`:

```sql
ALTER TABLE positions SET (
  timescaledb.compress,
  timescaledb.compress_segmentby = 'run_id',
  timescaledb.compress_orderby = 'time'
);
SELECT add_compression_policy('positions', INTERVAL '1 day', if_not_exists => TRUE);

ALTER TABLE current_samples SET (
  timescaledb.compress,
  timescaledb.compress_segmentby = 'snapshot_id',
  timescaledb.compress_orderby = 'time'
);
SELECT add_compression_policy('current_samples', INTERVAL '1 day', if_not_exists => TRUE);
```

Apply it once from the Tiger console SQL editor or with `psql "$DATABASE_URL" -f scripts/compression.sql`.
Expected: two policy job ids returned. Then rerun `python -m scripts.smoke`; expected `PASS` (compressed chunks stay readable and writable).

- [ ] **Step 5: Final full check and commit**

Run: `python -m pytest -q`
Expected: 77 passed.

```bash
git add README.md Dockerfile .dockerignore scripts/compression.sql
git commit -m "docs(backend): README, container image and Tiger compression policy"
```

- [ ] **Step 6: Deploy (only when the team picks a host)**

On Render or Fly, create a web service from `backend/Dockerfile`, set the four variables from `.env.example` as secrets with `CORS_ORIGIN` set to the deployed frontend origin, then run `python -m scripts.smoke https://<deployed-host>`.
Expected: `PASS`.

---

## Later, not in this plan

- **Multi-slice currents.** `Field.sample` already takes `t_seconds` and picks the slice by hour; `SnapshotKey.n_slices`, `snapshot_rows` and `field_from_rows` already carry a time axis. The change is: fetch `n_slices` hours in `copernicus.fetch_field`, keep every slice in `field_from_dataset`, set `USE_TIDE = True`, and pass the slice count through `key_for`.
- **Item-specific drift.** Change the values in `config.DRIFT_FACTOR` and document the source.
- **Speed.** Vectorise the engine loop across items with NumPy.

