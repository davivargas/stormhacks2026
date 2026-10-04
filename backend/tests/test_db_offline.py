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


def test_slow_database_at_startup_is_retried_not_abandoned(monkeypatch):
    # Seen live: Tiger took longer than the open timeout once at startup, and the server then
    # stayed disconnected until a restart. The pool keeps connecting in the background; keep it.
    from psycopg_pool import PoolTimeout

    from app import config, db

    class SlowPool:
        check_connection = staticmethod(lambda conn: None)  # referenced when the pool is built

        def __init__(self, *args, **kwargs):
            self.closed = False

        def open(self, wait=True, timeout=None):
            raise PoolTimeout("pool initialization incomplete")

        def close(self):
            self.closed = True

    monkeypatch.setattr(config, "DATABASE_URL", "postgres://example.invalid/db")
    monkeypatch.setattr(db, "ConnectionPool", SlowPool)
    monkeypatch.setattr(db, "_pool", None)
    assert db.init_pool() is False
    assert isinstance(db._pool, SlowPool) and not db._pool.closed
    assert db.available() is False  # skipped during the cooldown
    monkeypatch.setattr(config, "DATABASE_RETRY_S", 0)
    db.report_failure()
    assert db.available() is True  # tried again after the cooldown
