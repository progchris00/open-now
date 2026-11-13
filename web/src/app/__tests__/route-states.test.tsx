import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import ErrorPage from "../error";
import Loading from "../loading";


describe("route states", () => {
  it("renders the route loading state", () => {
    render(<Loading />);

    expect(screen.getByRole("status").textContent).toContain("Loading OpenNow");
  });

  it("resets the route error state", () => {
    const reset = vi.fn();
    render(<ErrorPage reset={reset} />);

    fireEvent.click(screen.getByRole("button", { name: "Try again" }));

    expect(reset).toHaveBeenCalledOnce();
  });
});
