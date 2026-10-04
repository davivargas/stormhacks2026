import { useEffect, useRef, useState } from "react";
import circle from "@turf/circle";
import { featureCollection, point } from "@turf/helpers";
import mapboxgl, { type GeoJSONSource, type MapMouseEvent } from "mapbox-gl";
import { AlertCircle, KeyRound, X } from "lucide-react";
import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import { registerMapSprites } from "./mapSprites";
import {
  impactEventsBetween,
  particleGeoJson,
  trailGeoJson,
} from "./simulation";
import type { ImpactEvent } from "./simulation";
import type { ParticleFrame, ParticleTrajectory, Placement, Tool } from "./types";

interface OceanMapProps {
  tool: Tool;
  placements: Placement[];
  frames: ParticleFrame[];
  trajectories: ParticleTrajectory[];
  timeSeconds: number;
  selectedParticleId?: string | null;
  onPlace: (coordinates: [number, number]) => void;
  onRemove: (id: string) => void;
  onSelect?: (id: string) => void;
  onInvalidPlacement: () => void;
}

const token = import.meta.env.VITE_MAPBOX_ACCESS_TOKEN;
const styleUrl = import.meta.env.VITE_MAPBOX_STYLE_URL || "mapbox://styles/mapbox/light-v11";

function hideBasemapRoads(map: mapboxgl.Map) {
  const style = map.getStyle();
  const roadLayerPattern = /(?:road|motorway|highway|street)/i;

  style.layers
    .filter((layer) => roadLayerPattern.test(layer.id) || layer.type === "fill-extrusion")
    .forEach((layer) => map.setLayoutProperty(layer.id, "visibility", "none"));

  // Standard's internal layers are exposed through import configuration.
  style.imports?.forEach((styleImport) => {
    if (!/^mapbox:\/\/styles\/mapbox\/standard(?:-satellite)?$/.test(styleImport.url)) return;

    map.setConfigProperty(styleImport.id, "showRoadLabels", false);
    map.setConfigProperty(styleImport.id, "showPedestrianRoads", false);
    map.setConfigProperty(styleImport.id, "showHdRoads", false);
    map.setConfigProperty(styleImport.id, "show3dObjects", false);
    map.setConfigProperty(styleImport.id, "show3dBuildings", false);
    map.setConfigProperty(styleImport.id, "show3dTrees", false);
    map.setConfigProperty(styleImport.id, "show3dLandmarks", false);
    map.setConfigProperty(styleImport.id, "show3dFacades", false);
    map.setConfigProperty(styleImport.id, "colorMotorways", "rgba(0, 0, 0, 0)");
    map.setConfigProperty(styleImport.id, "colorTrunks", "rgba(0, 0, 0, 0)");
    map.setConfigProperty(styleImport.id, "colorRoads", "rgba(0, 0, 0, 0)");
    map.setConfigProperty(styleImport.id, "colorHdRoads", "rgba(0, 0, 0, 0)");
  });
}

function collectorsGeoJson(placements: Placement[], timeSeconds: number) {
  return featureCollection(
    placements
      .filter((item) => item.type === "collector" && item.placedAtSeconds <= timeSeconds)
      .map((item) => point(item.coordinates, { id: item.id, type: item.type })),
  );
}

function collectionAreasGeoJson(placements: Placement[], timeSeconds: number) {
  return featureCollection(
    placements
      .filter((item) => item.type === "collector" && item.placedAtSeconds <= timeSeconds)
      .map((item) => circle(item.coordinates, 7, { units: "kilometers", steps: 48 })),
  );
}

function addSimulationLayers(map: mapboxgl.Map, placements: Placement[], frames: ParticleFrame[], trajectories: ParticleTrajectory[], timeSeconds: number) {
  registerMapSprites(map);

  if (!map.getSource("placement-streets")) {
    map.addSource("placement-streets", {
      type: "vector",
      url: "mapbox://mapbox.mapbox-streets-v8",
    });
  }

  const sources: Array<[string, GeoJSON.GeoJSON]> = [
    ["trails", trailGeoJson(trajectories, timeSeconds)],
    ["particles", particleGeoJson(frames)],
    ["collectors", collectorsGeoJson(placements, timeSeconds)],
    ["collection-areas", collectionAreasGeoJson(placements, timeSeconds)],
  ];

  sources.forEach(([id, data]) => {
    if (!map.getSource(id)) map.addSource(id, { type: "geojson", data });
  });

  if (!map.getLayer("placement-water-hit-area")) {
    map.addLayer({
      id: "placement-water-hit-area",
      type: "fill",
      source: "placement-streets",
      "source-layer": "water",
      paint: {
        "fill-color": "#35c7d0",
        "fill-opacity": 0.001,
      },
    });
  }
  if (!map.getLayer("collection-area-fill")) {
    map.addLayer({
      id: "collection-area-fill",
      type: "fill",
      source: "collection-areas",
      paint: { "fill-color": "#ffd45a", "fill-opacity": 0.2 },
    });
    map.addLayer({
      id: "collection-area-outline",
      type: "line",
      source: "collection-areas",
      paint: { "line-color": "#e6a92f", "line-width": 2, "line-dasharray": [2, 2] },
    });
  }
  if (!map.getLayer("trail-halo")) {
    map.addLayer({
      id: "trail-halo",
      type: "line",
      source: "trails",
      slot: "top",
      layout: { "line-cap": "round", "line-join": "round" },
      paint: {
        "line-color": "#ffffff",
        "line-width": 9,
        "line-opacity": 0.32,
        "line-emissive-strength": 1,
      },
    });
  }
  if (!map.getLayer("trail-line")) {
    map.addLayer({
      id: "trail-line",
      type: "line",
      source: "trails",
      slot: "top",
      layout: { "line-cap": "round", "line-join": "round" },
      paint: {
        "line-color": "#ffffff",
        "line-width": 5,
        "line-opacity": 1,
        "line-emissive-strength": 1,
      },
    });
  }
  if (!map.getLayer("collectors-layer")) {
    map.addLayer({
      id: "collectors-layer",
      type: "symbol",
      source: "collectors",
      layout: { "icon-image": "collector", "icon-size": 0.7, "icon-allow-overlap": true },
    });
  }
  if (!map.getLayer("particles-layer")) {
    map.addLayer({
      id: "particles-layer",
      type: "symbol",
      source: "particles",
      layout: {
        "icon-image": ["get", "type"],
        "icon-size": 0.62,
        "icon-allow-overlap": true,
        "icon-ignore-placement": true,
      },
      paint: {
        "icon-opacity": ["case", ["==", ["get", "status"], "captured"], 0.48, 1],
      },
    });
  }
}

export function OceanMap({
  tool,
  placements,
  frames,
  trajectories,
  timeSeconds,
  onSelect,
  onPlace,
  onRemove,
  onInvalidPlacement,
}: OceanMapProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<mapboxgl.Map | null>(null);
  const [mapError, setMapError] = useState(false);
  const [impacts, setImpacts] = useState<ImpactEvent[]>([]);
  const [, setViewportVersion] = useState(0);
  const previousTimeRef = useRef(timeSeconds);
  const prefersReducedMotion = useReducedMotion();
  const toolRef = useRef(tool);
  const onPlaceRef = useRef(onPlace);
  const onRemoveRef = useRef(onRemove);
  const onSelectRef = useRef(onSelect);
  const onInvalidPlacementRef = useRef(onInvalidPlacement);
  const mapDataRef = useRef({ placements, frames, trajectories, timeSeconds });

  mapDataRef.current = { placements, frames, trajectories, timeSeconds };

  useEffect(() => {
    toolRef.current = tool;
    onPlaceRef.current = onPlace;
    onRemoveRef.current = onRemove;
    onSelectRef.current = onSelect;
    onInvalidPlacementRef.current = onInvalidPlacement;
    if (mapRef.current) {
      mapRef.current.getCanvas().style.cursor = tool === "explore" ? "grab" : "crosshair";
    }
  }, [tool, onPlace, onRemove, onSelect, onInvalidPlacement]);

  useEffect(() => {
    if (!token || !containerRef.current) return;

    mapboxgl.accessToken = token;
    const map = new mapboxgl.Map({
      container: containerRef.current,
      style: styleUrl,
      center: [0, 20],
      zoom: 1.3,
      pitch: 0,
      projection: "mercator",
      maxPitch: 0,
      maxZoom: 12.5,
      pitchWithRotate: false,
      dragRotate: false,
      touchPitch: false,
      attributionControl: false,
    });
    mapRef.current = map;
    map.addControl(new mapboxgl.NavigationControl({ showCompass: false }), "top-right");
    map.addControl(new mapboxgl.AttributionControl({ compact: true }), "bottom-right");

    const handleMapError = (event: mapboxgl.ErrorEvent) => {
      if (mapRef.current !== map) return;
      console.warn("Mapbox could not load the configured map:", event.error.message);
      map.remove();
      mapRef.current = null;
      setMapError(true);
    };
    const handleStyleLoad = () => {
      const data = mapDataRef.current;
      map.setProjection("mercator");
      map.setTerrain(null);
      hideBasemapRoads(map);
      addSimulationLayers(map, data.placements, data.frames, data.trajectories, data.timeSeconds);
    };
    const isValidOceanPoint = (event: MapMouseEvent) => {
      if (!map.getLayer("placement-water-hit-area")) return false;

      const onRenderedWater = map.queryRenderedFeatures(event.point, {
        layers: ["placement-water-hit-area"],
      }).length > 0;

      return onRenderedWater;
    };

    const handleClick = (event: MapMouseEvent) => {
      const activeTool = toolRef.current;
      if (activeTool === "explore" || activeTool === "narrate") {
        if (!map.getLayer("particles-layer")) return;
        const features = map.queryRenderedFeatures(event.point, { layers: ["particles-layer"] });
        const id = features[0]?.properties?.id;
        if (typeof id === "string") onSelectRef.current?.(id);
        return;
      }

      if (activeTool === "remove") {
        if (!map.getLayer("particles-layer") || !map.getLayer("collectors-layer")) return;
        const features = map.queryRenderedFeatures(event.point, { layers: ["particles-layer", "collectors-layer"] });
        const id = features[0]?.properties?.id;
        if (typeof id === "string") onRemoveRef.current(id);
        return;
      }

      if (!isValidOceanPoint(event)) {
        onInvalidPlacementRef.current();
        return;
      }
      const coordinates: [number, number] = [event.lngLat.wrap().lng, event.lngLat.lat];
      onPlaceRef.current(coordinates);
    };

    const handleMouseMove = (event: MapMouseEvent) => {
      const activeTool = toolRef.current;
      if (activeTool === "explore") {
        map.getCanvas().style.cursor = "grab";
      } else if (activeTool === "narrate") {
        const hasLitter = Boolean(map.getLayer("particles-layer"))
          && map.queryRenderedFeatures(event.point, { layers: ["particles-layer"] }).length > 0;
        map.getCanvas().style.cursor = hasLitter ? "pointer" : "not-allowed";
      } else if (activeTool === "remove") {
        if (!map.getLayer("particles-layer") || !map.getLayer("collectors-layer")) {
          map.getCanvas().style.cursor = "not-allowed";
          return;
        }
        const hasRemovableItem = map.queryRenderedFeatures(event.point, {
          layers: ["particles-layer", "collectors-layer"],
        }).length > 0;
        map.getCanvas().style.cursor = hasRemovableItem ? "pointer" : "not-allowed";
      } else {
        map.getCanvas().style.cursor = isValidOceanPoint(event) ? "crosshair" : "not-allowed";
      }
    };

    map.on("error", handleMapError);
    map.on("style.load", handleStyleLoad);
    map.on("click", handleClick);
    map.on("mousemove", handleMouseMove);
    map.on("move", () => setViewportVersion((version) => version + 1));

    return () => {
      if (mapRef.current === map) {
        map.remove();
        mapRef.current = null;
      }
    };
  }, []);

  useEffect(() => {
    const previousTime = previousTimeRef.current;
    const nextImpacts = impactEventsBetween(trajectories, previousTime, timeSeconds);
    previousTimeRef.current = timeSeconds;
    if (timeSeconds < previousTime) {
      setImpacts([]);
      return;
    }
    if (nextImpacts.length) {
      setImpacts((current) => [...current, ...nextImpacts]);
    }
  }, [timeSeconds, trajectories]);

  useEffect(() => {
    const map = mapRef.current;
    // Tile loading can make isStyleLoaded() false even when these sources
    // already exist. Do not lose playback updates while panning or zooming.
    if (!map) return;
    const updates: Array<[string, GeoJSON.GeoJSON]> = [
      ["trails", trailGeoJson(trajectories, timeSeconds)],
      ["particles", particleGeoJson(frames)],
      ["collectors", collectorsGeoJson(placements, timeSeconds)],
      ["collection-areas", collectionAreasGeoJson(placements, timeSeconds)],
    ];
    updates.forEach(([id, data]) => (map.getSource(id) as GeoJSONSource | undefined)?.setData(data));
  }, [frames, placements, timeSeconds, trajectories]);

  if (!token || mapError) {
    return (
      <div className="map-fallback" aria-label="Decorative ocean map preview">
        <div className="fallback-island fallback-island--one" />
        <div className="fallback-island fallback-island--two" />
        <div className="fallback-island fallback-island--three" />
        <div className="credential-card" role="status">
          <div className="credential-icon"><KeyRound size={22} /></div>
          <div>
            <strong>{mapError ? "Mapbox preview unavailable" : "Connect your Mapbox map"}</strong>
            <span>
              {mapError
                ? "The Mapbox token was rejected, so you are viewing the built-in ocean preview."
                : <>Add a public token to <code>.env.local</code> to load the interactive Studio style.</>}
            </span>
          </div>
        </div>
        <div className="fallback-note"><AlertCircle size={16} /> Preview mode</div>
      </div>
    );
  }

  return (
    <>
      <div ref={containerRef} className="map-container" aria-label="Interactive LitterVoyage ocean map" />
      <div className="impact-overlay" aria-live="polite">
        <AnimatePresence>
          {impacts.map((impact) => {
            const pixel = mapRef.current?.project(impact.coordinates);
            if (!pixel) return null;
            const key = `${impact.id}-${impact.timeSeconds}-${impact.type}`;
            return (
              <div
                className="impact-position"
                key={key}
                style={{ left: pixel.x, top: pixel.y }}
              >
                <motion.div
                  className={`impact-x impact-x--${impact.type}`}
                  role="status"
                  aria-label={`${impact.type === "beached" ? "Land impact" : "Collector impact"} for ${impact.id}`}
                  initial={{ opacity: 0, scale: prefersReducedMotion ? 1 : 0.25, y: 10 }}
                  animate={prefersReducedMotion
                    ? { opacity: [0, 1, 1, 0] }
                    : {
                        opacity: [0, 1, 1, 1, 0],
                        scale: [0.25, 1.32, 0.92, 1, 1],
                        y: [10, -10, -14, -18, -28],
                        rotate: [-18, 12, -6, 0, 0],
                      }}
                  transition={{ duration: prefersReducedMotion ? 0.6 : 1.25, times: prefersReducedMotion ? [0, 0.2, 0.75, 1] : [0, 0.18, 0.38, 0.72, 1], ease: "easeOut" }}
                  onAnimationComplete={() => setImpacts((current) => current.filter((item) => `${item.id}-${item.timeSeconds}-${item.type}` !== key))}
                >
                  <X aria-hidden="true" strokeWidth={4.5} />
                </motion.div>
              </div>
            );
          })}
        </AnimatePresence>
      </div>
    </>
  );
}
