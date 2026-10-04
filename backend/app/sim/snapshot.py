"""Snapshots: one fetched box of surface currents around a drop point.

A Field holds the grid and answers sample / is_land / contains for the engine.
Longitudes are kept continuous around the box centre, so a box may extend past
+/-180 and queries are shifted into the box's frame before indexing.
"""

import concurrent.futures
import logging
import math
import threading
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

import numpy as np

from app import config

log = logging.getLogger(__name__)

COMPONENTS = ("uo", "vo", "utide", "vtide", "ustokes", "vstokes")
LandFn = Callable[[np.ndarray, np.ndarray], np.ndarray]


@dataclass(frozen=True)
class SnapshotKey:
    centre_lon: float
    centre_lat: float
    half_width_deg: float
    slice_time: datetime
    n_slices: int = 1


def _round_to(value: float, step: float) -> float:
    return round(value / step) * step


def make_key(lon: float, lat: float, duration_days: int, slice_time: datetime) -> SnapshotKey:
    return SnapshotKey(
        centre_lon=_round_to(lon, config.CENTRE_ROUND_DEG),
        centre_lat=_round_to(lat, config.CENTRE_ROUND_DEG),
        half_width_deg=config.half_width_deg(duration_days),
        slice_time=slice_time,
    )


def current_slice_time(now: datetime | None = None) -> datetime:
    """Run start rounded to the nearest hour, UTC."""
    now = now or datetime.now(UTC)
    return (now + timedelta(minutes=30)).replace(minute=0, second=0, microsecond=0)


def combine(components: dict[str, np.ndarray]) -> tuple[np.ndarray, np.ndarray]:
    """u_total / v_total from the raw components according to config."""
    u = components["uo"].copy()
    v = components["vo"].copy()
    if config.APPLY_STOKES:
        u += np.nan_to_num(components["ustokes"])
        v += np.nan_to_num(components["vstokes"])
    if config.APPLY_TIDE:
        u += np.nan_to_num(components["utide"])
        v += np.nan_to_num(components["vtide"])
    return u, v


@dataclass
class Field:
    key: SnapshotKey
    source: str  # copernicus | synthetic
    lon: np.ndarray  # (nx,) ascending, continuous around key.centre_lon
    lat: np.ndarray  # (ny,) ascending
    times: np.ndarray  # (nt,) seconds since key.slice_time
    components: dict[str, np.ndarray]  # each (nt, ny, nx) float32
    snapshot_id: str = field(default_factory=lambda: str(uuid.uuid4()))

    def __post_init__(self) -> None:
        u, v = combine(self.components)
        self.land = np.isnan(self.components["uo"])  # NaN circulation = land
        self.u = np.where(self.land, 0.0, u)
        self.v = np.where(self.land, 0.0, v)
        self._lon0, self._dlon = float(self.lon[0]), float(self.lon[1] - self.lon[0])
        self._lat0, self._dlat = float(self.lat[0]), float(self.lat[1] - self.lat[0])
        self._nx, self._ny = len(self.lon), len(self.lat)

    @property
    def nx(self) -> int:
        return self._nx

    @property
    def ny(self) -> int:
        return self._ny

    @property
    def u_total(self) -> np.ndarray:
        """Velocity with land as NaN, for display."""
        return np.where(self.land, np.nan, self.u)

    @property
    def v_total(self) -> np.ndarray:
        return np.where(self.land, np.nan, self.v)

    def _local_lon(self, lon: float) -> float:
        c = self.key.centre_lon
        return lon + 360.0 * round((c - lon) / 360.0)

    def _frac_index(self, lon: float, lat: float) -> tuple[float, float]:
        return (self._local_lon(lon) - self._lon0) / self._dlon, (lat - self._lat0) / self._dlat

    def _time_index(self, t: float) -> int:
        if len(self.times) == 1:
            return 0
        return int(np.abs(self.times - t).argmin())

    def contains(self, lon: float, lat: float) -> bool:
        fx, fy = self._frac_index(lon, lat)
        eps = 1e-6
        return -eps <= fx <= self._nx - 1 + eps and -eps <= fy <= self._ny - 1 + eps

    def is_land(self, lon: float, lat: float, t: float = 0.0) -> bool:
        """True when the nearest grid cell is land. Points outside the box are not land."""
        if not self.contains(lon, lat):
            return False
        fx, fy = self._frac_index(lon, lat)
        return bool(self.land[self._time_index(t), round(fy), round(fx)])

    def sample(self, lon: float, lat: float, t: float = 0.0) -> tuple[float, float]:
        """(u, v) in m/s: bilinear in space with land as zero, nearest slice in time."""
        fx, fy = self._frac_index(lon, lat)
        fx = min(max(fx, 0.0), self._nx - 1.0)
        fy = min(max(fy, 0.0), self._ny - 1.0)
        i0, j0 = min(int(fx), self._nx - 2), min(int(fy), self._ny - 2)
        ax, ay = fx - i0, fy - j0
        k = self._time_index(t)
        u, v = self.u[k], self.v[k]
        w00, w10, w01, w11 = (1 - ax) * (1 - ay), ax * (1 - ay), (1 - ax) * ay, ax * ay
        us = w00 * u[j0, i0] + w10 * u[j0, i0 + 1] + w01 * u[j0 + 1, i0] + w11 * u[j0 + 1, i0 + 1]
        vs = w00 * v[j0, i0] + w10 * v[j0, i0 + 1] + w01 * v[j0 + 1, i0] + w11 * v[j0 + 1, i0 + 1]
        return float(us), float(vs)

    def bounds(self) -> tuple[tuple[float, float], tuple[float, float]]:
        return (float(self.lon[0]), float(self.lat[0])), (float(self.lon[-1]), float(self.lat[-1]))


# ---- builders ---------------------------------------------------------------


def _grid(key: SnapshotKey, resolution: float) -> tuple[np.ndarray, np.ndarray]:
    n = int(round(2 * key.half_width_deg / resolution)) + 1
    lon = np.linspace(key.centre_lon - key.half_width_deg, key.centre_lon + key.half_width_deg, n)
    lat = np.linspace(key.centre_lat - key.half_width_deg, key.centre_lat + key.half_width_deg, n)
    lat = lat[(lat >= -90.0) & (lat <= 90.0)]
    return lon, lat


def synthetic_field(
    key: SnapshotKey,
    *,
    uniform: tuple[float, float] | None = None,
    land: LandFn | None = None,
    max_speed: float = 0.4,
    background: tuple[float, float] = (0.08, 0.0),
    resolution: float = config.GRID_RESOLUTION_DEG,
) -> Field:
    """A synthetic surface field on the snapshot grid.

    uniform=(u, v) gives a constant flow (used by tests). Otherwise a rotating gyre
    centred on the box, clockwise in the northern hemisphere, plus a weak background
    drift so an item dropped at the exact centre still moves.
    land(lon2d, lat2d) -> bool mask marks land cells as NaN.
    """
    lon, lat = _grid(key, resolution)
    lon2d, lat2d = np.meshgrid(lon, lat)

    if uniform is not None:
        u = np.full(lon2d.shape, uniform[0], dtype=np.float32)
        v = np.full(lon2d.shape, uniform[1], dtype=np.float32)
    else:
        dx = (lon2d - key.centre_lon) * math.cos(math.radians(key.centre_lat))
        dy = lat2d - key.centre_lat
        r = np.hypot(dx, dy)
        radius = 0.6 * key.half_width_deg
        speed = max_speed * (r / radius) * np.exp(1 - r / radius)
        spin = -1.0 if key.centre_lat >= 0 else 1.0  # clockwise north, anticlockwise south
        with np.errstate(invalid="ignore", divide="ignore"):
            u = np.where(r > 0, -spin * dy / r * speed, 0.0) + background[0]
            v = np.where(r > 0, spin * dx / r * speed, 0.0) + background[1]
        u, v = u.astype(np.float32), v.astype(np.float32)

    if land is not None:
        mask = land(lon2d, lat2d)
        u[mask] = np.nan
        v[mask] = np.nan

    zeros = np.zeros_like(u)
    components = {
        "uo": u[None],
        "vo": v[None],
        "utide": zeros[None],
        "vtide": zeros[None],
        "ustokes": zeros[None],
        "vstokes": zeros[None],
    }
    return Field(key=key, source="synthetic", lon=lon, lat=lat, times=np.array([0.0]), components=components)


_TIME_FORMAT = "%Y-%m-%dT%H:%M:%S"

# The dataset calls Stokes drift vsdx / vsdy; the rest of the code uses ustokes / vstokes.
_DATASET_NAMES = {"ustokes": "vsdx", "vstokes": "vsdy"}
_DATASET_VARIABLES = [_DATASET_NAMES.get(name, name) for name in COMPONENTS]


def fetch_bounds(key: SnapshotKey) -> tuple[float, float, float, float]:
    """(west, south, east, north) to request, cut at the edge of the map.

    A box that crosses the antimeridian is fetched only up to +/-180; an item that
    reaches the cut becomes outside. Synthetic boxes are not cut.
    """
    hw = key.half_width_deg
    return (
        max(-180.0, key.centre_lon - hw),
        max(-90.0, key.centre_lat - hw),
        min(180.0, key.centre_lon + hw),
        min(90.0, key.centre_lat + hw),
    )


def field_from_dataset(ds, key: SnapshotKey) -> Field:
    """Turn an xarray Dataset covering the box into a single-slice Field."""
    if "depth" in ds.dims:
        ds = ds.isel(depth=0)
    target = np.datetime64(key.slice_time.astimezone(UTC).replace(tzinfo=None))
    ds = ds.sel(time=target, method="nearest").load()
    lon = ds["longitude"].values.astype("float64")
    lat = ds["latitude"].values.astype("float64")
    if lon.size < 2 or lat.size < 2:
        raise ValueError(f"Copernicus returned no usable grid for {key}")
    layers = {
        name: ds[_DATASET_NAMES.get(name, name)].transpose("latitude", "longitude").values.astype(np.float32)
        for name in COMPONENTS
    }
    if lat[0] > lat[-1]:
        lat = lat[::-1].copy()
        layers = {name: values[::-1, :] for name, values in layers.items()}
    components = {name: np.ascontiguousarray(values)[None] for name, values in layers.items()}
    return Field(key=key, source="copernicus", lon=lon, lat=lat, times=np.array([0.0]), components=components)


def fetch_copernicus(key: SnapshotKey) -> Field:
    """Download one box of hourly surface currents. Credentials come from the environment."""
    import copernicusmarine  # lazy: slow import, and tests substitute it

    west, south, east, north = fetch_bounds(key)
    ds = copernicusmarine.open_dataset(
        dataset_id=config.COPERNICUS_DATASET_ID,
        variables=_DATASET_VARIABLES,
        minimum_longitude=west,
        maximum_longitude=east,
        minimum_latitude=south,
        maximum_latitude=north,
        start_datetime=(key.slice_time - timedelta(hours=1)).strftime(_TIME_FORMAT),
        end_datetime=(key.slice_time + timedelta(hours=1)).strftime(_TIME_FORMAT),
    )
    return field_from_dataset(ds, key)


# ---- in-process cache -------------------------------------------------------

# key -> (field, expiry). expiry is None for real snapshots, a time.monotonic() deadline for fallbacks.
_cache: dict[SnapshotKey, tuple[Field, float | None]] = {}
# Until this time.monotonic() deadline, Copernicus is skipped: one failure covers every box.
_copernicus_down_until: float = 0.0
_lock = threading.Lock()
_pool = concurrent.futures.ThreadPoolExecutor(max_workers=4)


def _cached(key: SnapshotKey) -> Field | None:
    with _lock:
        entry = _cache.get(key)
    if entry is None:
        return None
    fld, expires = entry
    if expires is not None and time.monotonic() >= expires:
        return None
    return fld


def _remember(key: SnapshotKey, fld: Field, ttl: float | None = None) -> Field:
    with _lock:
        _cache[key] = (fld, None if ttl is None else time.monotonic() + ttl)
    return fld


def _fetch_with_timeout(key: SnapshotKey) -> Field | None:
    """Copernicus within the time budget. Network, auth, timeout or empty box: None.

    After a failure Copernicus is skipped for SYNTHETIC_RETRY_S, so a request with
    many boxes pays for one failed fetch, not one per box.
    """
    global _copernicus_down_until
    if time.monotonic() < _copernicus_down_until:
        return None
    future = _pool.submit(fetch_copernicus, key)
    try:
        return future.result(timeout=config.COPERNICUS_TIMEOUT_S)
    except Exception:
        log.warning("copernicus fetch failed for %s, using synthetic field", key, exc_info=True)
        _copernicus_down_until = time.monotonic() + config.SYNTHETIC_RETRY_S
        return None


def load_field(key: SnapshotKey) -> Field:
    """Cached field for the key: Copernicus, or a synthetic gyre if that fails.

    A fallback is reused for SYNTHETIC_RETRY_S so one request sees one field per box,
    then the real source is tried again.
    """
    cached = _cached(key)
    if cached is not None:
        return cached
    fld = _fetch_with_timeout(key)
    if fld is None:
        return _remember(key, synthetic_field(key), ttl=config.SYNTHETIC_RETRY_S)
    return _remember(key, fld)
