# PlasticPaths

A kid-friendly ocean litter simulation built with React, TypeScript, Vite, Mapbox GL JS, and Mapbox Studio.

## Start locally

```bash
npm install
cp .env.example .env.local
npm run dev
```

Add a Mapbox public token and your published Studio style URL to `.env.local`. Without credentials, the application displays a styled preview so the surrounding interface can still be developed.

## Mapbox Studio style

Create a style based on Mapbox Standard and configure it for the PlasticPaths visual language:

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
- Ocean-only placement using Mapbox coastline water geometry
- Bottle, bag, foam, cleanup, and removal tools
- Play, pause, restart, and timeline scrubbing
- Placement-time-aware trajectories that begin when an item is added
- With/without cleanup comparison
- Floating, captured, beached, and outside-region counts
- Keyboard focus states and reduced-motion support
- Mock trajectories isolated in `src/simulation.ts` for later FastAPI replacement

## Backend handoff

Replace `buildTrajectories()` with data from the planned FastAPI endpoints. Preserve coordinates as `[longitude, latitude]`, timestamps as elapsed seconds, and the four existing particle statuses.
