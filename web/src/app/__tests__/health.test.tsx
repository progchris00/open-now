import { existsSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";


describe("health page", () => {
  it("renders_app_shell", async () => {
    const pagePath = fileURLToPath(new URL("../page.tsx", import.meta.url));

    expect(
      existsSync(pagePath),
      "Next.js has not been scaffolded in web/src/app yet",
    ).toBe(true);

    const testingLibraryModule = "@testing-library/react";
    const { render, screen } = await import(testingLibraryModule);
    const reactModule = "react";
    const { createElement } = await import(reactModule);
    const pageModule = "../page";
    const { default: Page } = await import(pageModule);

    render(createElement(Page));

    expect(
      screen.getByRole("heading", {
        level: 1,
        name: "OpenNow system health",
      }),
    ).toBeDefined();
  });
});
