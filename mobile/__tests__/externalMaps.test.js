/**
 * Tests for external map URL generation.
 */

jest.mock("react-native", () => ({
  Platform: { OS: "ios" },
  Linking: {},
  Alert: {},
}));

const { buildGoogleMapsDirectionsUrl } = require("../externalMaps.js");

describe("buildGoogleMapsDirectionsUrl", () => {
  test("builds valid Google Maps directions URL", () => {
    const url = buildGoogleMapsDirectionsUrl(37.7749, -122.4194);
    expect(url).toContain("https://www.google.com/maps/dir/");
    expect(url).toContain("destination=37.7749,-122.4194");
    expect(url).toContain("api=1");
  });

  test("handles negative coordinates", () => {
    const url = buildGoogleMapsDirectionsUrl(-33.8688, 151.2093);
    expect(url).toContain("destination=-33.8688,151.2093");
  });
});
