const { safeOpsActionResult } = require("../adminOpsApi.js");
const { safeGetOpsDashboardSummary } = require("../startupSafety.js");

describe("admin ops defensive parsing", () => {
  test("safeGetOpsDashboardSummary handles partial payload", () => {
    const out = safeGetOpsDashboardSummary({
      enrichment: { weak_suburbs: [{ area_key: "x" }] },
      push: null,
    });
    expect(Array.isArray(out.enrichment.weak_suburbs)).toBe(true);
    expect(Array.isArray(out.enrichment.next_targets)).toBe(true);
    expect(out.push).toEqual({});
    expect(out.scan).toEqual({});
  });

  test("safeOpsActionResult tolerates invalid action payload", () => {
    expect(safeOpsActionResult(null)).toEqual({});
    expect(safeOpsActionResult("bad")).toEqual({});
    expect(safeOpsActionResult({ ok: true })).toEqual({ ok: true });
  });
});
