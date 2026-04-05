/**
 * Tests for Smart Food Alerts API helper.
 * Run with: npx jest mobile/__tests__/smartAlertsApi.test.js
 */

// Mock fetch
const mockFetch = jest.fn();
global.fetch = mockFetch;

const {
  buildSmartAlertFetchParams,
  fetchSmartFoodAlertCandidates,
  fetchEligibleSmartAlerts,
} = require("../smartAlertsApi.js");

beforeEach(() => {
  mockFetch.mockReset();
});

describe("buildSmartAlertFetchParams", () => {
  test("includes userId lat lng", () => {
    const out = buildSmartAlertFetchParams({
      userId: "u123",
      lat: 37.7,
      lng: -122.4,
    });
    expect(out.user_id).toBe("u123");
    expect(out.lat).toBe(37.7);
    expect(out.lng).toBe(-122.4);
  });

  test("includes remainingCalories and remainingProteinG", () => {
    const out = buildSmartAlertFetchParams({
      lat: 1,
      lng: 2,
      remainingCalories: 800,
      remainingProteinG: 35,
    });
    expect(out.remaining_calories).toBe(800);
    expect(out.remaining_protein_g).toBe(35);
  });

  test("includes goal and ignoredStreak", () => {
    const out = buildSmartAlertFetchParams({
      lat: 1,
      lng: 2,
      goal: "fat_loss",
      ignoredStreak: 3,
    });
    expect(out.goal).toBe("fat_loss");
    expect(out.ignored_streak).toBe(3);
  });

  test("handles context flags", () => {
    const out = buildSmartAlertFetchParams({
      lat: 1,
      lng: 2,
      postWorkout: true,
      lateNight: true,
    });
    expect(out.post_workout).toBe(true);
    expect(out.late_night).toBe(true);
  });

  test("passes diet_preference through", () => {
    const out = buildSmartAlertFetchParams({
      lat: 1,
      lng: 2,
      diet_preference: "vegetarian",
    });
    expect(out.diet_preference).toBe("vegetarian");
  });

  test("invalid context returns safe defaults", () => {
    const out = buildSmartAlertFetchParams(null);
    expect(typeof out).toBe("object");
    expect(out.user_id).toBe("");
    expect(out.lat).toBeUndefined();
  });
});

describe("fetchSmartFoodAlertCandidates", () => {
  test("returns empty when params invalid", async () => {
    const out = await fetchSmartFoodAlertCandidates(null);
    expect(out.candidates).toEqual([]);
    expect(out.placesConsidered).toBe(0);
    expect(mockFetch).not.toHaveBeenCalled();
  });

  test("returns empty when lat/lng missing", async () => {
    const out = await fetchSmartFoodAlertCandidates({ user_id: "u1" });
    expect(out.candidates).toEqual([]);
    expect(mockFetch).not.toHaveBeenCalled();
  });

  test("normalizes API response shape", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        candidates: [
          { place_id: "p1", alert_type: "protein_rescue", best_item_name: "Grilled Chicken" },
          { place_id: "p2", alert_type: "worked_before_repeat" },
        ],
        places_considered: 12,
      }),
    });

    const out = await fetchSmartFoodAlertCandidates({
      lat: 37.7,
      lng: -122.4,
      diet_preference: "vegan",
    });
    expect(out.candidates).toHaveLength(2);
    expect(out.candidates[0].place_id).toBe("p1");
    expect(out.placesConsidered).toBe(12);
    expect(mockFetch.mock.calls[0][0]).toContain("diet_preference=vegan");
  });

  test("uses eligible_only=true when requested", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ candidates: [], places_considered: 0 }),
    });

    await fetchEligibleSmartAlerts({ lat: 37.7, lng: -122.4 });
    expect(mockFetch).toHaveBeenCalledTimes(1);
    expect(mockFetch.mock.calls[0][0]).toContain("eligible_only=true");
  });

  test("calls appendQuery when provided", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ candidates: [], places_considered: 0 }),
    });

    const appendQuery = (url) => url + "&tz=America/Los_Angeles";
    await fetchSmartFoodAlertCandidates({ lat: 1, lng: 2 }, false, appendQuery);
    expect(mockFetch.mock.calls[0][0]).toContain("tz=America/Los_Angeles");
  });

  test("handles network error gracefully", async () => {
    mockFetch.mockRejectedValueOnce(new Error("network fail"));
    const out = await fetchSmartFoodAlertCandidates({ lat: 37.7, lng: -122.4 });
    expect(out.candidates).toEqual([]);
    expect(out.placesConsidered).toBe(0);
  });
});
