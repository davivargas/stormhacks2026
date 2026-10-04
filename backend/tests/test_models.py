from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.models import SimulationSummary


def test_rejects_event_after_simulation_duration() -> None:
    with pytest.raises(ValidationError, match="cannot exceed duration_hours"):
        SimulationSummary.model_validate(
            {
                "simulation_id": "sim-001",
                "litter_type": "plastic_bottle",
                "particle_id": "particle-001",
                "duration_hours": 4,
                "events": [
                    {"elapsed_hours": 0, "type": "released"},
                    {"elapsed_hours": 5, "type": "beached"},
                ],
                "final_status": "beached",
                "assumptions": [],
            }
        )


def test_rejects_events_that_are_not_chronological() -> None:
    with pytest.raises(ValidationError, match="ordered by elapsed_hours"):
        SimulationSummary.model_validate(
            {
                "simulation_id": "sim-001",
                "litter_type": "plastic_bottle",
                "particle_id": "particle-001",
                "duration_hours": 8,
                "events": [
                    {"elapsed_hours": 6, "type": "floating"},
                    {"elapsed_hours": 2, "type": "released"},
                ],
                "final_status": "floating",
                "assumptions": [],
            }
        )


def test_rejects_unknown_final_status() -> None:
    with pytest.raises(ValidationError):
        SimulationSummary.model_validate(
            {
                "simulation_id": "sim-001",
                "litter_type": "plastic_bottle",
                "particle_id": "particle-001",
                "duration_hours": 8,
                "events": [{"elapsed_hours": 0, "type": "released"}],
                "final_status": "vanished",
                "assumptions": [],
            }
        )
