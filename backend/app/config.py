"""Constants for the simulation and the API. Everything tunable lives here."""

import math
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

# Durations: whole days, one timeline per run.
DURATION_MIN_DAYS = 1
DURATION_MAX_DAYS = 30
DURATION_DEFAULT_DAYS = 7

# Integration.
DT_SECONDS = 600  # 10 min Euler step
FRAME_INTERVAL_SECONDS = 3600  # one recorded sample per hour

# Collectors and request limits.
DEFAULT_COLLECTOR_RADIUS_M = 10_000.0
MAX_LITTER_PLACEMENTS = 50

# Snapshot box.
HALF_WIDTH_CAP_DEG = 8.0
CENTRE_ROUND_DEG = 0.5
GRID_RESOLUTION_DEG = 1 / 12

# Which current components are summed into u_total / v_total.
APPLY_STOKES = True
APPLY_TIDE = False  # frozen tidal phase is wrong for days-long drift; on with multi-slice

# Per litter type drift multiplier. Identical until documented otherwise.
LITTER_TYPES = ("bottle", "bag", "foam")
DRIFT_FACTOR = {"bottle": 1.0, "bag": 1.0, "foam": 1.0}

# Copernicus.
COPERNICUS_DATASET_ID = "cmems_mod_glo_phy_anfc_merged-uv_PT1H-i"
COPERNICUS_TIMEOUT_S = 20
SYNTHETIC_RETRY_S = 60  # a fallback field is reused this long before Copernicus is tried again

# Arrows returned by /currents: roughly this many per side.
CURRENT_ARROWS_PER_SIDE = 20

ATTRIBUTION_SOURCE = "Copernicus Marine Service, Global Ocean Physics Analysis and Forecast"
SYNTHETIC_SOURCE = "Synthetic rotating gyre (Copernicus data unavailable)"
LIMITATIONS = [
    "Single frozen time slice",
    "No tide in MVP",
    "No wind, sinking or breakdown",
    "About 9 km grid",
]

CORS_ORIGINS = [o.strip() for o in os.getenv("CORS_ORIGIN", "http://localhost:5173").split(",") if o.strip()]
DATABASE_URL = os.getenv("DATABASE_URL")


def half_width_deg(duration_days: int) -> float:
    """Box half-width: room for a 0.5 m/s current, rounded up to half a degree, capped."""
    raw = 1.0 + 0.4 * duration_days
    return min(HALF_WIDTH_CAP_DEG, math.ceil(raw * 2) / 2)
