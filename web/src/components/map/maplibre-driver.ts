import * as maplibregl from "maplibre-gl";
import type { ErrorEvent, StyleSpecification } from "maplibre-gl";
import { Protocol } from "pmtiles";

import type { MapDriver } from "./MapPin";


let protocolRegistered = false;


function ensurePmtilesProtocol() {
  if (protocolRegistered) return;
  const protocol = new Protocol();
  maplibregl.addProtocol("pmtiles", protocol.tile);
  protocolRegistered = true;
}


function mapStyle(tilesUrl: string): StyleSpecification {
  return {
    version: 8,
    sources: {
      protomaps: {
        type: "vector",
        url: `pmtiles://${tilesUrl}`,
      },
    },
    layers: [
      {
        id: "background",
        type: "background",
        paint: { "background-color": "#edf3ee" },
      },
      {
        id: "earth",
        type: "fill",
        source: "protomaps",
        "source-layer": "earth",
        paint: { "fill-color": "#f7f3e8" },
      },
      {
        id: "water",
        type: "fill",
        source: "protomaps",
        "source-layer": "water",
        paint: { "fill-color": "#acd8e8" },
      },
      {
        id: "roads",
        type: "line",
        source: "protomaps",
        "source-layer": "roads",
        paint: {
          "line-color": "#ffffff",
          "line-width": ["interpolate", ["linear"], ["zoom"], 8, 0.5, 16, 4],
        },
      },
      {
        id: "buildings",
        type: "fill",
        source: "protomaps",
        "source-layer": "buildings",
        minzoom: 13,
        paint: {
          "fill-color": "#d9d5ca",
          "fill-outline-color": "#c4bfb3",
        },
      },
    ],
  };
}


export const mapLibreDriver: MapDriver = {
  mount({
    container,
    initialPoint,
    onError,
    onPointChange,
    onReady,
    tilesUrl,
  }) {
    ensurePmtilesProtocol();
    const map = new maplibregl.Map({
      attributionControl: false,
      center: [initialPoint.longitude, initialPoint.latitude],
      container,
      style: mapStyle(tilesUrl),
      zoom: 16,
    });
    const marker = new maplibregl.Marker({
      color: "#176b46",
      draggable: true,
    })
      .setLngLat([initialPoint.longitude, initialPoint.latitude])
      .addTo(map);

    marker.on("dragend", () => {
      const point = marker.getLngLat();
      onPointChange({ latitude: point.lat, longitude: point.lng });
    });
    map.once("load", onReady);
    map.on("error", (event: ErrorEvent) => {
      onError(event.error?.message ?? "Check the PMTiles URL and R2 CORS policy.");
    });

    return () => {
      marker.remove();
      map.remove();
    };
  },
};
