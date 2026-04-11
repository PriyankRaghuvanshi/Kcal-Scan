/**
 * Tests for Smart Alert trust label mapping.
 * Run with: cd mobile && npm test -- __tests__/smartAlertTrustLabels.test.js
 */

const {
  TRUST_LABELS,
  TRUST_TONES,
  getAlertTrustLabel,
  getAlertTrustTone,
  shouldShowMenuMayVary,
  getEffectiveAlertTitle,
  getAlertHeroLabel,
  getTrustTierForBadge,
} = require("../smartAlertTrustLabels.js");

describe("getAlertTrustLabel", () => {
  test("A. source/confidence maps to Verified", () => {
    expect(getAlertTrustLabel({ confidence_label: "Verified" })).toBe(TRUST_LABELS.verified);
    expect(getAlertTrustLabel({ menu_item_source: "real_menu" })).toBe(TRUST_LABELS.verified);
    expect(getAlertTrustLabel({ menu_item_source: "user_scan" })).toBe(TRUST_LABELS.verified);
    expect(getAlertTrustLabel({ menu_item_source: "exact_menu_cache" })).toBe(TRUST_LABELS.verified);
  });

  test("B. weak generic alert gets Needs menu check", () => {
    expect(
      getAlertTrustLabel({ best_item_is_generic_fallback: true })
    ).toBe(TRUST_LABELS.needs_menu_check);
    expect(
      getAlertTrustLabel({ confidence_label: "Needs menu check" })
    ).toBe(TRUST_LABELS.needs_menu_check);
    expect(
      getAlertTrustLabel({ chosen_candidate_specificity_tier: "generic_fallback" })
    ).toBe(TRUST_LABELS.needs_menu_check);
  });

  test("C. ingested chain item gets Chain-backed", () => {
    expect(
      getAlertTrustLabel({ menu_item_source: "ingested_chain_item" })
    ).toBe(TRUST_LABELS.chain_backed);
    expect(
      getAlertTrustLabel({ menu_item_source: "chain_registry" })
    ).toBe(TRUST_LABELS.chain_backed);
    expect(
      getAlertTrustLabel({ confidence_label: "Chain-backed" })
    ).toBe(TRUST_LABELS.chain_backed);
  });

  test("D. enriched local profile gets Local favorite", () => {
    expect(
      getAlertTrustLabel({ matched_local_profile: true, local_profile_source: "curated_manual" })
    ).toBe(TRUST_LABELS.local_favorite);
    expect(
      getAlertTrustLabel({ menu_item_source: "enriched_local_profile" })
    ).toBe(TRUST_LABELS.local_favorite);
    expect(
      getAlertTrustLabel({ chosen_candidate_specificity_tier: "enriched_local_profile" })
    ).toBe(TRUST_LABELS.local_favorite);
  });

  test("E. heuristic Best pick gets Estimated", () => {
    expect(
      getAlertTrustLabel({ recommendation_label: "Best pick" })
    ).toBe(TRUST_LABELS.estimated);
    expect(
      getAlertTrustLabel({ recommendation_label: "Strong option" })
    ).toBe(TRUST_LABELS.estimated);
    expect(
      getAlertTrustLabel({ confidence_label: "Estimated" })
    ).toBe(TRUST_LABELS.estimated);
  });

  test("returns needs_menu_check for null/empty input", () => {
    expect(getAlertTrustLabel(null)).toBe(TRUST_LABELS.needs_menu_check);
    expect(getAlertTrustLabel({})).toBe(TRUST_LABELS.estimated);
  });
});

describe("getAlertTrustTone", () => {
  test("strong for Verified, Chain-backed, Local favorite", () => {
    expect(getAlertTrustTone({ confidence_label: "Verified" })).toBe(TRUST_TONES.strong);
    expect(getAlertTrustTone({ menu_item_source: "chain_registry" })).toBe(TRUST_TONES.strong);
    expect(getAlertTrustTone({ matched_local_profile: true, local_profile_source: "x" })).toBe(TRUST_TONES.strong);
  });

  test("medium for Estimated", () => {
    expect(getAlertTrustTone({ recommendation_label: "Best pick" })).toBe(TRUST_TONES.medium);
  });

  test("weak for Needs menu check", () => {
    expect(getAlertTrustTone({ best_item_is_generic_fallback: true })).toBe(TRUST_TONES.weak);
  });
});

describe("shouldShowMenuMayVary", () => {
  test("only true for Needs menu check", () => {
    expect(shouldShowMenuMayVary({ best_item_is_generic_fallback: true })).toBe(true);
    expect(shouldShowMenuMayVary({ confidence_label: "Needs menu check" })).toBe(true);
    expect(shouldShowMenuMayVary({ menu_item_source: "real_menu" })).toBe(false);
    expect(shouldShowMenuMayVary({ recommendation_label: "Best pick" })).toBe(false);
  });
});

describe("getEffectiveAlertTitle", () => {
  test("softens strong title for weak trust", () => {
    expect(
      getEffectiveAlertTitle({
        title: "Best nearby fit right now",
        best_item_is_generic_fallback: true,
      })
    ).toBe("Suggested nearby option");
  });

  test("keeps title when trust is not weak", () => {
    expect(
      getEffectiveAlertTitle({
        title: "You're still 25g short on protein.",
        menu_item_source: "real_menu",
      })
    ).toBe("You're still 25g short on protein.");
  });
});

describe("getAlertHeroLabel", () => {
  test("strong trust gets Best nearby right now", () => {
    expect(getAlertHeroLabel({ confidence_label: "Verified" })).toBe("Best nearby right now");
  });

  test("weak trust gets softer wording", () => {
    expect(getAlertHeroLabel({ best_item_is_generic_fallback: true })).toBe("Check menu before ordering");
  });
});

describe("item_provenance covered-chain gating", () => {
  test("covered chain + exact_chain_menu provenance => Chain-backed", () => {
    expect(
      getAlertTrustLabel({
        item_provenance: "exact_chain_menu",
        covered_chain_key: "dominos",
        menu_item_source: "ingested_chain_item",
      })
    ).toBe(TRUST_LABELS.chain_backed);
  });

  test("covered chain + heuristic suggestion => Estimated (never Chain-backed)", () => {
    expect(
      getAlertTrustLabel({
        covered_chain_key: "dominos",
        item_provenance: "heuristic_suggestion",
      })
    ).toBe(TRUST_LABELS.estimated);
  });

  test("covered chain card never shows fallback item as Chain-backed", () => {
    // Even if confidence_label says Chain-backed, generic_fallback provenance overrides
    expect(
      getAlertTrustLabel({
        item_provenance: "generic_fallback",
        confidence_label: "Chain-backed",
        menu_item_source: "heuristic",
      })
    ).toBe(TRUST_LABELS.needs_menu_check);
  });

  test("heuristic_suggestion provenance => Estimated (not Chain-backed)", () => {
    expect(
      getAlertTrustLabel({
        item_provenance: "heuristic_suggestion",
        confidence_label: "Chain-backed",
        menu_item_source: "ingested_chain_item",
      })
    ).toBe(TRUST_LABELS.estimated);
  });

  test("exact_menu provenance => Verified", () => {
    expect(
      getAlertTrustLabel({
        item_provenance: "exact_menu",
        menu_item_source: "real_menu",
      })
    ).toBe(TRUST_LABELS.verified);
  });

  test("badge is item-level: same venue, different item provenance => different badges", () => {
    const sameVenue = { covered_chain_key: "kfc", menu_item_source: "ingested_chain_item" };
    const withExact = { ...sameVenue, item_provenance: "exact_chain_menu" };
    const withSuggestion = { ...sameVenue, item_provenance: "heuristic_suggestion" };
    expect(getAlertTrustLabel(withExact)).toBe(TRUST_LABELS.chain_backed);
    expect(getAlertTrustLabel(withSuggestion)).toBe(TRUST_LABELS.estimated);
  });
});

describe("inbox and push consistency", () => {
  test("F. same signals produce same trust label (API vs push payload)", () => {
    const apiCandidate = {
      place_id: "ChIJ123",
      alert_type: "protein_rescue",
      best_item_name: "6-inch Grilled Chicken",
      confidence_label: "Chain-backed",
      menu_item_source: "ingested_chain_item",
      chosen_candidate_specificity_tier: "chain_registry",
    };
    const pushPayload = {
      place_id: "ChIJ123",
      alert_type: "protein_rescue",
      best_item_name: "6-inch Grilled Chicken",
      confidence_label: "Chain-backed",
      menu_item_source: "ingested_chain_item",
      chosen_candidate_specificity_tier: "chain_registry",
    };
    expect(getAlertTrustLabel(apiCandidate)).toBe(getAlertTrustLabel(pushPayload));
    expect(getAlertTrustLabel(apiCandidate)).toBe(TRUST_LABELS.chain_backed);
  });
});
