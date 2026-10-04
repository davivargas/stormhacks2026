from __future__ import annotations

from .geography import resolve_route
from .models import Coordinate, FinalStatus, SimulationEvent, SimulationSummary
from .schemas import ParticleStatus, ParticleTrajectory, SimulateResponse


def story_event_type(status: ParticleStatus) -> str:
    return "outside_domain" if status == "outside" else status


def build_story_summary_from_run(run: SimulateResponse, particle_id: str) -> SimulationSummary | None:
    trajectory = next((item for item in run.trajectories if item.id == particle_id), None)
    if trajectory is None or not trajectory.samples:
        return None
    item = next((candidate for candidate in run.items if candidate.id == trajectory.id), None)
    final_status = item.final_status if item is not None else trajectory.samples[-1].status
    geography = resolve_route(trajectory, beached=final_status == "beached")
    events = _events_for_trajectory(trajectory, geography.start.label, geography.end.label)
    return SimulationSummary(
        simulation_id=run.run_id,
        litter_type=f"plastic_{trajectory.type}",
        particle_id=trajectory.id,
        duration_hours=run.total_seconds / 3600,
        events=events,
        final_status=FinalStatus.outside_domain if final_status == "outside" else FinalStatus(final_status),
        assumptions=[
            "This path follows ocean current data",
            *run.attribution.limitations,
        ],
        geography=geography,
    )


def _events_for_trajectory(
    trajectory: ParticleTrajectory,
    start_location: str,
    end_location: str,
) -> list[SimulationEvent]:
    first = trajectory.samples[0]
    events = [
        SimulationEvent(
            elapsed_hours=first.time_seconds / 3600,
            type="released",
            location=start_location,
            coordinates=Coordinate(lon=first.coordinates[0], lat=first.coordinates[1]),
        )
    ]
    previous_status = first.status
    for sample in trajectory.samples[1:]:
        if sample.status == previous_status:
            continue
        events.append(
            SimulationEvent(
                elapsed_hours=sample.time_seconds / 3600,
                type=story_event_type(sample.status),
                location=end_location,
                coordinates=Coordinate(lon=sample.coordinates[0], lat=sample.coordinates[1]),
            )
        )
        previous_status = sample.status
    if len(events) == 1:
        last = trajectory.samples[-1]
        events.append(
            SimulationEvent(
                elapsed_hours=last.time_seconds / 3600,
                type="still_floating",
                location=end_location,
                coordinates=Coordinate(lon=last.coordinates[0], lat=last.coordinates[1]),
            )
        )
    return events
