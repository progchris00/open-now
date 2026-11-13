import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { HealthDashboard } from "../health-dashboard";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("HealthDashboard", () => {
  it("shows the loading state while the request is pending", () => {
    vi.stubGlobal("fetch", vi.fn(() => new Promise(() => undefined)));

    render(<HealthDashboard />);

    expect(screen.getByText("Checking services…")).toBeDefined();
  });

  it("shows an empty state when the API returns no content", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({ ok: true, text: async () => "" }),
    );

    render(<HealthDashboard />);

    expect(await screen.findByText("No health data was returned.")).toBeDefined();
  });

  it("shows an error state when the API is unavailable", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({ ok: false, status: 503 }),
    );

    render(<HealthDashboard />);

    expect((await screen.findByRole("alert")).textContent).toContain(
      "Health check failed with status 503",
    );
  });

  it("shows the successful service response", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        text: async () =>
          JSON.stringify({ status: "ok", database: "ok", postgis: "ok" }),
      }),
    );

    render(<HealthDashboard />);

    expect(await screen.findByRole("heading", { name: "Services are ready" }))
      .toBeDefined();
    await waitFor(() => {
      expect(screen.getAllByText("ok")).toHaveLength(3);
    });
  });
});
