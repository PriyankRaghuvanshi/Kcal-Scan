/**
 * Tests for push notification helpers.
 * Run with: npx jest mobile/__tests__/pushNotifications.test.js
 */

// Mock expo-notifications
jest.mock("expo-notifications", () => ({
  getPermissionsAsync: jest.fn(),
  requestPermissionsAsync: jest.fn(),
  getExpoPushTokenAsync: jest.fn(),
  addNotificationReceivedListener: jest.fn(() => ({ remove: jest.fn() })),
  addNotificationResponseReceivedListener: jest.fn(() => ({ remove: jest.fn() })),
  AndroidImportance: { MAX: 5 },
}));

// Mock expo-constants
jest.mock("expo-constants", () => ({
  expoConfig: { extra: { eas: { projectId: "test-project-id" } }, version: "1.0.3" },
  easConfig: { projectId: "test-project-id" },
}));

// Mock expo-device
jest.mock("expo-device", () => ({ isDevice: true }));

// Mock fetch for backend calls
const mockFetch = jest.fn();
global.fetch = mockFetch;

const {
  parseSmartAlertNotificationData,
  cleanupNotificationListeners,
  setupNotificationListeners,
} = require("../pushNotifications.js");

describe("parseSmartAlertNotificationData", () => {
  test("extracts expected fields", () => {
    const data = {
      alert_type: "protein_rescue",
      place_id: "ChIJ...",
      place_name: "Chipotle",
      best_item_name: "Chicken Bowl",
      alert_id: "alert-1",
      display_rank_score_100: 85,
    };
    const out = parseSmartAlertNotificationData(data);
    expect(out.alert_type).toBe("protein_rescue");
    expect(out.place_id).toBe("ChIJ...");
    expect(out.place_name).toBe("Chipotle");
    expect(out.best_item_name).toBe("Chicken Bowl");
    expect(out.alert_id).toBe("alert-1");
    expect(out.display_rank_score_100).toBe(85);
  });

  test("handles null/empty", () => {
    expect(parseSmartAlertNotificationData(null)).toEqual({});
    expect(parseSmartAlertNotificationData({})).toEqual({
      alert_type: "",
      place_id: "",
      place_name: "",
      best_item_name: "",
      deep_link: "",
      alert_id: "",
      display_rank_score_100: null,
      context_mode: "",
    });
  });
});

describe("setupNotificationListeners", () => {
  test("returns subscriptions when callbacks provided", () => {
    const onReceived = jest.fn();
    const onResponse = jest.fn();
    const subs = setupNotificationListeners({
      onNotificationReceived: onReceived,
      onNotificationResponse: onResponse,
    });
    expect(subs).not.toBeNull();
    expect(subs.received).toBeDefined();
    expect(subs.response).toBeDefined();
    expect(typeof subs.received?.remove).toBe("function");
    expect(typeof subs.response?.remove).toBe("function");
  });

  test("returns null on invalid opts", () => {
    const subs = setupNotificationListeners({});
    expect(subs).not.toBeNull();
    expect(subs.received).toBeNull();
    expect(subs.response).toBeNull();
  });
});

describe("cleanupNotificationListeners", () => {
  test("calls remove on subscriptions", () => {
    const remove1 = jest.fn();
    const remove2 = jest.fn();
    cleanupNotificationListeners({
      received: { remove: remove1 },
      response: { remove: remove2 },
    });
    expect(remove1).toHaveBeenCalled();
    expect(remove2).toHaveBeenCalled();
  });

  test("handles null", () => {
    expect(() => cleanupNotificationListeners(null)).not.toThrow();
  });
});
