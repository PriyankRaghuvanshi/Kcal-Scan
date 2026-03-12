/**
 * Tests for Smart Alert deep-link router.
 * Run with: cd mobile && npm test -- __tests__/deepLinkRouter.test.js
 */

const {
  parseSmartAlertDeepLink,
  resolveSmartAlertNavigationTarget,
} = require("../deepLinkRouter.js");

describe("parseSmartAlertDeepLink", () => {
  test("parses push data object with place and coords", () => {
    const data = {
      alert_id: "protein_rescue::ChIJ123::6-inch Grilled Chicken",
      place_id: "ChIJ123",
      place_name: "Subway",
      best_item_name: "6-inch Grilled Chicken",
      place_lat: -33.8,
      place_lng: 151.0,
      route_target: "smart_alert_place",
      display_rank_score_100: 85,
      context_mode: "default",
    };
    const out = parseSmartAlertDeepLink(data);
    expect(out.alert_id).toBe(data.alert_id);
    expect(out.place_id).toBe("ChIJ123");
    expect(out.place_name).toBe("Subway");
    expect(out.place_lat).toBe(-33.8);
    expect(out.place_lng).toBe(151.0);
    expect(out.route_target).toBe("smart_alert_place");
    expect(out.display_rank_score_100).toBe(85);
  });

  test("parses trust metadata from push payload for inbox consistency", () => {
    const data = {
      place_id: "ChIJ123",
      place_name: "Subway",
      best_item_name: "6-inch Grilled Chicken",
      confidence_label: "Chain-backed",
      recommendation_label: "Best pick",
      chosen_candidate_specificity_tier: "chain_registry",
      menu_item_source: "ingested_chain_item",
      matched_local_profile: true,
      local_profile_source: "curated_manual",
      used_venue_intelligence_cache: true,
    };
    const out = parseSmartAlertDeepLink(data);
    expect(out.confidence_label).toBe("Chain-backed");
    expect(out.recommendation_label).toBe("Best pick");
    expect(out.chosen_candidate_specificity_tier).toBe("chain_registry");
    expect(out.menu_item_source).toBe("ingested_chain_item");
    expect(out.matched_local_profile).toBe(true);
    expect(out.local_profile_source).toBe("curated_manual");
    expect(out.used_venue_intelligence_cache).toBe(true);
  });

  test("returns empty when passed null", () => {
    const out = parseSmartAlertDeepLink(null);
    expect(out.place_id).toBe("");
    expect(out.place_lat).toBeNull();
  });

  test("parses URL format", () => {
    const url = "calorieclick://smart-alert?alert_id=a&place_id=p1&place_lat=-33.8&place_lng=151";
    const out = parseSmartAlertDeepLink(url);
    expect(out.place_id).toBe("p1");
    expect(out.place_lat).toBe(-33.8);
    expect(out.place_lng).toBe(151);
  });
});

describe("resolveSmartAlertNavigationTarget", () => {
  test("open_place when place_id and coords present", () => {
    const parsed = {
      place_id: "ChIJ123",
      place_lat: -33.8,
      place_lng: 151.0,
      place_name: "Subway",
      best_item_name: "6-inch Grilled Chicken",
      alert_id: "protein_rescue::ChIJ123::6-inch",
    };
    const out = resolveSmartAlertNavigationTarget(parsed);
    expect(out.action).toBe("open_place");
    expect(out.place_id).toBe("ChIJ123");
    expect(out.place_lat).toBe(-33.8);
    expect(out.place_lng).toBe(151.0);
  });

  test("open_inbox when place_id but no coords", () => {
    const parsed = {
      place_id: "ChIJ123",
      place_lat: null,
      place_lng: null,
    };
    const out = resolveSmartAlertNavigationTarget(parsed);
    expect(out.action).toBe("open_inbox");
    expect(out.place_id).toBe("ChIJ123");
  });

  test("open_nearby when no place_id", () => {
    const parsed = { alert_id: "x", place_id: "" };
    const out = resolveSmartAlertNavigationTarget(parsed);
    expect(out.action).toBe("open_nearby");
    expect(out.place_id).toBeNull();
  });

  test("open_inbox fallback when place_id but no coords (local alert may be missing)", () => {
    const parsed = {
      place_id: "ChIJ123",
      place_name: "Subway",
      best_item_name: "Chicken Sub",
      place_lat: null,
      place_lng: null,
    };
    const out = resolveSmartAlertNavigationTarget(parsed);
    expect(out.action).toBe("open_inbox");
    expect(out.place_id).toBe("ChIJ123");
    expect(out.place_name).toBe("Subway");
    expect(out.best_item_name).toBe("Chicken Sub");
  });
});
