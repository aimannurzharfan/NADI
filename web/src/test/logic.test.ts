import { rescueOrder } from "@/components/emergency";
import { countScale, tempScale } from "@/components/charts";
import { change, countOf, duration, shown, statusOf, totals } from "@/lib/format";
import { T, hasKey } from "@/lib/i18n";
import type { Room } from "@/lib/types";

const room = (id: string, headcount: number | null, extra: Partial<Room> = {}): Room => ({
  room_id: id, name: id, headcount, at_least: headcount === 3, count_ts: 100, temp_c: 24, humidity: 60, live: true, waste: null, ...extra,
});

describe("format", () => {
  it("shows 3 as 3+ and missing as a dash", () => {
    expect(shown(3)).toBe("3+");
    expect(shown(2)).toBe("2");
    expect(shown(null)).toBe("–");
  });
  it("shows exact counts up to 100, then 100+, and lower bounds with +", () => {
    expect(shown(3, false)).toBe("3");
    expect(shown(45, false)).toBe("45");
    expect(shown(100, false)).toBe("100");
    expect(shown(101, false)).toBe("100+");
    expect(shown(2, true)).toBe("2+");
  });
  it("never shows a room that is not reporting as empty", () => {
    expect(countOf(room("a", 0, { live: false }))).toBe("?");
    expect(countOf(room("a", 150, { at_least: false }))).toBe("100+");
    const t = totals([room("a", 2), room("b", 0, { live: false }), room("c", 40, { at_least: false })]);
    expect([t.people, t.atLeast, t.unknown.length, t.occupied]).toEqual([42, true, 1, 2]);
    expect(totals([room("a", 2), room("c", 40, { at_least: false })]).atLeast).toBe(false);
  });
  it("scales the headcount axis to 5, 25 or 100", () => {
    expect(countScale(3).top).toBe(5);
    expect(countScale(18).top).toBe(25);
    expect(countScale(60).top).toBe(100);
    expect(countScale(400).top).toBe(100);
  });
  it("gives the temperature axis whole degrees and at least 4 °C", () => {
    const s = tempScale([23.9, 24.0, 24.1]);  // the demo's noise: labels used to read 24.0, 24.0, 23.9, 23.9
    expect(s.hi - s.lo).toBeGreaterThanOrEqual(4);
    expect(s.lo).toBeLessThanOrEqual(23.9);
    expect(s.hi).toBeGreaterThanOrEqual(24.1);
    expect(new Set(s.ticks).size).toBe(s.ticks.length);
    expect(s.ticks.every(Number.isInteger)).toBe(true);
    const wide = tempScale([18.2, 31.7]);
    expect(wide.lo).toBeLessThanOrEqual(18.2);
    expect(wide.hi).toBeGreaterThanOrEqual(31.7);
    expect(wide.ticks.length).toBeLessThanOrEqual(8);
    expect(tempScale([]).ticks.length).toBeGreaterThan(1);
  });
  it("gives each room one status", () => {
    expect(statusOf(room("a", 2))).toBe("ok");
    expect(statusOf(room("a", 0))).toBe("empty");
    expect(statusOf(room("a", 0, { waste: { since: 1, minutes: 12, rm: 0.4 } }))).toBe("waste");
    expect(statusOf(room("a", 2, { live: false }))).toBe("off");
    expect(statusOf(undefined)).toBe("off");
  });
  it("formats durations and changes", () => {
    expect(duration(65)).toBe("1:05");
    expect(duration(3725)).toBe("1:02:05");
    expect(change(4, 1)).toBe(3);
    expect(change(4, null)).toBeNull();
  });
});

describe("rescue order (same rules as the server's 'which room first')", () => {
  it("puts the most people first and offline rooms first on ties", () => {
    const { ranked, zero, total, plus, unknown } = rescueOrder([
      room("hall", 1), room("lab", 3), room("store", 0), room("room3", 1, { live: false }), room("unknown", null),
    ]);
    // rooms not reporting are checked too (unknown, never empty); the total counts reporting rooms only
    expect(ranked.map((r) => r.room_id)).toEqual(["lab", "room3", "hall", "unknown"]);
    expect(zero.map((r) => r.room_id)).toEqual(["store"]);
    expect(total).toBe(4);
    expect(plus).toBe(true);
    expect(unknown.map((r) => r.room_id)).toEqual(["room3", "unknown"]);
  });
});

describe("wording", () => {
  it("fills placeholders and keeps unknown keys visible", () => {
    expect(T("plan.title", { level: "Level 4" })).toBe("Level 4 floor plan");
    expect(T("no.such_key")).toBe("no.such_key");
    expect(T("legend.waste", undefined, "ms")).toBe("Kosong, A/C hidup");
    expect(hasKey("em.export")).toBe(true);
  });
});
