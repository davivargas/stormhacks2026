from app.geography import resolve_point, resolve_route
from app.schemas import ParticleTrajectory, TrajectorySample


def test_resolve_salish_sea_coordinate() -> None:
    place = resolve_point(-123.2, 48.5)

    assert place.label == "Salish Sea"
    assert place.ocean == "Pacific Ocean"
    assert place.sea == "Salish Sea"
    assert place.country == "Canada"


def test_resolve_beached_route_uses_coastal_label() -> None:
    route = resolve_route(
        ParticleTrajectory(
            id="bottle-1",
            type="bottle",
            samples=[
                TrajectorySample(time_seconds=0, coordinates=(-123.2, 48.5), status="floating"),
                TrajectorySample(time_seconds=3600, coordinates=(-123.0, 49.0), status="beached"),
            ],
        ),
        beached=True,
    )

    assert route.start.label == "Salish Sea"
    assert route.landfall is not None
    assert route.landfall.label == "British Columbia, Canada"
    assert "Salish Sea" in route.traversed_regions
