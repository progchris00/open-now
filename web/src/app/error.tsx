"use client";


export default function ErrorPage({ reset }: { reset: () => void }) {
  return (
    <main className="page-shell">
      <section className="health-card">
        <h1>OpenNow system health</h1>
        <div role="alert" className="error-state">
          <p>The health page could not be loaded.</p>
          <button type="button" onClick={reset}>
            Try again
          </button>
        </div>
      </section>
    </main>
  );
}
