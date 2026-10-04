"""Tests for the fix pass after the whole-branch review: limits, credential guard,
snapshot reuse, late-fetch capture and the database cooldown."""

import time
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from app import config, db
from app.main import app
from app.sim import snapshot
from app.sim.snapshot import load_field, make_key, synthetic_field

client = TestClient(app)

T0 = datetime(2026, 10, 3, 18, tzinfo=UTC)
KEY1 = make_key(10.2, -20.1, 1, T0)  # half-width 1.5
KEY7 = make_key(10.2, -20.1, 7, T0)  # half-width 6.5, same centre
BODY = {"placements": [{"id": "bottle-1", "type": "bottle", "coordinates": [10.2, -20.1]}], "durationDays": 1}


def real_field(key):
    fld = synthetic_field(key, uniform=(0.2, 0.0))
    fld.source = "copernicus"
    return fld


def bottles(n):
    """n bottles, each in its own half-degree box (10 degrees apart)."""
    return [{"id": f"b{i}", "type": "bottle", "coordinates": [-170.0 + 10.0 * i, 0.0]} for i in range(n)]


def collectors(n):
    return [{"id": f"c{i}", "type": "collector", "coordinates": [10.2 + 0.01 * i, -20.1]} for i in range(n)]


# ---- 1. limits --------------------------------------------------------------


def test_too_many_collectors_are_rejected():
    body = {"placements": [bottles(1)[0], *collectors(21)], "durationDays": 1}
    response = client.post("/api/simulate", json=body)
    assert response.status_code == 422
    assert response.json()["code"] == "invalid_request"


def test_twenty_collectors_are_accepted():
    body = {"placements": [{"id": "b", "type": "bottle", "coordinates": [10.2, -20.1]}, *collectors(20)],
            "durationDays": 1}
    assert client.post("/api/simulate", json=body).status_code == 200


def test_too_many_distinct_areas_are_rejected_before_any_fetch(monkeypatch):
    calls = []
    monkeypatch.setattr(snapshot, "fetch_copernicus", lambda key: calls.append(key))
    response = client.post("/api/simulate", json={"placements": bottles(17), "durationDays": 1})
    assert response.status_code == 422
    assert response.json()["code"] == "invalid_request"
    assert calls == []


def test_sixteen_distinct_areas_are_accepted():
    response = client.post("/api/simulate", json={"placements": bottles(16), "durationDays": 1})
    assert response.status_code == 200


# ---- 2. credential guard ----------------------------------------------------


@pytest.mark.parametrize("missing", ["COPERNICUSMARINE_SERVICE_USERNAME", "COPERNICUSMARINE_SERVICE_PASSWORD"])
def test_missing_credentials_skip_the_fetch_without_a_cooldown(monkeypatch, missing):
    calls = []
    monkeypatch.setattr(snapshot, "fetch_copernicus", lambda key: calls.append(key))
    monkeypatch.delenv(missing, raising=False)
    started = time.monotonic()
    assert load_field(KEY1).source == "synthetic"
    assert time.monotonic() - started < 0.5
    assert calls == []
    assert snapshot._copernicus_down_until == 0.0


def test_missing_credentials_are_logged_once(monkeypatch, caplog):
    monkeypatch.delenv("COPERNICUSMARINE_SERVICE_USERNAME", raising=False)
    with caplog.at_level("WARNING", logger=snapshot.log.name):
        load_field(KEY1)
        load_field(make_key(50.0, 10.0, 1, T0))
    assert len([r for r in caplog.records if "credentials" in r.getMessage()]) == 1


# ---- 3. superset reuse ------------------------------------------------------


def test_shorter_duration_reuses_a_cached_longer_box(monkeypatch):
    calls = []
    big = real_field(KEY7)
    monkeypatch.setattr(snapshot, "fetch_copernicus", lambda key: calls.append(key) or big)
    assert load_field(KEY7) is big
    assert load_field(KEY1) is big
    assert len(calls) == 1


def test_longer_duration_does_not_reuse_a_smaller_box(monkeypatch):
    calls = []
    monkeypatch.setattr(snapshot, "fetch_copernicus", lambda key: calls.append(key) or real_field(key))
    load_field(KEY1)
    assert load_field(KEY7).key == KEY7
    assert len(calls) == 2


def test_a_cached_fallback_is_not_a_superset(monkeypatch):
    assert load_field(KEY7).source == "synthetic"  # the autouse fixture blocks the fetch
    assert snapshot._cached_superset(KEY1) is None


def test_superset_needs_the_same_centre_hour_and_slices(monkeypatch):
    snapshot._remember(KEY7, real_field(KEY7))
    assert snapshot._cached_superset(make_key(10.2, -20.1, 1, T0.replace(hour=19))) is None
    assert snapshot._cached_superset(make_key(40.2, -20.1, 1, T0)) is None
    assert snapshot._cached_superset(KEY1) is not None


# ---- 4. late fetch ----------------------------------------------------------


def test_a_fetch_that_finishes_after_the_timeout_is_kept(monkeypatch):
    calls = []
    late = real_field(KEY1)

    def slow(key):
        calls.append(key)
        time.sleep(0.3)
        return late

    monkeypatch.setattr(snapshot, "fetch_copernicus", slow)
    monkeypatch.setattr(config, "COPERNICUS_TIMEOUT_S", 0.05)
    started = time.monotonic()
    assert load_field(KEY1).source == "synthetic"
    assert time.monotonic() - started < 0.25
    assert snapshot._copernicus_down_until > 0.0

    deadline = time.monotonic() + 2
    while time.monotonic() < deadline:
        cached = snapshot._cached(KEY1)
        if cached is late and snapshot._copernicus_down_until == 0.0:
            break
        time.sleep(0.01)
    assert snapshot._cached(KEY1) is late
    assert snapshot._copernicus_down_until == 0.0
    assert load_field(KEY1) is late
    assert len(calls) == 1


# ---- 5. database cooldown ---------------------------------------------------


def test_database_is_unavailable_during_the_cooldown(monkeypatch):
    monkeypatch.setattr(db, "_pool", object())
    assert db.available() is True
    db.report_failure()
    assert db.available() is False


def test_database_is_available_again_after_the_cooldown(monkeypatch):
    monkeypatch.setattr(db, "_pool", object())
    monkeypatch.setattr(config, "DATABASE_RETRY_S", 0)
    db.report_failure()
    assert db.available() is True


def test_ping_reports_a_failure_when_the_query_raises(monkeypatch):
    monkeypatch.setattr(db, "_pool", object())  # no .connection: the query raises
    assert db.ping() is False
    assert db.available() is False


@pytest.fixture
def failures(monkeypatch):
    snapshot._store_pool.submit(lambda: None).result()  # background saves of earlier tests are done
    recorded = []
    monkeypatch.setattr(db, "available", lambda: True)
    monkeypatch.setattr(db, "report_failure", lambda: recorded.append(1))
    yield recorded
    snapshot._store_pool.submit(lambda: None).result()  # and ours finish before the patches are undone


def _boom(*args):
    raise RuntimeError("connection lost")


def test_a_failed_run_save_reports_the_failure_and_still_succeeds(failures, monkeypatch):
    monkeypatch.setattr(db, "load_snapshot", lambda key: None)
    monkeypatch.setattr(db, "save_run", _boom)
    response = client.post("/api/simulate", json=BODY)
    assert response.status_code == 200
    assert response.json()["persisted"] is False
    assert failures == [1]


def test_a_failed_snapshot_lookup_reports_the_failure_and_still_fetches(failures, monkeypatch):
    fetched = real_field(KEY1)
    monkeypatch.setattr(db, "load_snapshot", _boom)
    monkeypatch.setattr(db, "save_snapshot", lambda fld: None)
    monkeypatch.setattr(snapshot, "fetch_copernicus", lambda key: fetched)
    assert load_field(KEY1) is fetched
    assert failures == [1]


def test_a_failed_snapshot_save_reports_the_failure(failures, monkeypatch):
    monkeypatch.setattr(db, "save_snapshot", _boom)
    snapshot._store(real_field(KEY1))
    assert failures == [1]


def test_a_failed_run_or_timeline_read_reports_the_failure(failures, monkeypatch):
    run_id = "00000000-0000-4000-8000-0000000000aa"
    monkeypatch.setattr(db, "load_run", _boom)
    monkeypatch.setattr(db, "timeline", _boom)
    assert client.get(f"/api/runs/{run_id}").status_code == 404
    assert client.get(f"/api/runs/{run_id}/timeline").status_code == 404
    assert failures == [1, 1]
