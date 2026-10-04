import { useEffect, useRef, useState } from "react";
import booleanPointInPolygon from "@turf/boolean-point-in-polygon";
import circle from "@turf/circle";
import { featureCollection, point } from "@turf/helpers";
import mapboxgl, { type GeoJSONSource, type MapMouseEvent } from "mapbox-gl";
import { AlertCircle, KeyRound } from "lucide-react";
import { registerMapSprites } from "./mapSprites";
import {
  currentGeoJson,
  particleGeoJson,
  PLAYABLE_WATER,
  REGION_BOUNDS,
  trailGeoJson,
} from "./simulation";
import type { ParticleFrame, ParticleTrajectory, Placement, Tool } from "./types";

interface OceanMapProps {
  tool: Tool;
  placements: Placement[];
  frames: ParticleFrame[];
  trajectories: ParticleTrajectory[];
  timeSeconds: number;
  onPlace: (coordinates: [number, number]) => void;
  onRemove: (id: string) => void;
  onInvalidPlacement: () => void;
}

const token = import.meta.env.VITE_MAPBOX_ACCESS_TOKEN;
const styleUrl = import.meta.env.VITE_MAPBOX_STYLE_URL || "mapbox://styles/mapbox/light-v11";

function collectorsGeoJson(placements: Placement[]) {
  return featureCollection(
    placements
      .filter((item) => item.type === "collector")
      .map((item) => point(item.coordinates, { id: item.id, type: item.type })),
  );
}

function collectionAreasGeoJson(placements: Placement[]) {
  return featureCollection(
    placements
      .filter((item) => item.type === "collector")
      .map((item) => circle(item.coordinates, 7, { units: "kilometers", steps: 48 })),
  );
}

function addSimulationLayers(map: mapboxgl.Map, placements: Placement[], frames: ParticleFrame[], trajectories: ParticleTrajectory[], timeSeconds: number) {
  registerMapSprites(map);

  const sources: Array<[string, GeoJSON.GeoJSON]> = [
    ["playable-water", PLAYABLE_WATER],
    ["current-arrows", currentGeoJson(timeSeconds)],
    ["trails", trailGeoJson(trajectories, timeSeconds)],
    ["particles", particleGeoJson(frames)],
    ["collectors", collectorsGeoJson(placements)],
    ["collection-areas", collectionAreasGeoJson(placements)],
  ];

  sources.forEach(([id, data]) => {
    if (!map.getSource(id)) map.addSource(id, { type: "geojson", data });
  });

  if (!map.getLayer("playable-water-fill")) {
    map.addLayer({
      id: "playable-water-fill",
      type: "fill",
      source: "playable-water",
      paint: { "fill-color": "#35c7d0", "fill-opacity": 0.08 },
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
  if (!map.getLayer("current-arrows-layer")) {
    map.addLayer({
      id: "current-arrows-layer",
      type: "symbol",
      source: "current-arrows",
      layout: {
        "icon-image": "current-arrow",
        "icon-size": 0.34,
        "icon-rotate": ["get", "bearing"],
        "icon-allow-overlap": true,
        "icon-ignore-placement": true,
      },
      paint: { "icon-opacity": 0.64 },
    });
  }
  if (!map.getLayer("trail-halo")) {
    map.addLayer({
      id: "trail-halo",
      type: "line",
      source: "trails",
      layout: { "line-cap": "round", "line-join": "round" },
      paint: { "line-color": "#ffffff", "line-width": 8, "line-opacity": 0.72 },
    });
    map.addLayer({
      id: "trail-line",
      type: "line",
      source: "trails",
      layout: { "line-cap": "round", "line-join": "round" },
      paint: {
        "line-color": ["match", ["get", "type"], "bottle", "#18a77b", "bag", "#ef668a", "#e6a92f"],
        "line-width": 4,
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
  onPlace,
  onRemove,
  onInvalidPlacement,
}: OceanMapProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<mapboxgl.Map | null>(null);
  const [mapError, setMapError] = useState(false);
  const toolRef = useRef(tool);
  const onPlaceRef = useRef(onPlace);
  const onRemoveRef = useRef(onRemove);
  const onInvalidPlacementRef = useRef(onInvalidPlacement);
  const mapDataRef = useRef({ placements, frames, trajectories, timeSeconds });

  mapDataRef.current = { placements, frames, trajectories, timeSeconds };

  useEffect(() => {
    toolRef.current = tool;
    onPlaceRef.current = onPlace;
    onRemoveRef.current = onRemove;
    onInvalidPlacementRef.current = onInvalidPlacement;
    if (mapRef.current) {
      mapRef.current.getCanvas().style.cursor = tool === "explore" ? "grab" : "crosshair";
    }
  }, [tool, onPlace, onRemove, onInvalidPlacement]);

  useEffect(() => {
    if (!token || !containerRef.current) return;

    mapboxgl.accessToken = token;
    const map = new mapboxgl.Map({
      container: containerRef.current,
      style: styleUrl,
      bounds: REGION_BOUNDS,
      fitBoundsOptions: { padding: { top: 100, right: 90, bottom: 150, left: 300 } },
      minZoom: 8,
      maxZoom: 12.5,
      maxBounds: [[-124.25, 48.72], [-122.55, 49.92]],
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
      addSimulationLayers(map, data.placements, data.frames, data.trajectories, data.timeSeconds);
    };
    const handleClick = (event: MapMouseEvent) => {
      const activeTool = toolRef.current;
      if (activeTool === "explore") return;

      if (activeTool === "remove") {
        const features = map.queryRenderedFeatures(event.point, { layers: ["particles-layer", "collectors-layer"] });
        const id = features[0]?.properties?.id;
        if (typeof id === "string") onRemoveRef.current(id);
        return;
      }

      const coordinates: [number, number] = [event.lngLat.lng, event.lngLat.lat];
      if (!booleanPointInPolygon(point(coordinates), PLAYABLE_WATER)) {
        onInvalidPlacementRef.current();
        return;
      }
      onPlaceRef.current(coordinates);
    };

    map.on("error", handleMapError);
    map.on("style.load", handleStyleLoad);
    map.on("click", handleClick);

    return () => {
      map.remove();
      mapRef.current = null;
    };
  }, []);

  useEffect(() => {
    const map = mapRef.current;
    if (!map?.isStyleLoaded()) return;
    const updates: Array<[string, GeoJSON.GeoJSON]> = [
      ["current-arrows", currentGeoJson(timeSeconds)],
      ["trails", trailGeoJson(trajectories, timeSeconds)],
      ["particles", particleGeoJson(frames)],
      ["collectors", collectorsGeoJson(placements)],
      ["collection-areas", collectionAreasGeoJson(placements)],
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

  return <div ref={containerRef} className="map-container" aria-label="Interactive PlasticPaths ocean map" />;
}
