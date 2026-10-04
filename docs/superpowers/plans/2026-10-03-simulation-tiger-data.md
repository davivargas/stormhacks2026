# Simulation and Tiger Data (Stream 3) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Finish the stream 3 backend: replace synthetic currents with real Copernicus snapshots and replace the in-memory run store with Tiger Data, without changing any response shape the other streams already build against.

**Architecture:** Phases 0 and 1 already exist in `backend/` (contract, fixtures, engine, all seven endpoints on synthetic currents, runs in memory, 13 passing tests). This plan extends that code in place. `snapshot.load_field` gains two real sources in front of the synthetic fallback (Tiger cache, then Copernicus). A new `app/db.py` stores snapshots and run positions in two hypertables; `routes.py` writes every run there and serves replay and the `time_bucket` timeline from it, keeping the in-memory store as the fallback when the database is down.

**Tech Stack:** Python 3.13, FastAPI, Pydantic v2, NumPy, xarray, `copernicusmarine` 2.5, psycopg 3 with `psycopg_pool`, pytest. All already installed in `backend/.venv` except `psycopg_pool`.

**Spec:** `docs/superpowers/specs/2026-10-03-simulation-tiger-data-design.md`

**Branch:** `feature/simulation-tiger-data`. All commands run from `backend/` with the project venv: `.venv/Scripts/python` (Git Bash) or `.venv\Scripts\python` (PowerShell).

## What already exists (read before starting)

| File | What it provides |
|---|---|
| `app/config.py` | constants: `DURATION_MIN_DAYS`, `DURATION_MAX_DAYS`, `DURATION_DEFAULT_DAYS`, `DT_SECONDS`, `FRAME_INTERVAL_SECONDS`, `HALF_WIDTH_CAP_DEG`, `CENTRE_ROUND_DEG`, `GRID_RESOLUTION_DEG`, `APPLY_STOKES`, `APPLY_TIDE`, `COPERNICUS_DATASET_ID`, `COPERNICUS_TIMEOUT_S`, `DATABASE_URL`, `half_width_deg(days)` |
| `app/schemas.py` | `ApiModel` (camelCase), `SimulateRequest`, `SimulateResponse`, `CompareResponse`, `Summary`, `SnapshotInfo`, `TimelineBucket`, `TimelineResponse(run_id, bucket_seconds, buckets)`, `HealthResponse(ok, db)`, `ErrorResponse` |
| `app/sim/snapshot.py` | `SnapshotKey`, `make_key(lon, lat, duration_days, slice_time)`, `current_slice_time()`, `COMPONENTS`, `Field(key, source, lon, lat, times, components, snapshot_id)` with `contains`, `is_land`, `sample`, `bounds`, `nx`, `ny`; `synthetic_field(key, uniform=, land=)`; `fetch_copernicus(key)` **stub that raises NotImplementedError**; `load_field(key)` with in-process `_cache`, thread pool timeout and synthetic fallback |
| `app/sim/engine.py` | `LitterItem`, `Collector`, `ItemOutcome`, `RunResult`, `drift_item`, `run`, `STATUSES` |
| `app/routes.py` | `ApiError`, all seven endpoints, `load_fields(req)`, `build_response(req, fields, honour_collectors=)`, `compare`, `timeline_of`, `snapshot_info`, in-memory `_runs` store via `_remember` and `_get_run` |
| `app/main.py` | `create_app()`, CORS, gzip, error handlers (`invalid_request`, `ApiError`) |
| `scripts/make_fixtures.py`, `scripts/fixtures/*.json` | canned responses for the other streams |

## Global Constraints

- **Do not change any JSON shape.** The other streams build against `scripts/fixtures/*.json`. The as-built contract differs from the spec text in these ways, and the as-built version wins: timeline is `{runId, bucketSeconds, buckets}`; meta is nested (`durationDays{min,max,default}`, `defaults{...}`); health is `{ok, db}`; validation errors are `{code: "invalid_request", message, details}`; a missing run is `{code: "run_not_found"}`; a request with no litter is rejected with 422.
- Statuses are exactly `floating`, `captured`, `beached`, `outside`. Coordinates are `[longitude, latitude]`. JSON is camelCase, Python and SQL snake_case.
- Longitudes inside a `Field` are continuous around the box centre and may pass 180; trajectories may therefore contain longitudes slightly beyond the range. Keep that; it makes trails continuous across the antimeridian.
- Dataset id comes from `config.COPERNICUS_DATASET_ID`. MVP sums circulation and wave drift (`APPLY_STOKES = True`); tide is fetched and stored but not applied (`APPLY_TIDE = False`). Land is where `uo` is NaN.
- One frozen time slice per snapshot (`n_slices = 1`), keyed by the hour. One duration and one timeline per run.
- Copernicus fetch budget is `config.COPERNICUS_TIMEOUT_S` (20 s), then synthetic fallback with `source: "synthetic"`. A simulate request never fails because of the network or the database.
- Secrets live only in `backend/.env` (gitignored). Tests never touch the network or a real database.
- Deviations from the spec, deliberate: the snapshot fetch lives in `app/sim/snapshot.py` (where the stub already is); run items and collectors are stored inside a `runs.envelope` JSONB column instead of two extra tables (fewer tables, exact replay); `/runs/{id}` falls back to the in-memory store instead of returning 503 when the database is down.

## Review Focus

1. **Item dropped inside a collector's radius.** Captured at second zero, counted once, never moves. Test in Task 1.
2. **Coastal cells with mixed land and water corners.** Sampling treats land corners as zero velocity and never returns NaN. Test in Task 1.
3. **Bad input.** Duplicate ids, coordinates out of range, no litter, more than 50 litter, fractional duration: each is a 422 with `code: "invalid_request"`, before any work. Tests in Task 1.
4. **Drop near the antimeridian.** Synthetic boxes span it. A real fetch is clamped to the map edge instead of failing, and the item becomes `outside` if it reaches the cut. Tests in Tasks 1 and 2.
5. **Copernicus slow, down, or returning nothing for the box.** The request still succeeds on a synthetic field, and the real source is retried a minute later rather than being pinned to synthetic for the whole hour. Tests in Task 2.

## File Structure

```
backend/
  pyproject.toml              modify: psycopg pool extra
  app/
    config.py                 modify: SYNTHETIC_RETRY_S
    sim/snapshot.py           modify: real fetch_copernicus, field_from_dataset, load_field with Tiger and retry
    db.py                     create: pool, snapshots, runs, timeline
    routes.py                 modify: persist runs, replay and timeline from Tiger, health
    main.py                   modify: lifespan opens and closes the pool
  scripts/
    schema.sql                create
    init_db.py                create
    smoke_copernicus.py       create
    smoke.py                  create
    compression.sql           create
  tests/
    conftest.py               create: no network, no database, clean caches
    test_hardening.py         create
    test_copernicus.py        create
    test_db_offline.py        create
    test_persistence.py       create
  Dockerfile, .dockerignore   create
  README.md                   modify
```

---

### Task 1: Baseline, test isolation and behaviour pins

The phase 0 and 1 code is uncommitted. This task makes it safe to build on: tests that can never reach the network or a database, tests pinning the edge cases the later tasks must not break, and a commit.

**Files:**
- Create: `backend/tests/conftest.py`, `backend/tests/test_hardening.py`
- Modify: `backend/pyproject.toml` (one dependency line)

**Interfaces:**
- Consumes: the existing modules listed above.
- Produces: an autouse fixture `isolated` that replaces `snapshot.fetch_copernicus` with a function that raises, and clears `snapshot._cache` and `routes._runs` before every test. Later tasks rely on it: any test that needs a working fetch must monkeypatch `snapshot.fetch_copernicus` itself.

- [ ] **Step 1: Add the pool dependency**

In `backend/pyproject.toml` change the line `"psycopg[binary]>=3.2",` to:

```toml
  "psycopg[binary,pool]>=3.2",
```

Run: `.venv/Scripts/python -m pip install -e ".[dev]"`
Expected: installs `psycopg-pool`.

- [ ] **Step 2: Isolate the tests**

Create `backend/tests/conftest.py`:

```python
import os

# Tests never touch a real database. Set before any app import;
# load_dotenv does not override variables that already exist.
os.environ["DATABASE_URL"] = ""

import pytest  # noqa: E402


@pytest.fixture(autouse=True)
def isolated(monkeypatch):
    """No test reaches Copernicus; every test starts with empty caches."""
    from app import routes
    from app.sim import snapshot

    def refuse(key):
        raise RuntimeError("network disabled in tests")

    monkeypatch.setattr(snapshot, "fetch_copernicus", refuse)
    snapshot._cache.clear()
    routes._runs.clear()
```

- [ ] **Step 3: Pin the edge cases**

Create `backend/tests/test_hardening.py`:

```python
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.sim import engine
from app.sim.snapshot import make_key, synthetic_field

client = TestClient(app)
T0 = datetime(2026, 10, 3, 18, tzinfo=UTC)
LON, LAT = -130.0, 40.0


def bottle(pid, coordinates=(LON, LAT)):
    return {"id": pid, "type": "bottle", "coordinates": list(coordinates)}


def test_item_dropped_inside_collector_is_captured_at_second_zero():
    fld = synthetic_field(make_key(LON, LAT, 1, T0), uniform=(0.5, 0.0))
    collector = engine.Collector("c1", LON, LAT, 10_000)
    item = engine.LitterItem("b", "bottle", LON + 0.01, LAT)
    result = engine.run([item], [collector], 1, {"b": fld})
    out = result.outcomes[0]
    assert out.samples[0][3] == "captured"
    assert out.status_changed_at_seconds == 0
    assert out.samples[-1][1] == pytest.approx(LON + 0.01)  # never moved
    assert result.captured_counts == {"c1": 1}


def test_sampling_beside_land_is_finite_and_slowed():
    # Land starts at the grid column just east of LON + 0.25.
    fld = synthetic_field(make_key(LON, LAT, 1, T0), uniform=(0.5, 0.5),
                          land=lambda lon, lat: lon > LON + 0.26)
    u, v = fld.sample(LON + 0.25 + 0.6 / 12, LAT)  # 60% of the way from a water cell to a land cell
    assert u == pytest.approx(0.2, abs=0.01)
    assert v == pytest.approx(0.2, abs=0.01)


def test_box_at_the_antimeridian_contains_both_sides():
    fld = synthetic_field(make_key(179.9, 0.0, 1, T0), uniform=(0.5, 0.0))
    assert fld.contains(179.9, 0.0)
    assert fld.contains(-179.9, 0.0)
    assert fld.sample(-179.9, 0.0) == pytest.approx((0.5, 0.0))


def test_item_drifts_across_the_antimeridian_without_jumping():
    fld = synthetic_field(make_key(179.9, 0.0, 1, T0), uniform=(0.5, 0.0))
    out = engine.drift_item(engine.LitterItem("b", "bottle", 179.95, 0.0), fld, [], 1)
    assert out.final_status == "floating"
    assert out.samples[-1][1] == pytest.approx(180.338, abs=0.01)  # continuous, not wrapped to -179.66


@pytest.mark.parametrize("body", [
    {"placements": [bottle("a"), bottle("a")]},                                  # duplicate ids
    {"placements": [bottle("a", (0, 91))]},                                       # latitude out of range
    {"placements": [bottle("a", (181, 0))]},                                      # longitude out of range
    {"placements": [{"id": "c", "type": "collector", "coordinates": [0, 0]}]},    # no litter
    {"placements": []},                                                           # nothing at all
    {"placements": [bottle(f"b{i}") for i in range(51)]},                         # too many
    {"placements": [bottle("a")], "durationDays": 1.5},                           # fractional days
    {"placements": [bottle("a")], "durationDays": 0},
])
def test_bad_requests_are_rejected_before_any_work(body):
    response = client.post("/api/simulate", json=body)
    assert response.status_code == 422
    assert response.json()["code"] == "invalid_request"
```

- [ ] **Step 4: Run the whole suite**

Run: `.venv/Scripts/python -m pytest -q`
Expected: 25 passed. These are pins on existing behaviour, so they pass immediately. If one fails, the existing code has a real bug: fix it in the module that owns it before going on.

- [ ] **Step 5: Commit the baseline**

From the repo root:

```bash
git add .gitignore backend/pyproject.toml backend/README.md backend/app backend/scripts backend/tests
git status --short   # confirm no .env, .venv, caches or egg-info are staged
git commit -m "feat(backend): phase 0 and 1 - contract, fixtures, engine, endpoints on synthetic currents"
```

---

### Task 2: Real currents from Copernicus Marine

**Prerequisite (human):** `backend/.env` contains `COPERNICUSMARINE_SERVICE_USERNAME` and `COPERNICUSMARINE_SERVICE_PASSWORD`. Only the manual smoke step needs them.

**Files:**
- Modify: `backend/app/config.py` (one constant), `backend/app/sim/snapshot.py` (replace the `fetch_copernicus` stub and the cache section)
- Create: `backend/scripts/smoke_copernicus.py`
- Test: `backend/tests/test_copernicus.py`

**Interfaces:**
- Consumes: `SnapshotKey`, `Field`, `COMPONENTS`, `synthetic_field`, `config.COPERNICUS_DATASET_ID`, `config.COPERNICUS_TIMEOUT_S`.
- Produces (all in `app.sim.snapshot`):
  - `fetch_bounds(key) -> tuple[float, float, float, float]` as `(west, south, east, north)`, clamped to the map.
  - `field_from_dataset(ds, key) -> Field` (pure; `ds` is an xarray Dataset).
  - `fetch_copernicus(key) -> Field` (network; raises on any failure).
  - `load_field(key) -> Field`, same signature as before. Real fields are cached for the process lifetime; a synthetic fallback is reused for `config.SYNTHETIC_RETRY_S` seconds and then the real source is retried.
  - `_cache: dict[SnapshotKey, tuple[Field, float | None]]` and `_remember(key, fld, ttl=None) -> Field`, `_cached(key) -> Field | None`, `_fetch_with_timeout(key) -> Field | None` (Task 4 reuses these).

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_copernicus.py`:

```python
import sys
import time
import types
from datetime import UTC, datetime

import numpy as np
import pytest
import xarray as xr

from app import config
from app.sim import snapshot
from app.sim.snapshot import COMPONENTS, field_from_dataset, load_field, make_key, synthetic_field
from app.sim.snapshot import fetch_copernicus as real_fetch  # captured before the autouse patch

T0 = datetime(2026, 10, 3, 18, tzinfo=UTC)
KEY = make_key(10.2, -20.1, 1, T0)  # centre (10.0, -20.0), half-width 1.5


def fake_dataset(lon=(9.0, 10.0, 11.0)) -> xr.Dataset:
    """Three hourly slices around T0, one depth level, latitude descending."""
    times = np.array(["2026-10-03T17:00", "2026-10-03T18:00", "2026-10-03T19:00"], dtype="datetime64[ns]")
    lat = np.array([-19.0, -20.0, -21.0])
    lon = np.array(lon)
    shape = (3, 1, lat.size, lon.size)
    data = {}
    for name in COMPONENTS:
        values = np.zeros(shape, dtype="float32")
        if name == "uo":
            values[0], values[1], values[2] = 0.1, 0.2, 0.3  # differs per hour
            values[:, :, 0, 0] = np.nan                       # land at lat -19, first lon
        if name == "ustokes":
            values[:] = 0.05
        if name == "utide":
            values[:] = 9.0
        data[name] = (("time", "depth", "latitude", "longitude"), values)
    return xr.Dataset(data, coords={"time": times, "depth": [0.49], "latitude": lat, "longitude": lon})


def real_field(key=KEY):
    fld = synthetic_field(key, uniform=(0.2, 0.0))
    fld.source = "copernicus"
    return fld


def test_field_from_dataset_picks_nearest_hour_and_combines_components():
    fld = field_from_dataset(fake_dataset(), KEY)
    assert fld.source == "copernicus" and fld.key == KEY
    assert (fld.nx, fld.ny) == (3, 3)
    assert fld.lat[0] < fld.lat[-1]                              # flipped to ascending
    assert fld.sample(10.0, -20.0)[0] == pytest.approx(0.25)     # 18:00 slice: 0.2 + stokes 0.05, no tide
    assert fld.is_land(9.0, -19.0)
    assert not fld.is_land(10.0, -20.0)
    assert fld.components["utide"].shape == (1, 3, 3)
    assert float(fld.components["utide"][0, 1, 1]) == 9.0        # tide kept for later, not applied


def test_field_from_dataset_rejects_an_empty_grid():
    with pytest.raises(ValueError):
        field_from_dataset(fake_dataset(lon=(10.0,)), KEY)


def test_fetch_requests_the_box_the_hour_and_the_dataset(monkeypatch):
    calls = {}

    def open_dataset(**kwargs):
        calls.update(kwargs)
        return fake_dataset()

    monkeypatch.setitem(sys.modules, "copernicusmarine", types.SimpleNamespace(open_dataset=open_dataset))
    fld = real_fetch(KEY)
    assert fld.source == "copernicus"
    assert calls["dataset_id"] == config.COPERNICUS_DATASET_ID
    assert calls["variables"] == list(COMPONENTS)
    assert (calls["minimum_longitude"], calls["maximum_longitude"]) == (8.5, 11.5)
    assert (calls["minimum_latitude"], calls["maximum_latitude"]) == (-21.5, -18.5)
    assert calls["start_datetime"] == "2026-10-03T17:00:00"
    assert calls["end_datetime"] == "2026-10-03T19:00:00"


def test_fetch_box_is_clamped_at_the_antimeridian_and_pole():
    assert snapshot.fetch_bounds(make_key(179.9, 0.0, 1, T0)) == (178.5, -1.5, 180.0, 1.5)
    assert snapshot.fetch_bounds(make_key(-179.9, 0.0, 1, T0)) == (-180.0, -1.5, -178.5, 1.5)
    assert snapshot.fetch_bounds(make_key(0.0, 89.8, 1, T0))[3] == 90.0


def test_failed_fetch_falls_back_to_synthetic_and_is_reused_briefly(monkeypatch):
    calls = []

    def failing(key):
        calls.append(key)
        raise RuntimeError("down")

    monkeypatch.setattr(snapshot, "fetch_copernicus", failing)
    first = load_field(KEY)
    assert first.source == "synthetic"
    assert load_field(KEY) is first      # within the retry window: same field, no second fetch
    assert len(calls) == 1


def test_real_source_is_retried_after_the_window_and_recovers(monkeypatch):
    monkeypatch.setattr(config, "SYNTHETIC_RETRY_S", 0)
    assert load_field(KEY).source == "synthetic"            # the autouse fixture makes this fetch fail
    recovered = real_field()
    monkeypatch.setattr(snapshot, "fetch_copernicus", lambda key: recovered)
    assert load_field(KEY) is recovered


def test_real_snapshot_is_cached_for_the_process(monkeypatch):
    calls = []
    real = real_field()

    def fetch(key):
        calls.append(key)
        return real

    monkeypatch.setattr(snapshot, "fetch_copernicus", fetch)
    assert load_field(KEY) is real
    assert load_field(KEY) is real
    assert len(calls) == 1


def test_slow_fetch_times_out_to_synthetic(monkeypatch):
    def slow(key):
        time.sleep(0.5)
        return real_field()

    monkeypatch.setattr(snapshot, "fetch_copernicus", slow)
    monkeypatch.setattr(config, "COPERNICUS_TIMEOUT_S", 0.05)
    started = time.monotonic()
    assert load_field(KEY).source == "synthetic"
    assert time.monotonic() - started < 0.4
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/Scripts/python -m pytest tests/test_copernicus.py -q`
Expected: `ImportError: cannot import name 'field_from_dataset' from 'app.sim.snapshot'`.

- [ ] **Step 3: Implement the fetch**

In `backend/app/config.py`, add below `COPERNICUS_TIMEOUT_S = 20`:

```python
SYNTHETIC_RETRY_S = 60  # a fallback field is reused this long before Copernicus is tried again
```

In `backend/app/sim/snapshot.py`, add `import time` to the imports, then replace the `fetch_copernicus` stub with:

```python
_TIME_FORMAT = "%Y-%m-%dT%H:%M:%S"


def fetch_bounds(key: SnapshotKey) -> tuple[float, float, float, float]:
    """(west, south, east, north) to request, cut at the edge of the map.

    A box that crosses the antimeridian is fetched only up to +/-180; an item that
    reaches the cut becomes outside. Synthetic boxes are not cut.
    """
    hw = key.half_width_deg
    return (
        max(-180.0, key.centre_lon - hw),
        max(-90.0, key.centre_lat - hw),
        min(180.0, key.centre_lon + hw),
        min(90.0, key.centre_lat + hw),
    )


def field_from_dataset(ds, key: SnapshotKey) -> Field:
    """Turn an xarray Dataset covering the box into a single-slice Field."""
    if "depth" in ds.dims:
        ds = ds.isel(depth=0)
    target = np.datetime64(key.slice_time.astimezone(UTC).replace(tzinfo=None))
    ds = ds.sel(time=target, method="nearest").load()
    lon = ds["longitude"].values.astype("float64")
    lat = ds["latitude"].values.astype("float64")
    if lon.size < 2 or lat.size < 2:
        raise ValueError(f"Copernicus returned no usable grid for {key}")
    layers = {
        name: ds[name].transpose("latitude", "longitude").values.astype(np.float32) for name in COMPONENTS
    }
    if lat[0] > lat[-1]:
        lat = lat[::-1].copy()
        layers = {name: values[::-1, :] for name, values in layers.items()}
    components = {name: np.ascontiguousarray(values)[None] for name, values in layers.items()}
    return Field(key=key, source="copernicus", lon=lon, lat=lat, times=np.array([0.0]), components=components)


def fetch_copernicus(key: SnapshotKey) -> Field:
    """Download one box of hourly surface currents. Credentials come from the environment."""
    import copernicusmarine  # lazy: slow import, and tests substitute it

    west, south, east, north = fetch_bounds(key)
    ds = copernicusmarine.open_dataset(
        dataset_id=config.COPERNICUS_DATASET_ID,
        variables=list(COMPONENTS),
        minimum_longitude=west,
        maximum_longitude=east,
        minimum_latitude=south,
        maximum_latitude=north,
        start_datetime=(key.slice_time - timedelta(hours=1)).strftime(_TIME_FORMAT),
        end_datetime=(key.slice_time + timedelta(hours=1)).strftime(_TIME_FORMAT),
    )
    return field_from_dataset(ds, key)
```

Replace everything from the `# ---- in-process cache` comment to the end of the file with:

```python
# ---- in-process cache -------------------------------------------------------

# key -> (field, expiry). expiry is None for real snapshots, a time.monotonic() deadline for fallbacks.
_cache: dict[SnapshotKey, tuple[Field, float | None]] = {}
_lock = threading.Lock()
_pool = concurrent.futures.ThreadPoolExecutor(max_workers=4)


def _cached(key: SnapshotKey) -> Field | None:
    with _lock:
        entry = _cache.get(key)
    if entry is None:
        return None
    fld, expires = entry
    if expires is not None and time.monotonic() >= expires:
        return None
    return fld


def _remember(key: SnapshotKey, fld: Field, ttl: float | None = None) -> Field:
    with _lock:
        _cache[key] = (fld, None if ttl is None else time.monotonic() + ttl)
    return fld


def _fetch_with_timeout(key: SnapshotKey) -> Field | None:
    """Copernicus within the time budget. Network, auth, timeout or empty box: None."""
    future = _pool.submit(fetch_copernicus, key)
    try:
        return future.result(timeout=config.COPERNICUS_TIMEOUT_S)
    except Exception:
        log.warning("copernicus fetch failed for %s, using synthetic field", key, exc_info=True)
        return None


def load_field(key: SnapshotKey) -> Field:
    """Cached field for the key: Copernicus, or a synthetic gyre if that fails.

    A fallback is reused for SYNTHETIC_RETRY_S so one request sees one field per box,
    then the real source is tried again.
    """
    cached = _cached(key)
    if cached is not None:
        return cached
    fld = _fetch_with_timeout(key)
    if fld is None:
        return _remember(key, synthetic_field(key), ttl=config.SYNTHETIC_RETRY_S)
    return _remember(key, fld)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/Scripts/python -m pytest -q`
Expected: 33 passed.

- [ ] **Step 5: Smoke test against the real service**

Create `backend/scripts/smoke_copernicus.py`:

```python
"""Manual check that real currents arrive. Run from backend/:  python scripts/smoke_copernicus.py"""
import math
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.sim.snapshot import current_slice_time, fetch_copernicus, make_key  # noqa: E402

POINTS = {
    "North Pacific": (-140.2, 32.1),
    "Bay of Bengal": (88.3, 15.2),
    "Off Vancouver Island": (-126.4, 48.6),
    "Fiji, at the antimeridian": (179.9, -17.0),
}

for name, (lon, lat) in POINTS.items():
    key = make_key(lon, lat, 7, current_slice_time())
    started = time.monotonic()
    fld = fetch_copernicus(key)
    u, v = fld.sample(lon, lat)
    print(f"{name}: {time.monotonic() - started:.1f}s  grid {fld.nx}x{fld.ny}  "
          f"land {fld.land.mean():.0%}  speed {math.hypot(u, v):.2f} m/s")
```

Run: `.venv/Scripts/python scripts/smoke_copernicus.py`
Expected: four lines, each a few seconds, grid about `97x97` (the Fiji box is narrower because it is cut at 180), speed between 0 and 2 m/s. If a fetch takes longer than 20 s, raise `COPERNICUS_TIMEOUT_S` in `config.py` to 40. A credentials error means `backend/.env` needs fixing first.

Then start the server (`.venv/Scripts/python -m uvicorn app.main:app --port 8000`) and run:

```bash
curl -s -X POST http://localhost:8000/api/simulate -H "Content-Type: application/json" \
  -d '{"placements":[{"id":"bottle-1","type":"bottle","coordinates":[-140.2,32.1]}],"durationDays":7}' \
  | .venv/Scripts/python -c "import sys,json; d=json.load(sys.stdin); print(d['snapshots'], d['summary'])"
```

Expected: the snapshot shows `"source": "copernicus"`.

- [ ] **Step 6: Commit**

```bash
git add app/config.py app/sim/snapshot.py scripts/smoke_copernicus.py tests/test_copernicus.py
git commit -m "feat(backend): fetch real surface currents from Copernicus with timeout and retry"
```

---

### Task 3: Tiger Data schema and database module

**Prerequisite (human):** a Tiger Cloud service exists and `backend/.env` has `DATABASE_URL` set to its direct (non-pooled) connection string with `sslmode=require`. Only Step 6 needs it.

**Files:**
- Create: `backend/scripts/schema.sql`, `backend/scripts/init_db.py`, `backend/app/db.py`
- Test: `backend/tests/test_db_offline.py`

**Interfaces:**
- Consumes: `Field`, `SnapshotKey`, `COMPONENTS` from `app.sim.snapshot`; `SimulateRequest`, `SimulateResponse`, `TimelineBucket`, `TimelineResponse` from `app.schemas`; `config.DATABASE_URL`, `config.FRAME_INTERVAL_SECONDS`.
- Produces (all in `app.db`; `app.db` must never be imported at module level by `app.sim.snapshot`, which it imports):
  - `init_pool() -> bool`, `close_pool() -> None`, `available() -> bool`, `ping() -> bool`, `apply_schema() -> None`.
  - Pure helpers: `snapshot_rows(fld: Field)` yielding 12-tuples `(time, snapshot_id, ix, iy, lon, lat, uo, vo, utide, vtide, ustokes, vstokes)` with `None` for NaN; `field_from_rows(key, snapshot_id, nx, ny, nt, rows) -> Field | None` where each row is `(time, ix, iy, lon, lat, uo, vo, utide, vtide, ustokes, vstokes)`; `run_envelope(resp: SimulateResponse) -> dict` (the camelCase response without `trajectories`, with `persisted: true`); `position_rows(resp, start_time)` yielding `(time, run_id, item_id, litter_type, lon, lat, status)`; `run_from_rows(envelope: dict, start_time: datetime, rows) -> SimulateResponse` where each row is `(item_id, time, lon, lat, status)` ordered by item then time; `timeline_buckets(start_time, rows) -> list[TimelineBucket]` where each row is `(bucket, status, count)`.
  - Database functions: `save_snapshot(fld: Field) -> None`, `load_snapshot(key: SnapshotKey) -> Field | None`, `save_run(resp: SimulateResponse, req: SimulateRequest, start_time: datetime, parent_run_id: str | None) -> None`, `load_run(run_id: str) -> SimulateResponse | None`, `timeline(run_id: str) -> TimelineResponse | None`.

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
  start_time     TIMESTAMPTZ NOT NULL,   -- the slice hour; positions.time = start_time + timeSeconds
  parent_run_id  UUID,                   -- links a "with" run to its "without" twin
  duration_days  INT NOT NULL CHECK (duration_days BETWEEN 1 AND 30),
  params         JSONB NOT NULL,         -- the request body
  summary        JSONB NOT NULL,         -- the four status counts
  envelope       JSONB NOT NULL          -- the full response except trajectories
);

-- One row per item per recorded sample.
CREATE TABLE IF NOT EXISTS positions (
  time        TIMESTAMPTZ NOT NULL,
  run_id      UUID NOT NULL,
  item_id     TEXT NOT NULL,
  litter_type TEXT NOT NULL,
  lon         DOUBLE PRECISION NOT NULL,
  lat         DOUBLE PRECISION NOT NULL,
  status      TEXT NOT NULL
);
SELECT create_hypertable('positions', by_range('time'), if_not_exists => TRUE);
CREATE INDEX IF NOT EXISTS positions_run_idx ON positions (run_id, time);
```

`create_hypertable(..., if_not_exists => TRUE)` is used instead of the `WITH (timescaledb.hypertable)` clause so the script can be re-run safely.

- [ ] **Step 2: Write the failing tests for the pure helpers**

Create `backend/tests/test_db_offline.py`:

```python
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import numpy as np

from app import db
from app.schemas import SimulateResponse
from app.sim.snapshot import make_key, synthetic_field

T0 = datetime(2026, 10, 3, 18, tzinfo=UTC)
KEY = make_key(10.2, -20.1, 1, T0)  # centre (10.0, -20.0)
FIXTURE = Path(__file__).resolve().parents[1] / "scripts" / "fixtures" / "simulate_response.json"


def field_with_land():
    return synthetic_field(KEY, land=lambda lon, lat: lon > 11.0)


def as_selected(fld):
    """Rows as load_snapshot's SELECT returns them: without the snapshot_id column."""
    return [(r[0], *r[2:]) for r in db.snapshot_rows(fld)]


def test_snapshot_rows_cover_every_cell_and_store_land_as_null():
    fld = field_with_land()
    rows = list(db.snapshot_rows(fld))
    assert len(rows) == fld.nx * fld.ny
    first, last = rows[0], rows[-1]
    assert first[0] == T0 and first[1] == fld.snapshot_id and first[2:4] == (0, 0)
    assert isinstance(first[6], float)                 # uo in the south-west corner: water
    assert last[6] is None and last[7] is None         # uo, vo in the north-east corner: land


def test_snapshot_survives_a_round_trip_through_rows():
    fld = field_with_land()
    loaded = db.field_from_rows(KEY, fld.snapshot_id, fld.nx, fld.ny, 1, as_selected(fld))
    assert loaded.snapshot_id == fld.snapshot_id
    assert loaded.key == KEY and loaded.source == "copernicus"
    np.testing.assert_allclose(loaded.lon, fld.lon)
    np.testing.assert_allclose(loaded.lat, fld.lat)
    np.testing.assert_array_equal(loaded.land, fld.land)
    np.testing.assert_array_equal(loaded.u, fld.u)
    np.testing.assert_array_equal(loaded.v, fld.v)
    assert loaded.sample(10.2, -20.1) == fld.sample(10.2, -20.1)


def test_field_from_rows_rejects_a_partial_snapshot():
    fld = field_with_land()
    assert db.field_from_rows(KEY, fld.snapshot_id, fld.nx, fld.ny, 1, as_selected(fld)[:-5]) is None


def test_run_survives_a_round_trip_through_position_rows():
    original = SimulateResponse.model_validate(json.loads(FIXTURE.read_text()))
    envelope = db.run_envelope(original)
    assert "trajectories" not in envelope and envelope["persisted"] is True
    stored = sorted((r[2], r[0], r[4], r[5], r[6]) for r in db.position_rows(original, T0))
    loaded = db.run_from_rows(json.loads(json.dumps(envelope)), T0, stored)  # through JSON, as JSONB does
    assert loaded.model_dump() == {**original.model_dump(), "persisted": True}


def test_timeline_buckets_fold_status_counts_per_hour():
    rows = [
        (T0, "floating", 3),
        (T0 + timedelta(hours=1), "floating", 2),
        (T0 + timedelta(hours=1), "captured", 1),
    ]
    buckets = db.timeline_buckets(T0, rows)
    assert [b.time_seconds for b in buckets] == [0, 3600]
    assert (buckets[0].floating, buckets[0].captured) == (3, 0)
    assert (buckets[1].floating, buckets[1].captured, buckets[1].beached, buckets[1].outside) == (2, 1, 0, 0)


def test_database_is_unavailable_without_a_url():
    assert db.init_pool() is False
    assert db.available() is False
    assert db.ping() is False
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `.venv/Scripts/python -m pytest tests/test_db_offline.py -q`
Expected: `ImportError: cannot import name 'db' from 'app'`.

- [ ] **Step 4: Implement the database module**

Create `backend/app/db.py`:

```python
"""Tiger Data (TimescaleDB) access.

Callers check available() first and catch exceptions: a database problem must never
fail a simulation. app.sim.snapshot imports this module lazily, never at module level.
"""

import logging
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
from psycopg.types.json import Jsonb
from psycopg_pool import ConnectionPool

from app import config
from app.schemas import SimulateRequest, SimulateResponse, TimelineBucket, TimelineResponse
from app.sim.snapshot import COMPONENTS, Field, SnapshotKey

log = logging.getLogger(__name__)
SCHEMA_PATH = Path(__file__).resolve().parent.parent / "scripts" / "schema.sql"
STATUSES = ("floating", "captured", "beached", "outside")

_pool: ConnectionPool | None = None


# ---- connection -------------------------------------------------------------


def init_pool() -> bool:
    """Open the pool. False (and unavailable) when there is no URL or no connection."""
    global _pool
    if not config.DATABASE_URL:
        return False
    try:
        pool = ConnectionPool(config.DATABASE_URL, min_size=1, max_size=4, open=False, timeout=5)
        pool.open(wait=True, timeout=10)
        _pool = pool
        return True
    except Exception:
        log.warning("Tiger Data unavailable", exc_info=True)
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


# ---- pure helpers (unit tested without a database) --------------------------


def snapshot_rows(fld: Field):
    """One current_samples row per grid cell per slice. NaN becomes None."""
    lon, lat = fld.lon.tolist(), fld.lat.tolist()
    for k, offset in enumerate(fld.times.tolist()):
        t = fld.key.slice_time + timedelta(seconds=offset)
        layers = [fld.components[name][k].tolist() for name in COMPONENTS]
        for j, la in enumerate(lat):
            for i, lo in enumerate(lon):
                values = [layer[j][i] for layer in layers]
                yield (t, fld.snapshot_id, i, j, lo, la, *[None if v != v else v for v in values])


def field_from_rows(key: SnapshotKey, snapshot_id, nx: int, ny: int, nt: int, rows) -> Field | None:
    """Rebuild a Field from current_samples rows. None if the snapshot is incomplete."""
    if len(rows) != nx * ny * nt:
        return None
    offsets = sorted({(row[0] - key.slice_time).total_seconds() for row in rows})
    if len(offsets) != nt:
        return None
    slice_index = {offset: k for k, offset in enumerate(offsets)}
    lon, lat = np.zeros(nx), np.zeros(ny)
    components = {name: np.full((nt, ny, nx), np.nan, dtype=np.float32) for name in COMPONENTS}
    for time, ix, iy, lo, la, *values in rows:
        k = slice_index[(time - key.slice_time).total_seconds()]
        lon[ix], lat[iy] = lo, la
        for name, value in zip(COMPONENTS, values):
            if value is not None:
                components[name][k, iy, ix] = value
    return Field(key=key, source="copernicus", lon=lon, lat=lat, times=np.array(offsets),
                 components=components, snapshot_id=str(snapshot_id))


def run_envelope(resp: SimulateResponse) -> dict:
    """The response as stored in runs.envelope: everything except the trajectories."""
    envelope = resp.model_dump(by_alias=True, mode="json", exclude={"trajectories"})
    envelope["persisted"] = True
    return envelope


def position_rows(resp: SimulateResponse, start_time: datetime):
    """One positions row per sample."""
    for trajectory in resp.trajectories:
        for sample in trajectory.samples:
            yield (start_time + timedelta(seconds=sample.time_seconds), resp.run_id, trajectory.id,
                   trajectory.type, sample.coordinates[0], sample.coordinates[1], sample.status)


def run_from_rows(envelope: dict, start_time: datetime, rows) -> SimulateResponse:
    """Rebuild a response from its envelope and positions rows (item_id, time, lon, lat, status)."""
    samples: dict[str, list] = {}
    for item_id, time, lon, lat, status in rows:
        samples.setdefault(item_id, []).append({
            "timeSeconds": int((time - start_time).total_seconds()),
            "coordinates": [lon, lat],
            "status": status,
        })
    trajectories = [
        {"id": item["id"], "type": item["type"], "samples": samples.get(item["id"], [])}
        for item in envelope["items"]  # the envelope keeps the original item order
    ]
    return SimulateResponse.model_validate({**envelope, "trajectories": trajectories})


def timeline_buckets(start_time: datetime, rows) -> list[TimelineBucket]:
    """Fold (bucket, status, count) rows into one TimelineBucket per bucket."""
    folded: dict[int, dict] = {}
    for bucket, status, count in rows:
        seconds = int((bucket - start_time).total_seconds())
        folded.setdefault(seconds, dict.fromkeys(STATUSES, 0))[status] = count
    return [TimelineBucket(time_seconds=seconds, **counts) for seconds, counts in sorted(folded.items())]


# ---- snapshots --------------------------------------------------------------


def save_snapshot(fld: Field) -> None:
    key = fld.key
    with _pool.connection() as conn:
        inserted = conn.execute(
            """INSERT INTO snapshots (snapshot_id, centre_lon, centre_lat, half_width_deg,
                                      slice_time, n_slices, source, nx, ny)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
               ON CONFLICT DO NOTHING RETURNING snapshot_id""",
            (fld.snapshot_id, key.centre_lon, key.centre_lat, key.half_width_deg,
             key.slice_time, key.n_slices, fld.source, fld.nx, fld.ny),
        ).fetchone()
        if inserted is None:
            return  # another request stored this box first
        with conn.cursor() as cur:
            with cur.copy(
                """COPY current_samples (time, snapshot_id, ix, iy, lon, lat,
                                         uo, vo, utide, vtide, ustokes, vstokes) FROM STDIN"""
            ) as copy:
                for row in snapshot_rows(fld):
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
    return field_from_rows(key, snapshot_id, nx, ny, nt, rows)


# ---- runs -------------------------------------------------------------------


def save_run(resp: SimulateResponse, req: SimulateRequest, start_time: datetime,
             parent_run_id: str | None) -> None:
    with _pool.connection() as conn:  # one transaction
        conn.execute(
            """INSERT INTO runs (run_id, start_time, parent_run_id, duration_days, params, summary, envelope)
               VALUES (%s, %s, %s, %s, %s, %s, %s)""",
            (resp.run_id, start_time, parent_run_id, resp.duration_days,
             Jsonb(req.model_dump(by_alias=True, mode="json")),
             Jsonb(resp.summary.model_dump()),
             Jsonb(run_envelope(resp))),
        )
        with conn.cursor() as cur:
            with cur.copy(
                "COPY positions (time, run_id, item_id, litter_type, lon, lat, status) FROM STDIN"
            ) as copy:
                for row in position_rows(resp, start_time):
                    copy.write_row(row)


def load_run(run_id: str) -> SimulateResponse | None:
    with _pool.connection() as conn:
        run = conn.execute("SELECT start_time, envelope FROM runs WHERE run_id = %s", (run_id,)).fetchone()
        if run is None:
            return None
        rows = conn.execute(
            """SELECT item_id, time, lon, lat, status FROM positions
               WHERE run_id = %s ORDER BY item_id, time""",
            (run_id,),
        ).fetchall()
    return run_from_rows(run[1], run[0], rows)


def timeline(run_id: str) -> TimelineResponse | None:
    """Status counts per sample interval, computed in the database with time_bucket."""
    bucket_seconds = config.FRAME_INTERVAL_SECONDS
    with _pool.connection() as conn:
        run = conn.execute("SELECT start_time FROM runs WHERE run_id = %s", (run_id,)).fetchone()
        if run is None:
            return None
        rows = conn.execute(
            """SELECT time_bucket(%s * INTERVAL '1 second', time) AS bucket, status, count(*)
               FROM positions WHERE run_id = %s
               GROUP BY bucket, status ORDER BY bucket""",
            (bucket_seconds, run_id),
        ).fetchall()
    return TimelineResponse(run_id=str(run_id), bucket_seconds=bucket_seconds,
                            buckets=timeline_buckets(run[0], rows))
```

Create `backend/scripts/init_db.py`:

```python
"""Create the Tiger Data schema. Safe to re-run. Run from backend/:  python scripts/init_db.py"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import db  # noqa: E402

if not db.init_pool():
    sys.exit("Could not connect. Check DATABASE_URL in backend/.env")
db.apply_schema()
with db._pool.connection() as conn:
    tables = conn.execute(
        "SELECT hypertable_name FROM timescaledb_information.hypertables ORDER BY 1"
    ).fetchall()
print("hypertables:", [t[0] for t in tables])
db.close_pool()
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv/Scripts/python -m pytest -q`
Expected: 39 passed.

- [ ] **Step 6: Create the schema on the real service**

Run: `.venv/Scripts/python scripts/init_db.py`
Expected: `hypertables: ['current_samples', 'positions']`. Run it a second time: identical output, no error.

- [ ] **Step 7: Commit**

```bash
git add scripts/schema.sql scripts/init_db.py app/db.py tests/test_db_offline.py
git commit -m "feat(backend): Tiger Data schema and database module with two hypertables"
```

---

### Task 4: Persist runs, cache snapshots in Tiger, serve replay and timeline from it

**Files:**
- Modify: `backend/app/sim/snapshot.py` (`load_field` and two helpers), `backend/app/routes.py` (persistence, replay, timeline, health), `backend/app/main.py` (lifespan)
- Create: `backend/scripts/smoke.py`
- Test: `backend/tests/test_persistence.py`

**Interfaces:**
- Consumes: every `db` function from Task 3; `_cached`, `_remember`, `_fetch_with_timeout` in `snapshot` from Task 2.
- Produces:
  - `snapshot.load_field(key)` order: memory, Tiger, Copernicus (then stored in Tiger), synthetic. Synthetic fields are never stored.
  - `routes.build_response(req, fields, *, honour_collectors=True, parent_run_id=None)`; `persisted` is `True` only when `db.save_run` succeeded. Every run is also kept in the in-memory `_runs` store.
  - `GET /api/runs/{run_id}` and `/timeline`: Tiger first when available and the id is a UUID, the in-memory store otherwise, 404 `run_not_found` if neither has it.
  - `GET /api/health` reports the real `db` flag.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_persistence.py`:

```python
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import db
from app.main import app
from app.schemas import SimulateResponse, TimelineBucket, TimelineResponse
from app.sim import snapshot
from app.sim.snapshot import load_field, make_key, synthetic_field

client = TestClient(app)  # no "with": the lifespan does not run, so no real pool is opened

T0 = datetime(2026, 10, 3, 18, tzinfo=UTC)
KEY = make_key(10.2, -20.1, 1, T0)
RUN_ID = "00000000-0000-4000-8000-0000000000aa"
BODY = {"placements": [
    {"id": "bottle-1", "type": "bottle", "coordinates": [10.2, -20.1]},
    {"id": "collector-1", "type": "collector", "coordinates": [10.4, -20.1]},
], "durationDays": 1}
FIXTURE = Path(__file__).resolve().parents[1] / "scripts" / "fixtures" / "simulate_response.json"


def real_field():
    fld = synthetic_field(KEY, uniform=(0.2, 0.0))
    fld.source = "copernicus"
    return fld


@pytest.fixture
def fake_db(monkeypatch):
    """Pretend Tiger is connected and record what the app asks of it."""
    calls = {"runs": [], "snapshots": [], "lookups": []}
    monkeypatch.setattr(db, "available", lambda: True)
    monkeypatch.setattr(db, "ping", lambda: True)
    monkeypatch.setattr(db, "load_snapshot", lambda key: calls["lookups"].append(key))
    monkeypatch.setattr(db, "save_snapshot", lambda fld: calls["snapshots"].append(fld.key))
    monkeypatch.setattr(db, "save_run", lambda resp, req, start_time, parent_run_id:
                        calls["runs"].append((resp.run_id, parent_run_id, start_time)))
    monkeypatch.setattr(db, "load_run", lambda run_id: None)
    monkeypatch.setattr(db, "timeline", lambda run_id: None)
    return calls


def test_health_reports_no_database():
    assert client.get("/api/health").json() == {"ok": True, "db": False}


def test_health_reports_a_connected_database(fake_db):
    assert client.get("/api/health").json() == {"ok": True, "db": True}


def test_simulate_without_database_succeeds_unpersisted():
    data = client.post("/api/simulate", json=BODY).json()
    assert data["persisted"] is False
    assert client.get(f"/api/runs/{data['runId']}").json() == data


def test_simulate_persists_when_database_is_available(fake_db):
    data = client.post("/api/simulate", json=BODY).json()
    assert data["persisted"] is True
    run_id, parent, start_time = fake_db["runs"][0]
    assert (run_id, parent) == (data["runId"], None)
    assert start_time == datetime.fromisoformat(data["snapshots"][0]["sliceTime"])
    assert len(fake_db["runs"]) == 1


def test_compare_links_the_with_run_to_the_without_run(fake_db):
    data = client.post("/api/compare", json=BODY).json()
    assert [(r[0], r[1]) for r in fake_db["runs"]] == [
        (data["without"]["runId"], None),
        (data["with"]["runId"], data["without"]["runId"]),
    ]
    assert data["with"]["persisted"] is True


def test_database_failure_during_save_does_not_fail_the_request(fake_db, monkeypatch):
    def boom(*args):
        raise RuntimeError("connection lost")

    monkeypatch.setattr(db, "save_run", boom)
    response = client.post("/api/simulate", json=BODY)
    assert response.status_code == 200
    data = response.json()
    assert data["persisted"] is False
    assert client.get(f"/api/runs/{data['runId']}").json() == data  # still replayable from memory


def test_stored_snapshot_is_used_before_copernicus(fake_db, monkeypatch):
    stored = real_field()
    fetches = []
    monkeypatch.setattr(db, "load_snapshot", lambda key: stored)
    monkeypatch.setattr(snapshot, "fetch_copernicus", lambda key: fetches.append(key))
    assert load_field(KEY) is stored
    assert fetches == [] and fake_db["snapshots"] == []
    assert load_field(KEY) is stored  # now from memory


def test_fetched_snapshot_is_stored_in_tiger(fake_db, monkeypatch):
    fetched = real_field()
    monkeypatch.setattr(snapshot, "fetch_copernicus", lambda key: fetched)
    assert load_field(KEY) is fetched
    assert fake_db["lookups"] == [KEY]
    assert fake_db["snapshots"] == [KEY]


def test_synthetic_fallback_is_never_stored(fake_db):
    assert load_field(KEY).source == "synthetic"  # the autouse fixture blocks the fetch
    assert fake_db["snapshots"] == []


def test_snapshot_lookup_failure_falls_through_to_copernicus(fake_db, monkeypatch):
    def boom(key):
        raise RuntimeError("connection lost")

    fetched = real_field()
    monkeypatch.setattr(db, "load_snapshot", boom)
    monkeypatch.setattr(snapshot, "fetch_copernicus", lambda key: fetched)
    assert load_field(KEY) is fetched


def test_replay_is_served_from_tiger_when_it_has_the_run(fake_db, monkeypatch):
    stored = SimulateResponse.model_validate(json.loads(FIXTURE.read_text()))
    asked = []
    monkeypatch.setattr(db, "load_run", lambda run_id: asked.append(run_id) or stored)
    response = client.get(f"/api/runs/{RUN_ID}")
    assert response.status_code == 200
    assert response.json()["runId"] == stored.run_id
    assert asked == [RUN_ID]


def test_replay_falls_back_to_memory_when_tiger_lacks_the_run(fake_db):
    data = client.post("/api/simulate", json=BODY).json()
    assert client.get(f"/api/runs/{data['runId']}").json() == data


def test_replay_falls_back_to_memory_when_tiger_errors(fake_db, monkeypatch):
    data = client.post("/api/simulate", json=BODY).json()

    def boom(run_id):
        raise RuntimeError("connection lost")

    monkeypatch.setattr(db, "load_run", boom)
    assert client.get(f"/api/runs/{data['runId']}").json() == data


@pytest.mark.parametrize("run_id", [RUN_ID, "not-a-uuid"])
def test_unknown_run_is_404(fake_db, run_id):
    response = client.get(f"/api/runs/{run_id}")
    assert response.status_code == 404
    assert response.json()["code"] == "run_not_found"


def test_timeline_is_served_from_tiger(fake_db, monkeypatch):
    stored = TimelineResponse(run_id=RUN_ID, bucket_seconds=3600, buckets=[
        TimelineBucket(time_seconds=0, floating=7, captured=0, beached=0, outside=0)])
    monkeypatch.setattr(db, "timeline", lambda run_id: stored)
    data = client.get(f"/api/runs/{RUN_ID}/timeline").json()
    assert data == {"runId": RUN_ID, "bucketSeconds": 3600, "buckets": [
        {"timeSeconds": 0, "floating": 7, "captured": 0, "beached": 0, "outside": 0}]}


def test_timeline_falls_back_to_memory(fake_db):
    data = client.post("/api/simulate", json=BODY).json()
    timeline = client.get(f"/api/runs/{data['runId']}/timeline").json()
    assert len(timeline["buckets"]) == 25
    assert timeline["buckets"][0]["floating"] == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/Scripts/python -m pytest tests/test_persistence.py -q`
Expected: failures. With the fake database, `persisted` is still `False`, nothing is recorded in `fake_db`, health reports `db: False`, and the Tiger replay and timeline tests get 404.

- [ ] **Step 3: Put Tiger in front of Copernicus**

In `backend/app/sim/snapshot.py`, replace the `load_field` function with:

```python
def _load_stored(key: SnapshotKey) -> Field | None:
    from app import db  # lazy: db imports this module

    if not db.available():
        return None
    try:
        return db.load_snapshot(key)
    except Exception:
        log.warning("snapshot lookup failed for %s", key, exc_info=True)
        return None


def _store(fld: Field) -> None:
    from app import db  # lazy: db imports this module

    if not db.available():
        return
    try:
        db.save_snapshot(fld)
    except Exception:
        log.warning("snapshot save failed for %s", fld.key, exc_info=True)


def load_field(key: SnapshotKey) -> Field:
    """Field for the key: memory, then Tiger, then Copernicus, then a synthetic gyre.

    Real snapshots are stored in Tiger and cached for the process. A fallback is reused
    for SYNTHETIC_RETRY_S so one request sees one field per box, then the real sources
    are tried again. Fallbacks are never stored.
    """
    cached = _cached(key)
    if cached is not None:
        return cached
    fld = _load_stored(key)
    if fld is None:
        fld = _fetch_with_timeout(key)
        if fld is None:
            return _remember(key, synthetic_field(key), ttl=config.SYNTHETIC_RETRY_S)
        _store(fld)
    return _remember(key, fld)
```

- [ ] **Step 4: Persist and replay runs in the routes**

In `backend/app/routes.py`:

Add `import logging` above `import uuid`, change `from app import config` to `from app import config, db`, and add below `_runs: OrderedDict[...] = OrderedDict()`:

```python
log = logging.getLogger(__name__)
```

Replace the `_remember` function with:

```python
def _persist(resp: SimulateResponse, req: SimulateRequest, fields: dict[str, Field],
             parent_run_id: str | None) -> bool:
    """Store the run in Tiger. A database problem never fails the request."""
    if not db.available():
        return False
    start_time = next(iter(fields.values())).key.slice_time  # one slice time per run
    try:
        db.save_run(resp, req, start_time, parent_run_id)
        return True
    except Exception:
        log.warning("run save failed for %s", resp.run_id, exc_info=True)
        return False


def _remember(resp: SimulateResponse, req: SimulateRequest, fields: dict[str, Field],
              parent_run_id: str | None = None) -> None:
    resp.persisted = _persist(resp, req, fields, parent_run_id)
    _runs[resp.run_id] = resp  # memory copy: the fallback when Tiger is down
    while len(_runs) > MAX_STORED_RUNS:
        _runs.popitem(last=False)
```

Change the `build_response` signature to:

```python
def build_response(
    req: SimulateRequest, fields: dict[str, Field], *, honour_collectors: bool = True,
    parent_run_id: str | None = None,
) -> SimulateResponse:
```

and at its end change `_remember(resp)` to:

```python
    _remember(resp, req, fields, parent_run_id)
```

In `compare`, change the line building `with_` to:

```python
    with_ = build_response(req, fields, honour_collectors=True, parent_run_id=without.run_id)
```

Replace the `health` endpoint with:

```python
@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(ok=True, db=db.ping())
```

Replace `_get_run`, `get_run` and `get_timeline` (the last three definitions in the file) with:

```python
def _tiger_run_id(run_id: str) -> str | None:
    """The canonical UUID string when Tiger can be asked about this id, else None."""
    if not db.available():
        return None
    try:
        return str(uuid.UUID(run_id))
    except ValueError:
        return None


def _memory_run(run_id: str) -> SimulateResponse:
    resp = _runs.get(run_id)
    if resp is None:
        raise ApiError(404, "run_not_found", f"No run with id {run_id}")
    return resp


@router.get("/runs/{run_id}", response_model=SimulateResponse)
def get_run(run_id: str) -> SimulateResponse:
    tiger_id = _tiger_run_id(run_id)
    if tiger_id is not None:
        try:
            stored = db.load_run(tiger_id)
            if stored is not None:
                return stored
        except Exception:
            log.warning("run load failed for %s, trying memory", run_id, exc_info=True)
    return _memory_run(run_id)


@router.get("/runs/{run_id}/timeline", response_model=TimelineResponse)
def get_timeline(run_id: str) -> TimelineResponse:
    tiger_id = _tiger_run_id(run_id)
    if tiger_id is not None:
        try:
            stored = db.timeline(tiger_id)
            if stored is not None:
                return stored
        except Exception:
            log.warning("timeline query failed for %s, trying memory", run_id, exc_info=True)
    return timeline_of(_memory_run(run_id))
```

- [ ] **Step 5: Open the pool with the app**

In `backend/app/main.py`, add to the imports:

```python
from contextlib import asynccontextmanager

from app import config, db
```

(replacing the existing `from app import config` line), add above `create_app`:

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_pool()  # returns False and carries on when Tiger is unreachable
    yield
    db.close_pool()
```

and change the `FastAPI(...)` call to:

```python
    app = FastAPI(title="PlasticPaths simulation API", version="0.1.0", lifespan=lifespan)
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `.venv/Scripts/python -m pytest -q`
Expected: 56 passed.

Then regenerate the fixtures to prove the response shapes did not change:

Run: `.venv/Scripts/python scripts/make_fixtures.py && git status --short scripts/fixtures`
Expected: no output from `git status`. The script uses fixed ids, so the regenerated fixtures must be byte-identical. If any file shows as modified, a response shape changed: stop and fix the code, not the fixture.

- [ ] **Step 7: End-to-end smoke test against real Copernicus and real Tiger**

Create `backend/scripts/smoke.py`:

```python
"""Manual end-to-end check against a running server.
Start the server, then from backend/:  python scripts/smoke.py [base_url]"""
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
assert replay == run, "replay from Tiger differs from the original run"

timeline = client.get(f"/api/runs/{run['runId']}/timeline").json()
assert len(timeline["buckets"]) == 7 * 24 + 1, f"expected 169 hourly buckets, got {len(timeline['buckets'])}"
assert all(sum(b[k] for k in ("floating", "captured", "beached", "outside")) == 2 for b in timeline["buckets"])

started = time.monotonic()
client.post("/api/simulate", json=body)
print(f"second run (snapshots cached): {time.monotonic() - started:.1f}s")
print("PASS")
```

Start the server (`.venv/Scripts/python -m uvicorn app.main:app --port 8000`), then run `.venv/Scripts/python scripts/smoke.py`.
Expected: `health: {'ok': True, 'db': True}`, a compare time of a few seconds, both sources `copernicus`, `persisted: True`, a second run clearly faster than the first, and `PASS`.

Restart the server and run the smoke script again within the same clock hour.
Expected: `PASS`, and the first compare is fast because the snapshots now load from Tiger. Snapshots are keyed by the hour, so a fresh fetch after the hour rolls over is correct.

- [ ] **Step 8: Commit**

```bash
git add app/sim/snapshot.py app/routes.py app/main.py scripts/smoke.py tests/test_persistence.py
git commit -m "feat(backend): persist runs and snapshots in Tiger Data, replay and timeline from hypertables"
```

---

### Task 5: Handoff, container and Tiger polish

**Files:**
- Modify: `backend/README.md`
- Create: `backend/Dockerfile`, `backend/.dockerignore`, `backend/scripts/compression.sql`

**Interfaces:**
- Consumes: the running API from Tasks 1 to 4.
- Produces: a container image serving the API on `$PORT`, and the document the other streams integrate from.

- [ ] **Step 1: Update the README**

In `backend/README.md`, replace the `## Status` section (heading and bullets) with:

````markdown
## One-time setup for real data

```powershell
.venv\Scripts\python scripts\init_db.py          # creates the Tiger tables and hypertables
.venv\Scripts\python scripts\smoke_copernicus.py # proves the Copernicus credentials work
```

With no credentials at all the server still runs: currents are synthetic (`"source": "synthetic"`) and runs are kept in memory (`"persisted": false`).

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
  if (!response.ok) throw data;   // data.code is "on_land" (with placementId) or "invalid_request"
  return data;                    // data.trajectories is ParticleTrajectory[]
}
```

Use `data.totalSeconds` for the timeline length instead of the fixed `DURATION_SECONDS`. `interpolateFrame`, `trailGeoJson` and `particleGeoJson` work unchanged. Near the antimeridian a trajectory's longitude may run slightly past 180 so the trail stays continuous.

## How the simulation works

- When items are dropped, the backend fetches one hourly snapshot of surface currents for a box around each item from Copernicus Marine (`cmems_mod_glo_phy_anfc_merged-uv_PT1H-i`, about 9 km grid).
- Every item drifts through its own frozen snapshot for the same number of days (1 to 30) in 10-minute steps; positions are recorded hourly.
- An item stops when it reaches land (`beached`), enters a collector's radius (`captured`), or leaves its box (`outside`).
- Simplifications: one frozen time slice, no tide, no wind, no sinking or breakdown, all litter types drift alike.

## Tiger Data

Two hypertables do real work. `current_samples` caches every fetched snapshot, so drops in the same area and hour reuse it even across restarts. `positions` stores every recorded sample of every run and is what replay reads. The timeline endpoint is one `time_bucket` query:

```sql
SELECT time_bucket('1 hour', time) AS bucket, status, count(*)
FROM positions WHERE run_id = $1 GROUP BY bucket, status ORDER BY bucket;
```

Where each item started and ended, using `first` and `last`:

```sql
SELECT item_id, first(lon, time), first(lat, time), last(lon, time), last(lat, time), last(status, time)
FROM positions WHERE run_id = $1 GROUP BY item_id;
```

How much each collector placement helped, across every comparison ever run:

```sql
SELECT w.run_id, (w.summary->>'captured')::int - (o.summary->>'captured')::int AS extra_captured
FROM runs w JOIN runs o ON o.run_id = w.parent_run_id ORDER BY extra_captured DESC;
```
````

- [ ] **Step 2: Add the container files**

Create `backend/Dockerfile`:

```dockerfile
FROM python:3.13-slim
WORKDIR /app
COPY pyproject.toml .
COPY app ./app
RUN pip install --no-cache-dir -e .
COPY scripts ./scripts
ENV PORT=8000
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT}"]
```

The install is editable on purpose: `app/db.py` finds `scripts/schema.sql` relative to the source tree.

Create `backend/.dockerignore`:

```
.venv
.env
__pycache__
*.egg-info
.pytest_cache
.ruff_cache
tests
```

- [ ] **Step 3: Verify the container**

```bash
docker build -t plasticpaths-backend .
docker run --rm -p 8000:8000 --env-file .env plasticpaths-backend
```

In another terminal: `.venv/Scripts/python scripts/smoke.py`
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

Apply it once from the Tiger console SQL editor.
Expected: two policy job ids. Then rerun `.venv/Scripts/python scripts/smoke.py`; expected `PASS`.

- [ ] **Step 5: Final check and commit**

Run: `.venv/Scripts/python -m pytest -q`
Expected: 56 passed.

```bash
git add README.md Dockerfile .dockerignore scripts/compression.sql
git commit -m "docs(backend): integration README, container image and Tiger compression policy"
```

- [ ] **Step 6: Deploy (only when the team picks a host)**

On Render or Fly, create a web service from `backend/Dockerfile`, set the four variables from `.env.example` as secrets with `CORS_ORIGIN` set to the deployed frontend origin, then run `.venv/Scripts/python scripts/smoke.py https://<deployed-host>`.
Expected: `PASS`.

---

## Later, not in this plan

- **Multi-slice currents.** `Field` already has a `times` axis and picks the nearest slice; `SnapshotKey.n_slices`, `snapshot_rows` and `field_from_rows` already carry it. The change is: request `n_slices` hours in `fetch_copernicus`, keep every slice in `field_from_dataset`, and set `APPLY_TIDE = True`.
- **Antimeridian with real data.** Fetch the two halves of a crossing box and join them in the box's continuous longitude frame, instead of cutting at 180.
- **Item-specific drift.** Change the values in `config.DRIFT_FACTOR` and document the source.

