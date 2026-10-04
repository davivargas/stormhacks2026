import { useEffect, useMemo, useRef, useState } from "react";
import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import {
  Anchor,
  Backpack,
  CupSoda,
  CircleHelp,
  Eraser,
  Info,
  Moon,
  X,
  Pause,
  Play,
  RotateCcw,
  Sparkles,
  Sun,
  Trash2,
  Waves,
} from "lucide-react";
import { OceanMap } from "./OceanMap";
import { deleteSessionRuns, requestSimulation } from "./simulationApi";
import type { SimulateResponse } from "./simulationApi";
import { requestStoryAudio, requestStoryForRun } from "./storyApi";
import {
  INITIAL_PLACEMENTS,
  interpolateFrame,
} from "./simulation";
import type { ComparisonMode, Coordinates, ParticleStatus, Placement, Tool } from "./types";
import {
  audioTimeToTimeline,
  clampTimelineTime,
  DEFAULT_DURATION_SECONDS,
  formatDurationLabel,
  formatTime,
  placementTime,
  SIMULATION_DURATION_DAYS,
  timelineTimeToAudio,
} from "./timeline";

const tools: Array<{ id: Tool; label: string; detail: string; icon: typeof CupSoda }> = [
  { id: "bottle", label: "Bottle", detail: "Place in water", icon: CupSoda },
  { id: "bag", label: "Bag", detail: "Place in water", icon: Backpack },
  { id: "foam", label: "Foam", detail: "Place in water", icon: Sparkles },
  { id: "collector", label: "Cleanup", detail: "Catch litter", icon: Anchor },
  { id: "remove", label: "Remove", detail: "Pick an item", icon: Eraser },
];

const START_MESSAGE = "Choose a litter type, then click the ocean to place it.";

const goalListVariants = {
  hidden: {},
  visible: {
    transition: { staggerChildren: 0.1, delayChildren: 0.18 },
  },
};

const goalCardVariants = {
  hidden: { opacity: 0, y: 14 },
  visible: { opacity: 1, y: 0 },
};

function splitNarrationLines(script: string) {
  return script.match(/[^.!?]+[.!?]+(?=\s|$)|[^.!?]+$/g)?.map((line) => line.trim()).filter(Boolean) ?? [script];
}

function getNarrationLineIndex(lines: string[], progress: number) {
  if (lines.length <= 1) return 0;
  const weights = lines.map((line) => Math.max(1, line.split(/\s+/).filter(Boolean).length));
  const totalWeight = weights.reduce((total, weight) => total + weight, 0);
  let accumulatedWeight = 0;

  for (let index = 0; index < weights.length; index += 1) {
    accumulatedWeight += weights[index];
    if (progress < accumulatedWeight / totalWeight) return index;
  }

  return lines.length - 1;
}

function isAbortError(error: unknown) {
  return error instanceof DOMException && error.name === "AbortError";
}

function statusLabel(status: ParticleStatus) {
  return status === "outside" ? "outside the map" : status;
}

function App() {
  const prefersReducedMotion = useReducedMotion();
  const [placements, setPlacements] = useState<Placement[]>(INITIAL_PLACEMENTS);
  const [selectedParticleId, setSelectedParticleId] = useState<string | null>(
INITIAL_PLACEMENTS.find(({ type }) => type !== "collector")?.id ?? null,
  );
  const [tool, setTool] = useState<Tool>("explore");
  const [comparison] = useState<ComparisonMode>("with");
  const [timeSeconds, setTimeSeconds] = useState(0);
  const [isPlaying, setIsPlaying] = useState(false);
  const [isNarrating, setIsNarrating] = useState(false);
  const [isPreparingNarration, setIsPreparingNarration] = useState(false);
  const [narrationLines, setNarrationLines] = useState<string[]>([]);
  const [narrationLineIndex, setNarrationLineIndex] = useState(0);
  const [isHelpOpen, setIsHelpOpen] = useState(false);
  const [isDataOpen, setIsDataOpen] = useState(false);
  const [isDarkMode, setIsDarkMode] = useState(false);
  const [isSimulating, setIsSimulating] = useState(false);
  const [simulationRun, setSimulationRun] = useState<SimulateResponse | null>(null);
  const [simulationError, setSimulationError] = useState<string | null>(null);
  const [message, setMessage] = useState(START_MESSAGE);
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
  const selectedTrajectory = trajectories.find(({ id }) => id === selectedParticleId) ?? trajectories[0];
  const storySignature = useMemo(
    () => (simulationRun && selectedTrajectory ? `${simulationRun.runId}:${selectedTrajectory.id}` : null),
    [simulationRun, selectedTrajectory],
  );
  const displayedMessage = isNarrating && narrationLines.length > 0
    ? narrationLines[narrationLineIndex]
    : message;

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
        if (controller.signal.aborted) return;
        setSimulationRun(run);
        setTimeSeconds((current) => clampTimelineTime(current, run.totalSeconds));
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
    setNarrationLines([]);
    setNarrationLineIndex(0);
  }, [storySignature]);

  useEffect(() => () => {
    playbackRequestRef.current += 1;
    detachAudio(audioRef.current);
  }, []);

  useEffect(() => {
    if (!isHelpOpen && !isDataOpen) return;
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setIsHelpOpen(false);
        setIsDataOpen(false);
      }
    };
    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, [isHelpOpen, isDataOpen]);

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
        const next = current + elapsed * (durationSeconds / 60_000);
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
      setNarrationLineIndex(0);
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

    if (!simulationRun || !selectedTrajectory || !storySignature) {
      setIsPlaying(true);
      return;
    }

    const requestId = playbackRequestRef.current + 1;
    playbackRequestRef.current = requestId;
    setIsPreparingNarration(true);
    setMessage("Shelly is getting your ocean story ready...");

    try {
      const story = await requestStoryForRun(simulationRun.runId, selectedTrajectory.id);
      if (playbackRequestRef.current !== requestId) return;
      const narration = await requestStoryAudio(story.story_id);
      if (playbackRequestRef.current !== requestId) return;
      const lines = splitNarrationLines(narration.script);
      setNarrationLines(lines);
      setNarrationLineIndex(0);
      setMessage(lines[0] ?? narration.script);

      detachAudio(audioRef.current);
      const audio = new Audio(narration.audio_url);
      audio.preload = "auto";
      audio.onplay = () => {
        setNarrationLineIndex(0);
        setIsNarrating(true);
      };
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
          setNarrationLineIndex(getNarrationLineIndex(lines, audio.currentTime / audio.duration));
          setTimeSeconds(audioTimeToTimeline(audio.currentTime, audio.duration, durationSeconds));
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
    stopPlayback();
    const placedAtSeconds = placementTime(timeSeconds, durationSeconds);
    setTimeSeconds(placedAtSeconds);
    const item: Placement = { id: `${tool}-${crypto.randomUUID()}`, type: tool, coordinates, placedAtSeconds };
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
      : START_MESSAGE);
  };

  const resetAll = () => {
    stopPlayback();
    detachAudio(audioRef.current);
    audioRef.current = null;
    setPlacements([]);
    setSelectedParticleId(null);
    setTool("explore");
    setTimeSeconds(0);
    setNarrationLines([]);
    setNarrationLineIndex(0);
    setMessage(START_MESSAGE);
    const warn = () => setMessage("The map is reset, but the saved runs could not be deleted. Try Reset all again.");
    deleteSessionRuns()
      .then(({ database }) => {
        if (database === "failed") warn();
      })
      .catch(warn);
  };

  return (
    <main className={`ocean-page ${isDarkMode ? "ocean-page--dark" : ""}`}>
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
        <motion.button
          className="theme-toggle"
          type="button"
          aria-label={isDarkMode ? "Switch to light mode" : "Switch to dark mode"}
          aria-pressed={isDarkMode}
          onClick={() => setIsDarkMode((current) => !current)}
          whileHover={{ scale: 1.06 }}
          whileTap={{ scale: 0.94 }}
        >
          {isDarkMode ? <Sun size={20} /> : <Moon size={20} />}
        </motion.button>
        <motion.header className="topbar" initial={{ opacity: 0, y: -24 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.55, ease: [0.22, 1, 0.36, 1] }}>
          <motion.a className="brand" href="#top" aria-label="LitterVoyage home" whileHover={{ y: -2 }}>
            <span className="brand-mark"><Waves size={27} /></span>
            <span>Litter<span>Voyage</span></span>
          </motion.a>
          <motion.button className="icon-button" type="button" aria-label="Open help" aria-expanded={isHelpOpen} onClick={() => setIsHelpOpen(true)} whileHover={{ scale: 1.06 }} whileTap={{ scale: 0.94 }}><CircleHelp size={22} /></motion.button>
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
            <motion.button
              className="tool-button tool-button--reset"
              type="button"
              onClick={resetAll}
              initial={{ opacity: 0, x: -10 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ delay: 0.28 + tools.length * 0.06, type: "spring", stiffness: 420, damping: 26 }}
              whileHover={{ x: 5, scale: 1.015 }}
              whileTap={{ scale: 0.98 }}
            >
              <span className="tool-icon tool-icon--reset"><Trash2 size={24} /></span>
              <span><strong>Reset all</strong><small>Clear the map</small></span>
            </motion.button>
          </div>
          <div className="current-key"><span>↗</span><p><strong>Ocean current</strong>Arrows show water direction</p></div>
        </motion.aside>

        <motion.section className={`guide-bubble ${isNarrating ? "guide-bubble--talking guide-bubble--speech" : ""}`} aria-live="polite" initial={{ opacity: 0, y: 22, scale: 0.94 }} animate={{ opacity: 1, y: 0, scale: 1 }} transition={{ duration: 0.5, delay: 0.35, ease: [0.22, 1, 0.36, 1] }}>
          <motion.div
            className={`mascot ${isNarrating ? "mascot--talking" : ""}`}
            aria-hidden="true"
            animate={isNarrating ? { y: [0, -4, 0], rotate: [-3, 3, -3], scale: [1, 1.06, 1] } : { y: [0, -5, 0], rotate: [-1, 1, -1], scale: 1 }}
            transition={{ duration: isNarrating ? 0.42 : 3.2, repeat: Infinity, ease: "easeInOut" }}
          >
            <img className="cartoon-turtle" src="/shelly-turtle.png" alt="Shelly the cartoon turtle" />
          </motion.div>
          <div><span className="eyebrow">{isNarrating ? "Shelly is talking" : "Shelly says"}</span><AnimatePresence mode="wait"><motion.p key={displayedMessage} initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -6 }} transition={{ duration: 0.2 }}>{displayedMessage}</motion.p></AnimatePresence></div>
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
                  const nextTime = clampTimelineTime(Number(event.target.value), durationSeconds);
                  setTimeSeconds(nextTime);
                  if (audioRef.current && Number.isFinite(audioRef.current.duration)) {
                    audioRef.current.currentTime = timelineTimeToAudio(nextTime, durationSeconds, audioRef.current.duration);
                  }
                }}
              />
              <div className="timeline-endpoints" aria-hidden="true">
                <span>Start · 0 days</span>
                <span>End · {formatDurationLabel(durationSeconds)}</span>
              </div>
            </div>
            {/* Comparison control temporarily hidden while the single cleanup mode is refined.
            <div className="comparison-control" role="group" aria-label="Compare cleanup results">
              <motion.button className={comparison === "without" ? "active" : ""} type="button" onClick={() => setComparison("without")} whileTap={{ scale: 0.96 }}>Without</motion.button>
              <motion.button className={comparison === "with" ? "active" : ""} type="button" onClick={() => setComparison("with")} whileTap={{ scale: 0.96 }}>With cleanup</motion.button>
            </div>
            */}
          </div>
        </motion.section>

        <motion.button className="source-button" type="button" aria-label="Open data and assumptions" aria-expanded={isDataOpen} onClick={() => setIsDataOpen(true)} whileHover={{ y: -3 }} whileTap={{ scale: 0.96 }}><Info size={15} /> Data & assumptions</motion.button>
      </div>

      <AnimatePresence>
      {isHelpOpen && (
        <motion.div
          className="help-backdrop"
          role="presentation"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: prefersReducedMotion ? 0 : 0.25 }}
          onMouseDown={(event) => {
            if (event.target === event.currentTarget) setIsHelpOpen(false);
          }}
        >
          <motion.section
            className="help-dialog"
            role="dialog"
            aria-modal="true"
            aria-labelledby="help-title"
            initial={prefersReducedMotion ? { opacity: 0 } : { opacity: 0, scale: 0.94, y: 12 }}
            animate={prefersReducedMotion ? { opacity: 1 } : { opacity: 1, scale: 1, y: 0 }}
            exit={prefersReducedMotion ? { opacity: 0 } : { opacity: 0, scale: 0.97, y: 8 }}
            transition={prefersReducedMotion ? { duration: 0 } : { type: "spring", stiffness: 360, damping: 28 }}
          >
            <button className="help-close" type="button" aria-label="Close help" onClick={() => setIsHelpOpen(false)}>
              <X size={20} />
            </button>
            <span className="eyebrow">About LitterVoyage</span>
            <h2 id="help-title">Explore how litter reaches the sea</h2>
            <p>LitterVoyage turns an everyday piece of litter into an interactive ocean journey. Place it on the map, follow the currents, and compare what happens when cleanup is added.</p>
            <motion.div
              className="goal-list"
              variants={prefersReducedMotion ? undefined : goalListVariants}
              initial="hidden"
              animate="visible"
            >
              <motion.article variants={prefersReducedMotion ? undefined : goalCardVariants} whileHover={prefersReducedMotion ? undefined : { y: -4, scale: 1.015 }}>
                <strong>SDG 14 · Life Below Water</strong>
                <p>Shows how plastic pollution can move through marine environments and why preventing litter at its source matters.</p>
              </motion.article>
              <motion.article variants={prefersReducedMotion ? undefined : goalCardVariants} whileHover={prefersReducedMotion ? undefined : { y: -4, scale: 1.015 }}>
                <strong>SDG 12 · Responsible Consumption and Production</strong>
                <p>Connects individual choices, waste disposal, and the path litter can take when it is not managed responsibly.</p>
              </motion.article>
              <motion.article variants={prefersReducedMotion ? undefined : goalCardVariants} whileHover={prefersReducedMotion ? undefined : { y: -4, scale: 1.015 }}>
                <strong>SDG 6 · Clean Water and Sanitation</strong>
                <p>Highlights the shared responsibility to keep waterways clean and reduce pollution before it spreads.</p>
              </motion.article>
              <motion.article variants={prefersReducedMotion ? undefined : goalCardVariants} whileHover={prefersReducedMotion ? undefined : { y: -4, scale: 1.015 }}>
                <strong>SDG 17 · Partnerships for the Goals</strong>
                <p>Invites people to learn, experiment, and work together on practical solutions for healthier oceans.</p>
              </motion.article>
            </motion.div>
            <p className="help-footer">Small actions add up. Use the map to learn, then help keep litter out of the water.</p>
          </motion.section>
        </motion.div>
      )}
      </AnimatePresence>

      <AnimatePresence>
        {isDataOpen && (
          <motion.div
            className="help-backdrop"
            role="presentation"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: prefersReducedMotion ? 0 : 0.25 }}
            onMouseDown={(event) => {
              if (event.target === event.currentTarget) setIsDataOpen(false);
            }}
          >
            <motion.section
              className="help-dialog data-dialog"
              role="dialog"
              aria-modal="true"
              aria-labelledby="data-title"
              initial={prefersReducedMotion ? { opacity: 0 } : { opacity: 0, scale: 0.94, y: 12 }}
              animate={prefersReducedMotion ? { opacity: 1 } : { opacity: 1, scale: 1, y: 0 }}
              exit={prefersReducedMotion ? { opacity: 0 } : { opacity: 0, scale: 0.97, y: 8 }}
              transition={prefersReducedMotion ? { duration: 0 } : { type: "spring", stiffness: 360, damping: 28 }}
            >
              <button className="help-close" type="button" aria-label="Close data and assumptions" onClick={() => setIsDataOpen(false)}>
                <X size={20} />
              </button>
              <span className="eyebrow">How the simulation works</span>
              <h2 id="data-title">Data & assumptions</h2>
              <p>LitterVoyage is an educational model that helps you explore how litter can move through an ocean environment and how cleanup can change its journey.</p>
              <div className="goal-list">
                <motion.article variants={prefersReducedMotion ? undefined : goalCardVariants}>
                  <strong>What the map shows</strong>
                  <p>Place a bottle, bag, or foam item on the water. The map displays its marker, simulated trail, current direction, and any cleanup area you add.</p>
                </motion.article>
                <motion.article variants={prefersReducedMotion ? undefined : goalCardVariants}>
                  <strong>How the one-year model works</strong>
                  <p>The backend calculates a one-year educational experiment using ocean-current data. Positions are recorded hourly, with additional samples at placement and terminal events. An item begins moving when you place it on the shared timeline.</p>
                </motion.article>
                <motion.article variants={prefersReducedMotion ? undefined : goalCardVariants}>
                  <strong>Statuses and cleanup</strong>
                  <p>Litter may remain floating, become beached, move outside the modeled area, or be captured. Collectors become active when placed and use the backend's configured capture radius{simulationRun?.collectors[0] ? ` (${simulationRun.collectors[0].radiusM / 1000} km for this run)` : ""}.</p>
                </motion.article>
                <motion.article variants={prefersReducedMotion ? undefined : goalCardVariants}>
                  <strong>Model assumptions</strong>
                  <p>Each area uses one frozen current snapshot throughout the experiment, with wave drift included when available. Tides, wind, sinking, and decomposition are not modeled. The simulated year is an educational “what if,” not a year-long forecast.</p>
                </motion.article>
                <motion.article variants={prefersReducedMotion ? undefined : goalCardVariants}>
                  <strong>Data sources and limitations</strong>
                  <p>{simulationRun ? simulationRun.attribution.source : "The backend uses Copernicus Marine currents when available and explicitly records synthetic fallback data when real data is unavailable."} This is not a validated real-world drift prediction.</p>
                  {simulationRun && <>
                    <p>Dataset: {simulationRun.attribution.dataset}</p>
                    <ul>{simulationRun.snapshots.map((snapshot) => <li key={snapshot.snapshotId}>{snapshot.source} · {new Date(snapshot.sliceTime).toLocaleString()}</li>)}</ul>
                    <ul>{simulationRun.attribution.limitations.map((limitation) => <li key={limitation}>{limitation}</li>)}</ul>
                  </>}
                </motion.article>
              </div>
              <p className="help-footer">Use the simulation to build intuition, compare choices, and learn why preventing litter at its source matters.</p>
            </motion.section>
          </motion.div>
        )}
      </AnimatePresence>
    </main>
  );
}

export default App;
