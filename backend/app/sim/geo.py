"""Small spherical-Earth helpers."""

import math

EARTH_RADIUS_M = 6_371_000.0
M_PER_DEG_LAT = 110_540.0
M_PER_DEG_LON_EQUATOR = 111_320.0


def haversine_m(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(a))


def m_per_deg_lon(lat: float) -> float:
    # Clamp so the poles do not divide by zero.
    return M_PER_DEG_LON_EQUATOR * max(math.cos(math.radians(lat)), 1e-3)


def bearing_deg(u: float, v: float) -> float:
    """Direction a (u east, v north) vector points, degrees clockwise from north."""
    return math.degrees(math.atan2(u, v)) % 360.0
