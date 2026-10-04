export type LitterType = "bottle" | "bag" | "foam";
export type PlacementType = LitterType | "collector";
export type Tool = "explore" | PlacementType | "remove";
export type ParticleStatus = "floating" | "captured" | "beached" | "outside";
export type ComparisonMode = "without" | "with";

export type Coordinates = [longitude: number, latitude: number];

export interface Placement {
  id: string;
  type: PlacementType;
  coordinates: Coordinates;
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
