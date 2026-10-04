from __future__ import annotations

from dataclasses import dataclass
from math import cos, radians, sqrt

from .models import Coordinate, PlaceContext, RouteGeography
from .schemas import ParticleTrajectory


@dataclass(frozen=True)
class RegionBox:
    name: str
    west: float
    south: float
    east: float
    north: float
    ocean: str
    sea: str | None = None
    country: str | None = None
    coast: str | None = None

    def contains(self, lon: float, lat: float) -> bool:
        return self.west <= lon <= self.east and self.south <= lat <= self.north

    def distance_to(self, lon: float, lat: float) -> float:
        nearest_lon = min(max(lon, self.west), self.east)
        nearest_lat = min(max(lat, self.south), self.north)
        x = (lon - nearest_lon) * cos(radians((lat + nearest_lat) / 2))
        y = lat - nearest_lat
        return sqrt(x * x + y * y)


MARINE_REGIONS = (
    RegionBox("Salish Sea", -125.5, 47.0, -122.0, 50.5, "Pacific Ocean", "Salish Sea", "Canada", "British Columbia"),
    RegionBox("Gulf of Alaska", -165.0, 50.0, -135.0, 61.5, "Pacific Ocean", "Gulf of Alaska", "United States", "Alaska"),
    RegionBox("California Current", -132.0, 30.0, -116.0, 48.5, "Pacific Ocean", None, "United States", "West Coast"),
    RegionBox("North Pacific Ocean", 120.0, 0.0, 180.0, 66.0, "Pacific Ocean"),
    RegionBox("North Pacific Ocean", -180.0, 0.0, -100.0, 66.0, "Pacific Ocean"),
    RegionBox("South Pacific Ocean", 120.0, -66.0, 180.0, 0.0, "Pacific Ocean"),
    RegionBox("South Pacific Ocean", -180.0, -66.0, -70.0, 0.0, "Pacific Ocean"),
    RegionBox("North Atlantic Ocean", -100.0, 0.0, 20.0, 66.0, "Atlantic Ocean"),
    RegionBox("South Atlantic Ocean", -70.0, -66.0, 20.0, 0.0, "Atlantic Ocean"),
    RegionBox("Indian Ocean", 20.0, -66.0, 120.0, 30.0, "Indian Ocean"),
    RegionBox("Arctic Ocean", -180.0, 66.0, 180.0, 90.0, "Arctic Ocean"),
    RegionBox("Southern Ocean", -180.0, -90.0, 180.0, -66.0, "Southern Ocean"),
    RegionBox("Mediterranean Sea", -6.0, 30.0, 36.0, 46.0, "Atlantic Ocean", "Mediterranean Sea"),
    RegionBox("Caribbean Sea", -89.5, 9.0, -59.0, 23.5, "Atlantic Ocean", "Caribbean Sea"),
    RegionBox("Gulf of Mexico", -98.5, 18.0, -80.0, 31.0, "Atlantic Ocean", "Gulf of Mexico", "United States", "Gulf Coast"),
)

COASTAL_REGIONS = (
    RegionBox("British Columbia coast", -134.5, 48.0, -122.0, 55.5, "Pacific Ocean", None, "Canada", "British Columbia"),
    RegionBox("Alaska coast", -170.0, 51.0, -130.0, 61.5, "Pacific Ocean", None, "United States", "Alaska"),
    RegionBox("United States West Coast", -125.5, 32.0, -117.0, 48.8, "Pacific Ocean", None, "United States", "West Coast"),
    RegionBox("Mexico Pacific coast", -118.0, 14.0, -86.0, 32.5, "Pacific Ocean", None, "Mexico", "Pacific coast"),
    RegionBox("Canada Atlantic coast", -67.5, 43.0, -52.0, 53.5, "Atlantic Ocean", None, "Canada", "Atlantic coast"),
    RegionBox("United States East Coast", -82.0, 25.0, -66.0, 45.5, "Atlantic Ocean", None, "United States", "East Coast"),
    RegionBox("Brazil coast", -52.0, -34.0, -34.0, 6.0, "Atlantic Ocean", None, "Brazil", "Atlantic coast"),
    RegionBox("Chile coast", -76.0, -56.0, -66.0, -17.0, "Pacific Ocean", None, "Chile", "Pacific coast"),
    RegionBox("Peru coast", -83.0, -18.5, -68.0, 0.0, "Pacific Ocean", None, "Peru", "Pacific coast"),
    RegionBox("Japan coast", 128.0, 30.0, 146.0, 46.0, "Pacific Ocean", None, "Japan", "Pacific coast"),
    RegionBox("Australia east coast", 145.0, -44.0, 155.0, -10.0, "Pacific Ocean", None, "Australia", "east coast"),
    RegionBox("Australia west coast", 112.0, -36.0, 116.5, -13.0, "Indian Ocean", None, "Australia", "west coast"),
    RegionBox("South Africa coast", 16.0, -36.0, 33.0, -26.0, "Atlantic Ocean", None, "South Africa", "southern coast"),
)


def _best_region(lon: float, lat: float, regions: tuple[RegionBox, ...]) -> RegionBox | None:
    matches = [region for region in regions if region.contains(lon, lat)]
    if matches:
        return min(matches, key=lambda region: (region.east - region.west) * (region.north - region.south))
    return None


def _nearest_region(lon: float, lat: float, regions: tuple[RegionBox, ...]) -> RegionBox:
    return min(regions, key=lambda region: region.distance_to(lon, lat))


def _label(region: RegionBox, *, coastal: bool) -> str:
    if coastal and region.country and region.coast:
        return f"{region.coast}, {region.country}"
    if region.sea:
        return region.sea
    return region.ocean


def resolve_point(lon: float, lat: float, *, prefer_coast: bool = False) -> PlaceContext:
    marine = _best_region(lon, lat, MARINE_REGIONS) or _nearest_region(lon, lat, MARINE_REGIONS)
    coast = _best_region(lon, lat, COASTAL_REGIONS)
    chosen = coast if prefer_coast and coast is not None else marine
    return PlaceContext(
        coordinates=Coordinate(lon=round(lon, 5), lat=round(lat, 5)),
        label=_label(chosen, coastal=prefer_coast and coast is not None),
        ocean=chosen.ocean,
        sea=chosen.sea,
        country=chosen.country,
        coast=chosen.coast,
    )


def resolve_route(trajectory: ParticleTrajectory, *, beached: bool) -> RouteGeography:
    start = trajectory.samples[0]
    end = trajectory.samples[-1]
    start_place = resolve_point(*start.coordinates)
    end_place = resolve_point(*end.coordinates, prefer_coast=beached)
    traversed: list[str] = []
    for sample in trajectory.samples:
        place = resolve_point(*sample.coordinates)
        for value in (place.sea, place.ocean):
            if value and value not in traversed:
                traversed.append(value)
    return RouteGeography(
        start=start_place,
        end=end_place,
        traversed_regions=traversed,
        landfall=end_place if beached else None,
    )
