/**
 * Tests for lunch decision remaining-line and Weekly Coach summary.
 * Run: npx jest mobile/__tests__/lunchAndWeeklyCoachUtils.test.js
 */

const {
  buildRemainingLine,
  buildWeeklyCoachSummaryLine,
} = require("../utils/lunchAndWeeklyCoachUtils.js");

describe("buildRemainingLine", () => {
  test("uses page-level when card has 0 but page has remaining (fixes contradictory 0)", () => {
    const line = buildRemainingLine({
      pageRemainingCal: 1762,
      pageRemainingProtein: 85,
      cardRemainingCal: 0,
      cardRemainingProtein: null,
      orderCal: null,
      orderProtein: null,
    });
    expect(line).toContain("1762");
    expect(line).toContain("85");
    expect(line).not.toContain("0 kcal");
    expect(line).toBe("Today left: 1762 kcal • 85g protein");
  });

  test("returns null when all sources missing (no 0 from empty fallback)", () => {
    const line = buildRemainingLine({
      pageRemainingCal: null,
      pageRemainingProtein: null,
      cardRemainingCal: null,
      cardRemainingProtein: null,
      orderCal: null,
      orderProtein: null,
    });
    expect(line).toBeNull();
  });

  test("shows After this order when order calories/protein known", () => {
    const line = buildRemainingLine({
      pageRemainingCal: 800,
      pageRemainingProtein: 40,
      cardRemainingCal: null,
      cardRemainingProtein: null,
      orderCal: 450,
      orderProtein: 25,
    });
    expect(line).toContain("After this order");
    expect(line).toContain("350"); // 800 - 450
    expect(line).toContain("15"); // 40 - 25
  });

  test("uses card remaining when card has valid non-zero value", () => {
    const line = buildRemainingLine({
      pageRemainingCal: 500,
      pageRemainingProtein: 30,
      cardRemainingCal: 600,
      cardRemainingProtein: 35,
      orderCal: null,
      orderProtein: null,
    });
    expect(line).toContain("600");
    expect(line).toContain("35");
    expect(line).toBe("Today left: 600 kcal • 35g protein");
  });

  test("shows 0 only when actual calculated remaining is zero (after order)", () => {
    const line = buildRemainingLine({
      pageRemainingCal: 500,
      pageRemainingProtein: 20,
      cardRemainingCal: null,
      cardRemainingProtein: null,
      orderCal: 500,
      orderProtein: 20,
    });
    expect(line).toContain("After this order");
    expect(line).toContain("0 kcal");
    expect(line).toContain("0g protein");
  });
});

describe("buildWeeklyCoachSummaryLine", () => {
  test("no days logged shows honest zero-state", () => {
    const line = buildWeeklyCoachSummaryLine({
      onTrackDays: 0,
      trackedDays: 0,
      avgProtein: 0,
      todayInProgress: false,
    });
    expect(line).toBe("No days logged this week yet");
  });

  test("one logged meal but no completed full-day shows in-progress messaging", () => {
    const line = buildWeeklyCoachSummaryLine({
      onTrackDays: 0,
      trackedDays: 2,
      avgProtein: 45,
      todayInProgress: true,
    });
    expect(line).toContain("0/2 days on track");
    expect(line).toContain("Today is still in progress");
    expect(line).toContain("Avg protein 45g");
  });

  test("distinguishes logged vs on-track when both exist", () => {
    const line = buildWeeklyCoachSummaryLine({
      onTrackDays: 2,
      trackedDays: 4,
      avgProtein: 120,
      todayInProgress: false,
    });
    expect(line).toContain("2/4 days on track");
    expect(line).not.toContain("Today is still in progress");
    expect(line).toContain("Avg protein 120g");
  });

  test("does not show in-progress when today has no logged meals", () => {
    const line = buildWeeklyCoachSummaryLine({
      onTrackDays: 0,
      trackedDays: 2,
      avgProtein: 50,
      todayInProgress: false,
    });
    expect(line).toContain("0/2 days on track");
    expect(line).not.toContain("Today is still in progress");
  });

  test("does not show in-progress when some days on track", () => {
    const line = buildWeeklyCoachSummaryLine({
      onTrackDays: 1,
      trackedDays: 3,
      avgProtein: 90,
      todayInProgress: true,
    });
    expect(line).toContain("1/3 days on track");
    expect(line).not.toContain("Today is still in progress");
  });
});
