import { fireEvent, render, screen } from "@testing-library/react";
import { expect, test, vi } from "vitest";

import DeliveryDetailsPage from "../delivery-details/page";

vi.mock("next/server", () => ({ connection: vi.fn() }));

test.each([undefined, " https://maps.example.test/philippines.pmtiles "])(
  "passes the runtime tiles URL to the delivery details screen (%s)",
  async (url) => {
    vi.stubEnv("MAP_TILES_URL", url);
    try {
      const page = await DeliveryDetailsPage();
      expect(page.props.tilesUrl).toBe(url?.trim() ?? "");
      if (!url) {
        render(page);
        expect(screen.getByText(/map tiles are not configured/i)).toBeDefined();
        const form = screen.getByRole("form", { name: "Delivery address" });
        expect(fireEvent.submit(form)).toBe(false);
      }
    } finally {
      vi.unstubAllEnvs();
    }
  },
);
