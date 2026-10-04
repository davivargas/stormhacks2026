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
  sessionId?: string;
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

export interface DeleteRunsResponse {
  deleted: number;
  database: "cleared" | "unavailable" | "failed";
}

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";
const SESSION_STORAGE_KEY = "littervoyage-session-id";

// One id per browser tab. sessionStorage keeps it across reloads, so runs saved before a
// reload can still be deleted; without storage the id lasts until the page is closed.
function loadSessionId(): string {
  try {
    const stored = sessionStorage.getItem(SESSION_STORAGE_KEY);
    if (stored && /^[A-Za-z0-9_-]{1,64}$/.test(stored)) return stored;
    const created = crypto.randomUUID();
    sessionStorage.setItem(SESSION_STORAGE_KEY, created);
    return created;
  } catch {
    return crypto.randomUUID();
  }
}

export const SESSION_ID = loadSessionId();

async function parseResponse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const body = (await response.json().catch(() => null)) as {
      detail?: string;
      message?: string;
    } | null;
    throw new Error(body?.message ?? body?.detail ?? `LitterVoyage API request failed (${response.status})`);
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
      sessionId: SESSION_ID,
    } satisfies SimulateRequest),
  });
  const run = await parseResponse<SimulateResponse>(response);
  if (run.durationDays !== options.durationDays || run.totalSeconds !== options.durationDays * SECONDS_PER_DAY) {
    throw new Error("The backend returned a different experiment duration. Please retry the simulation.");
  }
  return run;
}

export async function deleteSessionRuns(): Promise<DeleteRunsResponse> {
  const response = await fetch(`${API_BASE_URL}/api/sessions/${SESSION_ID}/runs`, { method: "DELETE" });
  return parseResponse<DeleteRunsResponse>(response);
}
