# PlasticPaths Stream 3: Simulation and Tiger Data

Date: 2026-10-03
Owner: Person 3 (numerical backend)
Status: draft for team review

## 1. Purpose

Stream 3 is the numerical backend of PlasticPaths. It turns "a litter item was dropped at this point on the ocean" into a stored, replayable path, and exposes that path and its summary counts to the other three streams over a small JSON API.

The goal for the weekend is to **illustrate litter moving on the ocean**, anywhere on Earth, using real current data and clearly labelled simplifications. It is not a validated drift forecast.

## 2. Agreed principles

These were settled in the design conversation and drive every choice below.

1. **Global.** A user can drop an item at any ocean point. No preset regions.
2. **Snapshot on drop.** When an item is placed, the backend fetches the currents around that point at that moment, once. That snapshot is the only environmental input for the item's whole path. Nothing is monitored or refreshed while the item drifts.
3. **One time slice for the MVP.** The snapshot is a single hourly field. The item drifts through a frozen picture of the currents. The code keeps a time axis so the final version can use 6 or 24 slices without touching the engine or the API.
4. **Lean.** No dependency, table, or endpoint that the other streams or a target track does not need.
5. **Honest labelling.** Every response carries the data source, the slice time, and the limitations, so Person 2 can show them in the parent/teacher panel.
6. **One timeline per run.** All items in a run start at hour zero and drift for the same number of days, each along its own route from its own snapshot. Items are never staggered in time.

## 3. Data source

**Copernicus Marine Service, Global Ocean Physics Analysis and Forecast, hourly surface currents.**

| Item | Value |
|---|---|
| Product | GLOBAL_ANALYSISFORECAST_PHY_001_024 |
| Dataset id | cmems_mod_glo_phy_anfc_merged-uv_PT1H-i (SMOC) |
| Grid | regular lat/lon, 1/12 degree (about 9 km) |
| Cadence | hourly, roughly two weeks back and ten days of forecast |
| Variables | uo, vo (circulation), utide, vtide (tide), ustokes, vstokes (wave drift) |
| Access | `copernicusmarine` Python toolbox, free account, credentials via env vars |

**Which components the MVP uses.** Circulation plus wave drift (uo + ustokes, vo + vstokes). Tide is fetched and stored but **not** applied, because a frozen tidal phase pushes everything one way for days and would be visibly wrong near coasts. Tide is switched on when the multi-slice version lands. This is one boolean in config.

**Land mask.** Cells where uo is NaN are land. No separate bathymetry dataset.

**Known limitation.** At about 9 km per cell, narrow inlets and harbours are one or two cells wide and will look wrong. Open and semi-open coasts look right. This goes in the limitations text.

**Fallback.** If the Copernicus fetch fails or times out, the backend builds a synthetic rotating gyre field centred on the drop point and marks the response `source: "synthetic"`. The UI can show a banner. The demo never dies because of a network call.

Why not SalishSeaCast: it covers only the Salish Sea. Why not HF radar or NOAA OFS: US coasts only. Why not HYCOM: no login needed but 3-hourly and lacks wave drift; it is the fallback source if a Copernicus account cannot be obtained.

## 4. Snapshot model

A **snapshot** is one fetched box of currents.

| Field | Meaning |
|---|---|
| snapshot_id | uuid |
| centre_lon, centre_lat | drop point rounded to the nearest 0.5 degree, to improve cache hits |
| half_width_deg | box half-width, derived from duration (see table) |
| slice_time | the hourly timestamp fetched, UTC. MVP: the run's start time rounded to the nearest available forecast hour. The same slice_time is used for every item in the run |
| n_slices | 1 for the MVP |
| source | `copernicus` or `synthetic` |
| grid | lon[nx], lat[ny], and arrays u_total[nt, ny, nx], v_total[nt, ny, nx], plus the six raw components |

**Box half-width by duration.** Duration is any whole number of days from 1 to 30. A 0.5 m/s current covers about 0.4 degrees per day, so:

```
half_width_deg = min(8.0, round_up_to_half_degree(1.0 + 0.4 * duration_days))
```

| Duration | Half-width | Cells (1/12 degree) | Approx size, 8 variables, float32 |
|---|---|---|---|
| 1 day | 1.5 degrees | 36 x 36 | 40 KB |
| 7 days | 4.0 degrees | 96 x 96 | 300 KB |
| 18 days or more | 8.0 degrees (cap) | 192 x 192 | 1.2 MB |

Rounding to half degrees keeps the number of distinct cache keys small. Beyond the cap a fast current can leave the box; that item becomes `outside`, which is a legitimate result. Cache key is (centre_lon, centre_lat, half_width_deg, slice_time, n_slices).

**Where snapshots live.** In Tiger Data (see section 7), plus an in-process dictionary for the current server lifetime. The engine loads a snapshot with one SELECT into NumPy arrays. There is no disk cache. If the database is unreachable the in-process cache still works and the response is marked `persisted: false`.

Each item in a run gets its own snapshot, because items may be dropped oceans apart. Items that round to the same centre share one.

## 5. Simulation engine

**Inputs.** The frontend's placement list exactly as it holds it (id, type, coordinates as [lon, lat]) where type is bottle, bag, foam, or collector; a collector radius; duration_days; and the snapshot for each litter item. One duration applies to the whole run: every item starts at hour zero and the timeline ends at `duration_days * 24` hours for all of them.

**Integration.** Forward Euler in lon/lat degrees.

```
u, v = field.sample(lon, lat, t)           # m/s, bilinear in space, nearest in time
lat += v * dt / 110_540
lon += u * dt / (111_320 * cos(radians(lat)))
```

| Parameter | Default | Why |
|---|---|---|
| Integration step dt | 10 min | accurate enough on a 9 km grid, 1 008 steps per week |
| Recorded frame | every 1 h | what goes over the wire; frontend interpolates between frames |
| Duration | integer days, 1 to 30, default 7 | 1 day is only one to four cells of movement on this grid; 30 days is a long clear route |
| Collection radius | 10 km default | 500 m would almost never capture on a 9 km grid |
| Drift factor per litter type | 1.0 for all three | PDF says identical drift unless documented; one dict to change later |

RK2 midpoint is a two-line upgrade if trails look jagged. Not in the MVP.

**Sampling rule.** Bilinear interpolation on the four surrounding cells. If the nearest cell is land, the item is beached. If some of the four cells are land but the nearest is water, land cells count as zero velocity.

**Status machine.** Each item is in exactly one state. Terminal states freeze the item at its last position.

| Status | Enter when | Terminal |
|---|---|---|
| floating | initial | no |
| beached | nearest grid cell is land | yes |
| captured | distance to any collection point <= radius (haversine) | yes |
| outside | position leaves the item's snapshot box | yes |

The four names match the frontend's `ParticleStatus` type in `src/types.ts`. Captured records which collector. Checks run every integration step in the order beached, captured, outside.

**Determinism.** No randomness anywhere. Same items plus same snapshots give the same frames. The before/after comparison therefore uses identical environmental inputs by construction.

**Validation.** A drop whose nearest cell is land is rejected with HTTP 422 and `code: "on_land"` before any simulation runs, so Person 2 can have the mascot say "that's land, try the water".

## 6. API

All JSON, served by FastAPI under `/api`. CORS open for the frontend origin. JSON keys are camelCase to match the frontend's TypeScript types (Pydantic alias generator); SQL stays snake_case.

| Method and path | Purpose | Consumer |
|---|---|---|
| GET /api/health | liveness, db reachable flag | ops |
| GET /api/meta | min, max and default duration_days, other defaults, attribution text, limitations text, litter types | Person 2 |
| GET /api/currents?lon&lat&durationDays | fetch or reuse the snapshot for that point and return downsampled arrows `[{coordinates, u, v, speed, bearing}]` plus snapshot metadata. `bearing` is degrees clockwise from north, which is what `currentGeoJson` already draws | Person 1 map overlay |
| POST /api/simulate | run one experiment, store it, return `trajectories` and summary | Person 1, Person 2 |
| POST /api/compare | run the same placements twice, once ignoring collectors and once honouring them, same snapshots; return `{without, with, delta}` where `without` and `with` are full simulate responses. The keys match the frontend's `ComparisonMode` | Person 4 (Gemini input), Person 2 (comparison card) |
| GET /api/runs/{runId} | replay a stored run: same shape as simulate response | Person 4, reload |
| GET /api/runs/{runId}/timeline | status counts per hour from a `time_bucket` query | Person 2 chart, Tiger track demo |

**POST /api/simulate request.** The `placements` array is the frontend's `Placement[]` unchanged.

```json
{
  "placements": [
    {"id": "bottle-1", "type": "bottle", "coordinates": [-125.3, 48.9]},
    {"id": "collector-1", "type": "collector", "coordinates": [-125.0, 48.8]}
  ],
  "durationDays": 7,
  "collectorRadiusM": 10000
}
```

**POST /api/simulate response.** The `trajectories` array is the frontend's `ParticleTrajectory[]` unchanged.

```json
{
  "runId": "uuid",
  "durationDays": 7,
  "totalSeconds": 604800,
  "sampleIntervalSeconds": 3600,
  "trajectories": [
    {
      "id": "bottle-1",
      "type": "bottle",
      "samples": [
        {"timeSeconds": 0, "coordinates": [-125.3, 48.9], "status": "floating"},
        {"timeSeconds": 3600, "coordinates": [-125.29, 48.9], "status": "floating"}
      ]
    }
  ],
  "items": [
    {"id": "bottle-1", "type": "bottle", "finalStatus": "captured", "capturedBy": "collector-1", "statusChangedAtSeconds": 133200}
  ],
  "collectors": [
    {"id": "collector-1", "coordinates": [-125.0, 48.8], "radiusM": 10000, "capturedCount": 1}
  ],
  "summary": {"floating": 0, "captured": 1, "beached": 0, "outside": 0},
  "snapshots": [
    {"snapshotId": "uuid", "source": "copernicus", "sliceTime": "2026-10-03T18:00:00Z", "nSlices": 1}
  ],
  "attribution": {
    "source": "Copernicus Marine Service, Global Ocean Physics Analysis and Forecast",
    "dataset": "cmems_mod_glo_phy_anfc_merged-uv_PT1H-i",
    "limitations": ["Single frozen time slice", "No tide in MVP", "No wind, sinking or breakdown", "About 9 km grid"]
  },
  "persisted": true
}
```

**Error shape.** `{"code": "on_land", "message": "That spot is land. Try the water!", "placementId": "bottle-1"}` with HTTP 422.

Payload size: 20 items for 30 days at hourly samples is about 14 400 samples, roughly 1 MB uncompressed and far less gzipped. Fine.

**Frontend contract notes.** Samples are hourly; the frontend's existing `interpolateFrame` already interpolates between samples, so scrubbing is smooth at any resolution. Terminal items repeat their final position in later samples so trails and counts need no special casing. `timeSeconds` is elapsed time from the run start, matching the frontend's timeline scale.

## 7. Tiger Data schema

Tiger Data is load-bearing: it is the snapshot cache and the run store, not a write-only audit log.

```sql
CREATE TABLE snapshots (
  snapshot_id    UUID PRIMARY KEY,
  centre_lon     DOUBLE PRECISION NOT NULL,
  centre_lat     DOUBLE PRECISION NOT NULL,
  half_width_deg DOUBLE PRECISION NOT NULL,
  slice_time     TIMESTAMPTZ NOT NULL,
  n_slices       INT NOT NULL DEFAULT 1,
  source         TEXT NOT NULL,              -- copernicus | synthetic
  nx INT NOT NULL, ny INT NOT NULL,
  created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (centre_lon, centre_lat, half_width_deg, slice_time, n_slices)
);

-- one row per grid cell per time slice; the engine loads a snapshot with one SELECT
CREATE TABLE current_samples (
  time        TIMESTAMPTZ NOT NULL,
  snapshot_id UUID NOT NULL,
  lon DOUBLE PRECISION NOT NULL, lat DOUBLE PRECISION NOT NULL,
  uo REAL, vo REAL, utide REAL, vtide REAL, ustokes REAL, vstokes REAL
) WITH (timescaledb.hypertable, timescaledb.partition_column = 'time');
CREATE INDEX ON current_samples (snapshot_id, time);

CREATE TABLE runs (
  run_id         UUID PRIMARY KEY,
  created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
  parent_run_id  UUID,                       -- links the "with" run to its "without" twin
  duration_days  INT NOT NULL CHECK (duration_days BETWEEN 1 AND 30),
  params         JSONB NOT NULL,             -- the request body
  summary        JSONB NOT NULL
);

CREATE TABLE run_items (
  run_id UUID NOT NULL, item_id TEXT NOT NULL,
  litter_type TEXT NOT NULL,
  start_lon DOUBLE PRECISION, start_lat DOUBLE PRECISION,
  snapshot_id UUID NOT NULL,
  final_status TEXT NOT NULL,
  captured_by TEXT,
  status_changed_at_seconds INT,
  PRIMARY KEY (run_id, item_id)
);

CREATE TABLE run_collection_points (
  run_id UUID NOT NULL, cp_id TEXT NOT NULL,
  lon DOUBLE PRECISION, lat DOUBLE PRECISION, radius_m DOUBLE PRECISION,
  captured_count INT NOT NULL DEFAULT 0,
  PRIMARY KEY (run_id, cp_id)
);

-- one row per item per recorded frame
CREATE TABLE positions (
  time    TIMESTAMPTZ NOT NULL,              -- run created_at + timeSeconds
  run_id  UUID NOT NULL,
  item_id TEXT NOT NULL,
  lon DOUBLE PRECISION NOT NULL, lat DOUBLE PRECISION NOT NULL,
  status  TEXT NOT NULL
) WITH (timescaledb.hypertable, timescaledb.partition_column = 'time');
CREATE INDEX ON positions (run_id, time);
```

**Writes.** Bulk via `COPY` (psycopg 3 `cursor.copy`). A 144 x 144 snapshot is about 21 000 rows and a week-long 20-item run is about 3 400 rows; both well under a second.

**Showcase queries for the Tiger track**

- `/runs/{id}/timeline`: `time_bucket('1 hour', time)` grouped by status.
- Start and end per item: `first(lon, time)`, `last(lon, time)`.
- Compression policy on `positions` and `current_samples` after 1 day (one SQL statement each). Optional, phase 4.

**Sizing.** Free plan is 750 MiB per service. Snapshots dominate: about 2 MB per 192 x 192 snapshot as rows before compression. Hundreds of runs fit comfortably for the weekend.

## 8. Repository layout

The repo root is the Vite frontend (`src/`, `package.json`). The backend lives in `backend/` at the root with its own env file and dependencies, so neither side's tooling touches the other.

```
backend/
  pyproject.toml              fastapi, uvicorn, numpy, scipy, psycopg[binary], copernicusmarine, xarray
  .env.example                COPERNICUSMARINE_SERVICE_USERNAME/PASSWORD, DATABASE_URL, CORS_ORIGIN
  app/
    main.py                   app factory, CORS, router include, startup db pool
    config.py                 constants: durations, half-widths, dt, frame interval, components used
    schemas.py                pydantic models = the API contract
    routes.py                 the seven endpoints
    sim/
      snapshot.py             SnapshotKey, fetch_copernicus(), synthetic_field(), Field.sample()
      engine.py               run(items, cps, duration, fields) -> frames, item results, summary
      geo.py                  haversine, metres-per-degree helpers
    db.py                     pool, get_or_create_snapshot, save_run, load_run, timeline
  scripts/
    schema.sql
    init_db.py                applies schema.sql
    fixtures/simulate_response.json   canned response for the frontend, produced in phase 0
  tests/
    test_engine.py
    test_snapshot.py
  Dockerfile
```

## 9. Error handling

| Situation | Behaviour |
|---|---|
| Copernicus fetch fails or exceeds 20 s | synthetic field, `source: "synthetic"`, HTTP 200 |
| Drop point on land | HTTP 422, `code: "on_land"` |
| durationDays not an integer in 1 to 30 | HTTP 422 |
| More than 50 litter placements | HTTP 422 |
| Database unreachable | simulation still runs from in-process cache, `persisted: false`; `/runs/{id}` returns 503 |
| Unknown run id | HTTP 404 |

## 10. Testing

Three engine tests on synthetic fields, no network, no database.

1. Uniform eastward field at 0.5 m/s for 24 h moves an item about 43 km east and leaves it floating.
2. A field pointing at a land cell beaches the item, and later samples repeat the beached position.
3. An item passing within 10 km of a collection point is captured once, credited to that point, and the summary counts match.

One snapshot test: the synthetic field builder returns arrays of the right shape with NaN land where requested.

Fetching from Copernicus and writing to Tiger are verified by hand with a smoke script, not unit tests.

## 11. Build order

| Phase | Hours | Deliverable | Unblocks |
|---|---|---|---|
| 0 | 0 to 1 | `schemas.py` plus `fixtures/simulate_response.json` committed, with `trajectories` in the exact `ParticleTrajectory` shape; API table shared with the team | Persons 1, 2, 4 start immediately |
| 1 | 1 to 4 | synthetic field, `Field.sample`, engine, status machine, three tests green, `/simulate` serving synthetic data | Person 1 integrates for real |
| 2 | 4 to 7 | Copernicus account, `fetch_copernicus`, `/currents` arrows, land validation | real data on the map |
| 3 | 7 to 11 | Tiger service, schema, snapshot cache in db, `save_run`, `/runs/{id}`, `/timeline`, `/compare` | Person 4 has comparison objects, Tiger track story |
| 4 | remainder | Dockerfile and deploy, compression policy, RK2 if needed, multi-slice flag end to end if time allows | polish |

## 12. Interfaces with the other streams

- **Person 1 (map).** Replaces `buildTrajectories()` in `src/simulation.ts` with a call to `POST /api/simulate` and uses the response's `trajectories` directly; `interpolateFrame`, `trailGeoJson` and `particleGeoJson` work unchanged. Reads `totalSeconds` from the response instead of the fixed `DURATION_SECONDS` constant. Uses `bearing` from `/currents` in `currentGeoJson`. Drops the Vancouver `REGION_BOUNDS` and `PLAYABLE_WATER` gating once the backend's `on_land` error is wired, because the map is global.
- **Person 2 (UI).** Needs `summary`, `items`, `attribution` and `/meta` for the parent panel, and the 422 `on_land` message.
- **Person 4 (AI).** Needs the `/compare` response as the structured input to Gemini: both summaries, the delta, per item final statuses and timings, and the attribution block so explanations cite the source.

## 13. Out of scope for the MVP

Multi-slice currents, tide component, wind, item-specific drift, Shapely coastlines, streaming or polling, authentication, rate limiting, any region presets.

## 14. Open items

- Copernicus Marine account to be created by one team member; credentials go in the deployment env, never in the repo.
- Tiger Cloud free service to be created; connection string in the deployment env.
- Organiser confirmation that one project may enter the Python, Tiger Data, and other tracks together.
