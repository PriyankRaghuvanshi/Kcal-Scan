jest.mock("react-native", () => ({ Platform: { OS: "ios" } }));

const { localCalendarDayToDate } = require("../utils/appleHealth.js");

describe("localCalendarDayToDate", () => {
  test("returns null for invalid input", () => {
    expect(localCalendarDayToDate("")).toBeNull();
    expect(localCalendarDayToDate("2026-1-5")).toBeNull();
    expect(localCalendarDayToDate("04-10-2026")).toBeNull();
  });

  test("interprets YYYY-MM-DD as local calendar day (not UTC parse)", () => {
    const d = localCalendarDayToDate("2026-06-15");
    expect(d).toBeInstanceOf(Date);
    expect(Number.isFinite(d.getTime())).toBe(true);
    expect(d.getFullYear()).toBe(2026);
    expect(d.getMonth()).toBe(5);
    expect(d.getDate()).toBe(15);
    const utcParsed = new Date("2026-06-15");
    expect(d.getTime()).not.toBe(utcParsed.getTime());
  });
});
