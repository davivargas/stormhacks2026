"""Tiger Data (TimescaleDB) access.

Callers check available() first and catch exceptions: a database problem must never
fail a simulation. app.sim.snapshot imports this module lazily, never at module level.
"""

import logging
import time
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
from psycopg.types.json import Jsonb
from psycopg_pool import ConnectionPool, PoolTimeout

from app import config
from app.schemas import SimulateRequest, SimulateResponse, TimelineBucket, TimelineResponse
from app.sim.snapshot import COMPONENTS, Field, SnapshotKey

log = logging.getLogger(__name__)
SCHEMA_PATH = Path(__file__).resolve().parent.parent / "scripts" / "schema.sql"
STATUSES = ("floating", "captured", "beached", "outside")

_pool: ConnectionPool | None = None
# Until this time.monotonic() deadline the database is skipped: one error covers every caller.
_down_until: float = 0.0


# ---- connection -------------------------------------------------------------


def init_pool() -> bool:
    """Open the pool. False (and unavailable) when there is no URL or no connection."""
    global _pool, _down_until
    if not config.DATABASE_URL:
        return False
    try:
        pool = ConnectionPool(
            # min_size=2: a background snapshot upload (~58k rows, ~11 s) holds one connection, so keep
            # a second one open; opening a new TLS connection during that upload measured 2 to 5+ s.
            config.DATABASE_URL, min_size=2, max_size=4, open=False, timeout=10,
            check=ConnectionPool.check_connection,  # replace a connection Tiger dropped while idle
        )
    except Exception:
        log.warning("Tiger Data unavailable", exc_info=True)
        _pool = None
        return False
    try:
        pool.open(wait=True, timeout=10)
    except PoolTimeout:
        # Slow to connect, not broken: the pool keeps connecting in the background. Keep it and
        # let the cooldown retry it, instead of staying disconnected until the server restarts.
        log.warning("Tiger Data slow to connect at startup; will retry", exc_info=True)
        _pool = pool
        report_failure()
        return False
    except Exception:
        log.warning("Tiger Data unavailable", exc_info=True)
        pool.close()
        _pool = None
        return False
    _pool = pool
    _down_until = 0.0
    return True


def close_pool() -> None:
    global _pool, _down_until
    if _pool is not None:
        _pool.close()
        _pool = None
    _down_until = 0.0


def report_failure() -> None:
    """A database call failed: skip the database for DATABASE_RETRY_S instead of waiting on it every time."""
    global _down_until
    _down_until = time.monotonic() + config.DATABASE_RETRY_S
    log.warning("database error, skipping it for %s seconds", config.DATABASE_RETRY_S)


def available() -> bool:
    return _pool is not None and time.monotonic() >= _down_until


def ping() -> bool:
    if not available():
        return False
    try:
        with _pool.connection() as conn:
            conn.execute("SELECT 1")
        return True
    except Exception:
        report_failure()
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
