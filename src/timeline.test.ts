import { afterEach, describe, expect, it, vi } from "vitest";
import {
  audioTimeToTimeline,
  DEFAULT_DURATION_SECONDS,
  formatDurationLabel,
  formatTime,
  placementTime,
  SECONDS_PER_DAY,
  SIMULATION_DURATION_DAYS,
  timelineTimeToAudio,
} from "./timeline";
import { impactEventsBetween, interpolateFrame, trailGeoJson } from "./simulation";
import { requestSimulation } from "./simulationApi";
import type { ParticleTrajectory } from "./types";

afterEach(() => vi.unstubAllGlobals());

describe("one-year timeline", () => {
  it("formats the start, day boundaries, and endpoint", () => {
    expect(formatTime(0)).toBe("0d 00h 00m");
    expect(formatTime(SECONDS_PER_DAY)).toBe("1d 00h 00m");
    expect(formatTime(3.5 * SECONDS_PER_DAY)).toBe("3d 12h 00m");
    expect(formatTime(DEFAULT_DURATION_SECONDS)).toBe("1y 0d 00h 00m");
    expect(formatDurationLabel(DEFAULT_DURATION_SECONDS)).toBe("1 year");
  });

  it("maps narration seeking onto all ten days and clamps overruns", () => {
    expect(audioTimeToTimeline(15, 60, DEFAULT_DURATION_SECONDS)).toBe(7884000);
    expect(timelineTimeToAudio(DEFAULT_DURATION_SECONDS * 0.75, DEFAULT_DURATION_SECONDS, 60)).toBe(45);
    expect(audioTimeToTimeline(65, 60, DEFAULT_DURATION_SECONDS)).toBe(31536000);
    expect(audioTimeToTimeline(0, NaN, DEFAULT_DURATION_SECONDS)).toBe(0);
    expect(placementTime(31536000.6, DEFAULT_DURATION_SECONDS)).toBe(31536000);
    expect(placementTime(-10, DEFAULT_DURATION_SECONDS)).toBe(0);
  });

  it("hides a day-three placement earlier and freezes at a terminal event", () => {
    const trajectory: ParticleTrajectory = { id: "late", type: "bottle", samples: [
      { timeSeconds: 259200, coordinates: [-130, 40], status: "floating" },
      { timeSeconds: 260000, coordinates: [-129.9, 40], status: "beached" },
      { timeSeconds: 864000, coordinates: [-129.9, 40], status: "beached" },
    ] };
    expect(interpolateFrame([trajectory], 259199)).toEqual([]);
    expect(trailGeoJson([trajectory], 259199).features).toEqual([]);
    expect(interpolateFrame([trajectory], 259200)[0].coordinates).toEqual([-130, 40]);
    expect(interpolateFrame([trajectory], 900000)[0].coordinates).toEqual([-129.9, 40]);
    expect(interpolateFrame([trajectory], 260000)[0].status).toBe("beached");
    expect(impactEventsBetween([trajectory], 259999, 260000)).toEqual([{
      id: "late",
      type: "beached",
      timeSeconds: 260000,
      coordinates: [-129.9, 40],
    }]);
    expect(impactEventsBetween([trajectory], 260000, 300000)).toEqual([]);
    expect(impactEventsBetween([trajectory], 300000, 259200)).toEqual([]);
  });

  it("clamps a floating trajectory at its endpoint instead of extrapolating", () => {
    const trajectory: ParticleTrajectory = { id: "floating", type: "foam", samples: [
      { timeSeconds: 259200, coordinates: [179.8, 0], status: "floating" },
      { timeSeconds: 864000, coordinates: [180.2, 0], status: "floating" },
    ] };
    expect(interpolateFrame([trajectory], 900000)[0].coordinates).toEqual([180.2, 0]);
    expect(interpolateFrame([{ ...trajectory, samples: [] }], 0)).toEqual([]);
    const endpoint = { ...trajectory, samples: [trajectory.samples[1]] };
    expect(interpolateFrame([endpoint], 864000)[0].coordinates).toEqual([180.2, 0]);
  });

  it("sends a one-year request with a bounded whole-second placement time", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ durationDays: 365, totalSeconds: 31536000 })));
    vi.stubGlobal("fetch", fetchMock);
    await requestSimulation([{ id: "end", type: "bottle", coordinates: [-130, 40], placedAtSeconds: 31536000.1 }], {
      durationDays: SIMULATION_DURATION_DAYS,
      honourCollectors: true,
    });
    expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toMatchObject({
      durationDays: 365,
      placements: [{ placedAtSeconds: 31536000 }],
    });
  });

  it("rejects a backend response whose duration does not match the request", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({ durationDays: 1, totalSeconds: 86400 }))));
    await expect(requestSimulation([], { durationDays: 365, honourCollectors: true })).rejects.toThrow("different experiment duration");
  });
});
