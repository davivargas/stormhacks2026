import type { Feature, FeatureCollection, LineString, Point, Polygon } from "geojson";
import type {
  ComparisonMode,
  Coordinates,
  ParticleFrame,
  ParticleStatus,
  ParticleTrajectory,
  Placement,
} from "./types";

export const DURATION_SECONDS = 24 * 60 * 60;

export const REGION_BOUNDS: [Coordinates, Coordinates] = [
  [-123.78, 49.05],
  [-122.92, 49.65],
];

export const PLAYABLE_WATER: Feature<Polygon> = {
  type: "Feature",
  properties: {},
  geometry: {
    type: "Polygon",
    coordinates: [[
      [-123.74, 49.56],
      [-123.56, 49.62],
      [-123.16, 49.53],
      [-123.02, 49.36],
      [-123.12, 49.12],
      [-123.42, 49.08],
      [-123.62, 49.2],
      [-123.74, 49.56],
    ]],
  },
};

export const INITIAL_PLACEMENTS: Placement[] = [];

const movement: Record<string, { east: number; north: number; curve: number }> = {
  bottle: { east: 0.029, north: -0.005, curve: 0.012 },
  bag: { east: -0.014, north: -0.009, curve: -0.008 },
  foam: { east: 0.019, north: -0.006, curve: 0.01 },
};

export function buildTrajectories(
  placements: Placement[],
  mode: ComparisonMode,
): ParticleTrajectory[] {
  const collectors = placements.filter((item) => item.type === "collector");

  return placements
    .filter((item): item is Placement & { type: "bottle" | "bag" | "foam" } => item.type !== "collector")
    .map((item) => {
      const vector = movement[item.type];
      const sampleInterval = 2 * 60 * 60;
      const sampleCount = Math.floor((DURATION_SECONDS - item.placedAtSeconds) / sampleInterval) + 1;
      const samples = Array.from({ length: sampleCount }, (_, index) => {
        const sampleTime = item.placedAtSeconds + index * sampleInterval;
        const hasActiveCollector = collectors.some((collector) => collector.placedAtSeconds <= sampleTime);
        let status: ParticleStatus = "floating";

        if (mode === "with" && hasActiveCollector && item.type === "bottle" && index >= 6) {
          status = "captured";
        } else if (item.type === "bag" && index >= 10) {
          status = "beached";
        } else if (item.type === "foam" && index >= 12) {
          status = "outside";
        }

        const terminalIndex = status === "captured" ? 6 : status === "beached" ? 10 : index;
        const terminalWave = Math.sin(terminalIndex * 0.75) * vector.curve;

        return {
          timeSeconds: sampleTime,
          coordinates: [
            item.coordinates[0] + vector.east * terminalIndex,
            item.coordinates[1] + vector.north * terminalIndex + terminalWave,
          ] as Coordinates,
          status,
        };
      });

      return { id: item.id, type: item.type, samples };
    });
}

export function interpolateFrame(
  trajectories: ParticleTrajectory[],
  timeSeconds: number,
): ParticleFrame[] {
  return trajectories.flatMap((trajectory) => {
    if (timeSeconds < trajectory.samples[0].timeSeconds) return [];

    const nextIndex = trajectory.samples.findIndex((sample) => sample.timeSeconds >= timeSeconds);
    const upperIndex = nextIndex === -1 ? trajectory.samples.length - 1 : nextIndex;
    const lowerIndex = Math.max(0, upperIndex - 1);
    const lower = trajectory.samples[lowerIndex];
    const upper = trajectory.samples[upperIndex];
    const duration = upper.timeSeconds - lower.timeSeconds;
    const progress = duration === 0 ? 0 : (timeSeconds - lower.timeSeconds) / duration;
    const status = timeSeconds >= upper.timeSeconds ? upper.status : lower.status;

    return {
      id: trajectory.id,
      type: trajectory.type,
      coordinates: [
        lower.coordinates[0] + (upper.coordinates[0] - lower.coordinates[0]) * progress,
        lower.coordinates[1] + (upper.coordinates[1] - lower.coordinates[1]) * progress,
      ],
      status,
    };
  });
}

export function particleGeoJson(frames: ParticleFrame[]): FeatureCollection<Point> {
  return {
    type: "FeatureCollection",
    features: frames
      .filter((frame) => frame.status !== "outside")
      .map((frame) => ({
        type: "Feature",
        properties: { id: frame.id, type: frame.type, status: frame.status },
        geometry: { type: "Point", coordinates: frame.coordinates },
      })),
  };
}

export function trailGeoJson(
  trajectories: ParticleTrajectory[],
  timeSeconds: number,
): FeatureCollection<LineString> {
  const frames = interpolateFrame(trajectories, timeSeconds);
  return {
    type: "FeatureCollection",
    features: trajectories.flatMap((trajectory) => {
      const frame = frames.find((item) => item.id === trajectory.id);
      if (!frame) return [];

      const completed = trajectory.samples
        .filter((sample) => sample.timeSeconds < timeSeconds)
        .map((sample) => sample.coordinates);
      completed.push(frame.coordinates);
      return {
        type: "Feature",
        properties: { id: trajectory.id, type: trajectory.type },
        geometry: {
          type: "LineString",
          coordinates: completed.length > 1 ? completed : [completed[0], completed[0]],
        },
      };
    }),
  };
}
