import { useEffect, useMemo, useRef, useState } from "react";
import { AnimatePresence, motion } from "motion/react";
import {
  Anchor,
  Backpack,
  CupSoda,
  ChevronRight,
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
import {
  buildTrajectories,
  DURATION_SECONDS,
  INITIAL_PLACEMENTS,
  interpolateFrame,
} from "./simulation";
import type { ComparisonMode, Coordinates, ParticleStatus, Placement, Tool } from "./types";

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
  return `${hours}h ${minutes.toString().padStart(2, "0")}m`;
}

function App() {
  const [placements, setPlacements] = useState<Placement[]>(INITIAL_PLACEMENTS);
  const [tool, setTool] = useState<Tool>("explore");
  const [comparison, setComparison] = useState<ComparisonMode>("with");
  const [timeSeconds, setTimeSeconds] = useState(6 * 3600);
  const [isPlaying, setIsPlaying] = useState(false);
  const [message, setMessage] = useState("Place some litter, then press play!");
  const lastFrameRef = useRef<number | null>(null);

  const trajectories = useMemo(
    () => buildTrajectories(placements, comparison),
    [placements, comparison],
  );
  const frames = useMemo(
    () => interpolateFrame(trajectories, timeSeconds),
    [trajectories, timeSeconds],
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
      setTimeSeconds((current) => {
        const next = current + elapsed * 12;
        if (next >= DURATION_SECONDS) {
          setIsPlaying(false);
          return DURATION_SECONDS;
        }
        return next;
      });
      requestId = requestAnimationFrame(animate);
    };
    requestId = requestAnimationFrame(animate);
    return () => cancelAnimationFrame(requestId);
  }, [isPlaying]);

  const placeItem = (coordinates: Coordinates) => {
    if (tool === "explore" || tool === "remove") return;
    const item: Placement = { id: `${tool}-${crypto.randomUUID()}`, type: tool, coordinates };
    setPlacements((current) => [...current, item]);
    setMessage(tool === "collector" ? "Great cleanup spot! Try the comparison." : "Splash! Your litter is ready to travel.");
  };

  const removeItem = (id: string) => {
    setPlacements((current) => current.filter((item) => item.id !== id));
    setMessage("Item removed. Keep experimenting!");
  };

  const resetExperiment = () => {
    setTimeSeconds(0);
    setIsPlaying(false);
    setPlacements(INITIAL_PLACEMENTS);
    setMessage("Fresh start! What will happen this time?");
  };

  return (
    <main className="ocean-page">
      <OceanMap
        tool={tool}
        placements={placements}
        frames={frames}
        trajectories={trajectories}
        timeSeconds={timeSeconds}
        onPlace={placeItem}
        onRemove={removeItem}
        onInvalidPlacement={() => setMessage("Try a spot inside the sparkling water zone.")}
      />

      <div className="map-overlay">
        <motion.header className="topbar" initial={{ opacity: 0, y: -24 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.55 }}>
          <motion.a className="brand" href="#top" aria-label="PlasticPaths home" whileHover={{ y: -2 }}>
            <span className="brand-mark"><Waves size={27} /></span>
            <span>Plastic<span>Paths</span></span>
          </motion.a>
          <nav className="journey" aria-label="Experiment progress">
            <motion.span className="journey-step journey-step--done" initial={{ scale: 0 }} animate={{ scale: 1 }} transition={{ delay: 0.2, type: "spring" }}>1</motion.span>
            <span>Place</span><ChevronRight size={16} />
            <motion.span className="journey-step" initial={{ scale: 0 }} animate={{ scale: 1 }} transition={{ delay: 0.3, type: "spring" }}>2</motion.span>
            <span>Predict</span><ChevronRight size={16} />
            <motion.span className="journey-step" initial={{ scale: 0 }} animate={{ scale: 1 }} transition={{ delay: 0.4, type: "spring" }}>3</motion.span>
            <span>Explore</span>
          </nav>
          <motion.button className="icon-button" type="button" aria-label="Open help" whileHover={{ scale: 1.06 }} whileTap={{ scale: 0.94 }}><CircleHelp size={22} /></motion.button>
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
          <div className="current-key"><span>↗</span><p><strong>Ocean current</strong>Arrows show water direction</p></div>
        </motion.aside>

        <motion.section className="guide-bubble" aria-live="polite" initial={{ opacity: 0, y: 22 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.5, delay: 0.35 }}>
          <motion.div className="mascot" aria-hidden="true" animate={{ y: [0, -4, 0] }} transition={{ duration: 3, repeat: Infinity, ease: "easeInOut" }}><span>•</span><span>•</span><b>⌣</b></motion.div>
          <div><span className="eyebrow">Finn says</span><AnimatePresence mode="wait"><motion.p key={message} initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -6 }} transition={{ duration: 0.2 }}>{message}</motion.p></AnimatePresence></div>
        </motion.section>

        <motion.section className="bottom-dock" aria-label="Simulation controls" initial={{ opacity: 0, y: 32 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.6, delay: 0.25 }}>
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
              aria-label={isPlaying ? "Pause simulation" : "Play simulation"}
              onClick={() => {
                if (timeSeconds >= DURATION_SECONDS) setTimeSeconds(0);
                setIsPlaying((current) => !current);
              }}
              whileHover={{ scale: 1.06 }}
              whileTap={{ scale: 0.92 }}
              animate={isPlaying ? { scale: [1, 1.04, 1] } : { scale: 1 }}
              transition={isPlaying ? { duration: 1.4, repeat: Infinity } : { duration: 0.2 }}
            >
              {isPlaying ? <Pause size={22} fill="currentColor" /> : <Play size={22} fill="currentColor" />}
            </motion.button>
            <motion.button className="reset-button" type="button" onClick={resetExperiment} aria-label="Restart experiment" whileHover={{ rotate: -45 }} whileTap={{ scale: 0.9 }}><RotateCcw size={19} /></motion.button>
            <div className="timeline">
              <label htmlFor="timeline-range"><span>Journey time</span><strong>{formatTime(timeSeconds)}</strong></label>
              <input
                id="timeline-range"
                type="range"
                min="0"
                max={DURATION_SECONDS}
                step="300"
                value={timeSeconds}
                aria-valuetext={formatTime(timeSeconds)}
                style={{ "--progress": `${(timeSeconds / DURATION_SECONDS) * 100}%` } as React.CSSProperties}
                onChange={(event) => {
                  setIsPlaying(false);
                  setTimeSeconds(Number(event.target.value));
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
