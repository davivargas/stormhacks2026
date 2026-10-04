// @vitest-environment jsdom
import { act, cleanup, renderHook } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError, simulate } from "../lib/api";
import { requestFixture, responseFixture } from "../testFixtures";
import { useSimulation } from "./useSimulation";
import type { SimulationResponse } from "../types";

vi.mock("../lib/api", async (importOriginal) => ({
  ...await importOriginal<typeof import("../lib/api")>(),
  simulate: vi.fn(),
}));

afterEach(() => {
  cleanup();
  vi.mocked(simulate).mockReset();
});

function deferred() {
  let resolve!: (response: SimulationResponse) => void;
  const promise = new Promise<SimulationResponse>((accept) => { resolve = accept; });
  return { promise, resolve };
}

describe("simulation request lifecycle", () => {
  it("accepts one completed run and ignores duplicate Play requests while loading", async () => {
    const pending = deferred();
    vi.mocked(simulate).mockReturnValue(pending.promise);
    const { result } = renderHook(() => useSimulation());
    let request!: Promise<SimulationResponse | null>;
    act(() => { request = result.current.calculate(requestFixture); });
    await act(async () => { expect(await result.current.calculate(requestFixture)).toBeNull(); });
    expect(simulate).toHaveBeenCalledTimes(1);
    await act(async () => { pending.resolve(responseFixture()); await request; });
    expect(result.current.status).toBe("ready");
    expect(result.current.run?.runId).toBe("run-1");
  });

  it("does not repopulate the map when a response arrives after reset", async () => {
    const pending = deferred();
    vi.mocked(simulate).mockReturnValue(pending.promise);
    const { result } = renderHook(() => useSimulation());
    let request!: Promise<SimulationResponse | null>;
    act(() => { request = result.current.calculate(requestFixture); });
    const signal = vi.mocked(simulate).mock.calls[0][1];
    act(() => result.current.invalidate(true));
    expect(signal?.aborted).toBe(true);
    await act(async () => { pending.resolve(responseFixture()); expect(await request).toBeNull(); });
    expect(result.current.run).toBeNull();
    expect(result.current.status).toBe("idle");
  });

  it("an edit invalidates an older response even after a newer response completes", async () => {
    const old = deferred();
    const next = { ...responseFixture(), runId: "new-run" };
    vi.mocked(simulate).mockReturnValueOnce(old.promise).mockResolvedValueOnce(next);
    const { result } = renderHook(() => useSimulation());
    let oldRequest!: Promise<SimulationResponse | null>;
    act(() => { oldRequest = result.current.calculate(requestFixture); });
    act(() => result.current.invalidate());
    await act(async () => { await result.current.calculate(requestFixture); });
    await act(async () => { old.resolve(responseFixture()); await oldRequest; });
    expect(result.current.run?.runId).toBe("new-run");
  });

  it("keeps placements retryable after a failed calculation", async () => {
    vi.mocked(simulate).mockRejectedValueOnce(new ApiError("Try the water", "on_land", "b"))
      .mockResolvedValueOnce(responseFixture());
    const { result } = renderHook(() => useSimulation());
    await act(async () => { await result.current.calculate(requestFixture); });
    expect(result.current.status).toBe("error");
    expect(result.current.error?.placementId).toBe("b");
    await act(async () => { await result.current.calculate(requestFixture); });
    expect(result.current.status).toBe("ready");
    expect(result.current.error).toBeNull();
  });
});
