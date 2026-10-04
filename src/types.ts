export type LitterType = "bottle" | "bag" | "foam";
export type PlacementType = LitterType | "collector";
export type Tool = "explore" | PlacementType | "remove";
export type ParticleStatus = "floating" | "captured" | "beached" | "outside";

export type Coordinates = [longitude: number, latitude: number];

export interface Placement {
  id: string;
  type: PlacementType;
  coordinates: Coordinates;
  placedAtSeconds: number;
}

export interface TrajectorySample {
  timeSeconds: number;
  coordinates: Coordinates;
  status: ParticleStatus;
}

export interface ParticleTrajectory {
  id: string;
  type: LitterType;
  samples: TrajectorySample[];
}

export interface ParticleFrame {
  id: string;
  type: LitterType;
  coordinates: Coordinates;
  status: ParticleStatus;
}

export interface Summary {
  floating: number;
  captured: number;
  beached: number;
  outside: number;
}

export interface Attribution {
  source: string;
  dataset: string;
  limitations: string[];
}

export interface SimulationRequest {
  placements: Placement[];
  durationDays: number;
  collectorRadiusM: number;
  honourCollectors: boolean;
}

export interface SimulationResponse {
  runId: string;
  durationDays: number;
  totalSeconds: number;
  sampleIntervalSeconds: number;
  trajectories: ParticleTrajectory[];
  items: Array<{
    id: string;
    type: LitterType;
    finalStatus: ParticleStatus;
    capturedBy: string | null;
    statusChangedAtSeconds: number | null;
  }>;
  collectors: Array<{
    id: string;
    coordinates: Coordinates;
    radiusM: number;
    capturedCount: number;
  }>;
  summary: Summary;
  snapshots: Array<{
    snapshotId: string;
    source: "copernicus" | "synthetic";
    sliceTime: string;
    nSlices: number;
  }>;
  attribution: Attribution;
  persisted: boolean;
}

export interface ApiMeta {
  durationDays: { min: number; max: number; default: number };
  defaults: {
    collectorRadiusM: number;
    sampleIntervalSeconds: number;
    integrationStepSeconds: number;
    maxLitterPlacements: number;
    maxCollectors: number;
    maxDistinctAreas: number;
  };
  litterTypes: LitterType[];
  attribution: Attribution;
}
