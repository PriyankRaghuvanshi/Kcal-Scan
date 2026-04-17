/**
 * Google Maps key gating: empty / missing config must not count as configured.
 */

const mockExpoConfig = {};

jest.mock("expo-constants", () => ({
  __esModule: true,
  default: {
    get expoConfig() {
      return mockExpoConfig;
    },
  },
}));

const {
  getGoogleMapsApiKeyFromExpoConfig,
  hasGoogleMapsKeyForNativeMap,
} = require("../utils/googleMapsConfig.js");

describe("googleMapsConfig", () => {
  beforeEach(() => {
    mockExpoConfig.android = undefined;
    mockExpoConfig.extra = undefined;
  });

  test("hasGoogleMapsKeyForNativeMap is false when no key", () => {
    expect(hasGoogleMapsKeyForNativeMap()).toBe(false);
    expect(getGoogleMapsApiKeyFromExpoConfig()).toBe("");
  });

  test("reads android.config.googleMaps.apiKey", () => {
    mockExpoConfig.android = { config: { googleMaps: { apiKey: "  k1  " } } };
    expect(getGoogleMapsApiKeyFromExpoConfig()).toBe("k1");
    expect(hasGoogleMapsKeyForNativeMap()).toBe(true);
  });

  test("reads extra.GOOGLE_MAPS_API_KEY when android key absent", () => {
    mockExpoConfig.extra = { GOOGLE_MAPS_API_KEY: "k2" };
    expect(getGoogleMapsApiKeyFromExpoConfig()).toBe("k2");
    expect(hasGoogleMapsKeyForNativeMap()).toBe(true);
  });

  test("whitespace-only keys are ignored", () => {
    mockExpoConfig.android = { config: { googleMaps: { apiKey: "   " } } };
    expect(hasGoogleMapsKeyForNativeMap()).toBe(false);
  });
});
