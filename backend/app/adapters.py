from __future__ import annotations

from typing import Any, Protocol

from .models import SimulationSummary


class SimulationAdapter(Protocol):
    """Boundary for the future simulation service contract."""

    def normalize(self, payload: SimulationSummary | dict[str, Any]) -> SimulationSummary: ...


class ContractSimulationAdapter:
    """Normalizes today's mock contract without coupling the AI pipeline to its producer."""

    def normalize(self, payload: SimulationSummary | dict[str, Any]) -> SimulationSummary:
        if isinstance(payload, SimulationSummary):
            return payload
        return SimulationSummary.model_validate(payload)
