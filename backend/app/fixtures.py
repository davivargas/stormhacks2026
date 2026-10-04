from __future__ import annotations

from .models import SimulationSummary


BEACHED_ITEM = SimulationSummary.model_validate(
    {
        "simulation_id": "sim-beached-001",
        "litter_type": "plastic_bottle",
        "particle_id": "particle-beached-001",
        "duration_hours": 24,
        "events": [
            {"elapsed_hours": 0, "type": "released"},
            {"elapsed_hours": 6, "type": "beached"},
        ],
        "final_status": "beached",
        "assumptions": ["Ocean currents only", "Wind and waves excluded"],
    }
)

CAPTURED_ITEM = SimulationSummary.model_validate(
    {
        "simulation_id": "sim-captured-001",
        "litter_type": "plastic_bag",
        "particle_id": "particle-captured-001",
        "duration_hours": 24,
        "events": [
            {"elapsed_hours": 0, "type": "released"},
            {"elapsed_hours": 9, "type": "captured"},
        ],
        "final_status": "captured",
        "assumptions": ["Ocean currents only", "Wind and waves excluded"],
    }
)

FLOATING_ITEM = SimulationSummary.model_validate(
    {
        "simulation_id": "sim-floating-001",
        "litter_type": "foam_container",
        "particle_id": "particle-floating-001",
        "duration_hours": 24,
        "events": [
            {"elapsed_hours": 0, "type": "released"},
            {"elapsed_hours": 24, "type": "still_floating"},
        ],
        "final_status": "floating",
        "assumptions": ["Ocean currents only", "Wind and waves excluded"],
    }
)

FIXTURES = {
    "beached": BEACHED_ITEM,
    "captured": CAPTURED_ITEM,
    "floating": FLOATING_ITEM,
}
