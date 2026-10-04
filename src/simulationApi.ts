import type { Coordinates, LitterType, ParticleStatus, ParticleTrajectory, Placement } from "./types";
import { placementTime, SECONDS_PER_DAY } from "./timeline";

export interface SimulationPlacement {
  id: string;
  type: LitterType | "collector";
  coordinates: Coordinates;
  placedAtSeconds: number;
}

export interface SimulateRequest {
  placements: SimulationPlacement[];
  durationDays: number;
  collectorRadiusM?: number;
  honourCollectors: boolean;
}

export interface ItemResult {
  id: string;
  type: LitterType;
  finalStatus: ParticleStatus;
  capturedBy?: string | null;
  statusChangedAtSeconds?: number | null;
}

export interface CollectorResult {
  id: string;
  coordinates: Coordinates;
  radiusM: number;
  capturedCount: number;
}

export interface SimulationSummaryCounts {
  floating: number;
  captured: number;
  beached: number;
  outside: number;
}

export interface SnapshotInfo {
  snapshotId: string;
  source: "copernicus" | "synthetic";
  sliceTime: string;
  nSlices: number;
}

export interface Attribution {
  source: string;
  dataset: string;
  limitations: string[];
}

export interface SimulateResponse {
  runId: string;
  durationDays: number;
  totalSeconds: number;
  sampleIntervalSeconds: number;
  trajectories: ParticleTrajectory[];
  items: ItemResult[];
  collectors: CollectorResult[];
  summary: SimulationSummaryCounts;
  snapshots: SnapshotInfo[];
  attribution: Attribution;
  persisted: boolean;
}

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

export class SimulationApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly code?: string,
    readonly placementId?: string,
  ) {
    super(message);
    this.name = "SimulationApiError";
  }
}

async function parseResponse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const body = (await response.json().catch(() => null)) as {
      code?: string;
      detail?: string;
      message?: string;
      placementId?: string;
    } | null;
    throw new SimulationApiError(
      body?.message ?? body?.detail ?? `LitterVoyage API request failed (${response.status})`,
      response.status,
      body?.code,
      body?.placementId,
    );
  }
  return response.json() as Promise<T>;
}

export async function requestSimulation(
  placements: Placement[],
  options: { durationDays: number; honourCollectors: boolean; signal?: AbortSignal },
): Promise<SimulateResponse> {
  const response = await fetch(`${API_BASE_URL}/api/simulate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    signal: options.signal,
    body: JSON.stringify({
      placements: placements.map((placement) => ({
        id: placement.id,
        type: placement.type,
        coordinates: placement.coordinates,
        placedAtSeconds: placementTime(placement.placedAtSeconds, options.durationDays * SECONDS_PER_DAY),
      })),
      durationDays: options.durationDays,
      honourCollectors: options.honourCollectors,
    } satisfies SimulateRequest),
  });
  const run = await parseResponse<SimulateResponse>(response);
  if (run.durationDays !== options.durationDays || run.totalSeconds !== options.durationDays * SECONDS_PER_DAY) {
    throw new Error("The backend returned a different experiment duration. Please retry the simulation.");
  }
  return run;
}
