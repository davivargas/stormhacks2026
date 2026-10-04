"""The /api endpoints.

Phase 1: runs are kept in an in-process store. Phase 3 swaps it for Tiger Data
(save_run / load_run / timeline in db.py) without changing response shapes.
"""

import uuid
from collections import OrderedDict

from fastapi import APIRouter, Query

from app import config
from app.schemas import (
    Attribution,
    CollectorResult,
    CompareResponse,
    CurrentArrow,
    CurrentsResponse,
    DurationRange,
    HealthResponse,
    ItemResult,
    MetaDefaults,
    MetaResponse,
    ParticleTrajectory,
    SimulateRequest,
    SimulateResponse,
    SnapshotInfo,
    Summary,
    TimelineBucket,
    TimelineResponse,
    TrajectorySample,
)
from app.sim import engine
from app.sim.geo import bearing_deg
from app.sim.snapshot import Field, current_slice_time, load_field, make_key

router = APIRouter(prefix="/api")

MAX_STORED_RUNS = 200
_runs: OrderedDict[str, SimulateResponse] = OrderedDict()


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str, placement_id: str | None = None):
        super().__init__(message)
        self.status, self.code, self.message, self.placement_id = status, code, message, placement_id


# ---- helpers ----------------------------------------------------------------


def attribution_for(fields: list[Field]) -> Attribution:
    if fields and all(f.source == "copernicus" for f in fields):
        return Attribution(
            source=config.ATTRIBUTION_SOURCE, dataset=config.COPERNICUS_DATASET_ID, limitations=config.LIMITATIONS
        )
    return Attribution(
        source=config.SYNTHETIC_SOURCE,
        dataset="synthetic",
        limitations=["Synthetic currents: real ocean data was unavailable", *config.LIMITATIONS],
    )


def snapshot_info(f: Field) -> SnapshotInfo:
    return SnapshotInfo(snapshot_id=f.snapshot_id, source=f.source, slice_time=f.key.slice_time, n_slices=f.key.n_slices)


def _remember(resp: SimulateResponse) -> None:
    _runs[resp.run_id] = resp
    while len(_runs) > MAX_STORED_RUNS:
        _runs.popitem(last=False)


def load_fields(req: SimulateRequest) -> dict[str, Field]:
    """One field per litter item (shared when keys match); rejects drops on land."""
    slice_time = current_slice_time()
    fields: dict[str, Field] = {}
    for p in req.placements:
        if p.type == "collector":
            continue
        lon, lat = p.coordinates
        fld = load_field(make_key(lon, lat, req.duration_days, slice_time))
        if fld.is_land(lon, lat):
            raise ApiError(422, "on_land", "That spot is land. Try the water!", p.id)
        fields[p.id] = fld
    return fields


def build_response(
    req: SimulateRequest, fields: dict[str, Field], *, honour_collectors: bool = True
) -> SimulateResponse:
    litter = [
        engine.LitterItem(p.id, p.type, *p.coordinates) for p in req.placements if p.type != "collector"
    ]
    collectors = [
        engine.Collector(p.id, *p.coordinates, req.collector_radius_m)
        for p in req.placements
        if p.type == "collector"
    ]
    result = engine.run(litter, collectors if honour_collectors else [], req.duration_days, fields)

    unique_fields = list({f.snapshot_id: f for f in fields.values()}.values())
    resp = SimulateResponse(
        run_id=str(uuid.uuid4()),
        duration_days=req.duration_days,
        total_seconds=req.duration_days * 24 * 3600,
        sample_interval_seconds=config.FRAME_INTERVAL_SECONDS,
        trajectories=[
            ParticleTrajectory(
                id=o.id,
                type=o.type,
                samples=[TrajectorySample(time_seconds=t, coordinates=(lo, la), status=s) for t, lo, la, s in o.samples],
            )
            for o in result.outcomes
        ],
        items=[
            ItemResult(
                id=o.id,
                type=o.type,
                final_status=o.final_status,
                captured_by=o.captured_by,
                status_changed_at_seconds=o.status_changed_at_seconds,
            )
            for o in result.outcomes
        ],
        collectors=[
            CollectorResult(
                id=c.id,
                coordinates=(c.lon, c.lat),
                radius_m=c.radius_m,
                captured_count=result.captured_counts.get(c.id, 0),
            )
            for c in collectors
        ],
        summary=Summary(**result.summary),
        snapshots=[snapshot_info(f) for f in unique_fields],
        attribution=attribution_for(unique_fields),
        persisted=False,
    )
    _remember(resp)
    return resp


def compare(req: SimulateRequest, fields: dict[str, Field]) -> CompareResponse:
    without = build_response(req, fields, honour_collectors=False)
    with_ = build_response(req, fields, honour_collectors=True)
    w, o = with_.summary, without.summary
    delta = Summary(
        floating=w.floating - o.floating,
        captured=w.captured - o.captured,
        beached=w.beached - o.beached,
        outside=w.outside - o.outside,
    )
    return CompareResponse(without=without, with_=with_, delta=delta)


def timeline_of(resp: SimulateResponse) -> TimelineResponse:
    n = len(resp.trajectories[0].samples) if resp.trajectories else 0
    buckets = []
    for i in range(n):
        counts = {s: 0 for s in engine.STATUSES}
        for traj in resp.trajectories:
            counts[traj.samples[i].status] += 1
        buckets.append(TimelineBucket(time_seconds=i * resp.sample_interval_seconds, **counts))
    return TimelineResponse(run_id=resp.run_id, bucket_seconds=resp.sample_interval_seconds, buckets=buckets)


def arrows_of(fld: Field) -> list[CurrentArrow]:
    stride = max(1, max(fld.nx, fld.ny) // config.CURRENT_ARROWS_PER_SIDE)
    u, v = fld.u_total[0], fld.v_total[0]
    arrows = []
    for j in range(0, fld.ny, stride):
        for i in range(0, fld.nx, stride):
            uu, vv = float(u[j, i]), float(v[j, i])
            if uu != uu:  # NaN: land
                continue
            lon = (float(fld.lon[i]) + 180.0) % 360.0 - 180.0
            arrows.append(
                CurrentArrow(
                    coordinates=(round(lon, 4), round(float(fld.lat[j]), 4)),
                    u=round(uu, 4),
                    v=round(vv, 4),
                    speed=round((uu * uu + vv * vv) ** 0.5, 4),
                    bearing=round(bearing_deg(uu, vv), 1),
                )
            )
    return arrows


# ---- endpoints --------------------------------------------------------------


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(ok=True, db=False)  # phase 3 pings Tiger


@router.get("/meta", response_model=MetaResponse)
def meta() -> MetaResponse:
    return MetaResponse(
        duration_days=DurationRange(
            min=config.DURATION_MIN_DAYS, max=config.DURATION_MAX_DAYS, default=config.DURATION_DEFAULT_DAYS
        ),
        defaults=MetaDefaults(
            collector_radius_m=config.DEFAULT_COLLECTOR_RADIUS_M,
            sample_interval_seconds=config.FRAME_INTERVAL_SECONDS,
            integration_step_seconds=config.DT_SECONDS,
            max_litter_placements=config.MAX_LITTER_PLACEMENTS,
        ),
        litter_types=list(config.LITTER_TYPES),
        attribution=Attribution(
            source=config.ATTRIBUTION_SOURCE, dataset=config.COPERNICUS_DATASET_ID, limitations=config.LIMITATIONS
        ),
    )


@router.get("/currents", response_model=CurrentsResponse)
def currents(
    lon: float = Query(ge=-180, le=180),
    lat: float = Query(ge=-90, le=90),
    duration_days: int = Query(
        default=config.DURATION_DEFAULT_DAYS,
        alias="durationDays",
        ge=config.DURATION_MIN_DAYS,
        le=config.DURATION_MAX_DAYS,
    ),
) -> CurrentsResponse:
    fld = load_field(make_key(lon, lat, duration_days, current_slice_time()))
    return CurrentsResponse(
        snapshot=snapshot_info(fld), bounds=fld.bounds(), arrows=arrows_of(fld), attribution=attribution_for([fld])
    )


@router.post("/simulate", response_model=SimulateResponse)
def simulate(req: SimulateRequest) -> SimulateResponse:
    return build_response(req, load_fields(req))


@router.post("/compare", response_model=CompareResponse)
def compare_endpoint(req: SimulateRequest) -> CompareResponse:
    return compare(req, load_fields(req))


def _get_run(run_id: str) -> SimulateResponse:
    resp = _runs.get(run_id)
    if resp is None:
        raise ApiError(404, "run_not_found", f"No run with id {run_id}")
    return resp


@router.get("/runs/{run_id}", response_model=SimulateResponse)
def get_run(run_id: str) -> SimulateResponse:
    return _get_run(run_id)


@router.get("/runs/{run_id}/timeline", response_model=TimelineResponse)
def get_timeline(run_id: str) -> TimelineResponse:
    return timeline_of(_get_run(run_id))
