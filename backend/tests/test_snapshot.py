from datetime import UTC, datetime

import numpy as np

from app import config
from app.sim.snapshot import COMPONENTS, make_key, synthetic_field

T0 = datetime(2026, 10, 3, 18, tzinfo=UTC)


def test_half_width_table():
    # room for about 1 m/s (0.8 degrees a day), rounded up to half a degree, capped at 10
    assert config.half_width_deg(1) == 1.5
    assert config.half_width_deg(2) == 2.5
    assert config.half_width_deg(7) == 6.5
    assert config.half_width_deg(11) == 9.5
    assert config.half_width_deg(12) == 10.0
    assert config.half_width_deg(30) == 10.0


def test_key_rounds_centre_to_half_degree():
    key = make_key(-125.3, 48.9, 7, T0)
    assert (key.centre_lon, key.centre_lat, key.half_width_deg) == (-125.5, 49.0, 6.5)


def test_synthetic_field_shape_and_land():
    key = make_key(-125.0, 49.0, 1, T0)
    fld = synthetic_field(key, land=lambda lon, lat: lon > -124.0)

    assert fld.nx == fld.ny == 37  # 3 degrees at 1/12 plus the closing edge
    for name in COMPONENTS:
        assert fld.components[name].shape == (1, fld.ny, fld.nx)
    land = np.isnan(fld.components["uo"][0])
    assert land[:, fld.lon > -124.0].all()
    assert not land[:, fld.lon <= -124.0].any()
    assert fld.is_land(-123.75, 49.0)
    assert fld.contains(-123.5, 49.0)  # exact box edge counts as inside
    assert not fld.is_land(-125.0, 49.0)
    assert fld.sample(-125.0, 49.0) != (0.0, 0.0)  # background drift: centre still moves
