/**
 * Tests for Smart Alert local state (settings, dedupe, suppression).
 * Run with: npx jest mobile/__tests__/smartAlertState.test.js
 */

// Mock AsyncStorage
const storage = {};
jest.mock("@react-native-async-storage/async-storage", () => ({
  getItem: jest.fn((k) => Promise.resolve(storage[k] ?? null)),
  setItem: jest.fn((k, v) => {
    storage[k] = v;
    return Promise.resolve();
  }),
}));

const {
  getAlertId,
  getSmartAlertState,
  updateSmartAlertSettings,
  shouldShowAlert,
  filterCandidatesForDisplay,
  recordAlertOpened,
  recordAlertDismissed,
  _resetCache,
} = require("../smartAlertState.js");

beforeEach(async () => {
  _resetCache();
  Object.keys(storage).forEach((k) => delete storage[k]);
});

describe("getAlertId", () => {
  test("creates deterministic ID from alert_type place_id best_item_name and date", () => {
    const c = {
      alert_type: "protein_rescue",
      place_id: "place_123",
      best_item_name: "Grilled Chicken Salad",
    };
    const id = getAlertId(c);
    expect(id).toContain("protein_rescue");
    expect(id).toContain("place_123");
    expect(id).toContain("Grilled Chicken Salad");
    expect(id).toMatch(/\d{4}-\d{2}-\d{2}/);
    expect(getAlertId(c)).toBe(id);
  });

  test("handles missing fields", () => {
    expect(getAlertId(null)).toBe("");
    expect(getAlertId({})).not.toBe("");
  });
});

describe("getSmartAlertState and updateSmartAlertSettings", () => {
  test("returns default state when empty", async () => {
    const state = await getSmartAlertState();
    expect(state.enabled).toBe(false);
    expect(state.frequency_mode).toBe("smart_only");
    expect(state.categories).toHaveProperty("protein_rescue", true);
  });

  test("updateSmartAlertSettings persists enabled", async () => {
    const next = await updateSmartAlertSettings({ enabled: true });
    expect(next.enabled).toBe(true);
    _resetCache();
    const loaded = await getSmartAlertState();
    expect(loaded.enabled).toBe(true);
  });

  test("updateSmartAlertSettings persists categories", async () => {
    await updateSmartAlertSettings({
      categories: { protein_rescue: false, habit_rescue: false },
    });
    _resetCache();
    const state = await getSmartAlertState();
    expect(state.categories.protein_rescue).toBe(false);
    expect(state.categories.habit_rescue).toBe(false);
  });

  test("updateSmartAlertSettings persists frequency_mode", async () => {
    await updateSmartAlertSettings({ frequency_mode: "low" });
    _resetCache();
    const state = await getSmartAlertState();
    expect(state.frequency_mode).toBe("low");
  });
});

describe("shouldShowAlert", () => {
  test("returns false when disabled", () => {
    const state = { enabled: false, categories: {}, frequency_mode: "smart_only" };
    const c = { alert_type: "protein_rescue", place_id: "p1", best_item_name: "x" };
    expect(shouldShowAlert(c, state)).toBe(false);
  });

  test("returns false when category off", async () => {
    await updateSmartAlertSettings({ enabled: true, categories: { protein_rescue: false } });
    const state = await getSmartAlertState();
    const c = { alert_type: "protein_rescue", place_id: "p1", best_item_name: "x" };
    expect(shouldShowAlert(c, state)).toBe(false);
  });

  test("returns false when alert was dismissed", async () => {
    await updateSmartAlertSettings({ enabled: true });
    const state = await getSmartAlertState();
    const c = { alert_type: "protein_rescue", place_id: "p1", best_item_name: "Salad" };
    const aid = getAlertId(c);
    state.dismissed_alert_ids = [aid];
    expect(shouldShowAlert(c, state)).toBe(false);
  });

  test("returns false when venue recently suppressed", async () => {
    await updateSmartAlertSettings({ enabled: true });
    const state = await getSmartAlertState();
    state.suppressed_venues_recent = { p1: Date.now() - 1000 }; // 1 sec ago
    const c = { alert_type: "protein_rescue", place_id: "p1", best_item_name: "x" };
    expect(shouldShowAlert(c, state)).toBe(false);
  });

  test("returns true when enabled and category on and not dismissed", async () => {
    await updateSmartAlertSettings({ enabled: true });
    const state = await getSmartAlertState();
    const c = { alert_type: "protein_rescue", place_id: "p1", best_item_name: "x" };
    expect(shouldShowAlert(c, state)).toBe(true);
  });
});

describe("filterCandidatesForDisplay", () => {
  test("filters by shouldShowAlert", async () => {
    await updateSmartAlertSettings({ enabled: true, categories: { protein_rescue: true, habit_rescue: false } });
    const state = await getSmartAlertState();
    const candidates = [
      { alert_type: "protein_rescue", place_id: "p1", best_item_name: "a" },
      { alert_type: "habit_rescue", place_id: "p2", best_item_name: "b" },
    ];
    const out = filterCandidatesForDisplay(candidates, state);
    expect(out).toHaveLength(1);
    expect(out[0].alert_type).toBe("protein_rescue");
  });
});

describe("recordAlertOpened and recordAlertDismissed", () => {
  test("recordAlertOpened adds to opened_alert_ids and suppressed_venues_recent", async () => {
    await updateSmartAlertSettings({ enabled: true });
    await recordAlertOpened("alert-1", "place-1");
    _resetCache();
    const state = await getSmartAlertState();
    expect(state.opened_alert_ids).toContain("alert-1");
    expect(state.suppressed_venues_recent["place-1"]).toBeDefined();
    expect(typeof state.last_alert_opened_at).toBe("number");
  });

  test("recordAlertDismissed adds to dismissed_alert_ids and increments ignored_streak_local", async () => {
    await updateSmartAlertSettings({ enabled: true });
    await recordAlertDismissed("alert-2", "place-2");
    _resetCache();
    const state = await getSmartAlertState();
    expect(state.dismissed_alert_ids).toContain("alert-2");
    expect(state.ignored_streak_local).toBe(1);
  });
});
