import { useEffect, useRef, useState } from "react";
import circle from "@turf/circle";
import { featureCollection, point } from "@turf/helpers";
import mapboxgl, { type GeoJSONSource, type MapMouseEvent } from "mapbox-gl";
import { AlertCircle, KeyRound } from "lucide-react";
import { registerMapSprites } from "./mapSprites";
import {
  particleGeoJson,
  trailGeoJson,
} from "./simulation";
import type { ParticleFrame, ParticleTrajectory, Placement, SimulationResponse, Tool } from "./types";

interface OceanMapProps {
  tool: Tool;
  placements: Placement[];
  frames: ParticleFrame[];
  trajectories: ParticleTrajectory[];
  timeSeconds: number;
  collectorRadiusM: number;
  collectors?: SimulationResponse["collectors"];
  onPlace: (coordinates: [number, number]) => void;
  onRemove: (id: string) => void;
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

function collectionAreasGeoJson(placements: Placement[], timeSeconds: number, collectorRadiusM: number, collectors?: SimulationResponse["collectors"]) {
  return featureCollection(
    placements
      .filter((item) => item.type === "collector" && item.placedAtSeconds <= timeSeconds)
      .map((item) => circle(item.coordinates, collectors?.find((collector) => collector.id === item.id)?.radiusM ?? collectorRadiusM, { units: "meters", steps: 48 })),
  );
}

function addSimulationLayers(map: mapboxgl.Map, placements: Placement[], frames: ParticleFrame[], trajectories: ParticleTrajectory[], timeSeconds: number, collectorRadiusM: number, collectors?: SimulationResponse["collectors"]) {
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
    ["collection-areas", collectionAreasGeoJson(placements, timeSeconds, collectorRadiusM, collectors)],
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
  collectorRadiusM,
  collectors,
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
  const mapDataRef = useRef({ placements, frames, trajectories, timeSeconds, collectorRadiusM, collectors });

  mapDataRef.current = { placements, frames, trajectories, timeSeconds, collectorRadiusM, collectors };

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
      addSimulationLayers(map, data.placements, data.frames, data.trajectories, data.timeSeconds, data.collectorRadiusM, data.collectors);
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
      if (activeTool === "explore") return;

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

    return () => {
      if (mapRef.current === map) {
        map.remove();
        mapRef.current = null;
      }
    };
  }, []);

  useEffect(() => {
    const map = mapRef.current;
    if (!map?.isStyleLoaded()) return;
    const updates: Array<[string, GeoJSON.GeoJSON]> = [
      ["trails", trailGeoJson(trajectories, timeSeconds)],
      ["particles", particleGeoJson(frames)],
      ["collectors", collectorsGeoJson(placements, timeSeconds)],
      ["collection-areas", collectionAreasGeoJson(placements, timeSeconds, collectorRadiusM, collectors)],
    ];
    updates.forEach(([id, data]) => (map.getSource(id) as GeoJSONSource | undefined)?.setData(data));
  }, [frames, placements, timeSeconds, trajectories, collectorRadiusM, collectors]);

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

  return <div ref={containerRef} className="map-container" aria-label="Interactive LitterVoyage ocean map" />;
}
