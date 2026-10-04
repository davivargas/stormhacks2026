from fastapi.testclient import TestClient

from app import routes
from app.main import app
from app.sim.snapshot import synthetic_field

client = TestClient(app)

BODY = {
    "placements": [
        {"id": "bottle-1", "type": "bottle", "coordinates": [-125.3, 48.9]},
        {"id": "collector-1", "type": "collector", "coordinates": [-125.0, 48.8]},
    ],
    "durationDays": 1,
    "collectorRadiusM": 10000,
}


def test_simulate_shape_and_replay():
    r = client.post("/api/simulate", json=BODY)
    assert r.status_code == 200
    data = r.json()
    assert data["totalSeconds"] == 86400 and data["sampleIntervalSeconds"] == 3600
    traj = data["trajectories"][0]
    assert traj["id"] == "bottle-1" and len(traj["samples"]) == 25
    assert set(traj["samples"][0]) == {"timeSeconds", "coordinates", "status"}
    assert data["snapshots"][0]["source"] == "synthetic"

    again = client.get(f"/api/runs/{data['runId']}")
    assert again.status_code == 200 and again.json() == data
    timeline = client.get(f"/api/runs/{data['runId']}/timeline").json()
    assert len(timeline["buckets"]) == 25


def test_compare_has_without_with_delta():
    data = client.post("/api/compare", json=BODY).json()
    assert set(data) == {"without", "with", "delta"}
    assert [c["capturedCount"] for c in data["without"]["collectors"]] == [0]
    assert data["without"]["summary"]["captured"] == 0


def test_on_land_is_422(monkeypatch):
    monkeypatch.setattr(routes, "load_field", lambda key: synthetic_field(key, land=lambda lon, lat: lon > -126))
    r = client.post("/api/simulate", json=BODY)
    assert r.status_code == 422
    assert r.json() == {"code": "on_land", "message": "That spot is land. Try the water!", "placementId": "bottle-1"}


def test_bad_duration_is_422():
    r = client.post("/api/simulate", json={**BODY, "durationDays": 366})
    assert r.status_code == 422 and r.json()["code"] == "invalid_request"


def test_unknown_run_is_404():
    assert client.get("/api/runs/nope").status_code == 404
