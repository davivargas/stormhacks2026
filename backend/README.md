# PlasticPaths backend (stream 3)

FastAPI service that drifts litter on ocean surface currents. The design is in
`docs/superpowers/specs/2026-10-03-simulation-tiger-data-design.md`; section 6 is the API contract.

## Setup (Windows, Python 3.12+)

```powershell
cd backend
py -3.13 -m venv .venv
.venv\Scripts\python -m pip install -e ".[dev]"
copy .env.example .env   # then fill in real values
```

## Run

```powershell
.venv\Scripts\python -m uvicorn app.main:app --reload --port 8000
```

Interactive docs at http://localhost:8000/docs.

## Test

```powershell
.venv\Scripts\python -m pytest
```

## Fixtures for the other streams

`scripts/fixtures/*.json` are canned responses in the exact API shapes (synthetic currents,
all four statuses). Regenerate after changing `app/schemas.py`:

```powershell
.venv\Scripts\python scripts\make_fixtures.py
```

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

## Latency

The first simulate for a new area in a given hour takes about 10 seconds, because a box of currents is fetched from Copernicus (boxes for items in different areas are fetched concurrently). Later runs in the same area and hour take under a second, and after a server restart about 3 seconds because the box is read back from Tiger. The frontend should show a loading state while a simulate or compare request is pending.

If Copernicus fails or exceeds its 30-second budget, the response still succeeds with synthetic currents (`"source": "synthetic"`), and Copernicus is not retried for 60 seconds.

## How the simulation works

- When items are dropped, the backend fetches one hourly snapshot of surface currents for a box around each item from Copernicus Marine (`cmems_mod_glo_phy_anfc_merged-uv_PT1H-i`, about 9 km grid).
- The dataset's wave-drift (Stokes) variables are named `vsdx` and `vsdy`; the backend requests those and treats them as the east and north wave-drift components.
- Every item drifts through its own frozen snapshot for the same number of days (1 to 30) in 10-minute steps; positions are recorded hourly.
- An item stops when it reaches land (`beached`), enters a collector's radius (`captured`), or leaves its box (`outside`).
- Simplifications: one frozen time slice, no tide, no wind, no sinking or breakdown, all litter types drift alike.

## Tiger Data

Two hypertables do real work. `current_samples` caches every fetched snapshot, so drops in the same area and hour reuse it even across restarts. `positions` stores every recorded sample of every run and is what replay reads. Replay and timeline are served from Tiger when it is connected and fall back to an in-memory copy when it is not. The timeline endpoint is one `time_bucket` query:

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

## Container

```bash
docker build -t plasticpaths-backend .
docker run --rm -p 8000:8000 --env-file .env plasticpaths-backend
```

The image serves the API on `$PORT` (default 8000). `.env` is not copied into the image; pass it at run time. `--env-file` passes values literally, so do not wrap values in quotes.

`scripts/compression.sql` holds an optional Tiger compression policy for the two hypertables.
