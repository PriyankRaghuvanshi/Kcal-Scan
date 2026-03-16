/**
 * Tests for Goal Coach utils: preferred mode derivation and filter mapping.
 * Run with: npx jest mobile/__tests__/goalCoachUtils.test.js
 */

const {
  derivePreferredModeFromContext,
  preferredModeToFilterKey,
  PREFERRED_MODES,
  ACTION_OPEN_HEALTHY_NEARBY,
  ACTION_OPEN_SCAN_CAMERA,
} = require("../utils/goalCoachUtils.js");

describe("derivePreferredModeFromContext", () => {
  test("high remaining protein + calories available returns protein_rescue", () => {
    const ctx = { remaining_protein_g: 45, remaining_calories: 600 };
    expect(derivePreferredModeFromContext(ctx, ACTION_OPEN_HEALTHY_NEARBY)).toBe(PREFERRED_MODES.PROTEIN_RESCUE);
  });

  test("calories tight + need protein returns lighter_option", () => {
    const ctx = { remaining_protein_g: 25, remaining_calories: 350 };
    expect(derivePreferredModeFromContext(ctx, ACTION_OPEN_HEALTHY_NEARBY)).toBe(PREFERRED_MODES.LIGHTER_OPTION);
  });

  test("remaining protein >= 35 and calories >= 300 returns protein_rescue", () => {
    expect(derivePreferredModeFromContext({ remaining_protein_g: 35, remaining_calories: 300 }, ACTION_OPEN_HEALTHY_NEARBY)).toBe(PREFERRED_MODES.PROTEIN_RESCUE);
  });

  test("reason includes dinner returns dinner_recovery", () => {
    const ctx = { remaining_protein_g: 20, remaining_calories: 800, reason: "Plan dinner options" };
    expect(derivePreferredModeFromContext(ctx, ACTION_OPEN_HEALTHY_NEARBY)).toBe(PREFERRED_MODES.DINNER_RECOVERY);
  });

  test("reason includes log returns logging_support", () => {
    const ctx = { reason: "Log your meals to stay on track" };
    expect(derivePreferredModeFromContext(ctx, ACTION_OPEN_HEALTHY_NEARBY)).toBe(PREFERRED_MODES.LOGGING_SUPPORT);
  });

  test("non open_healthy_nearby action returns best_fit_today", () => {
    const ctx = { remaining_protein_g: 45, remaining_calories: 600 };
    expect(derivePreferredModeFromContext(ctx, ACTION_OPEN_SCAN_CAMERA)).toBe(PREFERRED_MODES.BEST_FIT_TODAY);
  });

  test("null or empty context returns best_fit_today", () => {
    expect(derivePreferredModeFromContext(null, ACTION_OPEN_HEALTHY_NEARBY)).toBe(PREFERRED_MODES.BEST_FIT_TODAY);
    expect(derivePreferredModeFromContext({}, ACTION_OPEN_HEALTHY_NEARBY)).toBe(PREFERRED_MODES.BEST_FIT_TODAY);
  });
});

describe("preferredModeToFilterKey", () => {
  test("protein_rescue maps to high_protein", () => {
    expect(preferredModeToFilterKey(PREFERRED_MODES.PROTEIN_RESCUE)).toBe("high_protein");
  });

  test("dinner_recovery maps to high_protein", () => {
    expect(preferredModeToFilterKey(PREFERRED_MODES.DINNER_RECOVERY)).toBe("high_protein");
  });

  test("lighter_option maps to under_600", () => {
    expect(preferredModeToFilterKey(PREFERRED_MODES.LIGHTER_OPTION)).toBe("under_600");
  });

  test("logging_support maps to best_right_now", () => {
    expect(preferredModeToFilterKey(PREFERRED_MODES.LOGGING_SUPPORT)).toBe("best_right_now");
  });

  test("best_fit_today maps to fits_today", () => {
    expect(preferredModeToFilterKey(PREFERRED_MODES.BEST_FIT_TODAY)).toBe("fits_today");
  });

  test("unknown mode maps to fits_today", () => {
    expect(preferredModeToFilterKey("unknown")).toBe("fits_today");
  });
});
