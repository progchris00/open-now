import { HealthDashboard } from "./health-dashboard";

export default function Page() {
  return (
    <main className="shell">
      <header className="hero">
        <p className="eyebrow">OpenNow · developer environment</p>
        <h1>OpenNow system health</h1>
        <p className="intro">
          One view of the web app, API, database, and spatial services that power
          local development.
        </p>
      </header>
      <HealthDashboard />
    </main>
  );
}
