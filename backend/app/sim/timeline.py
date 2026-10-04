"""Counts on the run clock, including sparse birth and terminal-event samples."""

from bisect import bisect_right

from app.schemas import SimulateResponse, TimelineBucket, TimelineResponse
from app.sim.engine import STATUSES


def timeline_of(resp: SimulateResponse) -> TimelineResponse:
    sample_times = [[sample.time_seconds for sample in trajectory.samples] for trajectory in resp.trajectories]
    buckets = []
    for t in range(0, resp.total_seconds + 1, resp.sample_interval_seconds):
        counts = dict.fromkeys(STATUSES, 0)
        for trajectory, times in zip(resp.trajectories, sample_times):
            index = bisect_right(times, t) - 1
            if index >= 0:
                counts[trajectory.samples[index].status] += 1
        buckets.append(TimelineBucket(time_seconds=t, **counts))
    return TimelineResponse(run_id=resp.run_id, bucket_seconds=resp.sample_interval_seconds, buckets=buckets)
