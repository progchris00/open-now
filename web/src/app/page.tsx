import { HealthDashboard } from "./health-dashboard";


export default function Page() {
  return (
    <main className="page-shell">
      <section className="health-card" aria-labelledby="health-heading">
        <p className="eyebrow">OpenNow.online</p>
        <h1 id="health-heading">OpenNow system health</h1>
        <p className="intro">
          Local development services report their current availability here.
        </p>
        <HealthDashboard />
      </section>
    </main>
  );
}
