/**
 * Tests for map coordinate and filter utilities.
 */

const {
  getPlaceCoords,
  getVisibleMarkers,
  hasValidCoords,
  getTopRankedMarkers,
  getInitialSelectedPlace,
  shouldUseStrongBestNearbyLabel,
  getBestNearbyLabel,
  getMarkerVisualTier,
} = require("../mapUtils.js");

describe("getPlaceCoords", () => {
  test("extracts lat/lng from top-level lat and lng", () => {
    const place = { lat: 37.77, lng: -122.42 };
    expect(getPlaceCoords(place)).toEqual({ lat: 37.77, lng: -122.42 });
  });

  test("extracts from latitude/longitude", () => {
    const place = { latitude: 40.71, longitude: -74.01 };
    expect(getPlaceCoords(place)).toEqual({ lat: 40.71, lng: -74.01 });
  });

  test("extracts from geometry.location", () => {
    const place = {
      geometry: { location: { lat: 34.05, lng: -118.24 } },
    };
    expect(getPlaceCoords(place)).toEqual({ lat: 34.05, lng: -118.24 });
  });

  test("returns null for place without coords", () => {
    expect(getPlaceCoords({})).toBeNull();
    expect(getPlaceCoords({ place_name: "Test" })).toBeNull();
    expect(getPlaceCoords(null)).toBeNull();
  });

  test("returns null for invalid numbers", () => {
    expect(getPlaceCoords({ lat: "x", lng: -122 })).toBeNull();
  });
});

describe("getVisibleMarkers", () => {
  const places = [
    { place_id: "a", lat: 37.77, lng: -122.42, estimated_protein_g: 35, estimated_calories: 450, fit_for_today: true },
    { place_id: "b", lat: 37.78, lng: -122.43, estimated_protein_g: 25, estimated_calories: 700, cut_friendly: true },
    { place_id: "c", lat: 37.79, lng: -122.44, estimated_protein_g: 40, estimated_calories: 500, fit_for_today: false },
  ];

  test("all filter returns all places", () => {
    const out = getVisibleMarkers(places, "all");
    expect(out).toHaveLength(3);
  });

  test("high_protein filter returns places with ≥30g protein", () => {
    const out = getVisibleMarkers(places, "high_protein");
    expect(out).toHaveLength(2);
    expect(out.map((p) => p.place_id)).toContain("a");
    expect(out.map((p) => p.place_id)).toContain("c");
    expect(out.map((p) => p.place_id)).not.toContain("b");
  });

  test("under_600 filter returns places with calories ≤600", () => {
    const out = getVisibleMarkers(places, "under_600");
    expect(out).toHaveLength(2);
    expect(out.map((p) => p.place_id)).toContain("a");
    expect(out.map((p) => p.place_id)).toContain("c");
    expect(out.map((p) => p.place_id)).not.toContain("b");
  });

  test("fits_today filter returns places with fit_for_today true", () => {
    const out = getVisibleMarkers(places, "fits_today");
    expect(out).toHaveLength(1);
    expect(out[0].place_id).toBe("a");
  });

  test("cut_friendly filter returns places with cut_friendly or fat_loss_friendly", () => {
    const out = getVisibleMarkers(places, "cut_friendly");
    expect(out).toHaveLength(1);
    expect(out[0].place_id).toBe("b");
  });

  test("empty or invalid places returns empty array", () => {
    expect(getVisibleMarkers([], "all")).toEqual([]);
    expect(getVisibleMarkers(null, "all")).toEqual([]);
  });
});

describe("hasValidCoords", () => {
  test("returns true when place has valid lat/lng", () => {
    expect(hasValidCoords({ lat: 37.77, lng: -122.42 })).toBe(true);
  });

  test("returns false when coords missing or invalid", () => {
    expect(hasValidCoords({})).toBe(false);
    expect(hasValidCoords({ lat: 37.77 })).toBe(false);
    expect(hasValidCoords(null)).toBe(false);
  });
});

describe("getTopRankedMarkers", () => {
  test("returns first N places", () => {
    const places = [{ id: "a" }, { id: "b" }, { id: "c" }, { id: "d" }];
    expect(getTopRankedMarkers(places, 3)).toHaveLength(3);
    expect(getTopRankedMarkers(places, 3)[0].id).toBe("a");
    expect(getTopRankedMarkers(places, 2)[1].id).toBe("b");
  });

  test("default limit is 3", () => {
    const places = [{ id: "a" }, { id: "b" }, { id: "c" }, { id: "d" }];
    expect(getTopRankedMarkers(places)).toHaveLength(3);
  });
});

describe("getInitialSelectedPlace", () => {
  const getStableId = (p) => p.id;

  test("returns current place if still in visible", () => {
    const visible = [{ id: "a" }, { id: "b" }];
    const current = { id: "b" };
    const out = getInitialSelectedPlace(visible, current, "b", getStableId);
    expect(out.place.id).toBe("b");
    expect(out.index).toBe(1);
  });

  test("returns top place when current not in visible", () => {
    const visible = [{ id: "a" }, { id: "b" }];
    const out = getInitialSelectedPlace(visible, null, "x", getStableId);
    expect(out.place.id).toBe("a");
    expect(out.index).toBe(0);
  });

  test("returns top when selected id empty", () => {
    const visible = [{ id: "a" }];
    const out = getInitialSelectedPlace(visible, null, "", getStableId);
    expect(out.place.id).toBe("a");
  });
});

describe("shouldUseStrongBestNearbyLabel", () => {
  test("returns false for generic fallback", () => {
    expect(shouldUseStrongBestNearbyLabel({ best_item_is_generic_fallback: true })).toBe(false);
  });

  test("returns false for Needs menu check", () => {
    expect(shouldUseStrongBestNearbyLabel({ confidence_label: "Needs menu check" })).toBe(false);
    expect(shouldUseStrongBestNearbyLabel({ recommendation_label: "Needs menu check" })).toBe(false);
  });

  test("returns true for Best pick with real menu", () => {
    const place = {
      recommendation_label: "Best pick",
      display_rank_score_100: 80,
      menu_item_source: "real_menu",
    };
    expect(shouldUseStrongBestNearbyLabel(place)).toBe(true);
  });

  test("returns false for low score", () => {
    expect(shouldUseStrongBestNearbyLabel({ recommendation_label: "Best pick", display_rank_score_100: 50 })).toBe(false);
  });
});

describe("getBestNearbyLabel", () => {
  test("rank 1 strong returns Best nearby right now", () => {
    const place = {
      recommendation_label: "Best pick",
      display_rank_score_100: 80,
      menu_item_source: "real_menu",
    };
    expect(getBestNearbyLabel(place, 1)).toBe("Best nearby right now");
  });

  test("rank 2 returns #2 nearby", () => {
    expect(getBestNearbyLabel({}, 2)).toBe("#2 nearby");
  });

  test("rank 3 returns #3 nearby", () => {
    expect(getBestNearbyLabel({}, 3)).toBe("#3 nearby");
  });

  test("needs check uses softer language", () => {
    const place = { confidence_label: "Needs menu check", recommendation_label: "Suggested" };
    expect(getBestNearbyLabel(place, 1)).toBe("Likely best nearby");
  });
});

describe("getMarkerVisualTier", () => {
  const getStableId = (p, i) => p.id || `p-${i}`;

  test("returns 1 for first place", () => {
    const places = [{ id: "a" }, { id: "b" }];
    expect(getMarkerVisualTier({ id: "a" }, places, getStableId)).toBe(1);
  });

  test("returns 2 for second place", () => {
    const places = [{ id: "a" }, { id: "b" }];
    expect(getMarkerVisualTier({ id: "b" }, places, getStableId)).toBe(2);
  });

  test("returns 0 for place not in top 3", () => {
    const places = [{ id: "a" }, { id: "b" }, { id: "c" }, { id: "d" }];
    expect(getMarkerVisualTier({ id: "d" }, places, getStableId)).toBe(0);
  });
});
