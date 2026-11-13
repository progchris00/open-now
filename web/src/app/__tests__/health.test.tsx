import { existsSync } from "node:fs";
import { resolve } from "node:path";

import { describe, expect, it } from "vitest";


describe("health page", () => {
  it("renders_app_shell", async () => {
    const pagePath = resolve(import.meta.dirname, "../page.tsx");
    expect(
      existsSync(pagePath),
      "Next.js web scaffold has not been implemented",
    ).toBe(true);

    const testingLibraryModule = "@testing-library/react";
    const { render, screen } = await import(testingLibraryModule);
    const pageModule = "../page";
    const { default: Page } = await import(pageModule);
    render(<Page />);

    expect(
      screen.getByRole("heading", { level: 1, name: "OpenNow system health" }),
    ).toBeDefined();
  });
});
