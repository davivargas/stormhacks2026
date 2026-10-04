import { afterEach, describe, expect, it, vi } from "vitest";
import { deleteSessionRuns, requestSimulation, SESSION_ID } from "./simulationApi";

function stubFetch(status: number, body: unknown) {
  // The parameters are unused but type fetchMock.mock.calls.
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  const fetchMock = vi.fn(async (_url: string, _init?: RequestInit) => new Response(JSON.stringify(body), { status }));
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

afterEach(() => vi.unstubAllGlobals());

describe("session runs", () => {
  it("has a session id the backend accepts even without sessionStorage", () => {
    expect(SESSION_ID).toMatch(/^[A-Za-z0-9_-]{1,64}$/);
  });

  it("tags every simulation with this tab's session id", async () => {
    const fetchMock = stubFetch(200, { durationDays: 10, totalSeconds: 864000 });
    await requestSimulation(
      [{ id: "bottle-1", type: "bottle", coordinates: [-130, 40], placedAtSeconds: 0 }],
      { durationDays: 10, honourCollectors: true },
    );
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toMatch(/\/api\/simulate$/);
    expect(JSON.parse(String(init?.body)).sessionId).toBe(SESSION_ID);
  });

  it("deletes the runs saved under the same session id", async () => {
    const fetchMock = stubFetch(200, { deleted: 2, database: "cleared" });
    await expect(deleteSessionRuns()).resolves.toEqual({ deleted: 2, database: "cleared" });
    const [url, init] = fetchMock.mock.calls[0];
    expect(url.endsWith(`/api/sessions/${SESSION_ID}/runs`)).toBe(true);
    expect(init?.method).toBe("DELETE");
  });

  it("rejects when the backend refuses the delete", async () => {
    stubFetch(500, { message: "boom" });
    await expect(deleteSessionRuns()).rejects.toThrow("boom");
  });
});
