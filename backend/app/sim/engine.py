"""Forward Euler drift of litter items through frozen snapshot fields.

Deterministic: same items and same fields give the same frames.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

from app import config
from app.sim.geo import M_PER_DEG_LAT, haversine_m, m_per_deg_lon
from app.sim.snapshot import Field

STATUSES = ("floating", "captured", "beached", "outside")


@dataclass(frozen=True)
class LitterItem:
    id: str
    type: str
    lon: float
    lat: float


@dataclass(frozen=True)
class Collector:
    id: str
    lon: float
    lat: float
    radius_m: float


@dataclass
class ItemOutcome:
    id: str
    type: str
    final_status: str
    captured_by: str | None
    status_changed_at_seconds: int | None
    samples: list[tuple[int, float, float, str]]  # (timeSeconds, lon, lat, status)


@dataclass
class RunResult:
    outcomes: list[ItemOutcome]
    captured_counts: dict[str, int]
    summary: dict[str, int] = field(default_factory=dict)


def _nearest_collector(lon: float, lat: float, collectors: Sequence[Collector]) -> str | None:
    best_id, best_d = None, float("inf")
    for c in collectors:
        d = haversine_m(lon, lat, c.lon, c.lat)
        if d <= c.radius_m and d < best_d:
            best_id, best_d = c.id, d
    return best_id


def _check(lon: float, lat: float, t: float, fld: Field, collectors: Sequence[Collector]) -> tuple[str, str | None]:
    """Status checks in spec order: outside, beached, captured.

    Outside is first: a position beyond the snapshot box has no current data, so it
    must never be credited to a collector or reported as beached.
    """
    if not fld.contains(lon, lat):
        return "outside", None
    if fld.is_land(lon, lat, t):
        return "beached", None
    cp = _nearest_collector(lon, lat, collectors)
    if cp is not None:
        return "captured", cp
    return "floating", None


def drift_item(
    item: LitterItem,
    fld: Field,
    collectors: Sequence[Collector],
    duration_days: int,
    dt: int = config.DT_SECONDS,
    frame_interval: int = config.FRAME_INTERVAL_SECONDS,
) -> ItemOutcome:
    if frame_interval % dt:
        raise ValueError("frame_interval must be a multiple of dt")
    total = duration_days * 24 * 3600
    steps_per_frame = frame_interval // dt
    factor = config.DRIFT_FACTOR.get(item.type, 1.0)

    lon, lat = item.lon, item.lat
    status, captured_by = _check(lon, lat, 0, fld, collectors)
    changed_at = 0 if status != "floating" else None
    samples = [(0, round(lon, 5), round(lat, 5), status)]

    for step in range(1, total // dt + 1):
        t = step * dt
        if status == "floating":
            u, v = fld.sample(lon, lat, t - dt)
            lat += factor * v * dt / M_PER_DEG_LAT
            lon += factor * u * dt / m_per_deg_lon(lat)
            status, captured_by = _check(lon, lat, t, fld, collectors)
            if status != "floating":
                changed_at = t
        if step % steps_per_frame == 0:
            samples.append((t, round(lon, 5), round(lat, 5), status))

    return ItemOutcome(item.id, item.type, status, captured_by, changed_at, samples)


def run(
    items: Sequence[LitterItem],
    collectors: Sequence[Collector],
    duration_days: int,
    fields: Mapping[str, Field],
    **kwargs,
) -> RunResult:
    """Drift every item through its own field (fields keyed by item id) on one shared timeline."""
    outcomes = [drift_item(it, fields[it.id], collectors, duration_days, **kwargs) for it in items]
    counts = {c.id: 0 for c in collectors}
    summary = {s: 0 for s in STATUSES}
    for o in outcomes:
        summary[o.final_status] += 1
        if o.captured_by is not None:
            counts[o.captured_by] += 1
    return RunResult(outcomes, counts, summary)
