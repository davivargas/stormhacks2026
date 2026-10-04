import { useEffect, useMemo, useRef, useState } from "react";
import { AnimatePresence, motion } from "motion/react";
import {
  Anchor,
  Backpack,
  CupSoda,
  CircleHelp,
  Eraser,
  Info,
  Pause,
  Play,
  RotateCcw,
  Sparkles,
  Waves,
} from "lucide-react";
import { OceanMap } from "./OceanMap";
import { requestSimulation } from "./simulationApi";
import type { SimulateResponse } from "./simulationApi";
import { requestOceanStory, requestStoryAudio } from "./storyApi";
import type { StorySimulationSummary } from "./storyApi";
import {
  INITIAL_PLACEMENTS,
  interpolateFrame,
} from "./simulation";
import type { ComparisonMode, Coordinates, ParticleStatus, Placement, Tool } from "./types";

const SIMULATION_DURATION_DAYS = 1;
const DEFAULT_DURATION_SECONDS = SIMULATION_DURATION_DAYS * 24 * 60 * 60;

const tools: Array<{ id: Tool; label: string; detail: string; icon: typeof CupSoda }> = [
  { id: "bottle", label: "Bottle", detail: "Place in water", icon: CupSoda },
  { id: "bag", label: "Bag", detail: "Place in water", icon: Backpack },
  { id: "foam", label: "Foam", detail: "Place in water", icon: Sparkles },
  { id: "collector", label: "Cleanup", detail: "Catch litter", icon: Anchor },
  { id: "remove", label: "Remove", detail: "Pick an item", icon: Eraser },
];

function formatTime(seconds: number) {
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  return `${hours}h ${minutes.toString().padStart(2, "0")}m`;
}

function buildStorySummary(
  simulationRun: SimulateResponse | null,
  selectedParticleId: string | null,
): StorySimulationSummary | null {
  const trajectories = simulationRun?.trajectories ?? [];
  const trajectory = trajectories.find(({ id }) => id === selectedParticleId) ?? trajectories[0];
  if (!simulationRun || !trajectory) return null;

  const lastSample = trajectory.samples.at(-1);
  if (!lastSample) return null;
  const item = simulationRun.items.find(({ id }) => id === trajectory.id);
  const finalStatus = item?.finalStatus ?? lastSample.status;

  const events: StorySimulationSummary["events"] = [
    { elapsed_hours: 0, type: "released", location: "the ocean" },
  ];
  let previousStatus = trajectory.samples[0]?.status ?? "floating";

  trajectory.samples.slice(1).forEach((sample) => {
    if (sample.status === previousStatus) return;
    events.push({
      elapsed_hours: sample.timeSeconds / 3600,
      type: sample.status === "outside" ? "outside_domain" : sample.status,
    });
    previousStatus = sample.status;
  });

  if (events.length === 1) {
    events.push({
      elapsed_hours: simulationRun.totalSeconds / 3600,
      type: "still_floating",
    });
  }

  return {
    simulation_id: simulationRun.runId,
    litter_type: `plastic_${trajectory.type}`,
    particle_id: trajectory.id,
    duration_hours: simulationRun.totalSeconds / 3600,
    events,
    final_status: finalStatus === "outside" ? "outside_domain" : finalStatus,
    assumptions: [
      "This path follows ocean current data",
      ...simulationRun.attribution.limitations,
    ],
  };
}

function isAbortError(error: unknown) {
  return error instanceof DOMException && error.name === "AbortError";
}

function statusLabel(status: ParticleStatus) {
  return status === "outside" ? "outside the map" : status;
}

function App() {
  const [placements, setPlacements] = useState<Placement[]>(INITIAL_PLACEMENTS);
  const [selectedParticleId, setSelectedParticleId] = useState<string | null>(
INITIAL_PLACEMENTS.find(({ type }) => type !== "collector")?.id ?? null,
  );
  const [tool, setTool] = useState<Tool>("explore");
  const [comparison, setComparison] = useState<ComparisonMode>("with");
  const [timeSeconds, setTimeSeconds] = useState(0);
  const [isPlaying, setIsPlaying] = useState(false);
  const [isNarrating, setIsNarrating] = useState(false);
  const [isPreparingNarration, setIsPreparingNarration] = useState(false);
  const [isSimulating, setIsSimulating] = useState(false);
  const [simulationRun, setSimulationRun] = useState<SimulateResponse | null>(null);
  const [simulationError, setSimulationError] = useState<string | null>(null);
  const [message, setMessage] = useState("Choose a litter type, then click the ocean to place it.");
  const lastFrameRef = useRef<number | null>(null);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const narrationSignatureRef = useRef<string | null>(null);
  const playbackRequestRef = useRef(0);

  const durationSeconds = simulationRun?.totalSeconds ?? DEFAULT_DURATION_SECONDS;
  const trajectories = useMemo(() => simulationRun?.trajectories ?? [], [simulationRun]);
  const frames = useMemo(
    () => interpolateFrame(trajectories, timeSeconds),
    [trajectories, timeSeconds],
  );
  const storySummary = useMemo(
    () => buildStorySummary(simulationRun, selectedParticleId),
    [simulationRun, selectedParticleId],
  );
  const storySignature = useMemo(
    () => (storySummary ? JSON.stringify(storySummary) : null),
    [storySummary],
  );

  const detachAudio = (audio: HTMLAudioElement | null) => {
    if (!audio) return;
    audio.pause();
    audio.onplay = null;
    audio.onpause = null;
    audio.onended = null;
    audio.onerror = null;
    audio.ontimeupdate = null;
  };

  const stopPlayback = () => {
    playbackRequestRef.current += 1;
    setIsPreparingNarration(false);
    setIsPlaying(false);
    setIsNarrating(false);
    audioRef.current?.pause();
  };

  useEffect(() => {
    const hasLitter = placements.some(({ type }) => type !== "collector");
    if (!hasLitter) {
      setSimulationRun(null);
      setSimulationError(null);
      setIsSimulating(false);
      return;
    }

    const controller = new AbortController();
    setIsSimulating(true);
    setSimulationError(null);

    requestSimulation(placements, {
      durationDays: SIMULATION_DURATION_DAYS,
      honourCollectors: comparison === "with",
      signal: controller.signal,
    })
      .then((run) => {
        setSimulationRun(run);
        setTimeSeconds((current) => Math.min(current, run.totalSeconds));
      })
      .catch((error) => {
        if (isAbortError(error)) return;
        const detail = error instanceof Error ? error.message : "Could not run the ocean simulation.";
        setSimulationRun(null);
        setSimulationError(detail);
        setMessage(`${detail} Try another ocean spot or restart the backend.`);
      })
      .finally(() => {
        if (!controller.signal.aborted) setIsSimulating(false);
      });

    return () => controller.abort();
  }, [placements, comparison]);

  useEffect(() => {
    if (narrationSignatureRef.current === null) {
      narrationSignatureRef.current = storySignature;
      return;
    }
    if (narrationSignatureRef.current === storySignature) return;

    playbackRequestRef.current += 1;
    detachAudio(audioRef.current);
    audioRef.current = null;
    narrationSignatureRef.current = storySignature;
    setIsPreparingNarration(false);
    setIsPlaying(false);
    setIsNarrating(false);
  }, [storySignature]);

  useEffect(() => () => {
    playbackRequestRef.current += 1;
    detachAudio(audioRef.current);
  }, []);

  useEffect(() => {
    if (trajectories.some(({ id }) => id === selectedParticleId)) return;
    setSelectedParticleId(trajectories[0]?.id ?? null);
  }, [selectedParticleId, trajectories]);

  useEffect(() => {
    if (!isPlaying || isNarrating) {
      lastFrameRef.current = null;
      return;
    }

    let requestId = 0;
    const animate = (timestamp: number) => {
      if (lastFrameRef.current === null) lastFrameRef.current = timestamp;
      const elapsed = timestamp - lastFrameRef.current;
      lastFrameRef.current = timestamp;
      setTimeSeconds((current) => {
        const next = current + elapsed * 12;
        if (next >= durationSeconds) {
          setIsPlaying(false);
          return durationSeconds;
        }
        return next;
      });
      requestId = requestAnimationFrame(animate);
    };
    requestId = requestAnimationFrame(animate);
    return () => cancelAnimationFrame(requestId);
  }, [durationSeconds, isPlaying, isNarrating]);

  const playNarration = async (audio: HTMLAudioElement) => {
    if (audio.ended || audio.currentTime >= audio.duration - 0.05) {
      audio.currentTime = 0;
      setTimeSeconds(0);
    }
    try {
      await audio.play();
      setIsPlaying(true);
    } catch {
      setIsPlaying(false);
      setIsNarrating(false);
      setMessage("Shelly's story is ready. Press Play once more to hear it!");
    }
  };

  const startPlayback = async () => {
    if (isPlaying || isPreparingNarration) {
      stopPlayback();
      return;
    }

    if (timeSeconds >= durationSeconds) setTimeSeconds(0);

    if (audioRef.current && narrationSignatureRef.current === storySignature) {
      await playNarration(audioRef.current);
      return;
    }

    if (isSimulating) {
      setMessage("Waiting for the real ocean simulation to finish...");
      return;
    }

    if (simulationError) {
      setMessage(`${simulationError} The story needs a successful backend simulation first.`);
      return;
    }

    if (!storySummary || !storySignature) {
      setIsPlaying(true);
      return;
    }

    const requestId = playbackRequestRef.current + 1;
    playbackRequestRef.current = requestId;
    setIsPreparingNarration(true);
    setMessage("Shelly is getting your ocean story ready...");

    try {
      const story = await requestOceanStory(storySummary);
      if (playbackRequestRef.current !== requestId) return;
      setMessage(story.script);

      const narration = await requestStoryAudio(story.story_id);
      if (playbackRequestRef.current !== requestId) return;

      detachAudio(audioRef.current);
      const audio = new Audio(narration.audio_url);
      audio.preload = "auto";
      audio.onplay = () => setIsNarrating(true);
      audio.onpause = () => setIsNarrating(false);
      audio.onended = () => {
        setIsNarrating(false);
        setIsPlaying(false);
        setTimeSeconds(durationSeconds);
      };
      audio.onerror = () => {
        setIsNarrating(false);
        setIsPlaying(false);
        setMessage("Shelly could not play the narration. Please try again.");
      };
      audio.ontimeupdate = () => {
        if (Number.isFinite(audio.duration) && audio.duration > 0) {
          setTimeSeconds((audio.currentTime / audio.duration) * durationSeconds);
        }
      };
      audioRef.current = audio;
      narrationSignatureRef.current = storySignature;
      await playNarration(audio);
    } catch (error) {
      if (playbackRequestRef.current !== requestId) return;
      const detail = error instanceof Error ? error.message : "Narration is unavailable.";
      setMessage(`${detail} The simulation can still play without narration.`);
      setIsPlaying(true);
    } finally {
      if (playbackRequestRef.current === requestId) setIsPreparingNarration(false);
    }
  };

  const placeItem = (coordinates: Coordinates) => {
    if (tool === "explore" || tool === "remove") return;
    const item: Placement = { id: `${tool}-${crypto.randomUUID()}`, type: tool, coordinates, placedAtSeconds: timeSeconds };
    setPlacements((current) => [...current, item]);
    if (item.type === "collector") {
      setMessage("Great cleanup spot! Running the ocean simulation again...");
    } else {
      setSelectedParticleId(item.id);
      setMessage(`${item.type[0].toUpperCase()}${item.type.slice(1)} selected! Running the ocean simulation...`);
    }
  };

  const selectParticle = (id: string) => {
    const trajectory = trajectories.find((item) => item.id === id);
    if (!trajectory) return;
    stopPlayback();
    setSelectedParticleId(id);
    const item = simulationRun?.items.find(({ id: itemId }) => itemId === trajectory.id);
    const finalStatus = item ? ` It ends ${statusLabel(item.finalStatus)}.` : "";
    setMessage(`${trajectory.type[0].toUpperCase()}${trajectory.type.slice(1)} selected from the backend run.${finalStatus} Press play for its journey.`);
  };

  const removeItem = (id: string) => {
    setPlacements((current) => current.filter((item) => item.id !== id));
    setMessage("Item removed. Keep experimenting!");
  };

  const resetExperiment = () => {
    stopPlayback();
    if (audioRef.current) audioRef.current.currentTime = 0;
    setTimeSeconds(0);
    setMessage(placements.some(({ type }) => type !== "collector")
      ? "Restarted the backend simulation playback."
      : "Choose a litter type, then click the ocean to place it.");
  };

  return (
    <main className="ocean-page">
      <OceanMap
        tool={tool}
        placements={placements}
        frames={frames}
        trajectories={trajectories}
        timeSeconds={timeSeconds}
        selectedParticleId={selectedParticleId}
        onPlace={placeItem}
        onRemove={removeItem}
        onSelect={selectParticle}
        onInvalidPlacement={() => setMessage("Try a spot inside the sparkling water zone.")}
      />

      <div className="map-overlay">
        <motion.header className="topbar" initial={{ opacity: 0, y: -24 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.55, ease: [0.22, 1, 0.36, 1] }}>
          <motion.a className="brand" href="#top" aria-label="LitterVoyage home" whileHover={{ y: -2 }}>
            <span className="brand-mark"><Waves size={27} /></span>
            <span>Litter<span>Voyage</span></span>
          </motion.a>
          <motion.button className="icon-button" type="button" aria-label="Open help" whileHover={{ scale: 1.06 }} whileTap={{ scale: 0.94 }}><CircleHelp size={22} /></motion.button>
        </motion.header>

        <motion.aside className="tool-panel" aria-label="Map tools" initial={{ opacity: 0, x: -28, scale: 0.96 }} animate={{ opacity: 1, x: 0, scale: 1 }} transition={{ duration: 0.55, delay: 0.15, ease: [0.22, 1, 0.36, 1] }}>
          <div className="panel-heading">
            <span className="eyebrow">Choose a tool</span>
            <h1>Make a splash</h1>
          </div>
          <div className="tool-grid">
            {tools.map(({ id, label, detail, icon: Icon }, index) => (
              <motion.button
                className={`tool-button ${tool === id ? "tool-button--active" : ""}`}
                key={id}
                type="button"
                aria-pressed={tool === id}
                onClick={() => setTool(tool === id ? "explore" : id)}
                initial={{ opacity: 0, x: -10 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ delay: 0.28 + index * 0.06, type: "spring", stiffness: 420, damping: 26 }}
                whileHover={{ x: 5, scale: 1.015 }}
                whileTap={{ scale: 0.98 }}
              >
                <span className={`tool-icon tool-icon--${id}`}><Icon size={24} /></span>
                <span><strong>{label}</strong><small>{detail}</small></span>
                {tool === id && <motion.span className="tool-selection-dot" layoutId="tool-selection" />}
              </motion.button>
            ))}
          </div>
          <div className="current-key"><span>↗</span><p><strong>Ocean current</strong>Arrows show water direction</p></div>
        </motion.aside>

        <motion.section className={`guide-bubble ${isNarrating ? "guide-bubble--talking" : ""}`} aria-live="polite" initial={{ opacity: 0, y: 22, scale: 0.94 }} animate={{ opacity: 1, y: 0, scale: 1 }} transition={{ duration: 0.5, delay: 0.35, ease: [0.22, 1, 0.36, 1] }}>
          <motion.div
            className={`mascot ${isNarrating ? "mascot--talking" : ""}`}
            aria-hidden="true"
            animate={isNarrating ? { y: [0, -4, 0], rotate: [-3, 3, -3], scale: [1, 1.06, 1] } : { y: [0, -5, 0], rotate: [-1, 1, -1], scale: 1 }}
            transition={{ duration: isNarrating ? 0.42 : 3.2, repeat: Infinity, ease: "easeInOut" }}
          >
            <img className="cartoon-turtle" src="/shelly-turtle.png" alt="Shelly the cartoon turtle" />
          </motion.div>
          <div><span className="eyebrow">{isNarrating ? "Shelly is talking" : "Shelly says"}</span><AnimatePresence mode="wait"><motion.p key={message} initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -6 }} transition={{ duration: 0.2 }}>{message}</motion.p></AnimatePresence></div>
        </motion.section>

        <motion.section className="bottom-dock" aria-label="Simulation controls" initial={{ opacity: 0, y: 32 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.6, delay: 0.25 }}>
          <div className="playback-card">
            <motion.button
              className="play-button"
              type="button"
              aria-label={isPlaying || isPreparingNarration ? "Pause simulation and narration" : "Play simulation and narration"}
              aria-busy={isPreparingNarration}
              onClick={() => void startPlayback()}
              whileHover={{ scale: 1.06 }}
              whileTap={{ scale: 0.92 }}
              animate={isPlaying || isPreparingNarration ? { scale: [1, 1.04, 1] } : { scale: 1 }}
              transition={isPlaying || isPreparingNarration ? { duration: 1.4, repeat: Infinity } : { duration: 0.2 }}
            >
              {isPlaying || isPreparingNarration ? <Pause size={22} fill="currentColor" /> : <Play size={22} fill="currentColor" />}
            </motion.button>
            <motion.button className="reset-button" type="button" onClick={resetExperiment} aria-label="Restart experiment" whileHover={{ rotate: -45 }} whileTap={{ scale: 0.9 }}><RotateCcw size={19} /></motion.button>
            <div className="timeline">
              <label htmlFor="timeline-range"><span>Journey time</span><strong>{formatTime(timeSeconds)}</strong></label>
              <input
                id="timeline-range"
                type="range"
                min="0"
                max={durationSeconds}
                step="300"
                value={timeSeconds}
                aria-valuetext={formatTime(timeSeconds)}
                style={{ "--progress": `${durationSeconds > 0 ? (timeSeconds / durationSeconds) * 100 : 0}%` } as React.CSSProperties}
                onChange={(event) => {
                  stopPlayback();
                  const nextTime = Number(event.target.value);
                  setTimeSeconds(nextTime);
                  if (audioRef.current && Number.isFinite(audioRef.current.duration)) {
                    audioRef.current.currentTime = (nextTime / durationSeconds) * audioRef.current.duration;
                  }
                }}
              />
            </div>
            <div className="comparison-control" role="group" aria-label="Compare cleanup results">
              <motion.button className={comparison === "without" ? "active" : ""} type="button" onClick={() => setComparison("without")} whileTap={{ scale: 0.96 }}>Without</motion.button>
              <motion.button className={comparison === "with" ? "active" : ""} type="button" onClick={() => setComparison("with")} whileTap={{ scale: 0.96 }}>With cleanup</motion.button>
            </div>
          </div>
        </motion.section>

        <motion.button className="source-button" type="button" whileHover={{ y: -3 }} whileTap={{ scale: 0.96 }}><Info size={15} /> Data & assumptions</motion.button>
      </div>
    </main>
  );
}

export default App;
