import { afterEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";

import { HealthDashboard } from "../health-dashboard";


function response(body: unknown, ok = true): Response {
  return {
    ok,
    json: async () => body,
  } as Response;
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("HealthDashboard", () => {
  it("shows the loading state", () => {
    vi.stubGlobal("fetch", vi.fn(() => new Promise(() => undefined)));

    render(<HealthDashboard />);

    expect(screen.getByRole("status").textContent).toContain("Checking");
  });

  it("shows the success state", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        response({ status: "ok", database: "ok", postgis: "ok" }),
      ),
    );

    render(<HealthDashboard />);

    expect(await screen.findByText("Database")).toBeDefined();
    expect(screen.getAllByText("ok")).toHaveLength(3);
  });

  it("shows the empty state", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(response({})));

    render(<HealthDashboard />);

    expect(
      await screen.findByText("No health information is available."),
    ).toBeDefined();
  });

  it("shows the error state and retries", async () => {
    const fetchMock = vi
      .fn()
      .mockRejectedValueOnce(new Error("offline"))
      .mockResolvedValueOnce(
        response({ status: "ok", database: "ok", postgis: "ok" }),
      );
    vi.stubGlobal("fetch", fetchMock);

    render(<HealthDashboard />);

    fireEvent.click(await screen.findByRole("button", { name: "Try again" }));

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
    expect(await screen.findByText("PostGIS")).toBeDefined();
  });

  it("treats a non-success response as an error", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(response({}, false)));

    render(<HealthDashboard />);

    expect(await screen.findByRole("alert")).toBeDefined();
  });
});
