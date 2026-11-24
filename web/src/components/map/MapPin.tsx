"use client";

import { useEffect, useRef, useState } from "react";

import styles from "./map-pin.module.css";
import { mapLibreDriver } from "./maplibre-driver";


export type MapPoint = {
  latitude: number;
  longitude: number;
};

export type MapMountOptions = {
  container: HTMLDivElement;
  initialPoint: MapPoint;
  onError: (message: string) => void;
  onPointChange: (point: MapPoint) => void;
  onReady: () => void;
  tilesUrl: string;
};

export type MapDriver = {
  mount: (options: MapMountOptions) => () => void;
};

type MapPinProps = {
  driver?: MapDriver;
  initialPoint: MapPoint;
  onPointChange: (point: MapPoint) => void;
  tilesUrl: string;
};

type MapStatus = "empty" | "error" | "loading" | "success";


export function MapPin({
  driver = mapLibreDriver,
  initialPoint,
  onPointChange,
  tilesUrl,
}: MapPinProps) {
  const container = useRef<HTMLDivElement>(null);
  const [status, setStatus] = useState<MapStatus>(
    tilesUrl ? "loading" : "empty",
  );
  const [error, setError] = useState("");

  useEffect(() => {
    if (!tilesUrl || !container.current) {
      setStatus("empty");
      return;
    }

    setStatus("loading");
    setError("");
    const showError = (message: string) => {
      setError(message);
      setStatus("error");
    };
    try {
      return driver.mount({
        container: container.current,
        initialPoint,
        tilesUrl,
        onPointChange,
        onReady: () => setStatus("success"),
        onError: showError,
      });
    } catch {
      showError("Check whether your browser supports WebGL.");
    }
  }, [driver, initialPoint, onPointChange, tilesUrl]);

  return (
    <section
      aria-label="Delivery location map"
      className={styles.shell}
      data-testid="map-shell"
    >
      <div className={styles.canvas} ref={container} />
      {status === "loading" && (
        <p className={styles.state} role="status">
          Loading the map…
        </p>
      )}
      {status === "empty" && (
        <div className={styles.state}>
          <strong>Map tiles are not configured.</strong>
          <span>Add the R2 PMTiles URL to show the map locally.</span>
        </div>
      )}
      {status === "error" && (
        <p className={`${styles.state} ${styles.error}`} role="alert">
          The map could not load. {error}
        </p>
      )}
      {status === "success" && (
        <p className={styles.ready} role="status">
          Map ready. Drag the pin to your exact location.
        </p>
      )}
      <p className={styles.attribution}>
        ©{" "}
        <a
          href="https://www.openstreetmap.org/copyright"
          rel="noreferrer"
          target="_blank"
        >
          OpenStreetMap contributors
        </a>
      </p>
    </section>
  );
}
