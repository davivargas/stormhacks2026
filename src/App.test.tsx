// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import App from "./App";
import { fetchMeta, simulate } from "./lib/api";
import { responseFixture } from "./testFixtures";
import type { Coordinates } from "./types";

vi.mock("./OceanMap", () => ({
  OceanMap: ({ onPlace }: { onPlace: (coordinates: Coordinates) => void }) => (
    <button onClick={() => onPlace([-130, 40])}>Place at test ocean point</button>
  ),
}));
vi.mock("./lib/api", async (importOriginal) => ({
  ...await importOriginal<typeof import("./lib/api")>(),
  fetchMeta: vi.fn(),
  simulate: vi.fn(),
}));

beforeEach(() => {
  // jsdom does not implement the browser's native modal-dialog methods.
  Object.defineProperties(HTMLDialogElement.prototype, {
    showModal: { configurable: true, value: function (this: HTMLDialogElement) { this.setAttribute("open", ""); } },
    close: { configurable: true, value: function (this: HTMLDialogElement) { this.removeAttribute("open"); } },
  });
  vi.mocked(fetchMeta).mockResolvedValue({
    durationDays: { min: 1, max: 30, default: 7 },
    defaults: {
      collectorRadiusM: 10000, sampleIntervalSeconds: 3600, integrationStepSeconds: 600,
      maxLitterPlacements: 50, maxCollectors: 20, maxDistinctAreas: 8,
    },
    litterTypes: ["bottle", "bag", "foam"],
    attribution: { source: "Copernicus", dataset: "ocean", limitations: [] },
  });
  vi.mocked(simulate).mockImplementation(async (body) => {
    const response = responseFixture();
    response.trajectories = body.placements.filter((item) => item.type !== "collector").map((item) => ({
      id: item.id, type: item.type as "bottle" | "bag" | "foam", samples: [
        { timeSeconds: item.placedAtSeconds, coordinates: item.coordinates, status: "floating" },
        { timeSeconds: 86400, coordinates: [-129.9, 40], status: "floating" },
      ],
    }));
    response.summary = { floating: response.trajectories.length, captured: 0, beached: 0, outside: 0 };
    return response;
  });
});

afterEach(() => {
  cleanup();
  vi.mocked(fetchMeta).mockReset();
  vi.mocked(simulate).mockReset();
});

describe("Play connects to backend", () => {
  it("requests one run and reuses it when pausing and resuming", async () => {
    render(<App />);
    fireEvent.click(screen.getByRole("button", { name: /Bottle/ }));
    fireEvent.click(screen.getByRole("button", { name: "Place at test ocean point" }));
    const play = screen.getByRole("button", { name: "Calculate or play simulation" });
    await waitFor(() => expect((play as HTMLButtonElement).disabled).toBe(false));
    fireEvent.click(play);
    await screen.findByRole("button", { name: "Pause simulation" });
    expect(simulate).toHaveBeenCalledTimes(1);
    expect(vi.mocked(simulate).mock.calls[0][0]).toMatchObject({
      durationDays: 1, collectorRadiusM: 10000, honourCollectors: true,
    });
    fireEvent.click(screen.getByRole("button", { name: "Pause simulation" }));
    fireEvent.click(screen.getByRole("button", { name: "Calculate or play simulation" }));
    await screen.findByRole("button", { name: "Pause simulation" });
    expect(simulate).toHaveBeenCalledTimes(1);
  });

  it("sends current timeline placement timestamps and calculates again after editing", async () => {
    render(<App />);
    fireEvent.click(screen.getByRole("button", { name: /Bottle/ }));
    fireEvent.click(screen.getByRole("button", { name: "Place at test ocean point" }));
    await waitFor(() => expect((screen.getByRole("button", { name: "Calculate or play simulation" }) as HTMLButtonElement).disabled).toBe(false));
    fireEvent.click(screen.getByRole("button", { name: "Calculate or play simulation" }));
    await screen.findByRole("button", { name: "Pause simulation" });
    fireEvent.change(screen.getByRole("slider"), { target: { value: "21600" } });
    fireEvent.click(screen.getByRole("button", { name: "Place at test ocean point" }));
    expect(simulate).toHaveBeenCalledTimes(1);
    fireEvent.click(screen.getByRole("button", { name: "Calculate or play simulation" }));
    await waitFor(() => expect(simulate).toHaveBeenCalledTimes(2));
    expect(vi.mocked(simulate).mock.calls[1][0].placements[1].placedAtSeconds).toBe(21600);
    fireEvent.click(screen.getByRole("button", { name: "Restart experiment" }));
    expect((screen.getByRole("slider") as HTMLInputElement).value).toBe("0");
    expect((screen.getByRole("button", { name: "Calculate or play simulation" }) as HTMLButtonElement).disabled).toBe(true);
  });
});
