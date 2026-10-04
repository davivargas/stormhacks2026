import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError, parseSimulationResponse, simulate } from "./api";
import { requestFixture, responseFixture } from "../testFixtures";

afterEach(() => vi.unstubAllGlobals());

describe("simulation API contract", () => {
  it("accepts a complete response and rejects invalid coordinates or unsorted samples", () => {
    expect(parseSimulationResponse(responseFixture()).runId).toBe("run-1");
    const invalid = responseFixture();
    invalid.trajectories[0].samples[0].coordinates[0] = NaN;
    expect(() => parseSimulationResponse(invalid)).toThrow(ApiError);
    invalid.trajectories[0].samples[0].coordinates[0] = -130;
    invalid.trajectories[0].samples.reverse();
    expect(() => parseSimulationResponse(invalid)).toThrow(ApiError);
  });

  it("sends placement timestamps and collector settings", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify(responseFixture()), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    await simulate(requestFixture);
    const [url, options] = fetchMock.mock.calls[0];
    expect(url).toMatch(/\/api\/simulate$/);
    expect(JSON.parse(options.body)).toEqual(requestFixture);
  });

  it("rejects a response from an old backend that ignores placement time", async () => {
    const response = responseFixture();
    response.trajectories[0].samples[0].timeSeconds = 0;
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify(response))));
    await expect(simulate(requestFixture)).rejects.toMatchObject({ code: "invalid_response" });
  });

  it("preserves structured land errors and the offending item ID", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({
      code: "on_land", message: "That spot is land.", placementId: "b",
    }), { status: 422 })));
    await expect(simulate(requestFixture)).rejects.toMatchObject({ code: "on_land", placementId: "b" });
  });

  it("reports network failure rather than generating mock movement", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("connection refused")));
    await expect(simulate(requestFixture)).rejects.toMatchObject({ code: "network_error" });
  });
});
