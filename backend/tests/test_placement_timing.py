from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app import db, routes
from app.main import app
from app.schemas import SimulateResponse
from app.sim import engine
from app.sim.geo import haversine_m
from app.sim.snapshot import make_key, synthetic_field

client = TestClient(app)
T0 = datetime(2026, 10, 3, 18, tzinfo=UTC)
LON, LAT = -130.0, 40.0


def field(speed=0.5):
    return synthetic_field(make_key(LON, LAT, 1, T0), uniform=(speed, 0.0))


def test_late_item_drifts_only_for_remaining_time():
    item = engine.LitterItem("late", "bottle", LON, LAT, 6 * 3600 + 123)
    out = engine.drift_item(item, field(), [], 1)
    assert out.samples[0] == (item.placed_at_seconds, LON, LAT, "floating")
    assert out.samples[-1][0] == 86400
    assert all(sample[0] >= item.placed_at_seconds for sample in out.samples)
    _, lon, lat, _ = out.samples[-1]
    assert haversine_m(LON, LAT, lon, lat) == pytest.approx((86400 - item.placed_at_seconds) * 0.5, abs=300)
    assert any(sample[0] == 7 * 3600 for sample in out.samples)


def test_collector_activates_at_exact_placement_time():
    item = engine.LitterItem("b", "bottle", LON, LAT)
    collector = engine.Collector("c", LON, LAT, 10_000, 3600 + 123)
    out = engine.drift_item(item, field(0), [collector], 1)
    assert out.status_changed_at_seconds == collector.placed_at_seconds
    assert out.captured_by == "c"
    assert all(s[3] == "floating" for s in out.samples if s[0] < collector.placed_at_seconds)
    assert (collector.placed_at_seconds, LON, LAT, "captured") in out.samples


def test_late_collector_does_not_capture_an_item_that_already_passed():
    item = engine.LitterItem("b", "bottle", LON, LAT)
    collector = engine.Collector("c", LON, LAT, 1000, 6 * 3600)
    out = engine.drift_item(item, field(), [collector], 1)
    assert out.final_status == "floating"
    assert out.captured_by is None


def test_placement_at_endpoint_returns_one_sample():
    out = engine.drift_item(engine.LitterItem("end", "foam", LON, LAT, 86400), field(), [], 1)
    assert out.samples == [(86400, LON, LAT, "floating")]


def test_terminal_event_sample_is_recorded_between_hours():
    collector = engine.Collector("c", LON, LAT, 10_000, 600)
    out = engine.drift_item(engine.LitterItem("b", "bottle", LON, LAT), field(0), [collector], 1)
    assert out.samples[:3] == [(0, LON, LAT, "floating"), (600, LON, LAT, "captured"), (3600, LON, LAT, "captured")]


@pytest.mark.parametrize("placed_at", [-1, 86401, 1.5, True])
def test_invalid_placement_times_are_rejected(placed_at):
    response = client.post("/api/simulate", json={
        "placements": [{"id": "b", "type": "bottle", "coordinates": [LON, LAT], "placedAtSeconds": placed_at}],
        "durationDays": 1,
    })
    assert response.status_code == 422
    assert response.json()["code"] == "invalid_request"


def delayed_response(monkeypatch):
    monkeypatch.setattr(routes, "load_field", lambda key: field(0))
    response = client.post("/api/simulate", json={
        "placements": [
            {"id": "b", "type": "bottle", "coordinates": [LON, LAT], "placedAtSeconds": 21600},
            {"id": "c", "type": "collector", "coordinates": [LON, LAT], "placedAtSeconds": 25201},
        ],
        "durationDays": 1,
        "honourCollectors": True,
    })
    assert response.status_code == 200
    return response.json()


def test_api_preserves_births_events_and_memory_timeline(monkeypatch):
    data = delayed_response(monkeypatch)
    assert data["trajectories"][0]["samples"][0]["timeSeconds"] == 21600
    assert data["items"][0]["statusChangedAtSeconds"] == 25201
    assert data["summary"]["captured"] == 1
    assert client.get(f"/api/runs/{data['runId']}").json() == data
    buckets = client.get(f"/api/runs/{data['runId']}/timeline").json()["buckets"]
    assert len(buckets) == 25
    assert sum(buckets[5][s] for s in engine.STATUSES) == 0
    assert buckets[6]["floating"] == 1
    assert buckets[7]["floating"] == 1
    assert buckets[8]["captured"] == 1


def test_delayed_run_survives_database_serialization(monkeypatch):
    response = SimulateResponse.model_validate(delayed_response(monkeypatch))
    rows = db.position_rows(response, T0)
    reconstructed = [(item_id, time, lon, lat, status)
                     for time, _, item_id, _, lon, lat, status in rows]
    replay = db.run_from_rows(db.run_envelope(response), T0, reconstructed)
    assert replay == response.model_copy(update={"persisted": True})
    assert reconstructed[0][1] == T0 + timedelta(seconds=21600)
    assert routes.timeline_of(replay) == routes.timeline_of(response)


def test_timeline_keeps_zero_count_buckets_before_birth():
    buckets = db.timeline_buckets(T0, [(T0, None, 0), (T0 + timedelta(hours=1), "floating", 1)])
    assert buckets[0].model_dump() == {"time_seconds": 0, "floating": 0, "captured": 0, "beached": 0, "outside": 0}
    assert buckets[1].floating == 1
