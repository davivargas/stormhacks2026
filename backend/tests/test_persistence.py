import json
import time
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import db
from app.main import app
from app.schemas import SimulateResponse, TimelineBucket, TimelineResponse
from app.sim import snapshot
from app.sim.snapshot import load_field, make_key, synthetic_field

client = TestClient(app)  # no "with": the lifespan does not run, so no real pool is opened

T0 = datetime(2026, 10, 3, 18, tzinfo=UTC)
KEY = make_key(10.2, -20.1, 1, T0)
RUN_ID = "00000000-0000-4000-8000-0000000000aa"
BODY = {"placements": [
    {"id": "bottle-1", "type": "bottle", "coordinates": [10.2, -20.1]},
    {"id": "collector-1", "type": "collector", "coordinates": [10.4, -20.1]},
], "durationDays": 1}
FIXTURE = Path(__file__).resolve().parents[1] / "scripts" / "fixtures" / "simulate_response.json"


def flush_store_pool():
    """Snapshots are stored in the background; the pool has one worker, so this waits for them."""
    snapshot._store_pool.submit(lambda: None).result()


def real_field():
    fld = synthetic_field(KEY, uniform=(0.2, 0.0))
    fld.source = "copernicus"
    return fld


@pytest.fixture
def fake_db(monkeypatch):
    """Pretend Tiger is connected and record what the app asks of it."""
    calls = {"runs": [], "snapshots": [], "lookups": []}
    monkeypatch.setattr(db, "available", lambda: True)
    monkeypatch.setattr(db, "ping", lambda: True)
    monkeypatch.setattr(db, "load_snapshot", lambda key: calls["lookups"].append(key))
    monkeypatch.setattr(db, "save_snapshot", lambda fld: calls["snapshots"].append(fld.key))
    monkeypatch.setattr(db, "save_run", lambda resp, req, start_time, parent_run_id:
                        calls["runs"].append((resp.run_id, parent_run_id, start_time)))
    monkeypatch.setattr(db, "load_run", lambda run_id: None)
    monkeypatch.setattr(db, "timeline", lambda run_id: None)
    return calls


def test_health_reports_no_database():
    assert client.get("/api/health").json() == {"ok": True, "db": False}


def test_health_reports_a_connected_database(fake_db):
    assert client.get("/api/health").json() == {"ok": True, "db": True}


def test_simulate_without_database_succeeds_unpersisted():
    data = client.post("/api/simulate", json=BODY).json()
    assert data["persisted"] is False
    assert client.get(f"/api/runs/{data['runId']}").json() == data


def test_simulate_persists_when_database_is_available(fake_db):
    data = client.post("/api/simulate", json=BODY).json()
    assert data["persisted"] is True
    run_id, parent, start_time = fake_db["runs"][0]
    assert (run_id, parent) == (data["runId"], None)
    assert start_time == datetime.fromisoformat(data["snapshots"][0]["sliceTime"])
    assert len(fake_db["runs"]) == 1


def test_compare_links_the_with_run_to_the_without_run(fake_db):
    data = client.post("/api/compare", json=BODY).json()
    assert [(r[0], r[1]) for r in fake_db["runs"]] == [
        (data["without"]["runId"], None),
        (data["with"]["runId"], data["without"]["runId"]),
    ]
    assert data["with"]["persisted"] is True


def test_database_failure_during_save_does_not_fail_the_request(fake_db, monkeypatch):
    def boom(*args):
        raise RuntimeError("connection lost")

    monkeypatch.setattr(db, "save_run", boom)
    response = client.post("/api/simulate", json=BODY)
    assert response.status_code == 200
    data = response.json()
    assert data["persisted"] is False
    assert client.get(f"/api/runs/{data['runId']}").json() == data  # still replayable from memory


def test_stored_snapshot_is_used_before_copernicus(fake_db, monkeypatch):
    stored = real_field()
    fetches = []
    monkeypatch.setattr(db, "load_snapshot", lambda key: stored)
    monkeypatch.setattr(snapshot, "fetch_copernicus", lambda key: fetches.append(key))
    assert load_field(KEY) is stored
    flush_store_pool()
    assert fetches == [] and fake_db["snapshots"] == []
    assert load_field(KEY) is stored  # now from memory


def test_fetched_snapshot_is_stored_in_tiger(fake_db, monkeypatch):
    fetched = real_field()
    monkeypatch.setattr(snapshot, "fetch_copernicus", lambda key: fetched)
    assert load_field(KEY) is fetched
    flush_store_pool()
    assert fake_db["lookups"] == [KEY]
    assert fake_db["snapshots"] == [KEY]


def test_synthetic_fallback_is_never_stored(fake_db):
    assert load_field(KEY).source == "synthetic"  # the autouse fixture blocks the fetch
    flush_store_pool()
    assert fake_db["snapshots"] == []


def test_snapshot_lookup_failure_falls_through_to_copernicus(fake_db, monkeypatch):
    def boom(key):
        raise RuntimeError("connection lost")

    fetched = real_field()
    monkeypatch.setattr(db, "load_snapshot", boom)
    monkeypatch.setattr(snapshot, "fetch_copernicus", lambda key: fetched)
    assert load_field(KEY) is fetched


def test_replay_is_served_from_tiger_when_it_has_the_run(fake_db, monkeypatch):
    stored = SimulateResponse.model_validate(json.loads(FIXTURE.read_text()))
    asked = []
    monkeypatch.setattr(db, "load_run", lambda run_id: asked.append(run_id) or stored)
    response = client.get(f"/api/runs/{RUN_ID}")
    assert response.status_code == 200
    assert response.json()["runId"] == stored.run_id
    assert asked == [RUN_ID]


def test_replay_falls_back_to_memory_when_tiger_lacks_the_run(fake_db):
    data = client.post("/api/simulate", json=BODY).json()
    assert client.get(f"/api/runs/{data['runId']}").json() == data


def test_replay_falls_back_to_memory_when_tiger_errors(fake_db, monkeypatch):
    data = client.post("/api/simulate", json=BODY).json()

    def boom(run_id):
        raise RuntimeError("connection lost")

    monkeypatch.setattr(db, "load_run", boom)
    assert client.get(f"/api/runs/{data['runId']}").json() == data


@pytest.mark.parametrize("run_id", [RUN_ID, "not-a-uuid"])
def test_unknown_run_is_404(fake_db, run_id):
    response = client.get(f"/api/runs/{run_id}")
    assert response.status_code == 404
    assert response.json()["code"] == "run_not_found"


def test_timeline_is_served_from_tiger(fake_db, monkeypatch):
    stored = TimelineResponse(run_id=RUN_ID, bucket_seconds=3600, buckets=[
        TimelineBucket(time_seconds=0, floating=7, captured=0, beached=0, outside=0)])
    monkeypatch.setattr(db, "timeline", lambda run_id: stored)
    data = client.get(f"/api/runs/{RUN_ID}/timeline").json()
    assert data == {"runId": RUN_ID, "bucketSeconds": 3600, "buckets": [
        {"timeSeconds": 0, "floating": 7, "captured": 0, "beached": 0, "outside": 0}]}


def test_timeline_falls_back_to_memory(fake_db):
    data = client.post("/api/simulate", json=BODY).json()
    timeline = client.get(f"/api/runs/{data['runId']}/timeline").json()
    assert len(timeline["buckets"]) == 25
    assert timeline["buckets"][0]["floating"] == 1


def test_distinct_boxes_are_resolved_concurrently(monkeypatch):
    def slow_fetch(key):
        time.sleep(0.3)
        fld = synthetic_field(key, uniform=(0.2, 0.0))
        fld.source = "copernicus"
        return fld

    monkeypatch.setattr(snapshot, "fetch_copernicus", slow_fetch)
    body = {"placements": [
        {"id": "a", "type": "bottle", "coordinates": [10.2, -20.1]},
        {"id": "b", "type": "bottle", "coordinates": [60.3, -30.2]},
        {"id": "c", "type": "bottle", "coordinates": [-140.2, 32.1]},
    ], "durationDays": 1}
    started = time.monotonic()
    response = client.post("/api/simulate", json=body)
    elapsed = time.monotonic() - started
    assert response.status_code == 200
    assert len(response.json()["snapshots"]) == 3
    assert elapsed < 0.75, f"boxes were fetched one after another ({elapsed:.2f}s)"


def test_big_snapshots_are_not_stored_or_looked_up_in_tiger(fake_db, monkeypatch):
    # A 25-degree box is ~360,000 rows: tens of MB and about a minute to upload, while refetching it
    # from Copernicus takes seconds. Only boxes up to SNAPSHOT_STORE_MAX_CELLS go to Tiger.
    from app import config

    monkeypatch.setattr(config, "SNAPSHOT_STORE_MAX_CELLS", 100)  # KEY's box is 37 x 37 cells
    fetched = real_field()
    monkeypatch.setattr(snapshot, "fetch_copernicus", lambda key: fetched)
    assert load_field(KEY) is fetched
    snapshot._store_pool.submit(lambda: None).result()
    assert fake_db["lookups"] == []
    assert fake_db["snapshots"] == []
