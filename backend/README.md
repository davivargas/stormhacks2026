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

## Status

- Phase 0 and 1 done: contract, fixtures, engine, all endpoints on synthetic currents, runs kept in memory.
- Phase 2: `fetch_copernicus` in `app/sim/snapshot.py`.
- Phase 3: Tiger Data (`app/db.py`, `scripts/schema.sql`) replaces the in-memory run store.
