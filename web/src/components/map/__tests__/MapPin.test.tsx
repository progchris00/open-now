import { act, render, screen } from "@testing-library/react";
import { expect, test, vi } from "vitest";

import { MapPin, type MapMountOptions } from "../MapPin";

type Point = {
  latitude: number;
  longitude: number;
};

function readyDriver() {
  let emitDrag: ((point: Point) => void) | undefined;
  const driver = {
    mount: vi.fn((options: MapMountOptions) => {
      emitDrag = options.onPointChange;
      options.onReady();
      return vi.fn();
    }),
  };
  return {
    driver,
    drag(point: Point) {
      act(() => emitDrag?.(point));
    },
  };
}


test("renders_attribution", () => {
  const { driver } = readyDriver();
  render(
    <MapPin
      driver={driver}
      initialPoint={{ latitude: 14.5995, longitude: 120.9842 }}
      onPointChange={vi.fn()}
      tilesUrl="https://maps.example.test/philippines.pmtiles"
    />,
  );

  const attribution = screen.getByRole("link", {
    name: /openstreetmap contributors/i,
  });
  expect(attribution.getAttribute("href")).toBe(
    "https://www.openstreetmap.org/copyright",
  );
});


test("emits_point_on_drag", () => {
  const onPointChange = vi.fn();
  const { driver, drag } = readyDriver();
  render(
    <MapPin
      driver={driver}
      initialPoint={{ latitude: 14.5995, longitude: 120.9842 }}
      onPointChange={onPointChange}
      tilesUrl="https://maps.example.test/philippines.pmtiles"
    />,
  );

  drag({ latitude: 14.6091, longitude: 121.0223 });

  expect(onPointChange).toHaveBeenCalledOnce();
  expect(onPointChange).toHaveBeenCalledWith({
    latitude: 14.6091,
    longitude: 121.0223,
  });
});

test("reports missing tiles, loading and failure, and releases its map", () => {
  let fail: MapMountOptions["onError"] | undefined;
  const dispose = vi.fn();
  const driver = {
    mount: vi.fn((options: MapMountOptions) => {
      fail = options.onError;
      return dispose;
    }),
  };
  const props = {
    driver,
    initialPoint: { latitude: 14.6, longitude: 121 },
    onPointChange: vi.fn(),
  };
  const { rerender, unmount } = render(<MapPin {...props} tilesUrl="" />);
  expect(screen.getByText(/map tiles are not configured/i)).toBeDefined();
  expect(driver.mount).not.toHaveBeenCalled();
  rerender(<MapPin {...props} tilesUrl="https://maps.example.test/philippines.pmtiles" />);
  expect(screen.getByRole("status").textContent).toMatch(/loading/i);
  act(() => fail?.("Unavailable"));
  expect(screen.getByRole("alert").textContent).toMatch(/unavailable/i);
  unmount();
  expect(dispose).toHaveBeenCalledOnce();
});

test("shows an error if the browser cannot initialize the map", () => {
  render(
    <MapPin
      driver={{ mount() { throw new Error("WebGL unavailable"); } }}
      initialPoint={{ latitude: 14.6, longitude: 121 }}
      onPointChange={vi.fn()}
      tilesUrl="https://maps.example.test/philippines.pmtiles"
    />,
  );
  expect(screen.getByRole("alert").textContent).toMatch(/webgl/i);
});
