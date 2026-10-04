from app.models import FinalStatus
from app.schemas import (
    Attribution,
    ItemResult,
    ParticleTrajectory,
    SimulateResponse,
    Summary,
    TrajectorySample,
)
from app.story_summary import build_story_summary_from_run


def make_run() -> SimulateResponse:
    return SimulateResponse(
        run_id="run-geo-001",
        duration_days=1,
        total_seconds=86400,
        sample_interval_seconds=3600,
        trajectories=[
            ParticleTrajectory(
                id="bottle-1",
                type="bottle",
                samples=[
                    TrajectorySample(time_seconds=0, coordinates=(-123.2, 48.5), status="floating"),
                    TrajectorySample(time_seconds=3600, coordinates=(-123.0, 49.0), status="beached"),
                ],
            )
        ],
        items=[
            ItemResult(
                id="bottle-1",
                type="bottle",
                final_status="beached",
                status_changed_at_seconds=3600,
            )
        ],
        collectors=[],
        summary=Summary(beached=1),
        snapshots=[],
        attribution=Attribution(
            source="Copernicus Marine Service",
            dataset="test",
            limitations=["No wind, sinking or breakdown"],
        ),
        persisted=True,
    )


def test_build_story_summary_from_run_adds_geography() -> None:
    summary = build_story_summary_from_run(make_run(), "bottle-1")

    assert summary is not None
    assert summary.simulation_id == "run-geo-001"
    assert summary.particle_id == "bottle-1"
    assert summary.final_status == FinalStatus.beached
    assert summary.events[0].location == "Salish Sea"
    assert summary.events[0].coordinates is not None
    assert summary.events[1].location == "British Columbia, Canada"
    assert summary.geography is not None
    assert summary.geography.start.label == "Salish Sea"
    assert summary.geography.landfall is not None
    assert summary.geography.landfall.country == "Canada"


def test_build_story_summary_from_run_returns_none_for_missing_particle() -> None:
    assert build_story_summary_from_run(make_run(), "missing") is None
