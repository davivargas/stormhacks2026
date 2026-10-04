import { useEffect, useMemo, useRef, useState } from "react";
import { AnimatePresence, motion } from "motion/react";
import {
  Anchor,
  Backpack,
  CupSoda,
  LoaderCircle,
  Eraser,
  Info,
  Pause,
  Play,
  RotateCcw,
  Sparkles,
  Waves,
} from "lucide-react";
import { OceanMap } from "./OceanMap";
import { useSimulation } from "./hooks/useSimulation";
import { fetchMeta } from "./lib/api";
import {
  draftFrames,
  DURATION_SECONDS,
  INITIAL_PLACEMENTS,
} from "./simulation";
import type { ApiMeta, Coordinates, ParticleStatus, Placement, Tool } from "./types";

const tools: Array<{ id: Tool; label: string; detail: string; icon: typeof CupSoda }> = [
  { id: "bottle", label: "Bottle", detail: "Place in water", icon: CupSoda },
  { id: "bag", label: "Bag", detail: "Place in water", icon: Backpack },
  { id: "foam", label: "Foam", detail: "Place in water", icon: Sparkles },
  { id: "collector", label: "Cleanup", detail: "Catch litter", icon: Anchor },
  { id: "remove", label: "Remove", detail: "Pick an item", icon: Eraser },
];

const statusLabels: Record<ParticleStatus, string> = {
  floating: "Floating",
  captured: "Captured",
  beached: "Beached",
  outside: "Outside",
};

function formatTime(seconds: number) {
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  const days = Math.floor(hours / 24);
  return `${days ? `${days}d ` : ""}${hours % 24}h ${minutes.toString().padStart(2, "0")}m`;
}

function App() {
  const [placements, setPlacements] = useState<Placement[]>(INITIAL_PLACEMENTS);
  const [tool, setTool] = useState<Tool>("explore");
  const [timeSeconds, setTimeSeconds] = useState(0);
  const [isPlaying, setIsPlaying] = useState(false);
  const [message, setMessage] = useState("Place some litter, then press play!");
  const [meta, setMeta] = useState<ApiMeta | null>(null);
  const [metaError, setMetaError] = useState<string | null>(null);
  const [metaAttempt, setMetaAttempt] = useState(0);
  const [showSources, setShowSources] = useState(false);
  const sourcesRef = useRef<HTMLDialogElement>(null);
  const sourcesButtonRef = useRef<HTMLButtonElement>(null);
  const { run, status, error, calculate, invalidate } = useSimulation();
  const lastFrameRef = useRef<number | null>(null);
  const totalSeconds = run?.totalSeconds ?? DURATION_SECONDS;
  const collectorRadiusM = meta?.defaults.collectorRadiusM ?? 10_000;
  const isLoading = status === "loading";
  const hasLitter = placements.some((item) => item.type !== "collector");

  useEffect(() => {
    const controller = new AbortController();
    setMetaError(null);
    fetchMeta(controller.signal).then((settings) => {
      if (!controller.signal.aborted) setMeta(settings);
    }).catch((failure: unknown) => {
      if (!controller.signal.aborted) {
        setMetaError(failure instanceof Error ? failure.message : "Cannot load experiment settings.");
      }
    });
    return () => controller.abort();
  }, [metaAttempt]);

  useEffect(() => {
    if (showSources) sourcesRef.current?.showModal();
    else sourcesRef.current?.close();
  }, [showSources]);

  const trajectories = useMemo(
    () => {
      const ids = new Set(placements.map((item) => item.id));
      return run?.trajectories.filter((item) => ids.has(item.id)) ?? [];
    },
    [placements, run],
  );
  const frames = useMemo(
    () => draftFrames(placements, trajectories, timeSeconds),
    [placements, trajectories, timeSeconds],
  );

  const counts = frames.reduce<Record<ParticleStatus, number>>(
    (totals, frame) => ({ ...totals, [frame.status]: totals[frame.status] + 1 }),
    { floating: 0, captured: 0, beached: 0, outside: 0 },
  );

  useEffect(() => {
    if (!isPlaying) {
      lastFrameRef.current = null;
      return;
    }

    let requestId = 0;
    const animate = (timestamp: number) => {
      if (lastFrameRef.current === null) lastFrameRef.current = timestamp;
      const elapsed = timestamp - lastFrameRef.current;
      lastFrameRef.current = timestamp;
      setTimeSeconds((current) => Math.min(totalSeconds, current + elapsed * 12));
      requestId = requestAnimationFrame(animate);
    };
    requestId = requestAnimationFrame(animate);
    return () => cancelAnimationFrame(requestId);
  }, [isPlaying, totalSeconds]);

  useEffect(() => {
    if (timeSeconds >= totalSeconds) setIsPlaying(false);
  }, [timeSeconds, totalSeconds]);

  const togglePlayback = async () => {
    if (isPlaying) {
      setIsPlaying(false);
      return;
    }
    if (isLoading || !meta || !hasLitter) return;
    if (status === "ready" && run) {
      if (timeSeconds >= totalSeconds) setTimeSeconds(0);
      setIsPlaying(true);
      return;
    }
    const result = await calculate({
      placements,
      durationDays: Math.max(meta.durationDays.min, Math.min(1, meta.durationDays.max)),
      collectorRadiusM,
      honourCollectors: true,
    });
    if (result) {
      setTimeSeconds((current) => current >= result.totalSeconds ? 0 : current);
      setMessage("Your ocean paths are ready! Let's follow the litter.");
      setIsPlaying(true);
    }
  };

  const placeItem = (coordinates: Coordinates) => {
    if (tool === "explore" || tool === "remove") return;
    if (meta) {
      const count = placements.filter((item) => (item.type === "collector") === (tool === "collector")).length;
      const limit = tool === "collector" ? meta.defaults.maxCollectors : meta.defaults.maxLitterPlacements;
      if (count >= limit) {
        setMessage(`This experiment can have up to ${limit} ${tool === "collector" ? "cleanup points" : "litter items"}.`);
        return;
      }
    }
    setIsPlaying(false);
    const placedAtSeconds = Math.min(totalSeconds, Math.round(timeSeconds));
    setTimeSeconds(placedAtSeconds);
    invalidate();
    const item: Placement = {
      id: `${tool}-${crypto.randomUUID()}`,
      type: tool,
      coordinates,
      placedAtSeconds,
    };
    setPlacements((current) => [...current, item]);
    setMessage(tool === "collector" ? "Great cleanup spot! Press play to watch for litter." : "Splash! Your litter is ready to travel.");
  };

  const removeItem = (id: string) => {
    setIsPlaying(false);
    invalidate();
    setPlacements((current) => current.filter((item) => item.id !== id));
    setMessage("Item removed. Keep experimenting!");
  };

  const resetExperiment = () => {
    invalidate(true);
    setTimeSeconds(0);
    setIsPlaying(false);
    setPlacements(INITIAL_PLACEMENTS);
    setMessage("Fresh start! What will happen this time?");
  };

  const rejectedPlacement = error?.placementId ? placements.find((item) => item.id === error.placementId) : undefined;
  const guideMessage = isLoading ? "Calculating ocean paths… This may take a moment."
    : error ? error.message : message;
  const sources = new Set(run?.snapshots.map((snapshot) => snapshot.source));
  const dataLabel = !run ? "" : sources.size > 1 ? "Mixed real & synthetic currents"
    : sources.has("synthetic") ? "Synthetic demo currents" : "Copernicus ocean currents";

  return (
    <main className="ocean-page">
      <OceanMap
        tool={tool}
        placements={placements}
        frames={frames}
        trajectories={trajectories}
        collectorRadiusM={collectorRadiusM}
        collectors={run?.collectors}
        timeSeconds={timeSeconds}
        onPlace={placeItem}
        onRemove={removeItem}
        onInvalidPlacement={() => setMessage("Choose a spot in the ocean, away from land!")}
      />

      <div className="map-overlay">
        <motion.header className="topbar" initial={{ opacity: 0, y: -24 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.55 }}>
          <motion.a className="brand" href="#top" aria-label="LitterVoyage home" whileHover={{ y: -2 }}>
            <span className="brand-mark"><Waves size={27} /></span>
            <span>Litter<span>Voyage</span></span>
          </motion.a>
        </motion.header>

        <motion.aside className="tool-panel" aria-label="Map tools" initial={{ opacity: 0, x: -28 }} animate={{ opacity: 1, x: 0 }} transition={{ duration: 0.55, delay: 0.15 }}>
          <div className="panel-heading">
            <span className="eyebrow">Choose a tool</span>
            <h1>Make a splash</h1>
          </div>
          <div className="tool-grid">
            {tools.map(({ id, label, detail, icon: Icon }) => (
              <motion.button
                className={`tool-button ${tool === id ? "tool-button--active" : ""}`}
                key={id}
                type="button"
                aria-pressed={tool === id}
                onClick={() => setTool(tool === id ? "explore" : id)}
                whileHover={{ x: 5 }}
                whileTap={{ scale: 0.98 }}
              >
                <span className={`tool-icon tool-icon--${id}`}><Icon size={24} /></span>
                <span><strong>{label}</strong><small>{detail}</small></span>
                {tool === id && <motion.span className="tool-selection-dot" layoutId="tool-selection" />}
              </motion.button>
            ))}
          </div>
        </motion.aside>

        <motion.section className="guide-bubble" aria-live="polite" initial={{ opacity: 0, y: 22 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.5, delay: 0.35 }}>
          <motion.div className="mascot" aria-hidden="true" animate={{ y: [0, -4, 0] }} transition={{ duration: 3, repeat: Infinity, ease: "easeInOut" }}><span>•</span><span>•</span><b>⌣</b></motion.div>
          <div><span className="eyebrow">Finn says</span><AnimatePresence mode="wait"><motion.p key={guideMessage} initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -6 }} transition={{ duration: 0.2 }}>{guideMessage}</motion.p></AnimatePresence></div>
        </motion.section>

        <motion.section className="bottom-dock" aria-label="Simulation controls" initial={{ opacity: 0, y: 32 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.6, delay: 0.25 }}>
          <div className="simulation-feedback" aria-live="polite" aria-atomic="true">
            {!meta && !metaError && <span><LoaderCircle size={15} className="spinner" /> Connecting to the API…</span>}
            {metaError && <div role="alert"><span>{metaError}</span><button type="button" onClick={() => setMetaAttempt((current) => current + 1)}>Retry connection</button></div>}
            {isLoading && <span><LoaderCircle size={15} className="spinner" /> Calculating ocean paths…</span>}
            {error && <div role="alert"><span>{error.message}</span>{rejectedPlacement && <button type="button" onClick={() => removeItem(rejectedPlacement.id)}>Remove rejected {rejectedPlacement.type}</button>}{!rejectedPlacement && <button type="button" onClick={() => void togglePlayback()}>Retry</button>}</div>}
            {run && !error && !isLoading && <span>{dataLabel}{status === "dirty" ? " · Changes need recalculation" : ""}</span>}
          </div>
          <div className="status-row" aria-label="Simulation results">
            {(Object.keys(statusLabels) as ParticleStatus[]).map((status) => (
              <motion.div className={`status-chip status-chip--${status}`} key={status} layout>
                <motion.span key={counts[status]} initial={{ scale: 1.35 }} animate={{ scale: 1 }}>{counts[status]}</motion.span>{statusLabels[status]}
              </motion.div>
            ))}
          </div>

          <div className="playback-card">
            <motion.button
              className="play-button"
              type="button"
              aria-label={isLoading ? "Calculating simulation" : isPlaying ? "Pause simulation" : "Calculate or play simulation"}
              disabled={isLoading || !meta || !hasLitter}
              onClick={() => void togglePlayback()}
              whileHover={{ scale: 1.06 }}
              whileTap={{ scale: 0.92 }}
              animate={isPlaying ? { scale: [1, 1.04, 1] } : { scale: 1 }}
              transition={isPlaying ? { duration: 1.4, repeat: Infinity } : { duration: 0.2 }}
            >
              {isLoading ? <LoaderCircle size={22} className="spinner" /> : isPlaying ? <Pause size={22} fill="currentColor" /> : <Play size={22} fill="currentColor" />}
            </motion.button>
            <motion.button className="reset-button" type="button" onClick={resetExperiment} aria-label="Restart experiment" whileHover={{ rotate: -45 }} whileTap={{ scale: 0.9 }}><RotateCcw size={19} /></motion.button>
            <div className="timeline">
              <label htmlFor="timeline-range"><span>Journey time</span><strong>{formatTime(timeSeconds)}</strong></label>
              <input
                id="timeline-range"
                type="range"
                min="0"
                max={totalSeconds}
                step="1"
                disabled={isLoading || !hasLitter}
                value={timeSeconds}
                aria-valuetext={formatTime(timeSeconds)}
                style={{ "--progress": `${(timeSeconds / totalSeconds) * 100}%` } as React.CSSProperties}
                onChange={(event) => {
                  setIsPlaying(false);
                  setTimeSeconds(Number(event.target.value));
                }}
              />
            </div>
          </div>
        </motion.section>

        <motion.button ref={sourcesButtonRef} className="source-button" type="button" onClick={() => setShowSources(true)} whileHover={{ y: -3 }} whileTap={{ scale: 0.96 }}><Info size={15} /> Data & assumptions</motion.button>
      </div>
      <dialog ref={sourcesRef} className="sources-dialog" aria-labelledby="sources-title" onClose={() => {
        setShowSources(false);
        sourcesButtonRef.current?.focus();
      }}>
        <h2 id="sources-title">Data & assumptions</h2>
        {run ? <>
          <p><strong>{dataLabel}</strong></p>
          {status === "dirty" && <p>These details describe the last calculated run. Press Play to update your changes.</p>}
          <p>{run.attribution.source}</p>
          <p>Dataset: {run.attribution.dataset}</p>
          <ul>{run.snapshots.map((snapshot) => <li key={snapshot.snapshotId}>{snapshot.source}: {new Date(snapshot.sliceTime).toLocaleString()}</li>)}</ul>
          <p>{run.persisted ? "Run saved to the database." : "Run stored temporarily in backend memory."}</p>
          <h3>Final results</h3>
          <p>{run.summary.floating} floating · {run.summary.captured} captured · {run.summary.beached} beached · {run.summary.outside} outside</p>
        </> : <p>Place litter and press Play to calculate a run. Its actual data sources will appear here.</p>}
        <p>This is a simplified educational simulation, not a validated real-world prediction.</p>
        <ul>{(run?.attribution.limitations ?? meta?.attribution.limitations ?? []).map((limitation) => <li key={limitation}>{limitation}</li>)}</ul>
        <form method="dialog"><button type="submit" className="dialog-close">Close</button></form>
      </dialog>
    </main>
  );
}

export default App;
