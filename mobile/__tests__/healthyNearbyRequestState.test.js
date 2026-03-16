const {
  buildHealthyNearbyContextKey,
  hasMaterialLocationChange,
  shouldApplyHealthyNearbyResponse,
} = require("../utils/healthyNearbyRequestState.js");

describe("healthyNearbyRequestState helpers", () => {
  test("context key stable for tiny jitter", () => {
    const base = buildHealthyNearbyContextKey({
      lat: 12.971234,
      lng: 77.594111,
      radiusM: 3000,
      goal: "fat_loss",
      cutMode: true,
      filterKey: "all",
    });
    const jitter = buildHealthyNearbyContextKey({
      lat: 12.971245,
      lng: 77.594099,
      radiusM: 3000,
      goal: "fat_loss",
      cutMode: true,
      filterKey: "all",
    });
    expect(base).toBe(jitter);
  });

  test("context key changes when goal changes", () => {
    const a = buildHealthyNearbyContextKey({
      lat: 12.971,
      lng: 77.594,
      radiusM: 3000,
      goal: "fat_loss",
      cutMode: true,
      filterKey: "all",
    });
    const b = buildHealthyNearbyContextKey({
      lat: 12.971,
      lng: 77.594,
      radiusM: 3000,
      goal: "muscle_gain",
      cutMode: false,
      filterKey: "all",
    });
    expect(a).not.toBe(b);
  });

  test("hasMaterialLocationChange ignores tiny movement", () => {
    const prev = { lat: 12.971, lng: 77.594 };
    const next = { lat: 12.9711, lng: 77.5941 };
    expect(hasMaterialLocationChange(prev, next, 500)).toBe(false);
  });

  test("hasMaterialLocationChange detects larger movement", () => {
    const prev = { lat: 12.971, lng: 77.594 };
    const next = { lat: 12.981, lng: 77.604 };
    expect(hasMaterialLocationChange(prev, next, 500)).toBe(true);
  });

  test("shouldApplyHealthyNearbyResponse enforces latest id and context key", () => {
    expect(shouldApplyHealthyNearbyResponse(1, 2, "a", "a")).toBe(false);
    expect(shouldApplyHealthyNearbyResponse(2, 2, "a", "b")).toBe(false);
    expect(shouldApplyHealthyNearbyResponse(2, 2, "a", "a")).toBe(true);
  });
});

