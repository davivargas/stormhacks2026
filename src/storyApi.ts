export type StoryFinalStatus =
  | "floating"
  | "beached"
  | "captured"
  | "outside_domain"
  | "missing_data";

export interface StorySimulationEvent {
  elapsed_hours: number;
  type: string;
  location?: string;
}

export interface StorySimulationSummary {
  simulation_id: string;
  litter_type: string;
  particle_id: string;
  duration_hours: number;
  events: StorySimulationEvent[];
  final_status: StoryFinalStatus;
  assumptions: string[];
}

export interface StorySource {
  document_id: string;
  title: string;
  url: string;
}

export interface OceanStory {
  story_id: string;
  simulation_id: string;
  particle_id: string;
  title: string;
  script: string;
  sources: StorySource[];
  generation_mode: "live" | "fallback";
  retrieval_mode: "tidb" | "local";
}

export interface StoryAudio {
  story_id: string;
  audio_url: string;
  content_type: string;
  script: string;
  voice_id: string;
  model_id: string;
  cached: boolean;
}

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

async function parseResponse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const body = (await response.json().catch(() => null)) as { detail?: string } | null;
    throw new Error(body?.detail ?? `LitterVoyage API request failed (${response.status})`);
  }
  return response.json() as Promise<T>;
}

export async function requestOceanStory(
  summary: StorySimulationSummary,
): Promise<OceanStory> {
  const response = await fetch(`${API_BASE_URL}/api/stories`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(summary),
  });
  return parseResponse<OceanStory>(response);
}

export async function requestStoryForRun(
  runId: string,
  particleId: string,
): Promise<OceanStory> {
  const response = await fetch(`${API_BASE_URL}/api/runs/${encodeURIComponent(runId)}/stories`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ particle_id: particleId }),
  });
  return parseResponse<OceanStory>(response);
}

export async function requestStoryAudio(storyId: string): Promise<StoryAudio> {
  const response = await fetch(`${API_BASE_URL}/api/stories/${encodeURIComponent(storyId)}/audio`, {
    method: "POST",
  });
  const audio = await parseResponse<StoryAudio>(response);
  return {
    ...audio,
    audio_url: new URL(audio.audio_url, `${API_BASE_URL}/`).toString(),
  };
}
