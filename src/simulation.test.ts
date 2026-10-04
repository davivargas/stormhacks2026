import { describe, expect, it } from "vitest";
import { draftFrames, interpolateFrame, particleGeoJson, trailGeoJson } from "./simulation";
import { requestFixture, responseFixture } from "./testFixtures";

describe("backend trajectory playback", () => {
  it("hides an item and its trail before placement", () => {
    const { trajectories } = responseFixture();
    expect(interpolateFrame(trajectories, 21599)).toEqual([]);
    expect(trailGeoJson(trajectories, 21599).features).toEqual([]);
  });

  it("starts exactly at the placement coordinate", () => {
    expect(interpolateFrame(responseFixture().trajectories, 21600)[0]).toMatchObject({
      coordinates: [-130, 40], status: "floating",
    });
  });

  it("interpolates only before the exact terminal timestamp, then freezes", () => {
    const { trajectories } = responseFixture();
    expect(interpolateFrame(trajectories, 21900)[0].coordinates[0]).toBeCloseTo(-129.995);
    expect(interpolateFrame(trajectories, 22199)[0].status).toBe("floating");
    expect(interpolateFrame(trajectories, 22200)[0].status).toBe("captured");
    expect(interpolateFrame(trajectories, 90000)[0].coordinates).toEqual([-129.99, 40]);
  });

  it("handles placement at the endpoint and empty samples", () => {
    const sample = { timeSeconds: 86400, coordinates: [-130, 40] as [number, number], status: "floating" as const };
    expect(interpolateFrame([{ id: "end", type: "foam", samples: [sample] }], 86400)[0].coordinates).toEqual(sample.coordinates);
    expect(interpolateFrame([{ id: "empty", type: "foam", samples: [] }], 0)).toEqual([]);
  });

  it("shows a draft at its original position without inventing a trail", () => {
    expect(draftFrames(requestFixture.placements, [], 21600)[0].coordinates).toEqual([-130, 40]);
    expect(draftFrames(requestFixture.placements, [], 0)).toEqual([]);
    expect(trailGeoJson([], 21600).features).toEqual([]);
  });

  it("preserves continuous longitude across the antimeridian", () => {
    const trajectories = [{ id: "crossing", type: "bag" as const, samples: [
      { timeSeconds: 0, coordinates: [179.8, 0] as [number, number], status: "floating" as const },
      { timeSeconds: 3600, coordinates: [180.2, 0] as [number, number], status: "floating" as const },
    ] }];
    expect(interpolateFrame(trajectories, 1800)[0].coordinates[0]).toBeCloseTo(180);
    expect(trailGeoJson(trajectories, 3600).features[0].geometry.coordinates[1][0]).toBe(180.2);
  });

  it("hides outside markers but retains travelled trails", () => {
    const trajectories = responseFixture().trajectories;
    trajectories[0].samples[1].status = "outside";
    trajectories[0].samples[2].status = "outside";
    expect(particleGeoJson(interpolateFrame(trajectories, 22200)).features).toHaveLength(0);
    expect(trailGeoJson(trajectories, 22200).features).toHaveLength(1);
  });
});
