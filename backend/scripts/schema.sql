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
