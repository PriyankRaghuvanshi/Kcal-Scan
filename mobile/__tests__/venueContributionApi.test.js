const {
  buildVenueContributionPayload,
} = require("../utils/venueContributionApi.js");

describe("venueContributionApi payload", () => {
  const basePlace = {
    place_id: "abc123",
    place_name: "Test Cafe",
    area_key: "parramatta",
    best_item_name: "Grilled chicken salad",
  };

  test("buildVenueContributionPayload returns null without place_name or area_key", () => {
    expect(
      buildVenueContributionPayload({
        place: { place_name: "", area_key: "" },
        userId: "u1",
        contributionType: "better_order_suggestion",
      })
    ).toBeNull();
  });

  test("buildVenueContributionPayload includes core fields", () => {
    const out = buildVenueContributionPayload({
      place: basePlace,
      userId: "user-1",
      contributionType: "better_order_suggestion",
      suggestedItemText: "Falafel bowl",
      sourceSurface: "healthy_nearby_map",
      dietContext: { goal: "fat_loss" },
    });
    expect(out.place_id).toBe("abc123");
    expect(out.place_name).toBe("Test Cafe");
    expect(out.area_key).toBe("parramatta");
    expect(out.contribution_type).toBe("better_order_suggestion");
    expect(out.user_id).toBe("user-1");
    expect(out.payload.source_surface).toBe("healthy_nearby_map");
    expect(out.payload.suggested_item_text).toBe("Falafel bowl");
    expect(out.payload.current_recommended_item).toBe("Grilled chicken salad");
  });
});

