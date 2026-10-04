import type { SimulationRequest, SimulationResponse } from "./types";

export const requestFixture: SimulationRequest = {
  placements: [{ id: "b", type: "bottle", coordinates: [-130, 40], placedAtSeconds: 21600 }],
  durationDays: 1,
  collectorRadiusM: 10_000,
  honourCollectors: true,
};

export function responseFixture(): SimulationResponse {
  return {
    runId: "run-1",
    durationDays: 1,
    totalSeconds: 86400,
    sampleIntervalSeconds: 3600,
    trajectories: [{
      id: "b", type: "bottle", samples: [
        { timeSeconds: 21600, coordinates: [-130, 40], status: "floating" },
        { timeSeconds: 22200, coordinates: [-129.99, 40], status: "captured" },
        { timeSeconds: 86400, coordinates: [-129.99, 40], status: "captured" },
      ],
    }],
    items: [{ id: "b", type: "bottle", finalStatus: "captured", capturedBy: "c", statusChangedAtSeconds: 22200 }],
    collectors: [{ id: "c", coordinates: [-129.99, 40], radiusM: 10_000, capturedCount: 1 }],
    summary: { floating: 0, captured: 1, beached: 0, outside: 0 },
    snapshots: [{ snapshotId: "snapshot-1", source: "synthetic", sliceTime: "2026-10-04T12:00:00Z", nSlices: 1 }],
    attribution: { source: "Synthetic demo", dataset: "synthetic", limitations: ["Single frozen time slice"] },
    persisted: false,
  };
}
