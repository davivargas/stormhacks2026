"""Manual check that real currents arrive. Run from backend/:  python scripts/smoke_copernicus.py"""
import math
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.sim.snapshot import current_slice_time, fetch_copernicus, make_key  # noqa: E402

POINTS = {
    "North Pacific": (-140.2, 32.1),
    "Bay of Bengal": (88.3, 15.2),
    "Off Vancouver Island": (-126.4, 48.6),
    "Fiji, at the antimeridian": (179.9, -17.0),
}

for name, (lon, lat) in POINTS.items():
    key = make_key(lon, lat, 7, current_slice_time())
    started = time.monotonic()
    fld = fetch_copernicus(key)
    u, v = fld.sample(lon, lat)
    print(f"{name}: {time.monotonic() - started:.1f}s  grid {fld.nx}x{fld.ny}  "
          f"land {fld.land.mean():.0%}  speed {math.hypot(u, v):.2f} m/s")
