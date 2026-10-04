// @vitest-environment jsdom
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import App from "./App";
import { deleteSessionRuns, requestSimulation } from "./simulationApi";
import { requestStoryAudio, requestStoryForRun } from "./storyApi";
import type { Coordinates } from "./types";

vi.mock("./OceanMap", () => ({
  OceanMap: ({ onPlace, onSelect, frames, trajectories }: {
    onPlace: (coordinates: Coordinates) => void;
    onSelect: (id: string) => void;
    frames: unknown[];
    trajectories: Array<{ id: string }>;
  }) => <>
    <button onClick={() => onPlace([-130, 40])}>Drop at test ocean point</button>
    {trajectories.map(({ id }, index) => (
      <button key={id} onClick={() => onSelect(id)}>Pick litter {index + 1}</button>
    ))}
    <output data-testid="frames">{JSON.stringify(frames)}</output>
  </>,
}));
vi.mock("./simulationApi", () => ({ requestSimulation: vi.fn(), deleteSessionRuns: vi.fn() }));
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
  vi.mocked(deleteSessionRuns).mockResolvedValue({ deleted: 1, database: "cleared" });
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.mocked(requestSimulation).mockReset();
  vi.mocked(requestStoryForRun).mockReset();
  vi.mocked(requestStoryAudio).mockReset();
  vi.mocked(deleteSessionRuns).mockReset();
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
});

describe("reset all", () => {
  const START_MESSAGE = "Choose a litter type, then click the ocean to place it.";
  const FAILED_MESSAGE = "The map is reset, but the saved runs could not be deleted. Try Reset all again.";

  async function placeBottleOnDayThree() {
    const slider = screen.getByRole("slider") as HTMLInputElement;
    fireEvent.click(screen.getByRole("button", { name: /Bottle/ }));
    fireEvent.change(slider, { target: { value: "259200" } });
    fireEvent.click(screen.getByRole("button", { name: "Drop at test ocean point" }));
    await waitFor(() => expect(screen.getByTestId("frames").textContent).not.toBe("[]"));
    return slider;
  }

  it("clears the map, rewinds the timer, and deletes this session's runs", async () => {
    render(<App />);
    const slider = await placeBottleOnDayThree();
    expect(slider.value).toBe("259200");

    fireEvent.click(screen.getByRole("button", { name: /Reset all/ }));

    expect(slider.value).toBe("0");
    expect(slider.getAttribute("aria-valuetext")).toBe("0d 00h 00m");
    expect(screen.getByTestId("frames").textContent).toBe("[]");
    expect(screen.getByRole("button", { name: /Bottle/ }).getAttribute("aria-pressed")).toBe("false");
    expect(deleteSessionRuns).toHaveBeenCalledTimes(1);
    await waitFor(() => expect(screen.getByText(START_MESSAGE)).toBeTruthy());
    expect(requestSimulation).toHaveBeenCalledTimes(1); // an empty map asks for no new simulation
  });

  it("discards the loaded narration", async () => {
    render(<App />);
    await placeBottleOnDayThree();
    fireEvent.click(screen.getByRole("button", { name: "Play simulation and narration" }));
    await waitFor(() => expect(FakeAudio.instances).toHaveLength(1));
    const audio = FakeAudio.instances[0];

    fireEvent.click(screen.getByRole("button", { name: /Reset all/ }));

    expect(audio.ontimeupdate).toBeNull();
    expect(screen.getByRole("button", { name: "Play simulation and narration" })).toBeTruthy();
  });

  it.each([
    ["the request fails", () => vi.mocked(deleteSessionRuns).mockRejectedValue(new Error("offline"))],
    ["the database delete fails", () => vi.mocked(deleteSessionRuns).mockResolvedValue({ deleted: 1, database: "failed" })],
  ])("still resets the map and says so when %s", async (_label, arrange) => {
    arrange();
    render(<App />);
    const slider = await placeBottleOnDayThree();

    fireEvent.click(screen.getByRole("button", { name: /Reset all/ }));

    expect(slider.value).toBe("0");
    expect(screen.getByTestId("frames").textContent).toBe("[]");
    await waitFor(() => expect(screen.getByText(FAILED_MESSAGE)).toBeTruthy());
  });

  it("does not warn when no database is configured", async () => {
    vi.mocked(deleteSessionRuns).mockResolvedValue({ deleted: 1, database: "unavailable" });
    render(<App />);
    await placeBottleOnDayThree();
    fireEvent.click(screen.getByRole("button", { name: /Reset all/ }));
    await waitFor(() => expect(screen.getByText(START_MESSAGE)).toBeTruthy());
    expect(screen.queryByText(FAILED_MESSAGE)).toBeNull();
  });
});

describe("narrate tool", () => {
  it("narrates the litter picked with the Narrate tool", async () => {
    render(<App />);
    fireEvent.click(screen.getByRole("button", { name: /Bottle/ }));
    fireEvent.click(screen.getByRole("button", { name: "Drop at test ocean point" }));
    fireEvent.click(screen.getByRole("button", { name: "Drop at test ocean point" }));
    await waitFor(() => expect(screen.getByRole("button", { name: "Pick litter 2" })).toBeTruthy());
    const firstId = vi.mocked(requestSimulation).mock.calls.at(-1)![0][0].id;

    const narrate = screen.getByRole("button", { name: /Narrate/ });
    fireEvent.click(narrate);
    expect(narrate.getAttribute("aria-pressed")).toBe("true");
    fireEvent.click(screen.getByRole("button", { name: "Pick litter 1" }));

    expect(narrate.getAttribute("aria-pressed")).toBe("false");
    await waitFor(() => expect(screen.getByText("Shelly will tell this bottle's story. Press play to hear it!")).toBeTruthy());
    fireEvent.click(screen.getByRole("button", { name: "Play simulation and narration" }));
    await waitFor(() => expect(requestStoryForRun).toHaveBeenCalledWith("run-2", firstId));
  });
});
