"use client";

import { useEffect, useState } from "react";

import type { components } from "@/api/schema";

type Health = components["schemas"]["HealthResponse"];
type ViewState =
  | { kind: "loading" }
  | { kind: "empty" }
  | { kind: "error"; message: string }
  | { kind: "success"; health: Health };

const serviceLabels: Record<keyof Omit<Health, "status">, string> = {
  database: "PostgreSQL",
  postgis: "PostGIS",
};

export function HealthDashboard() {
  const [state, setState] = useState<ViewState>({ kind: "loading" });

  useEffect(() => {
    const controller = new AbortController();

    async function loadHealth() {
      try {
        const response = await fetch("/api/health", {
          signal: controller.signal,
          headers: { Accept: "application/json" },
        });

        if (!response.ok) {
          throw new Error(`Health check failed with status ${response.status}`);
        }

        const body = await response.text();
        if (!body) {
          setState({ kind: "empty" });
          return;
        }

        setState({ kind: "success", health: JSON.parse(body) as Health });
      } catch (error) {
        if (error instanceof DOMException && error.name === "AbortError") {
          return;
        }

        setState({
          kind: "error",
          message: error instanceof Error ? error.message : "Health check failed",
        });
      }
    }

    void loadHealth();
    return () => controller.abort();
  }, []);

  if (state.kind === "loading") {
    return <p className="state-card">Checking services…</p>;
  }

  if (state.kind === "empty") {
    return <p className="state-card">No health data was returned.</p>;
  }

  if (state.kind === "error") {
    return (
      <section className="state-card state-card--error" role="alert">
        <h2>Health check unavailable</h2>
        <p>{state.message}</p>
      </section>
    );
  }

  return (
    <section aria-labelledby="service-health">
      <div className="section-heading">
        <div>
          <p className="eyebrow">Live response</p>
          <h2 id="service-health">Services are ready</h2>
        </div>
        <span className="overall-status">{state.health.status}</span>
      </div>
      <div className="service-grid">
        {Object.entries(serviceLabels).map(([service, label]) => {
          const status = state.health[service as keyof typeof serviceLabels];
          return (
            <article className="service-card" key={service}>
              <span className="status-dot" aria-hidden="true" />
              <div>
                <h3>{label}</h3>
                <p>{status}</p>
              </div>
            </article>
          );
        })}
      </div>
    </section>
  );
}
