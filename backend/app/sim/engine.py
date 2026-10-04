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
    placed_at_seconds: int = 0


@dataclass(frozen=True)
class Collector:
    id: str
    lon: float
    lat: float
    radius_m: float
    placed_at_seconds: int = 0


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


def _nearest_collector(lon: float, lat: float, collectors: Sequence[Collector], t: float) -> str | None:
    best_id, best_d = None, float("inf")
    for c in collectors:
        if c.placed_at_seconds > t:
            continue
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
    cp = _nearest_collector(lon, lat, collectors, t)
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
    factor = config.DRIFT_FACTOR.get(item.type, 1.0)

    lon, lat = item.lon, item.lat
    t = item.placed_at_seconds
    if not 0 <= t <= total:
        raise ValueError("placement time must be within the experiment duration")
    status, captured_by = _check(lon, lat, t, fld, collectors)
    changed_at = t if status != "floating" else None
    samples = [(t, round(lon, 5), round(lat, 5), status)]
    activation_times = sorted({c.placed_at_seconds for c in collectors if t < c.placed_at_seconds <= total})

    while t < total:
        # Split steps at placements so neither litter nor a collector is active
        # before its exact timestamp. Hourly samples stay on the shared clock.
        next_t = min(total, (t // dt + 1) * dt)
        if activation_times:
            next_t = min(next_t, activation_times[0])
        step_seconds = next_t - t
        previous_status = status
        if status == "floating":
            u, v = fld.sample(lon, lat, t)
            lat += factor * v * step_seconds / M_PER_DEG_LAT
            lon += factor * u * step_seconds / m_per_deg_lon(lat)
            status, captured_by = _check(lon, lat, next_t, fld, collectors)
            if status != "floating":
                changed_at = next_t
        t = next_t
        if activation_times and activation_times[0] == t:
            activation_times.pop(0)
        if t % frame_interval == 0 or t == total or status != previous_status:
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
