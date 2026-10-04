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

Place litter and press Play. The app fetches settings from `/api/meta`, then sends
`{placements, durationDays: 1, collectorRadiusM, honourCollectors: true}` to
`/api/simulate`. Each placement includes `placedAtSeconds` on the shared experiment
timeline; all particles stop at the one-day endpoint. Pause, resume, and scrubbing
use the downloaded result without further requests. Editing pauses playback and
the next Play recalculates. Reset cancels pending work and clears the map.

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
