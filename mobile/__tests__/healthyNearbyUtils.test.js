/**
 * Tests for Healthy Nearby normalization and wording.
 * Run with: npx jest mobile/__tests__/healthyNearbyUtils.test.js
 * (Add jest to devDependencies if not present.)
 */

const {
  normalizeHealthyPlacesResponse,
  getHealthyItemLineLabel,
  getHealthyPanelItemHeading,
} = require("../healthyNearbyUtils.js");

describe("normalizeHealthyPlacesResponse", () => {
  test("flat_score mode uses response.items", () => {
    const response = {
      sort_mode: "flat_score",
      items: [{ name: "A", display_rank_score_100: 80 }, { name: "B", display_rank_score_100: 70 }],
    };
    const out = normalizeHealthyPlacesResponse(response);
    expect(out.sortMode).toBe("flat_score");
    expect(out.items).toHaveLength(2);
    expect(out.items[0].name).toBe("A");
    expect(out.items[1].name).toBe("B");
    expect(out.sections).toBeUndefined();
  });

  test("sectioned mode with sections flattens sections in order and does not use response.places", () => {
    const response = {
      sort_mode: "sectioned",
      places: [{ name: "WrongOrder" }],
      sections: [
        { name: "Best fit for your goal", items: [{ name: "First" }, { name: "Second" }] },
        { name: "Decent nearby options", items: [{ name: "Third" }] },
        { name: "Needs menu check", items: [{ name: "Fourth" }] },
      ],
    };
    const out = normalizeHealthyPlacesResponse(response);
    expect(out.sortMode).toBe("sectioned");
    expect(out.sections).toHaveLength(3);
    expect(out.items).toHaveLength(4);
    expect(out.items[0].name).toBe("First");
    expect(out.items[1].name).toBe("Second");
    expect(out.items[2].name).toBe("Third");
    expect(out.items[3].name).toBe("Fourth");
    expect(out.items.map((i) => i.name)).not.toContain("WrongOrder");
  });

  test("sectioned mode with no sections falls back to response.places", () => {
    const response = {
      sort_mode: "sectioned",
      places: [{ name: "Fallback" }, { name: "Also" }],
    };
    const out = normalizeHealthyPlacesResponse(response);
    expect(out.sortMode).toBe("sectioned");
    expect(out.items).toHaveLength(2);
    expect(out.items[0].name).toBe("Fallback");
    expect(out.sections).toBeUndefined();
  });

  test("invalid or null response returns empty items and flat_score", () => {
    expect(normalizeHealthyPlacesResponse(null).items).toEqual([]);
    expect(normalizeHealthyPlacesResponse(null).sortMode).toBe("flat_score");
    expect(normalizeHealthyPlacesResponse({}).items).toEqual([]);
  });
});

describe("getHealthyItemLineLabel", () => {
  test("Best pick returns Recommended", () => {
    expect(getHealthyItemLineLabel("Best pick")).toBe("Recommended");
  });

  test("Strong option returns Recommended", () => {
    expect(getHealthyItemLineLabel("Strong option")).toBe("Recommended");
  });

  test("Suggested healthier pick returns Suggested option", () => {
    expect(getHealthyItemLineLabel("Suggested healthier pick")).toBe("Suggested option");
  });

  test("Needs menu check returns Possible option", () => {
    expect(getHealthyItemLineLabel("Needs menu check")).toBe("Possible option");
  });
});

describe("getHealthyPanelItemHeading", () => {
  test("Best pick place returns Recommended", () => {
    expect(getHealthyPanelItemHeading({ recommendation_label: "Best pick" })).toBe("Recommended");
  });

  test("Suggested healthier pick returns Suggested option", () => {
    expect(getHealthyPanelItemHeading({ recommendation_label: "Suggested healthier pick" })).toBe("Suggested option");
  });

  test("Needs menu check returns Possible option", () => {
    expect(getHealthyPanelItemHeading({ recommendation_label: "Needs menu check" })).toBe("Possible option");
  });

  test("best_item_is_generic_fallback uses softer wording", () => {
    const place = { recommendation_label: "Best pick", best_item_is_generic_fallback: true };
    expect(getHealthyPanelItemHeading(place)).toBe("Suggested option");
  });
});
