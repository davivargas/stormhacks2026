import type { FeatureCollection, LineString, Point } from "geojson";
import type {
  ParticleFrame,
  ParticleTrajectory,
  Placement,
} from "./types";

export const DURATION_SECONDS = 24 * 60 * 60;

export const INITIAL_PLACEMENTS: Placement[] = [];

export function interpolateFrame(
  trajectories: ParticleTrajectory[],
  timeSeconds: number,
): ParticleFrame[] {
  return trajectories.flatMap((trajectory) => {
    if (!trajectory.samples.length) return [];
    if (timeSeconds < trajectory.samples[0].timeSeconds) return [];

    const nextIndex = trajectory.samples.findIndex((sample) => sample.timeSeconds >= timeSeconds);
    const upperIndex = nextIndex === -1 ? trajectory.samples.length - 1 : nextIndex;
    const lowerIndex = Math.max(0, upperIndex - 1);
    const lower = trajectory.samples[lowerIndex];
    const upper = trajectory.samples[upperIndex];
    const duration = upper.timeSeconds - lower.timeSeconds;
    const progress = duration === 0 ? 0 : Math.min(1, Math.max(0, (timeSeconds - lower.timeSeconds) / duration));
    const status = timeSeconds >= upper.timeSeconds ? upper.status : lower.status;

    return {
      id: trajectory.id,
      type: trajectory.type,
      coordinates: [
        lower.coordinates[0] + (lower.status === "floating" ? (upper.coordinates[0] - lower.coordinates[0]) * progress : 0),
        lower.coordinates[1] + (lower.status === "floating" ? (upper.coordinates[1] - lower.coordinates[1]) * progress : 0),
      ],
      status,
    };
  });
}

export function draftFrames(placements: Placement[], trajectories: ParticleTrajectory[], timeSeconds: number): ParticleFrame[] {
  const predicted = interpolateFrame(trajectories, timeSeconds);
  const predictedIds = new Set(predicted.map((item) => item.id));
  const drafts: ParticleFrame[] = placements.flatMap((item) => {
    if (item.type === "collector" || item.placedAtSeconds > timeSeconds || predictedIds.has(item.id)) return [];
    return { id: item.id, type: item.type, coordinates: item.coordinates, status: "floating" as const };
  });
  return [...predicted, ...drafts];
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
