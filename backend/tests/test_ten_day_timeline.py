from datetime import UTC, datetime

from fastapi.testclient import TestClient

from app import db, routes
from app.main import app
from app.schemas import SimulateResponse
from app.sim.snapshot import make_key, synthetic_field
from app.story_summary import build_story_summary_from_run

client = TestClient(app)
T0 = datetime(2026, 10, 4, 12, tzinfo=UTC)


def ten_day_run(monkeypatch):
    monkeypatch.setattr(routes, "load_field", lambda key: synthetic_field(key, uniform=(0.0, 0.0)))
    response = client.post("/api/simulate", json={
        "placements": [
            {"id": "late", "type": "bottle", "coordinates": [-130, 40], "placedAtSeconds": 259200},
            {"id": "cleanup", "type": "collector", "coordinates": [-130, 40], "placedAtSeconds": 345723},
            {"id": "endpoint", "type": "foam", "coordinates": [-130.1, 40], "placedAtSeconds": 864000},
        ],
        "durationDays": 10,
        "collectorRadiusM": 1000,
        "honourCollectors": True,
    })
    assert response.status_code == 200
    return response.json()


def test_ten_day_run_has_absolute_birth_times_and_delayed_capture(monkeypatch):
    data = ten_day_run(monkeypatch)
    assert data["durationDays"] == 10
    assert data["totalSeconds"] == 864000
    trajectory = data["trajectories"][0]
    assert trajectory["samples"][0]["timeSeconds"] == 259200
    assert trajectory["samples"][-1]["timeSeconds"] == 864000
    assert all(s["timeSeconds"] >= 259200 for s in trajectory["samples"])
    assert data["items"][0]["statusChangedAtSeconds"] == 345723
    captured = [s for s in trajectory["samples"] if s["status"] == "captured"]
    assert all(s["coordinates"] == captured[0]["coordinates"] for s in captured)
    assert len(data["trajectories"][1]["samples"]) == 1


def test_ten_day_timeline_counts_late_placements_and_replays(monkeypatch):
    data = ten_day_run(monkeypatch)
    assert client.get(f"/api/runs/{data['runId']}").json() == data
    buckets = client.get(f"/api/runs/{data['runId']}/timeline").json()["buckets"]
    assert len(buckets) == 241
    assert buckets[71]["floating"] == 0
    assert buckets[72]["floating"] == 1
    assert buckets[96]["captured"] == 0
    assert buckets[97]["captured"] == 1
    assert buckets[-1]["timeSeconds"] == 864000
    assert buckets[-1]["floating"] == 1
    assert buckets[-1]["captured"] == 1


def test_ten_day_run_survives_database_serialization(monkeypatch):
    response = SimulateResponse.model_validate(ten_day_run(monkeypatch))
    rows = [(item_id, time, lon, lat, status)
            for time, _, item_id, _, lon, lat, status in db.position_rows(response, T0)]
    replay = db.run_from_rows(db.run_envelope(response), T0, rows)
    assert replay == response.model_copy(update={"persisted": True})
    assert routes.timeline_of(replay) == routes.timeline_of(response)


def test_story_summary_covers_240_hours_with_day_three_release(monkeypatch):
    response = SimulateResponse.model_validate(ten_day_run(monkeypatch))
    summary = build_story_summary_from_run(response, "late")
    assert summary.duration_hours == 240
    assert summary.events[0].elapsed_hours == 72
    assert all(event.elapsed_hours <= 240 for event in summary.events)


def test_ten_day_snapshot_box_is_large_enough():
    assert make_key(-130, 40, 10, T0).half_width_deg == 8.5
