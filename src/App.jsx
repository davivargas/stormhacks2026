import React, { useState } from "react";
import { motion } from "motion/react";
import {
  ArrowRight,
  CalendarDays,
  ChevronRight,
  Headphones,
  Leaf,
  MapPin,
  Play,
  Waves,
} from "lucide-react";

const litterTypes = [
  { label: "Plastic bottle", emoji: "🧴", color: "#ffb35c" },
  { label: "Food wrapper", emoji: "🍬", color: "#ff7b73" },
  { label: "Fishing line", emoji: "🪢", color: "#87c9f5" },
];

function App() {
  const [selectedLitter, setSelectedLitter] = useState(litterTypes[0].label);
  const [journeyDay, setJourneyDay] = useState(32);

  return (
    <main className="app-shell">
      <nav className="topbar">
        <a className="brand" href="/" aria-label="Ocean Scouts home">
          <span className="brand-mark">✦</span>
          <span>Ocean Scouts</span>
        </a>
        <div className="nav-links">
          <a className="active" href="#explore">Explore</a>
          <a href="#learn">Learn</a>
          <a href="#about">About</a>
        </div>
        <button className="audio-button" type="button" aria-label="Play audio narration">
          <Headphones size={17} />
          <span>Listen</span>
        </button>
      </nav>

      <section className="hero" id="explore">
        <div className="hero-copy">
          <motion.div
            className="eyebrow"
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5 }}
          >
            <Waves size={16} /> Become an ocean scientist
          </motion.div>
          <motion.h1
            initial={{ opacity: 0, y: 18 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.6, delay: 0.1 }}
          >
            Follow the journey
            <br />
            of <em>ocean litter.</em>
          </motion.h1>
          <p className="hero-intro">
            Pick up a piece of litter and see how currents can carry it across
            our beautiful blue planet.
          </p>
          <a className="primary-button" href="#map">
            Start exploring <ArrowRight size={18} />
          </a>
        </div>

        <motion.div
          className="hero-orbit"
          initial={{ opacity: 0, scale: 0.8 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ duration: 0.8, delay: 0.2 }}
        >
          <div className="orbit orbit-one" />
          <div className="orbit orbit-two" />
          <div className="planet">
            <div className="planet-shine" />
            <span className="planet-land land-one" />
            <span className="planet-land land-two" />
            <span className="planet-land land-three" />
          </div>
          <span className="floating-dot dot-one" />
          <span className="floating-dot dot-two" />
          <span className="floating-dot dot-three" />
        </motion.div>
      </section>

      <section className="workspace" id="map">
        <div className="section-heading">
          <div>
            <p className="section-kicker">Your field notebook</p>
            <h2>Where should we look?</h2>
          </div>
          <div className="location-pill"><MapPin size={16} /> Pacific Ocean</div>
        </div>

        <div className="explorer-grid">
          <motion.div
            className="map-card"
            initial={{ opacity: 0, y: 24 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true, amount: 0.2 }}
            transition={{ duration: 0.5 }}
          >
            <div className="map-toolbar">
              <span className="map-status"><span className="status-dot" /> Live current map</span>
              <button className="icon-button" type="button" aria-label="Play map animation"><Play size={16} fill="currentColor" /></button>
            </div>
            <div className="map-surface">
              <span className="map-grid-lines" />
              <span className="current current-one" />
              <span className="current current-two" />
              <span className="current current-three" />
              <div className="map-pin pin-one"><span>1</span></div>
              <div className="map-pin pin-two"><span>2</span></div>
              <div className="map-pin pin-three"><span>3</span></div>
              <div className="map-label label-one">Hawaiian Islands</div>
              <div className="map-label label-two">North Pacific</div>
              <div className="map-compass">N</div>
            </div>
            <div className="map-footer">
              <span><strong>2,840 km</strong> traveled so far</span>
              <span>Day {journeyDay} of 120</span>
            </div>
          </motion.div>

          <aside className="side-panel">
            <motion.div
              className="panel-card litter-card"
              initial={{ opacity: 0, x: 24 }}
              whileInView={{ opacity: 1, x: 0 }}
              viewport={{ once: true, amount: 0.2 }}
              transition={{ duration: 0.5, delay: 0.1 }}
            >
              <div className="card-title-row">
                <div><p className="section-kicker">Step 01</p><h3>Choose your litter</h3></div>
                <span className="step-number">1/3</span>
              </div>
              <div className="litter-list">
                {litterTypes.map((item) => (
                  <motion.button
                    className={`litter-option ${selectedLitter === item.label ? "selected" : ""}`}
                    key={item.label}
                    type="button"
                    onClick={() => setSelectedLitter(item.label)}
                    whileHover={{ x: 4 }}
                    whileTap={{ scale: 0.98 }}
                  >
                    <span className="litter-icon" style={{ backgroundColor: item.color }}>{item.emoji}</span>
                    <span>{item.label}</span>
                    <ChevronRight size={16} />
                    {selectedLitter === item.label && (
                      <motion.span
                        className="selection-indicator"
                        layoutId="selected-litter"
                        transition={{ type: "spring", stiffness: 500, damping: 30 }}
                      />
                    )}
                  </motion.button>
                ))}
              </div>
            </motion.div>
            <motion.div
              className="panel-card timeline-card"
              initial={{ opacity: 0, x: 24 }}
              whileInView={{ opacity: 1, x: 0 }}
              viewport={{ once: true, amount: 0.2 }}
              transition={{ duration: 0.5, delay: 0.2 }}
            >
              <div className="card-title-row">
                <div><p className="section-kicker">Step 02</p><h3>Travel through time</h3></div>
                <CalendarDays size={19} />
              </div>
              <input className="timeline" type="range" min="1" max="120" value={journeyDay} onChange={(event) => setJourneyDay(Number(event.target.value))} aria-label="Journey day" />
              <div className="timeline-labels"><span>Day 1</span><strong>Day {journeyDay}</strong><span>Day 120</span></div>
            </motion.div>
          </aside>
        </div>
      </section>

      <section className="learn-section" id="learn">
        <motion.div
          className="mascot-card"
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true, amount: 0.3 }}
        >
          <div className="mascot">🐢</div>
          <div><p className="section-kicker">Meet Shelly</p><h3>“Small choices make big waves!”</h3><p>Want to know why this current moves west?</p></div>
          <button className="round-button" type="button" aria-label="Play Shelly's explanation"><Play size={16} fill="currentColor" /></button>
        </motion.div>
        <motion.div
          className="fact-card"
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true, amount: 0.3 }}
          transition={{ delay: 0.12 }}
        >
          <p className="section-kicker">Did you know?</p>
          <h3>Ocean currents act like giant conveyor belts.</h3>
          <p>They move heat, nutrients, and even litter around the globe.</p>
          <a href="#about">Discover more <ArrowRight size={16} /></a>
        </motion.div>
      </section>
    </main>
  );
}

export default App;
