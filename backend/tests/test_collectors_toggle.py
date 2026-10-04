"""Collectors are placed and reported but do not capture unless the request asks for it."""

from fastapi.testclient import TestClient

from app import routes
from app.main import app
from app.sim.snapshot import synthetic_field

client = TestClient(app)

BODY = {
    "placements": [
        {"id": "bottle-1", "type": "bottle", "coordinates": [-130.0, 40.0]},
        {"id": "collector-1", "type": "collector", "coordinates": [-129.8, 40.0]},  # directly downstream
    ],
    "durationDays": 1,
}


def eastward(monkeypatch):
    monkeypatch.setattr(routes, "load_field", lambda key: synthetic_field(key, uniform=(0.5, 0.0)))


def test_simulate_ignores_collectors_by_default(monkeypatch):
    eastward(monkeypatch)
    data = client.post("/api/simulate", json=BODY).json()
    assert data["summary"]["captured"] == 0
    assert data["items"][0]["finalStatus"] == "floating"
    assert data["collectors"] == [
        {"id": "collector-1", "coordinates": [-129.8, 40.0], "radiusM": 10000.0, "capturedCount": 0}
    ]


def test_simulate_honours_collectors_when_asked(monkeypatch):
    eastward(monkeypatch)
    data = client.post("/api/simulate", json={**BODY, "honourCollectors": True}).json()
    assert data["summary"]["captured"] == 1
    assert data["items"][0]["capturedBy"] == "collector-1"


def test_compare_still_runs_both(monkeypatch):
    eastward(monkeypatch)
    data = client.post("/api/compare", json=BODY).json()
    assert data["without"]["summary"]["captured"] == 0
    assert data["with"]["summary"]["captured"] == 1
