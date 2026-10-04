# PlasticPaths backend (stream 3)

FastAPI service that drifts litter on ocean surface currents. The design is in
`docs/superpowers/specs/2026-10-03-simulation-tiger-data-design.md`. The API contract is what
`scripts/fixtures/*.json` and http://localhost:8000/docs show (the spec's section 6 text is older).

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

Run a single uvicorn worker (do not pass `--workers`): the run store and the snapshot cache live in the process.

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

With no credentials at all the server still runs: currents are synthetic (`"source": "synthetic"`, used immediately, with no wait for Copernicus) and runs are kept in memory (`"persisted": false`).

## Storytelling and narration

The same FastAPI app also serves the educational story flow:

- `POST /api/stories` accepts a normalized simulation summary and returns a 50–80 word script.
- `POST /api/stories/{story_id}/audio` creates or reuses ElevenLabs narration.
- `GET /api/stories/{story_id}/audio/content` serves the generated audio file.

With `RETRIEVAL_MODE=local`, facts come from the bundled educational passages. Without a Gemini key,
the endpoint returns a deterministic fallback story. Audio returns `503` until both
`ELEVENLABS_API_KEY` and `ELEVENLABS_VOICE_ID` are configured. To use TiDB vector retrieval, apply
`sql/schema.sql`, run `plasticpaths-seed-tidb`, and set `RETRIEVAL_MODE=tidb` with the Gemini and
TiDB variables from `.env.example`.

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

## Requests

- `POST /api/simulate` takes `{placements, durationDays, collectorRadiusM, honourCollectors}`. `collectorRadiusM` is optional (default 10000 m). `honourCollectors` is optional and defaults to `false`: collectors are listed in the response with `capturedCount: 0` but do not capture anything. Send `true` to let them capture litter.
- `POST /api/compare` takes the same body and returns `{without, with, delta}`: `without` ignores the collectors, `with` honours them, and `delta` is `with` minus `without` for the four status counts.
- `sessionId` is an optional field on both bodies: 1 to 64 characters of `A-Z a-z 0-9 _ -`, one value per browser tab. It is stored with the run.
- `DELETE /api/sessions/{sessionId}/runs` deletes every run saved with that `sessionId`, in memory and in Tiger Data (`runs` and `positions`). It returns `{deleted, database}`, where `database` is `cleared`, `unavailable` (no database configured) or `failed` (the database is configured but the delete did not happen). Cached current snapshots are kept.
- Limits per run: at most 50 litter items, 20 collectors and 8 distinct areas (half-degree boxes); durations of 1 to 30 whole days. Breaking a limit is a 422 `invalid_request`.

## Latency

A snapshot (one box of currents) is reused when the drop point rounds to the same half-degree centre, in the same clock hour, and the run's duration needs a box no larger than one already fetched this session. The hour used is the nearest hour, so it rolls over at half past. Going from a longer duration to a shorter one is therefore instant, and going to a longer one fetches again. Otherwise the first request takes about 5 to 12 seconds, because the box is sliced from Copernicus (boxes for items in different areas are fetched concurrently). The server opens the Copernicus dataset once at startup, which takes about 8 seconds in the background, and keeps it open; box size makes little difference to the fetch time. If a fetch takes longer than 30 seconds the response uses synthetic currents, and the real box is kept as soon as it arrives, so the next request uses it. Later runs that reuse a snapshot take under a second, and after a server restart about 3 seconds when the exact box is read back from Tiger (boxes up to 10 degrees; larger ones are refetched from Copernicus). To warm up the demo spot, run it once at the longest duration you will show, after half past the hour. The frontend should show a loading state while a simulate or compare request is pending.

If Copernicus fails or exceeds its 30-second budget, the response still succeeds with synthetic currents (`"source": "synthetic"`), and Copernicus is not retried for 60 seconds. A fetch that finishes after the budget is still kept and stored, so the next request in that area gets real currents. If Tiger errors, it is skipped for 60 seconds and runs stay in memory.

## How the simulation works

- When items are dropped, the backend fetches one hourly snapshot of surface currents for a box around each item from Copernicus Marine (`cmems_mod_glo_phy_anfc_merged-uv_PT1H-i`, about 9 km grid).
- The dataset's wave-drift (Stokes) variables are named `vsdx` and `vsdy`; the backend requests those and treats them as the east and north wave-drift components.
- Every item drifts through its own frozen snapshot for the same number of days (1 to 30) in 10-minute steps; positions are recorded hourly.
- An item stops when it reaches land (`beached`), enters a collector's radius (`captured`), or leaves its box (`outside`).
- The box is sized for currents of about 1 m/s: its half-width is 0.8 degrees per day of duration plus 0.5, rounded up to half a degree (1 day = 1.5, 7 days = 6.5, 30 days = 24.5). A 1 m/s current covers 0.78 degrees of latitude a day, and about 1 degree of longitude a day at 40 degrees north, so only an item that stays in a jet faster than that for the whole run can still end `outside`.
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

`scripts/retention.sql` drops cached currents older than two days. Only boxes up to 10 degrees (runs of up to 11 days) are cached in Tiger; bigger ones would be hundreds of thousands of rows each and are quicker to refetch than to store. A 10-degree box is about 58,000 rows (~7 MB before compression) and every new area-hour stores one, so without this script the 750 MiB free tier fills after roughly a hundred area-hours. Snapshots from past hours are never read again, so nothing the app uses is lost; runs are not touched. Apply it once from the Tiger console SQL editor.

Storing a new box in Tiger happens in the background and takes about 10 seconds for a 10-degree box; it never delays a response. Runs of any size are always stored.
