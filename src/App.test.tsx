// @vitest-environment jsdom
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import App from "./App";
import { requestSimulation, SimulationApiError } from "./simulationApi";
import { requestStoryAudio, requestStoryForRun } from "./storyApi";
import type { Coordinates } from "./types";

vi.mock("./OceanMap", () => ({
  OceanMap: ({ onPlace, frames }: { onPlace: (coordinates: Coordinates) => void; frames: unknown[] }) => <>
    <button onClick={() => onPlace([-130, 40])}>Drop at test ocean point</button>
    <output data-testid="frames">{JSON.stringify(frames)}</output>
  </>,
}));
vi.mock("./simulationApi", async (importOriginal) => {
  const actual = await importOriginal<typeof import("./simulationApi")>();
  return { ...actual, requestSimulation: vi.fn() };
});
vi.mock("./storyApi", () => ({ requestStoryForRun: vi.fn(), requestStoryAudio: vi.fn() }));

class FakeAudio {
  static instances: FakeAudio[] = [];
  currentTime = 0;
  duration = 60;
  ended = false;
  preload = "";
  onplay: (() => void) | null = null;
  onpause: (() => void) | null = null;
  onended: (() => void) | null = null;
  onerror: (() => void) | null = null;
  ontimeupdate: (() => void) | null = null;
  constructor() { FakeAudio.instances.push(this); }
  play() { this.onplay?.(); return Promise.resolve(); }
  pause() { this.onpause?.(); }
}

beforeEach(() => {
  FakeAudio.instances = [];
  vi.stubGlobal("Audio", FakeAudio);
  vi.mocked(requestSimulation).mockImplementation(async (placements, options) => ({
    runId: `run-${placements.length}`,
    durationDays: options.durationDays,
    totalSeconds: options.durationDays * 86400,
    sampleIntervalSeconds: 3600,
    trajectories: placements.filter((p) => p.type !== "collector").map((p) => ({
      id: p.id, type: p.type as "bottle" | "bag" | "foam", samples: [
        { timeSeconds: p.placedAtSeconds, coordinates: p.coordinates, status: "floating" },
        { timeSeconds: 864000, coordinates: [-129.9, 40], status: "floating" },
      ],
    })),
    items: [], collectors: [], summary: { floating: placements.length, captured: 0, beached: 0, outside: 0 },
    snapshots: [{ snapshotId: "snapshot", source: "synthetic", sliceTime: "2026-10-04T12:00:00Z", nSlices: 1 }],
    attribution: { source: "Synthetic demo", dataset: "synthetic", limitations: ["Single frozen time slice"] },
    persisted: false,
  }));
  vi.mocked(requestStoryForRun).mockResolvedValue({
    story_id: "story", simulation_id: "run-1", particle_id: "bottle", title: "Ocean voyage",
    script: "A ten-day journey.", sources: [], generation_mode: "fallback", retrieval_mode: "local",
  });
  vi.mocked(requestStoryAudio).mockResolvedValue({
    story_id: "story", audio_url: "http://localhost/test.mp3", content_type: "audio/mpeg",
    script: "A ten-day journey.", voice_id: "voice", model_id: "model", cached: true,
  });
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.mocked(requestSimulation).mockReset();
  vi.mocked(requestStoryForRun).mockReset();
  vi.mocked(requestStoryAudio).mockReset();
});

describe("ten-day timeline UI", () => {
  it("requests ten days, places on day three, and restarts at zero", async () => {
    render(<App />);
    const slider = screen.getByRole("slider") as HTMLInputElement;
    expect(slider.max).toBe("864000");
    expect(slider.step).toBe("300");
    expect(slider.getAttribute("aria-valuetext")).toBe("0d 00h 00m");
    fireEvent.click(screen.getByRole("button", { name: /Bottle/ }));
    fireEvent.change(slider, { target: { value: "259200" } });
    fireEvent.click(screen.getByRole("button", { name: "Drop at test ocean point" }));
    await waitFor(() => expect(requestSimulation).toHaveBeenCalledTimes(1));
    expect(vi.mocked(requestSimulation).mock.calls[0][0][0].placedAtSeconds).toBe(259200);
    expect(vi.mocked(requestSimulation).mock.calls[0][1].durationDays).toBe(10);
    await waitFor(() => expect(screen.getByTestId("frames").textContent).not.toBe("[]"));
    fireEvent.change(slider, { target: { value: "172800" } });
    expect(screen.getByTestId("frames").textContent).toBe("[]");
    fireEvent.change(slider, { target: { value: "864000" } });
    expect(slider.getAttribute("aria-valuetext")).toBe("10d 00h 00m");
    fireEvent.click(screen.getByRole("button", { name: "Restart experiment" }));
    expect(slider.value).toBe("0");
  });

  it("maps narration progress and seeking across the complete ten-day run", async () => {
    render(<App />);
    fireEvent.click(screen.getByRole("button", { name: /Bottle/ }));
    fireEvent.click(screen.getByRole("button", { name: "Drop at test ocean point" }));
    await waitFor(() => expect(screen.getByTestId("frames").textContent).not.toBe("[]"));
    fireEvent.click(screen.getByRole("button", { name: "Play simulation and narration" }));
    await waitFor(() => expect(FakeAudio.instances).toHaveLength(1));
    const audio = FakeAudio.instances[0];
    const slider = screen.getByRole("slider") as HTMLInputElement;
    act(() => { audio.currentTime = 15; audio.ontimeupdate?.(); });
    expect(slider.value).toBe("216000");
    fireEvent.change(slider, { target: { value: "648000" } });
    expect(audio.currentTime).toBe(45);
    fireEvent.click(screen.getByRole("button", { name: "Play simulation and narration" }));
    act(() => audio.onended?.());
    expect(slider.value).toBe("864000");
    expect(slider.getAttribute("aria-valuetext")).toBe("10d 00h 00m");
    fireEvent.click(screen.getByRole("button", { name: "Restart experiment" }));
    expect(audio.currentTime).toBe(0);
    expect(slider.value).toBe("0");
  });

  it("removes a rejected land placement so the next water placement can run", async () => {
    let rejectedId = "";
    vi.mocked(requestSimulation).mockImplementationOnce(async (placements) => {
      rejectedId = placements[0].id;
      throw new SimulationApiError("That spot is land. Try the water!", 422, "on_land", rejectedId);
    });

    render(<App />);
    fireEvent.click(screen.getByRole("button", { name: /Bottle/ }));
    fireEvent.click(screen.getByRole("button", { name: "Drop at test ocean point" }));

    await screen.findByText("That spot is too close to land for the ocean model. Try farther offshore.");
    expect(requestSimulation).toHaveBeenCalledTimes(1);

    fireEvent.click(screen.getByRole("button", { name: "Drop at test ocean point" }));
    await waitFor(() => expect(requestSimulation).toHaveBeenCalledTimes(2));
    expect(vi.mocked(requestSimulation).mock.calls[1][0]).toHaveLength(1);
    expect(vi.mocked(requestSimulation).mock.calls[1][0][0]).toMatchObject({ coordinates: [-130, 40] });
    expect(vi.mocked(requestSimulation).mock.calls[1][0][0].id).not.toBe(rejectedId);
    await waitFor(() => expect(screen.getByTestId("frames").textContent).not.toBe("[]"));
  });
});
