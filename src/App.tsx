import { useEffect, useMemo, useRef, useState } from "react";
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
        <header className="topbar">
          <a className="brand" href="#top" aria-label="PlasticPaths home">
            <span className="brand-mark"><Waves size={27} /></span>
            <span>Plastic<span>Paths</span></span>
          </a>
          <nav className="journey" aria-label="Experiment progress">
            <span className="journey-step journey-step--done">1</span>
            <span>Place</span><ChevronRight size={16} />
            <span className="journey-step">2</span>
            <span>Predict</span><ChevronRight size={16} />
            <span className="journey-step">3</span>
            <span>Explore</span>
          </nav>
          <button className="icon-button" type="button" aria-label="Open help"><CircleHelp size={22} /></button>
        </header>

        <aside className="tool-panel" aria-label="Map tools">
          <div className="panel-heading">
            <span className="eyebrow">Choose a tool</span>
            <h1>Make a splash</h1>
          </div>
          <div className="tool-grid">
            {tools.map(({ id, label, detail, icon: Icon }) => (
              <button
                className={`tool-button ${tool === id ? "tool-button--active" : ""}`}
                key={id}
                type="button"
                aria-pressed={tool === id}
                onClick={() => setTool(tool === id ? "explore" : id)}
              >
                <span className={`tool-icon tool-icon--${id}`}><Icon size={24} /></span>
                <span><strong>{label}</strong><small>{detail}</small></span>
              </button>
            ))}
          </div>
          <div className="current-key"><span>↗</span><p><strong>Ocean current</strong>Arrows show water direction</p></div>
        </aside>

        <section className="guide-bubble" aria-live="polite">
          <div className="mascot" aria-hidden="true"><span>•</span><span>•</span><b>⌣</b></div>
          <div><span className="eyebrow">Finn says</span><p>{message}</p></div>
        </section>

        <section className="bottom-dock" aria-label="Simulation controls">
          <div className="status-row" aria-label="Simulation results">
            {(Object.keys(statusLabels) as ParticleStatus[]).map((status) => (
              <div className={`status-chip status-chip--${status}`} key={status}>
                <span>{counts[status]}</span>{statusLabels[status]}
              </div>
            ))}
          </div>

          <div className="playback-card">
            <button
              className="play-button"
              type="button"
              aria-label={isPlaying ? "Pause simulation" : "Play simulation"}
              onClick={() => {
                if (timeSeconds >= DURATION_SECONDS) setTimeSeconds(0);
                setIsPlaying((current) => !current);
              }}
            >
              {isPlaying ? <Pause size={22} fill="currentColor" /> : <Play size={22} fill="currentColor" />}
            </button>
            <button className="reset-button" type="button" onClick={resetExperiment} aria-label="Restart experiment"><RotateCcw size={19} /></button>
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
              <button className={comparison === "without" ? "active" : ""} type="button" onClick={() => setComparison("without")}>Without</button>
              <button className={comparison === "with" ? "active" : ""} type="button" onClick={() => setComparison("with")}>With cleanup</button>
            </div>
          </div>
        </section>

        <button className="source-button" type="button"><Info size={15} /> Data & assumptions</button>
      </div>
    </main>
  );
}

export default App;
