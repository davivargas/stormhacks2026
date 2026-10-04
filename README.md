# LitterVoyage

A kid-friendly ocean litter simulation built with React, TypeScript, Vite, Mapbox GL JS, and Mapbox Studio.

## Start locally

Run both the backend and frontend from one terminal:

```bash
./start-dev.sh
```

The launcher requires Python 3.12+, Node.js/npm, and Linux's `setsid` command.
On first launch it creates `backend/.venv` and installs missing backend/frontend
dependencies. It uses one backend worker with reload, starts the frontend on
http://localhost:5173 and the API on http://localhost:8000, and stops both servers
when you press Ctrl+C. API documentation is at http://localhost:8000/docs.
Configure Mapbox in the root `.env` or `.env.local`; optional backend credentials
belong in `backend/.env`. The launcher does not create or overwrite environment
files. Both servers share the terminal's log output.

If a port is already occupied, the launcher exits before starting either server.
Choose another backend port with:

```bash
BACKEND_PORT=8001 ./start-dev.sh
```

You can also set `FRONTEND_PORT=5174`. The launcher automatically points Vite's
`VITE_API_BASE_URL` at the selected backend port and sets the default backend CORS
origins to the selected frontend port.

To run just the frontend:

```bash
npm install
cp .env.example .env.local
npm run dev
```

Add a Mapbox public token and your published Studio style URL to `.env.local`. Without credentials, the application displays a styled preview so the surrounding interface can still be developed.

## Mapbox Studio style

Create a style based on Mapbox Standard and configure it for the LitterVoyage visual language:

- Water: `#73DDE5`
- Land: `#B7E88A`
- Greenspace: `#8DD779`
- Labels: `#173B50`
- Hide POI, road, transit, 3D, and administrative clutter
- Keep only useful regional labels

Publish the style and put its `mapbox://styles/...` URL in `VITE_MAPBOX_STYLE_URL`.

## Current prototype

- Full-viewport responsive map layout
- Mapbox GeoJSON sources for particles, trails, and cleanup zones
- Worldwide ocean-only placement using Mapbox coastline water geometry
- Bottle, bag, foam, cleanup, and removal tools
- Play, pause, restart, and timeline scrubbing
- Placement-time-aware trajectories that begin when an item is added
- Floating, captured, beached, and outside-region counts
- Keyboard focus states and reduced-motion support
- Backend-calculated trajectories from `POST /api/simulate`
- Loading, retry, and land-validation feedback
- Actual snapshot sources, dates, final results, and limitations in Data & assumptions

## Playback integration

Set `VITE_API_BASE_URL` to the API address (for example `http://localhost:8001`).
The launcher sets it automatically for its chosen backend port. When running
servers separately, run the frontend with:

```bash
VITE_API_BASE_URL=http://localhost:8001 npm run dev -- --port 5173 --strictPort
```

Placing or removing an item sends a new simulation request with
`{placements, durationDays: 10, honourCollectors: true}` to `/api/simulate`.
Each placement includes `placedAtSeconds` on the shared experiment timeline;
the experiment ends at ten days (864,000 seconds). An item placed on day three
drifts only during the remaining seven days. The slider uses the backend's
`totalSeconds`, displays days/hours/minutes, and retains five-minute scrubbing.
Pause, resume, and scrubbing use the downloaded trajectories without additional
simulation requests. Restart returns playback and narration to the beginning.

The shared frontend duration is defined in `src/timeline.ts`. Without narration,
ten days play in about 72 real seconds at the current speed. With narration,
timeline progress and scrubbing map to the audio's duration. Each area uses one
frozen current snapshot: this is an educational ten-day experiment, not a
changing ten-day forecast.

Backend synthetic-current fallback is explicitly labelled. A failed API request
never substitutes frontend mock movement. Snapshot source and date, storage
status, final totals, and assumptions are available in Data & assumptions.

After updating an existing database, run the idempotent initialization script
to add the item/time lookup index used by placement-aware timeline queries:

```bash
cd backend
.venv/bin/python scripts/init_db.py
```

## Verification

```bash
npm test
npm run lint
npm run build
```

Backend tests (run from `backend/`):

```bash
.venv/bin/python -m pytest -q
```

## Deploy on Railway

Deploy the frontend and backend as two services in the same Railway project.

### Backend service

- Connect the GitHub repository and set the service root directory to `/backend`.
- Railway detects `backend/Dockerfile` automatically.
- Generate a public domain for the service.
- Set `CORS_ORIGIN` to the frontend's Railway URL, for example:
  `https://your-frontend.up.railway.app`.
- Add optional `GEMINI_API_KEY`, `ELEVENLABS_API_KEY`, and
  `ELEVENLABS_VOICE_ID` variables if live stories and narration are enabled.
- Set `RETRIEVAL_MODE=local` for the bundled educational passages, or configure
  the TiDB variables before selecting `tidb`.

The backend health check is available at `/health`.

### Frontend service

- Add a second service from the same repository with the root directory left at `/`.
- Railway detects the root `Dockerfile`, which builds the Vite app and serves it
  with Nginx.
- Set these variables on the frontend service before deploying:

```text
VITE_API_BASE_URL=https://your-backend.up.railway.app
VITE_MAPBOX_ACCESS_TOKEN=your_public_mapbox_token
VITE_MAPBOX_STYLE_URL=mapbox://styles/your-account/your-style
```

The frontend container listens on Railway's injected `PORT` and includes an
SPA fallback so direct routes continue to load correctly. Because Vite embeds
`VITE_*` values at build time, redeploy the frontend after changing them.

After both services deploy, replace the placeholder backend and frontend
domains in the variables with the generated Railway domains and redeploy both
services once.
