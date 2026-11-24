import { expect, test, vi } from "vitest";

import { mapLibreDriver } from "../maplibre-driver";

const mocks = vi.hoisted(() => ({
  addProtocol: vi.fn(),
  mapOn: vi.fn(),
  mapOnce: vi.fn(),
  mapRemove: vi.fn(),
  markerOn: vi.fn(),
  markerRemove: vi.fn(),
  mapOptions: vi.fn(),
}));

vi.mock("maplibre-gl", () => ({
  addProtocol: mocks.addProtocol,
  Map: class {
    constructor(options: unknown) { mocks.mapOptions(options); }
    on = mocks.mapOn;
    once = mocks.mapOnce;
    remove = mocks.mapRemove;
  },
  Marker: class {
    setLngLat() { return this; }
    addTo() { return this; }
    on = mocks.markerOn;
    remove = mocks.markerRemove;
    getLngLat() { return { lng: 121.02, lat: 14.61 }; }
  },
}));

test("mounts the PMTiles source and forwards readiness, errors and dragged coordinates", () => {
  const onPointChange = vi.fn();
  const onReady = vi.fn();
  const onError = vi.fn();
  const options = {
    container: document.createElement("div"),
    initialPoint: { latitude: 14.6, longitude: 121 },
    tilesUrl: "https://maps.example.test/philippines.pmtiles",
    onPointChange, onReady, onError,
  };
  const dispose = mapLibreDriver.mount(options);
  expect(mocks.mapOptions.mock.calls[0][0].style.sources.protomaps.url)
    .toBe("pmtiles://https://maps.example.test/philippines.pmtiles");
  expect(mocks.mapOnce).toHaveBeenCalledWith("load", onReady);
  mocks.markerOn.mock.calls[0][1]();
  expect(onPointChange).toHaveBeenCalledWith({ latitude: 14.61, longitude: 121.02 });
  mocks.mapOn.mock.calls[0][1]({ error: new Error("Unavailable") });
  mocks.mapOn.mock.calls[0][1]({});
  expect(onError.mock.calls.flat()).toEqual([
    "Unavailable", "Check the PMTiles URL and R2 CORS policy.",
  ]);
  dispose();
  expect(mocks.markerRemove).toHaveBeenCalledOnce();
  expect(mocks.mapRemove).toHaveBeenCalledOnce();
  mapLibreDriver.mount(options)();
  expect(mocks.addProtocol).toHaveBeenCalledOnce();
});
