const {
  safeParseJson,
  safeArray,
  safeObject,
  safeGetSmartAlertPayload,
  safeGetOpsDashboardSummary,
} = require("../startupSafety.js");

describe("startupSafety", () => {
  test("safeParseJson returns fallback on bad JSON", () => {
    expect(safeParseJson("{bad", { ok: false }, "x")).toEqual({ ok: false });
  });

  test("safeArray returns [] for non-array", () => {
    expect(safeArray(null)).toEqual([]);
    expect(safeArray({})).toEqual([]);
    expect(safeArray([1, 2])).toEqual([1, 2]);
  });

  test("safeObject returns fallback for non-object", () => {
    expect(safeObject(null, { x: 1 })).toEqual({ x: 1 });
    expect(safeObject("abc", { x: 1 })).toEqual({ x: 1 });
    expect(safeObject({ a: 1 }, {})).toEqual({ a: 1 });
  });

  test("safeGetSmartAlertPayload tolerates malformed payload", () => {
    const out = safeGetSmartAlertPayload({
      alert_id: 123,
      place_id: null,
      place_lat: "-33.9",
      place_lng: "abc",
      route_target: "",
      confidence_label: { any: "thing" },
    });
    expect(out.alert_id).toBe("123");
    expect(out.place_id).toBe("");
    expect(out.place_lat).toBe(-33.9);
    expect(out.place_lng).toBeNull();
    expect(out.route_target).toBe("smart_alert_inbox");
    expect(out.confidence_label).toBe("[object Object]");
  });

  test("safeGetOpsDashboardSummary returns stable sections", () => {
    const out = safeGetOpsDashboardSummary({ push: { rollout_mode: "off" } });
    expect(Array.isArray(out.enrichment.weak_suburbs)).toBe(true);
    expect(Array.isArray(out.enrichment.next_targets)).toBe(true);
    expect(out.push.rollout_mode).toBe("off");
    expect(out.scan).toEqual({});
  });
});
