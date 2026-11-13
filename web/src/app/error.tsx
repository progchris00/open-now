"use client";

export default function ErrorPage({ reset }: { reset: () => void }) {
  return (
    <main className="shell">
      <section className="state-card state-card--error" role="alert">
        <h1>OpenNow could not load</h1>
        <button type="button" onClick={reset}>
          Try again
        </button>
      </section>
    </main>
  );
}
