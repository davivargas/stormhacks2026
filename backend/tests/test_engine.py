from datetime import UTC, datetime

from app.sim import engine
from app.sim.geo import haversine_m
from app.sim.snapshot import make_key, synthetic_field

T0 = datetime(2026, 10, 3, 18, tzinfo=UTC)
LON, LAT = -130.0, 40.0


def eastward_field(land=None):
    key = make_key(LON, LAT, 1, T0)
    return synthetic_field(key, uniform=(0.5, 0.0), land=land)


def test_uniform_eastward_moves_about_43_km_and_stays_floating():
    item = engine.LitterItem("bottle-1", "bottle", LON, LAT)
    result = engine.run([item], [], 1, {"bottle-1": eastward_field()})

    out = result.outcomes[0]
    assert out.final_status == "floating"
    assert len(out.samples) == 25  # hourly for 24 h, including t=0
    _, lon, lat, _ = out.samples[-1]
    assert lon > LON
    assert abs(haversine_m(LON, LAT, lon, lat) - 43_200) < 300
    assert result.summary == {"floating": 1, "captured": 0, "beached": 0, "outside": 0}


def test_field_pointing_at_land_beaches_and_freezes():
    fld = eastward_field(land=lambda lon, lat: lon > LON + 0.25)
    item = engine.LitterItem("bag-1", "bag", LON, LAT)
    out = engine.run([item], [], 1, {"bag-1": fld}).outcomes[0]

    assert out.final_status == "beached"
    assert out.status_changed_at_seconds is not None and 0 < out.status_changed_at_seconds < 24 * 3600
    beached = [s for s in out.samples if s[3] == "beached"]
    assert len(beached) > 1
    assert {(s[1], s[2]) for s in beached} == {(beached[0][1], beached[0][2])}
    assert not fld.is_land(beached[0][1], beached[0][2], beached[0][0])
    assert all(s[0] < out.status_changed_at_seconds for s in out.samples if s[3] == "floating")


def test_segment_crossing_a_narrow_island_beaches_before_reaching_water_again():
    key = make_key(LON, LAT, 1, T0)
    fld = synthetic_field(
        key,
        uniform=(0.5, 0.0),
        land=lambda lon, lat: (lon > LON + 0.02) & (lon < LON + 0.04),
        resolution=0.005,
    )
    item = engine.LitterItem("bottle-island", "bottle", LON, LAT)

    out = engine.run(
        [item],
        [],
        1,
        {item.id: fld},
        dt=14_400,
        frame_interval=14_400,
    ).outcomes[0]

    assert out.final_status == "beached"
    terminal = next(sample for sample in out.samples if sample[3] == "beached")
    assert LON + 0.015 < terminal[1] < LON + 0.04
    assert not fld.is_land(terminal[1], terminal[2], terminal[0])
    assert {(sample[1], sample[2]) for sample in out.samples if sample[3] == "beached"} == {
        (terminal[1], terminal[2])
    }


def test_item_passing_collector_is_captured_once_and_credited():
    near = engine.Collector("collector-near", LON + 0.25, LAT + 5_000 / 110_540, 10_000)
    far = engine.Collector("collector-far", LON - 1.0, LAT - 1.0, 10_000)
    items = [engine.LitterItem("foam-1", "foam", LON, LAT)]

    result = engine.run(items, [near, far], 1, {"foam-1": eastward_field()})

    out = result.outcomes[0]
    assert out.final_status == "captured"
    assert out.captured_by == "collector-near"
    assert result.captured_counts == {"collector-near": 1, "collector-far": 0}
    assert result.summary == {"floating": 0, "captured": 1, "beached": 0, "outside": 0}
    captured_positions = {(s[1], s[2]) for s in out.samples if s[3] == "captured"}
    assert len(captured_positions) == 1


def test_fast_current_leaves_box_as_outside():
    key = make_key(LON, LAT, 1, T0)  # 1.5 degree half-width
    fld = synthetic_field(key, uniform=(2.0, 0.0))  # ~2 degrees/day at 40N
    out = engine.drift_item(engine.LitterItem("b", "bottle", LON, LAT), fld, [], 1)
    assert out.final_status == "outside"


def test_deterministic():
    fld = synthetic_field(make_key(LON, LAT, 3, T0))
    item = engine.LitterItem("b", "bottle", LON + 0.3, LAT + 0.2)
    assert engine.drift_item(item, fld, [], 3).samples == engine.drift_item(item, fld, [], 3).samples
