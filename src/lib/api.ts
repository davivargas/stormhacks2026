import type { ApiMeta, SimulationRequest, SimulationResponse } from "../types";

const baseUrl = (import.meta.env.VITE_API_BASE_URL || "http://localhost:8001").replace(/\/+$/, "");
const statuses = new Set(["floating", "captured", "beached", "outside"]);
const litterTypes = new Set(["bottle", "bag", "foam"]);

export class ApiError extends Error {
  constructor(
    message: string,
    readonly code: string,
    readonly placementId?: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

function record(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function coordinates(value: unknown) {
  // Backend trajectories keep longitude continuous at the antimeridian.
  return Array.isArray(value) && value.length === 2
    && value.every((part) => typeof part === "number" && Number.isFinite(part))
    && Math.abs(value[1]) <= 90;
}

function validAttribution(value: unknown) {
  return record(value) && typeof value.source === "string" && typeof value.dataset === "string"
    && Array.isArray(value.limitations) && value.limitations.every((item) => typeof item === "string");
}

function validSummary(value: unknown) {
  return record(value) && [...statuses].every((key) => Number.isInteger(value[key]) && Number(value[key]) >= 0);
}

export function parseSimulationResponse(value: unknown): SimulationResponse {
  const fail = () => { throw new ApiError("The backend returned an invalid simulation response.", "invalid_response"); };
  if (!record(value) || typeof value.runId !== "string" || !value.runId
    || !Number.isInteger(value.durationDays) || Number(value.durationDays) < 1
    || !Number.isInteger(value.totalSeconds) || Number(value.totalSeconds) <= 0
    || !Number.isInteger(value.sampleIntervalSeconds) || Number(value.sampleIntervalSeconds) <= 0
    || !Array.isArray(value.trajectories) || !value.trajectories.length
    || !Array.isArray(value.items) || !Array.isArray(value.collectors)
    || !Array.isArray(value.snapshots) || !value.snapshots.length
    || !validSummary(value.summary) || !validAttribution(value.attribution)
    || typeof value.persisted !== "boolean") return fail();

  const total = Number(value.totalSeconds);
  const ids = new Set<string>();
  for (const trajectory of value.trajectories) {
    if (!record(trajectory) || typeof trajectory.id !== "string" || ids.has(trajectory.id)
      || !litterTypes.has(String(trajectory.type)) || !Array.isArray(trajectory.samples)
      || !trajectory.samples.length) return fail();
    ids.add(trajectory.id);
    let previousTime = -1;
    for (const sample of trajectory.samples) {
      if (!record(sample) || !Number.isInteger(sample.timeSeconds)
        || Number(sample.timeSeconds) <= previousTime || Number(sample.timeSeconds) > total
        || !coordinates(sample.coordinates) || !statuses.has(String(sample.status))) return fail();
      previousTime = Number(sample.timeSeconds);
    }
    if (previousTime !== total) return fail();
  }
  if (value.items.length !== ids.size) return fail();
  const itemIds = new Set<string>();
  for (const item of value.items) {
    if (!record(item) || typeof item.id !== "string" || !ids.has(item.id) || itemIds.has(item.id)
      || !litterTypes.has(String(item.type)) || !statuses.has(String(item.finalStatus))
      || !(item.capturedBy === null || typeof item.capturedBy === "string")
      || !(item.statusChangedAtSeconds === null || (Number.isInteger(item.statusChangedAtSeconds)
        && Number(item.statusChangedAtSeconds) >= 0 && Number(item.statusChangedAtSeconds) <= total))) return fail();
    itemIds.add(item.id);
  }
  for (const collector of value.collectors) {
    if (!record(collector) || typeof collector.id !== "string" || !coordinates(collector.coordinates)
      || typeof collector.radiusM !== "number" || !Number.isFinite(collector.radiusM) || collector.radiusM <= 0
      || !Number.isInteger(collector.capturedCount) || Number(collector.capturedCount) < 0) return fail();
  }
  for (const snapshot of value.snapshots) {
    if (!record(snapshot) || typeof snapshot.snapshotId !== "string"
      || !["copernicus", "synthetic"].includes(String(snapshot.source))
      || typeof snapshot.sliceTime !== "string" || !Number.isFinite(Date.parse(snapshot.sliceTime))
      || !Number.isInteger(snapshot.nSlices) || Number(snapshot.nSlices) < 1) return fail();
  }
  return value as unknown as SimulationResponse;
}

async function request(path: string, options: RequestInit, timeoutMs: number): Promise<unknown> {
  const controller = new AbortController();
  const abort = () => controller.abort();
  const external = options.signal;
  if (external?.aborted) controller.abort();
  external?.addEventListener("abort", abort, { once: true });
  let timedOut = false;
  const timer = setTimeout(() => {
    timedOut = true;
    controller.abort();
  }, timeoutMs);

  try {
    const response = await fetch(`${baseUrl}${path}`, { ...options, signal: controller.signal });
    let data: unknown;
    try {
      data = await response.json();
    } catch (error) {
      if (controller.signal.aborted) throw error;
      throw new ApiError("The backend returned an unreadable response.", "invalid_response");
    }
    if (!response.ok) {
      throw new ApiError(
        record(data) && typeof data.message === "string" ? data.message : `Request failed (${response.status}).`,
        record(data) && typeof data.code === "string" ? data.code : "request_failed",
        record(data) && typeof data.placementId === "string" ? data.placementId : undefined,
      );
    }
    return data;
  } catch (error) {
    if (external?.aborted) throw new DOMException("Request cancelled", "AbortError");
    if (timedOut) throw new ApiError("Ocean data is taking too long. Please try again.", "timeout");
    if (error instanceof ApiError) throw error;
    throw new ApiError("Cannot reach the backend. Check that the API is running, then retry.", "network_error");
  } finally {
    clearTimeout(timer);
    external?.removeEventListener("abort", abort);
  }
}

export async function fetchMeta(signal?: AbortSignal): Promise<ApiMeta> {
  const data = await request("/api/meta", { signal }, 15_000);
  if (!record(data) || !record(data.durationDays) || !record(data.defaults)
    || !validAttribution(data.attribution) || !Array.isArray(data.litterTypes)
    || !data.litterTypes.length || !data.litterTypes.every((item) => litterTypes.has(String(item)))
    || !["min", "max", "default"].every((key) => Number.isInteger((data.durationDays as Record<string, unknown>)[key])
      && Number((data.durationDays as Record<string, unknown>)[key]) > 0)
    || !["collectorRadiusM", "sampleIntervalSeconds", "integrationStepSeconds", "maxLitterPlacements", "maxCollectors", "maxDistinctAreas"]
      .every((key) => typeof (data.defaults as Record<string, unknown>)[key] === "number"
        && Number.isFinite((data.defaults as Record<string, unknown>)[key])
        && Number((data.defaults as Record<string, unknown>)[key]) > 0)) {
    throw new ApiError("The backend returned invalid experiment settings.", "invalid_response");
  }
  return data as unknown as ApiMeta;
}

export async function simulate(body: SimulationRequest, signal?: AbortSignal): Promise<SimulationResponse> {
  const response = parseSimulationResponse(await request("/api/simulate", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    signal,
  }, 120_000));
  const litter = body.placements.filter((item) => item.type !== "collector");
  if (response.totalSeconds !== body.durationDays * 86400 || response.durationDays !== body.durationDays
    || response.trajectories.length !== litter.length
    || litter.some((placement) => {
      const trajectory = response.trajectories.find((item) => item.id === placement.id);
      return !trajectory || trajectory.type !== placement.type
        || trajectory.samples[0].timeSeconds !== placement.placedAtSeconds;
    })) {
    throw new ApiError("The backend response does not match this experiment. Please restart the updated API.", "invalid_response");
  }
  return response;
}
