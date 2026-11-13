"use client";

import { useEffect, useState } from "react";

import type { components } from "@/api/schema";


type HealthResponse = components["schemas"]["HealthResponse"];
type HealthState =
  | { kind: "loading" }
  | { kind: "empty" }
  | { kind: "error" }
  | { kind: "success"; health: HealthResponse };

function isHealthResponse(value: unknown): value is HealthResponse {
  if (typeof value !== "object" || value === null) {
    return false;
  }

  const candidate = value as Record<string, unknown>;
  return (
    candidate.status === "ok" &&
    candidate.database === "ok" &&
    candidate.postgis === "ok"
  );
}

async function fetchHealthState(): Promise<HealthState> {
  try {
    const response = await fetch("/api/health", {
      headers: { Accept: "application/json" },
    });

    if (!response.ok) {
      throw new Error("Health endpoint is unavailable");
    }

    const health: unknown = await response.json();
    return isHealthResponse(health)
      ? { kind: "success", health }
      : { kind: "empty" };
  } catch {
    return { kind: "error" };
  }
}

export function HealthDashboard() {
  const [state, setState] = useState<HealthState>({ kind: "loading" });

  useEffect(() => {
    let active = true;

    void fetchHealthState().then((healthState) => {
      if (active) {
        setState(healthState);
      }
    });

    return () => {
      active = false;
    };
  }, []);

  if (state.kind === "loading") {
    return <p role="status">Checking services…</p>;
  }

  if (state.kind === "empty") {
    return <p role="status">No health information is available.</p>;
  }

  if (state.kind === "error") {
    return (
      <div role="alert" className="error-state">
        <p>OpenNow services could not be reached.</p>
        <button
          type="button"
          onClick={() => {
            setState({ kind: "loading" });
            void fetchHealthState().then(setState);
          }}
        >
          Try again
        </button>
      </div>
    );
  }

  const services = [
    ["API", state.health.status],
    ["Database", state.health.database],
    ["PostGIS", state.health.postgis],
  ];

  return (
    <dl className="service-list">
      {services.map(([name, serviceStatus]) => (
        <div className="service-row" key={name}>
          <dt>{name}</dt>
          <dd>
            <span aria-hidden="true" className="status-dot" />
            {serviceStatus}
          </dd>
        </div>
      ))}
    </dl>
  );
}
