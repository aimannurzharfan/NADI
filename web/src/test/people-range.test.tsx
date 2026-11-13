// The People card (docs/design/PLAN.md, final review U3, U4, U9): its range helpers, the series of the chart and
// what the card shows in each state.
import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import { PeopleCard, occupiedText, peopleSeries, peopleTicks, sinceOf, sinceText } from "@/components/overview/people-chart";
import { ApiError } from "@/lib/api";
import { PEOPLE_BUCKET_S, PEOPLE_MINUTES, PEOPLE_RANGES, pickRange, peopleRefetchMs, storeRange, storedRange } from "@/lib/people-range";
import type { People, Room } from "@/lib/types";

const NOW = 1_800_000_000;
const room = (extra: Partial<Room> = {}): Room => ({
  room_id: "room1", name: "Demo Room", headcount: 1, at_least: false, counter: "csi", count_ts: NOW - 3, temp_c: 24, humidity: 60,
  live: true, waste: null, ...extra,
});
const people = (bucket: number, points: [number, number, number][], since: People["since"] = null): People =>
  ({ now: NOW, bucket_s: bucket, room_id: "room1", people: points, since });
const SIZE = { width: 640, height: 220 };

describe("people range", () => {
  it("takes the address, then this browser, then the last hour; ignores what it does not know", () => {
    expect(PEOPLE_RANGES).toEqual(["1h", "24h", "7d", "30d"]);
    expect(pickRange("7d", "1h")).toBe("7d");
    expect(pickRange(null, "24h")).toBe("24h");
    expect(pickRange("90d", null)).toBe("1h");
    expect(pickRange("5m", null)).toBe("1h");  // the range the card no longer has
  });

  it("keeps the choice in this browser, drops a stored range it no longer has, and does without when storage is blocked", () => {
    storeRange("30d");
    expect(storedRange()).toBe("30d");
    localStorage.setItem("nadiSignalRange", "5m");
    expect(storedRange()).toBeNull();
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => { throw new DOMException("blocked", "SecurityError"); });
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => { throw new DOMException("full", "QuotaExceededError"); });
    expect(storedRange()).toBeNull();
    expect(() => storeRange("1h")).not.toThrow();
    vi.restoreAllMocks();
  });

  it("asks for a point a minute, 30 minutes, 3 hours or a day, and never again faster than one of them (5 minutes at most)", () => {
    expect(PEOPLE_RANGES.map((r) => PEOPLE_BUCKET_S[r])).toEqual([60, 1800, 10800, 86400]);
    expect(PEOPLE_MINUTES["30d"]).toBe(30 * 24 * 60);
    expect(peopleRefetchMs("1h")).toBe(20_000);
    expect(peopleRefetchMs("24h")).toBe(300_000);
    expect(peopleRefetchMs("30d")).toBe(300_000);
  });
});

describe("people series", () => {
  it("has a point for every stretch, null where there was no report (a gap, never 0)", () => {
    const hour = NOW - (NOW % 1800);
    const s = peopleSeries(people(1800, [[hour - 3 * 1800, 3, 20], [hour - 1800, 1, 4]]), 6 * 30);
    expect(s.points.slice(-4).map((p) => p.n)).toEqual([3, null, 1, null]);
    expect(s.points.every((p, i) => i === 0 || p.ts - s.points[i - 1].ts === 1800)).toBe(true);
    expect(s.max).toBe(3);
  });

  it("marks a lone point between two gaps, so it can be drawn as a dot", () => {
    const m = NOW - (NOW % 60);
    const s = peopleSeries(people(60, [[m - 600, 1, 1], [m - 120, 1, 1], [m - 60, 2, 1]]), 60);
    const lone = s.points.filter((p) => p.lone).map((p) => p.ts);
    expect(lone).toEqual([m - 600]);
  });

  it("starts at the first report when the range reaches back further, and says from when", () => {
    const day = NOW - ((NOW + 8 * 3600) % 86400);  // midnight Malaysia time
    const s = peopleSeries(people(86400, [[day - 2 * 86400, 4, 300], [day, 1, 20]]), 30 * 24 * 60);
    expect(s.dataFrom).toBe(day - 2 * 86400);
    expect(s.points.every((p) => (p.ts + 8 * 3600) % 86400 === 0)).toBe(true);  // daily points on Malaysian midnights
    expect(s.points.length).toBe(6);  // never fewer than six stretches: one report is not a chart of one point
    expect(s.points[s.points.length - 1].ts).toBe(day);
    // data for the whole range: no note, and the chart spans the range
    const full = peopleSeries(people(86400, Array.from({ length: 31 }, (_, i) => [day - (30 - i) * 86400, 1, 5] as [number, number, number])), 30 * 24 * 60);
    expect(full.dataFrom).toBeNull();
    expect(full.points.length).toBe(31);
  });

  it("uses whole-number ticks, at most six, that reach the capacity", () => {
    expect(peopleTicks(0)).toEqual([0, 1, 2]);
    expect(peopleTicks(7)).toEqual([0, 2, 4, 6, 8]);
    expect(peopleTicks(30)).toEqual([0, 10, 20, 30]);
    expect(peopleTicks(1000)).toEqual([0, 200, 400, 600, 800, 1000]);
    for (const max of [1, 3, 12, 47, 120, 999]) {
      const t = peopleTicks(max);
      expect(t.every(Number.isInteger) && t.length <= 6 && t[t.length - 1] >= max).toBe(true);
    }
  });

  it("words the time occupied and the time of the last change", () => {
    expect(occupiedText(45)).toBe("45 min");
    expect(occupiedText(125)).toBe("2 h 5 min");
    expect(sinceText(NOW - 600, NOW)).toMatch(/^\d\d:\d\d$/);
    expect(sinceText(NOW - 3 * 86400, NOW)).toMatch(/^\d{1,2} \w+, \d\d:\d\d$/);
  });

  it("gives 'since' only while the live count agrees with the stored reports", () => {
    const since = (occupied: boolean, ts: number | null = NOW - 600) => people(60, [], { occupied, ts });
    expect(sinceOf(room({ headcount: 1 }), since(true))).toBe(NOW - 600);
    expect(sinceOf(room({ headcount: 0 }), since(false))).toBe(NOW - 600);
    expect(sinceOf(room({ headcount: 1 }), since(false))).toBeNull();     // filled a moment ago
    expect(sinceOf(room({ live: false }), since(true))).toBeNull();       // offline: the count is unknown
    expect(sinceOf(room(), since(true, null))).toBeNull();                // unchanged for longer than the look back
    expect(sinceOf(room({ room_id: "room2" }), since(true))).toBeNull();  // another room's answer
  });
});

describe("people card", () => {
  beforeEach(() => vi.stubGlobal("ResizeObserver", class { observe() {} unobserve() {} disconnect() {} }));
  afterEach(() => vi.unstubAllGlobals());
  const m = NOW - (NOW % 60);
  const hour = people(60, [[m - 180, 0, 0], [m - 120, 1, 1], [m - 60, 2, 1], [m, 1, 1]], { occupied: true, ts: NOW - 150 });
  const card = (props: Partial<Parameters<typeof PeopleCard>[0]> = {}) => render(
    <MemoryRouter><PeopleCard room={room()} people={hour} range="1h" onRange={() => {}} size={SIZE} {...props} /></MemoryRouter>);

  it("has a title, the room's count now with 'since', the range and a link to the room, and draws a line with a light fill", () => {
    const { container } = card({ roomLink: "/floor?room=room1", rooms: [{ id: "room1", name: "Demo Room" }], selected: "room1", onSelect: () => {} });
    expect(screen.getByRole("heading", { name: "People" })).toBeInTheDocument();
    expect(container.querySelector("[data-people-now]")).toHaveTextContent(/^Now 1 · since \d\d:\d\d$/);
    expect(screen.getByRole("link", { name: "Room details" })).toHaveAttribute("href", "/floor?room=room1");
    expect(screen.getByRole("combobox", { name: "Room shown" })).toHaveValue("room1");
    expect(screen.getByRole("figure")).toHaveAccessibleName("People in Demo Room over the last hour: at most 2 at once.");
    const line = container.querySelector(".recharts-area-curve") as SVGPathElement;
    expect(line.getAttribute("d")).toMatch(/C/);                 // a smooth curve, no vertical steps
    expect(container.querySelector(".recharts-area-area")).toHaveAttribute("fill-opacity", "0.12");
    expect(container.querySelector("[data-capacity]")).toBeNull();  // no capacity on the plan: no line
    expect(container.querySelector("[data-data-from]")).toHaveTextContent(/^Data from \d\d:\d\d$/);  // four minutes of an hour
  });

  it("draws the capacity as a dashed line that names itself on hover or focus, and reaches it with the scale", () => {
    const { container } = card({ capacity: 30 });
    const line = container.querySelector("[data-capacity]") as SVGGElement;
    expect(line).toHaveAccessibleName("Capacity 30");
    expect(line.querySelector("line")).toHaveAttribute("stroke-dasharray");
    expect(container.querySelector("[data-capacity-tip]")).toBeNull();
    fireEvent.focus(line);
    expect(container.querySelector("[data-capacity-tip]")).toHaveTextContent("Capacity 30");
    fireEvent.blur(line);
    expect(container.querySelector("[data-capacity-tip]")).toBeNull();
    const ticks = [...container.querySelectorAll(".recharts-yAxis .recharts-cartesian-axis-tick-value")].map((t) => t.textContent);
    expect(ticks).toEqual(["0", "10", "20", "30"]);
    expect(screen.getByRole("figure")).toHaveAccessibleName("People in Demo Room over the last hour: at most 2 at once. Capacity 30.");
  });

  it("says in words why a room has no chart: no sensor, no report yet, nothing in the range", () => {
    const { container, unmount } = card({ room: undefined, people: undefined, none: "no_sensor" });
    expect(screen.getByText("No sensor in this room")).toBeInTheDocument();
    expect(container.querySelector("[data-people-chart], [data-people-now]")).toBeNull();
    unmount();
    const second = card({ room: undefined, people: undefined, none: "no_report" });
    expect(screen.getByText("No report from this room yet")).toBeInTheDocument();
    second.unmount();
    card({ people: people(1800, []), range: "24h" });
    expect(screen.getByText("No reports from this room in the last 24 hours.")).toBeInTheDocument();
  });

  it("does not draw another range's or another room's answer while the new one loads", () => {
    const { container } = card({ range: "7d" });  // the answer on hand is the last hour's
    expect(container.querySelector("[data-people-chart]")).toBeNull();
    expect(container.querySelector("[aria-busy=true]")).not.toBeNull();
  });

  it("says the history database is offline instead of drawing nothing", () => {
    card({ people: undefined, error: new ApiError(503, "offline") });
    expect(screen.getByRole("status")).toHaveTextContent("History database offline");
  });

  it("in the room panel leaves the count to the panel's header and always uses the compact range select", () => {
    const { container } = card({ panel: true });
    expect(container.querySelector("[data-people-now]")).toBeNull();
    expect(screen.getByRole("combobox", { name: "Time range" })).toHaveValue("1h");
  });
});
