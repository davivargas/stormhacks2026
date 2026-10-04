import sys
import time
import types
from datetime import UTC, datetime

import numpy as np
import pytest
import xarray as xr

from app import config
from app.sim import snapshot
from app.sim.snapshot import COMPONENTS, field_from_dataset, load_field, make_key, synthetic_field
from app.sim.snapshot import fetch_copernicus as real_fetch  # captured before the autouse patch

T0 = datetime(2026, 10, 3, 18, tzinfo=UTC)
KEY = make_key(10.2, -20.1, 1, T0)  # centre (10.0, -20.0), half-width 1.5


def fake_dataset(lon=(9.0, 10.0, 11.0)) -> xr.Dataset:
    """Three hourly slices around T0, one depth level, latitude descending."""
    times = np.array(["2026-10-03T17:00", "2026-10-03T18:00", "2026-10-03T19:00"], dtype="datetime64[ns]")
    lat = np.array([-19.0, -20.0, -21.0])
    lon = np.array(lon)
    shape = (3, 1, lat.size, lon.size)
    data = {}
    for name in ("uo", "vo", "utide", "vtide", "vsdx", "vsdy"):  # the dataset's own variable names
        values = np.zeros(shape, dtype="float32")
        if name == "uo":
            values[0], values[1], values[2] = 0.1, 0.2, 0.3  # differs per hour
            values[:, :, 0, 0] = np.nan                       # land at lat -19, first lon
        if name == "vsdx":
            values[:] = 0.05
        if name == "utide":
            values[:] = 9.0
        data[name] = (("time", "depth", "latitude", "longitude"), values)
    return xr.Dataset(data, coords={"time": times, "depth": [0.49], "latitude": lat, "longitude": lon})


def real_field(key=KEY):
    fld = synthetic_field(key, uniform=(0.2, 0.0))
    fld.source = "copernicus"
    return fld


def test_field_from_dataset_picks_nearest_hour_and_combines_components():
    fld = field_from_dataset(fake_dataset(), KEY)
    assert fld.source == "copernicus" and fld.key == KEY
    assert (fld.nx, fld.ny) == (3, 3)
    assert fld.lat[0] < fld.lat[-1]                              # flipped to ascending
    assert fld.sample(10.0, -20.0)[0] == pytest.approx(0.25)     # 18:00 slice: 0.2 + stokes 0.05, no tide
    assert fld.is_land(9.0, -19.0)
    assert not fld.is_land(10.0, -20.0)
    assert fld.components["utide"].shape == (1, 3, 3)
    assert float(fld.components["utide"][0, 1, 1]) == 9.0        # tide kept for later, not applied


def test_field_from_dataset_rejects_an_empty_grid():
    with pytest.raises(ValueError):
        field_from_dataset(fake_dataset(lon=(10.0,)), KEY)


def test_fetch_requests_the_box_the_hour_and_the_dataset(monkeypatch):
    calls = {}

    def open_dataset(**kwargs):
        calls.update(kwargs)
        return fake_dataset()

    monkeypatch.setitem(sys.modules, "copernicusmarine", types.SimpleNamespace(open_dataset=open_dataset))
    fld = real_fetch(KEY)
    assert fld.source == "copernicus"
    assert calls["dataset_id"] == config.COPERNICUS_DATASET_ID
    assert calls["variables"] == ["uo", "vo", "utide", "vtide", "vsdx", "vsdy"]
    assert (calls["minimum_longitude"], calls["maximum_longitude"]) == (8.5, 11.5)
    assert (calls["minimum_latitude"], calls["maximum_latitude"]) == (-21.5, -18.5)
    assert calls["start_datetime"] == "2026-10-03T17:00:00"
    assert calls["end_datetime"] == "2026-10-03T19:00:00"


def test_fetch_box_is_clamped_at_the_antimeridian_and_pole():
    assert snapshot.fetch_bounds(make_key(179.9, 0.0, 1, T0)) == (178.5, -1.5, 180.0, 1.5)
    assert snapshot.fetch_bounds(make_key(-179.9, 0.0, 1, T0)) == (-180.0, -1.5, -178.5, 1.5)
    assert snapshot.fetch_bounds(make_key(0.0, 89.8, 1, T0))[3] == 90.0


def test_failed_fetch_falls_back_to_synthetic_and_is_reused_briefly(monkeypatch):
    calls = []

    def failing(key):
        calls.append(key)
        raise RuntimeError("down")

    monkeypatch.setattr(snapshot, "fetch_copernicus", failing)
    first = load_field(KEY)
    assert first.source == "synthetic"
    assert load_field(KEY) is first      # within the retry window: same field, no second fetch
    assert len(calls) == 1


def test_real_source_is_retried_after_the_window_and_recovers(monkeypatch):
    monkeypatch.setattr(config, "SYNTHETIC_RETRY_S", 0)
    assert load_field(KEY).source == "synthetic"            # the autouse fixture makes this fetch fail
    recovered = real_field()
    monkeypatch.setattr(snapshot, "fetch_copernicus", lambda key: recovered)
    assert load_field(KEY) is recovered


def test_real_snapshot_is_cached_for_the_process(monkeypatch):
    calls = []
    real = real_field()

    def fetch(key):
        calls.append(key)
        return real

    monkeypatch.setattr(snapshot, "fetch_copernicus", fetch)
    assert load_field(KEY) is real
    assert load_field(KEY) is real
    assert len(calls) == 1


def test_slow_fetch_times_out_to_synthetic(monkeypatch):
    def slow(key):
        time.sleep(0.5)
        return real_field()

    monkeypatch.setattr(snapshot, "fetch_copernicus", slow)
    monkeypatch.setattr(config, "COPERNICUS_TIMEOUT_S", 0.05)
    started = time.monotonic()
    assert load_field(KEY).source == "synthetic"
    assert time.monotonic() - started < 0.4
    while snapshot._cached(KEY).source != "copernicus":  # the late result lands in the cache; let it, so it cannot leak
        time.sleep(0.01)


def _failing_fetch(calls):
    def failing(key):
        calls.append(key)
        raise RuntimeError("down")

    return failing


def test_one_failed_fetch_skips_copernicus_for_other_boxes_during_the_cooldown(monkeypatch):
    calls = []
    monkeypatch.setattr(snapshot, "fetch_copernicus", _failing_fetch(calls))
    assert load_field(KEY).source == "synthetic"
    assert load_field(make_key(50.0, 10.0, 1, T0)).source == "synthetic"
    assert len(calls) == 1


def test_cooldown_expires_and_other_boxes_are_fetched_again(monkeypatch):
    monkeypatch.setattr(config, "SYNTHETIC_RETRY_S", 0)
    calls = []
    monkeypatch.setattr(snapshot, "fetch_copernicus", _failing_fetch(calls))
    assert load_field(KEY).source == "synthetic"
    assert load_field(make_key(50.0, 10.0, 1, T0)).source == "synthetic"
    assert len(calls) == 2


def test_fallback_does_not_replace_a_real_cached_field():
    real = synthetic_field(KEY, uniform=(0.2, 0.0))
    real.source = "copernicus"
    snapshot._remember(KEY, real)
    returned = snapshot._remember(KEY, synthetic_field(KEY), ttl=60)
    assert returned is real
    assert snapshot._cached(KEY) is real


def test_fields_from_past_hours_are_dropped_from_memory():
    # Big boxes take several MB each in memory and the key includes the hour, so old hours are never read again.
    from datetime import timedelta

    old = make_key(10.2, -20.1, 1, T0)
    recent = make_key(10.2, -20.1, 1, T0 + timedelta(hours=2))
    now = make_key(10.2, -20.1, 1, T0 + timedelta(hours=3))
    for key in (old, recent, now):
        snapshot._remember(key, synthetic_field(key))
    assert snapshot._cached(old) is None
    assert snapshot._cached(recent) is not None
    assert snapshot._cached(now) is not None
