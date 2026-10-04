from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.sim import engine
from app.sim.snapshot import make_key, synthetic_field

client = TestClient(app)
T0 = datetime(2026, 10, 3, 18, tzinfo=UTC)
LON, LAT = -130.0, 40.0


def bottle(pid, coordinates=(LON, LAT)):
    return {"id": pid, "type": "bottle", "coordinates": list(coordinates)}


def test_item_dropped_inside_collector_is_captured_at_second_zero():
    fld = synthetic_field(make_key(LON, LAT, 1, T0), uniform=(0.5, 0.0))
    collector = engine.Collector("c1", LON, LAT, 10_000)
    item = engine.LitterItem("b", "bottle", LON + 0.01, LAT)
    result = engine.run([item], [collector], 1, {"b": fld})
    out = result.outcomes[0]
    assert out.samples[0][3] == "captured"
    assert out.status_changed_at_seconds == 0
    assert out.samples[-1][1] == pytest.approx(LON + 0.01)  # never moved
    assert result.captured_counts == {"c1": 1}


def test_sampling_beside_land_is_finite_and_slowed():
    # Land starts at the grid column just east of LON + 0.25.
    fld = synthetic_field(make_key(LON, LAT, 1, T0), uniform=(0.5, 0.5),
                          land=lambda lon, lat: lon > LON + 0.26)
    u, v = fld.sample(LON + 0.25 + 0.6 / 12, LAT)  # 60% of the way from a water cell to a land cell
    assert u == pytest.approx(0.2, abs=0.01)
    assert v == pytest.approx(0.2, abs=0.01)


def test_box_at_the_antimeridian_contains_both_sides():
    fld = synthetic_field(make_key(179.9, 0.0, 1, T0), uniform=(0.5, 0.0))
    assert fld.contains(179.9, 0.0)
    assert fld.contains(-179.9, 0.0)
    assert fld.sample(-179.9, 0.0) == pytest.approx((0.5, 0.0))


def test_item_drifts_across_the_antimeridian_without_jumping():
    fld = synthetic_field(make_key(179.9, 0.0, 1, T0), uniform=(0.5, 0.0))
    out = engine.drift_item(engine.LitterItem("b", "bottle", 179.95, 0.0), fld, [], 1)
    assert out.final_status == "floating"
    assert out.samples[-1][1] == pytest.approx(180.338, abs=0.01)  # continuous, not wrapped to -179.66


def test_item_leaving_the_box_is_outside_even_within_a_collector_radius():
    fld = synthetic_field(make_key(LON, LAT, 1, T0), uniform=(2.0, 0.0))
    # Box east edge is LON + 1.5. With the 10-minute step the item is last inside the box at
    # about LON + 1.4916 and first outside at about LON + 1.5057. A 500 m collector (~0.006 deg)
    # centred there covers only the outside position, never the last inside one.
    collector = engine.Collector("c1", LON + 1.506, LAT, 500)
    item = engine.LitterItem("b", "bottle", LON, LAT)
    result = engine.run([item], [collector], 1, {"b": fld})
    out = result.outcomes[0]
    assert out.final_status == "outside"
    assert out.captured_by is None
    assert result.captured_counts == {"c1": 0}


@pytest.mark.parametrize("body", [
    {"placements": [bottle("a"), bottle("a")]},                                  # duplicate ids
    {"placements": [bottle("a", (0, 91))]},                                       # latitude out of range
    {"placements": [bottle("a", (181, 0))]},                                      # longitude out of range
    {"placements": [{"id": "c", "type": "collector", "coordinates": [0, 0]}]},    # no litter
    {"placements": []},                                                           # nothing at all
    {"placements": [bottle(f"b{i}") for i in range(51)]},                         # too many
    {"placements": [bottle("a")], "durationDays": 1.5},                           # fractional days
    {"placements": [bottle("a")], "durationDays": 0},
])
def test_bad_requests_are_rejected_before_any_work(body):
    response = client.post("/api/simulate", json=body)
    assert response.status_code == 422
    assert response.json()["code"] == "invalid_request"
