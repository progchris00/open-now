import { act, render, screen } from "@testing-library/react";
import type { ComponentType } from "react";
import { expect, test, vi } from "vitest";


type Point = {
  latitude: number;
  longitude: number;
};

type DriverOptions = {
  onError: (message: string) => void;
  onPointChange: (point: Point) => void;
  onReady: () => void;
};

type MapPinProps = {
  driver: {
    mount: (options: DriverOptions) => () => void;
  };
  initialPoint: Point;
  onPointChange: (point: Point) => void;
  tilesUrl: string;
};


async function loadMapPin(): Promise<ComponentType<MapPinProps> | null> {
  const componentPath = "../MapPin";
  try {
    const loaded = await import(/* @vite-ignore */ componentPath);
    return loaded.MapPin as ComponentType<MapPinProps>;
  } catch {
    return null;
  }
}


function readyDriver() {
  let emitDrag: ((point: Point) => void) | undefined;
  const driver = {
    mount: vi.fn((options: DriverOptions) => {
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


test("renders_attribution", async () => {
  const MapPin = await loadMapPin();
  expect(MapPin, "MapPin has not been implemented yet").not.toBeNull();
  if (!MapPin) return;

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


test("emits_point_on_drag", async () => {
  const MapPin = await loadMapPin();
  expect(MapPin, "MapPin has not been implemented yet").not.toBeNull();
  if (!MapPin) return;

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
