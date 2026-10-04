"""Write canned API responses to scripts/fixtures/ for the frontend and AI streams.

Runs the real engine and schemas on hand-built synthetic fields so the canned run
shows all four statuses. Regenerate with:  python scripts/make_fixtures.py
"""

import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import routes  # noqa: E402
from app.schemas import SimulateRequest  # noqa: E402
from app.sim.snapshot import make_key, synthetic_field  # noqa: E402

OUT = Path(__file__).resolve().parent / "fixtures"
T0 = datetime(2026, 10, 3, 18, tzinfo=UTC)
DAYS = 7

REQUEST = {
    "placements": [
        {"id": "bottle-1", "type": "bottle", "coordinates": [-125.3, 48.9]},
        {"id": "bag-1", "type": "bag", "coordinates": [-125.6, 49.3]},
        {"id": "foam-1", "type": "foam", "coordinates": [-126.5, 48.5]},
        {"id": "bottle-2", "type": "bottle", "coordinates": [-126.0, 49.0]},
        {"id": "collector-1", "type": "collector", "coordinates": [-124.95, 48.82]},
    ],
    "durationDays": DAYS,
    "collectorRadiusM": 10000,
}


def fields_for_fixture() -> dict:
    def key(i: int, lon: float, lat: float):
        k = make_key(lon, lat, DAYS, T0)
        return k, f"00000000-0000-4000-8000-00000000000{i}"

    k1, id1 = key(1, -125.3, 48.9)
    k2, id2 = key(2, -125.6, 49.3)
    k3, id3 = key(3, -126.5, 48.5)
    k4, id4 = key(4, -126.0, 49.0)
    fields = {
        "bottle-1": synthetic_field(k1, uniform=(0.15, -0.05)),  # drifts into collector-1
        "bag-1": synthetic_field(k2, uniform=(0.2, 0.02), land=lambda lon, lat: lon > -125.0),  # beaches
        "foam-1": synthetic_field(k3, uniform=(-0.8, 0.1)),  # fast current, leaves the box
        "bottle-2": synthetic_field(k4, max_speed=0.3),  # gyre, still floating at the end
    }
    for f, sid in zip(fields.values(), (id1, id2, id3, id4), strict=True):
        f.snapshot_id = sid
    return fields


def write(name: str, model) -> None:
    path = OUT / name
    path.write_text(model.model_dump_json(by_alias=True, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {path.relative_to(OUT.parent.parent)} ({path.stat().st_size // 1024} KB)")


def main() -> None:
    OUT.mkdir(exist_ok=True)
    req = SimulateRequest.model_validate(REQUEST)
    fields = fields_for_fixture()

    sim = routes.build_response(req, fields).model_copy(update={"run_id": "fixture-run-simulate"})
    cmp = routes.compare(req, fields)
    cmp = cmp.model_copy(
        update={
            "without": cmp.without.model_copy(update={"run_id": "fixture-run-without"}),
            "with_": cmp.with_.model_copy(update={"run_id": "fixture-run-with"}),
        }
    )
    gyre = synthetic_field(make_key(-125.3, 48.9, DAYS, T0))
    gyre.snapshot_id = "00000000-0000-4000-8000-000000000005"
    currents = routes.CurrentsResponse(
        snapshot=routes.snapshot_info(gyre),
        bounds=gyre.bounds(),
        arrows=routes.arrows_of(gyre),
        attribution=routes.attribution_for([gyre]),
    )

    write("simulate_response.json", sim)
    write("compare_response.json", cmp)
    write("timeline_response.json", routes.timeline_of(sim))
    write("currents_response.json", currents)
    write("meta_response.json", routes.meta())
    print("summary:", sim.summary.model_dump())


if __name__ == "__main__":
    main()
