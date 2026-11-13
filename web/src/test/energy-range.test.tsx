// The Energy page's period (docs/design/PLAN.md, Part 27): Today / 7 days / 30 days at the top drives the figures and
// the chart and the room list; kept in the address and in this browser (and still works when the browser keeps nothing).
// Final review U8 and U9: one chart of the waste over time, the rooms as a ranked list whose rows filter the chart,
// and a day chart that starts at the first day with data.
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter, useLocation } from "react-router-dom";

import { TooltipProvider } from "@/components/ui/tooltip";
import { ENERGY_RANGE_KEY, changeText, pickEnergyRange, storedEnergyRange } from "@/lib/energy-range";
import { T } from "@/lib/i18n";
import type { EnergyPeriod } from "@/lib/types";
import { EnergyPage } from "@/pages/energy";

const NOW = 1_794_470_400;  // 13 Nov 2026, 8 pm Malaysia time
const A = (rm: number) => ({ rm, kwh: rm * 3, co2_kg: rm * 2 });

function period(id: EnergyPeriod["id"], total: number, previous: number | null, room: string | null = null, firstDay = 0): EnergyPeriod {
  const one = (room_id: string, name: string, rm: number) => ({ room_id, name, rm, kwh: Math.round(rm * 30) / 10, hours: Math.round(rm * 3) / 10 });
  const rooms = [one("room1", "Lab 2", total * 0.25), one("room2", "Hall A", total * 0.75), one("room3", "Room 3", 0)];
  const series: EnergyPeriod["series"] = id === "today"
    ? { unit: "hour", points: Array.from({ length: 24 }, (_, h) => ({ ts: NOW - 20 * 3600 + h * 3600, rm: h > 20 ? null : 0.1 })) }
    : { unit: "day", points: Array.from({ length: id === "7d" ? 7 : 30 }, (_, i) => ({ day: `2026-11-${String(i + 1).padStart(2, "0")}`, rm: i < firstDay ? null : 1 })) };
  return { id, days: id === "today" ? 1 : id === "7d" ? 7 : 30, total: A(total), previous: previous == null ? null : A(previous), by_room: rooms, series,
    series_room: room, first_ts: null };
}

function show(at: string, setup?: (qc: QueryClient, base: Record<string, unknown>) => void) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false, staleTime: Infinity, refetchInterval: false } } });
  const base = { now: NOW, today: A(1), week: A(7), previous_week: A(5), yesterday: A(1), daily: [], by_room: [], tariff_rm_per_kwh: 0.2983,
    ac_kw: 10, co2_kg_per_kwh: 0.75, stale_ts: null, rate_changes: [] };
  qc.setQueryData(["energy", "today", ""], { ...base, range: period("today", 2.4, 1.4) });
  qc.setQueryData(["energy", "7d", ""], { ...base, range: period("7d", 7, 7) });
  qc.setQueryData(["energy", "30d", ""], { ...base, range: period("30d", 32, null) });
  setup?.(qc, base);
  qc.setQueryData(["me"], { admin: false, who: null, rule: "token", viewer: true, viewer_required: false });
  qc.setQueryData(["info", "en"], { building: "B", level: "L", room_names: {} });
  qc.setQueryData(["energy-settings"], { now: NOW, settings: { tariff_rm_per_kwh: 0.2983, ac_kw: 10, ac_kw_rooms: {}, ac_on_below_c: 26,
    waste_after_min: 10, co2_kg_per_kwh: 0.75 }, effective_from: null, changed_by: null, source: "defaults", database: true,
    limits: {}, max_rooms: 100, history: [], history_total: 0 });
  let where = "";
  function Where() {
    where = useLocation().search;
    return null;
  }
  render(<QueryClientProvider client={qc}><TooltipProvider><MemoryRouter initialEntries={[at]}><EnergyPage /><Where /></MemoryRouter></TooltipProvider></QueryClientProvider>);
  return () => where;
}

beforeEach(() => {
  localStorage.clear();
  vi.stubGlobal("ResizeObserver", class { observe() {} unobserve() {} disconnect() {} });
});
afterEach(() => vi.unstubAllGlobals());

describe("the Energy page period", () => {
  it("opens on the period in the address: today per hour, figures named for today and set against yesterday", () => {
    show("/energy?range=today");
    const toggle = document.querySelector("[data-energy-range]") as HTMLElement;
    expect(toggle).toHaveAccessibleName("Period");
    expect(within(toggle).getByRole("radio", { name: "Today" })).toHaveAttribute("aria-checked", "true");
    expect(screen.getByText("Wasted today")).toBeInTheDocument();
    expect(screen.getByText("Energy wasted today")).toBeInTheDocument();
    expect(screen.getByText("CO2 estimate, today")).toBeInTheDocument();
    expect(screen.getByText("+RM 1.00 vs yesterday")).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Waste per hour, today" })).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Waste by room, today" })).toBeInTheDocument();
    expect(document.querySelector("[data-waste-over]")).toHaveAttribute("data-waste-over", "hour");
    expect(document.querySelector("[data-waste-over]")).toHaveAttribute("data-points", "24");
  });

  it("switches to 30 days: the address and this browser keep it, the figures, titles and the comparison follow", () => {
    const where = show("/energy");
    expect(screen.getByRole("radio", { name: "7 days" })).toHaveAttribute("aria-checked", "true");  // the default
    expect(screen.getByText("Same as the 7 days before")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("radio", { name: "30 days" }));
    expect(where()).toBe("?range=30d");
    expect(localStorage.getItem(ENERGY_RANGE_KEY)).toBe("30d");
    expect(screen.getByText("Wasted, last 30 days")).toBeInTheDocument();
    expect(screen.getByText("RM 32.00")).toBeInTheDocument();
    expect(screen.getByText(T("ov.no_previous"))).toBeInTheDocument();  // nothing reported in the 30 days before
    expect(screen.getByRole("region", { name: "Waste per day, last 30 days" })).toBeInTheDocument();
    expect(document.querySelector("[data-waste-over]")).toHaveAttribute("data-points", "30");
  });

  it("comes back on the last choice of this browser, and the address wins over it", () => {
    localStorage.setItem(ENERGY_RANGE_KEY, "today");
    expect(pickEnergyRange(null, storedEnergyRange())).toBe("today");
    expect(pickEnergyRange("30d", storedEnergyRange())).toBe("30d");
    expect(pickEnergyRange("90d", null)).toBe("7d");
  });

  it("still works when the browser keeps nothing", () => {
    vi.stubGlobal("localStorage", { getItem: () => { throw new Error("blocked"); }, setItem: () => { throw new Error("blocked"); },
      clear: () => {} });
    expect(storedEnergyRange()).toBeNull();
    show("/energy");
    fireEvent.click(screen.getByRole("radio", { name: "Today" }));
    expect(screen.getByText("Wasted today")).toBeInTheDocument();
  });

  it("ranks the rooms by what they wasted: room, RM, kWh and hours, with a bar against the highest", () => {
    show("/energy?range=7d");
    const box = document.querySelector("[data-by-room]") as HTMLElement;
    expect(box).toHaveAttribute("data-by-room", "3");
    expect(within(box).getAllByRole("columnheader").map((h) => h.textContent)).toEqual(["Room", "Wasted", "kWh", "Hours"]);
    const rows = [...box.querySelectorAll("tbody tr")] as HTMLElement[];
    expect(rows.map((r) => r.getAttribute("data-room"))).toEqual(["room2", "room1", "room3"]);  // highest first
    expect(within(rows[0]).getAllByRole("cell").map((c) => c.textContent!.replace(/\s/g, " "))).toEqual(["RM 5.25", "15.8", "1.6"]);
    const bars = rows.map((r) => (r.querySelector("[data-room-bar]") as HTMLElement).style.width);
    expect(bars[0]).toBe("100%");
    expect(parseFloat(bars[1])).toBeCloseTo(33.33, 1);
    expect(bars[2]).toBe("0%");
    expect(document.querySelectorAll("[data-waste-over]")).toHaveLength(1);  // one chart: the bar chart by room is gone
    expect(screen.queryByRole("region", { name: /Waste by room/ })).not.toBeNull();
  });

  it("a room on the plan that has never reported is listed last with 'No sensor' and dashes, not RM 0.00", () => {
    show("/energy?range=7d", (qc) => {
      const room = (room_id: string) => ({ room_id, name: room_id, headcount: 0, at_least: false, count_ts: NOW, counter: "csi", temp_c: 24,
        humidity: 60, live: true, waste: null });
      qc.setQueryData(["rooms", "en"], { now: NOW, stale_s: 30, rooms: [room("room1"), room("room2")], waste_today_rm: 0, waste_today_kwh: 0,
        emergency: { on: false, since: null, drill: false, id: null }, accountability: {}, alerts: [], offline: {}, stale_ts: null });
    });
    const row = document.querySelector("[data-by-room] tr[data-room=room3]") as HTMLElement;
    expect(row).toHaveAttribute("data-no-sensor-row");
    expect(within(row).getByRole("rowheader")).toHaveTextContent("Room 3No sensor");
    expect(within(row).getAllByRole("cell").map((c) => c.textContent)).toEqual(["–", "–", "–"]);
    expect(within(row).queryByRole("button")).toBeNull();  // nothing to filter the chart to
    // a reporting room that wasted nothing keeps its figures
    expect(document.querySelector("[data-by-room] tr[data-room=room1]")).not.toHaveAttribute("data-no-sensor-row");
  });

  it("filters the chart to a room from its row: a chip names it, the address keeps it, and the chip's button removes it", () => {
    const where = show("/energy?range=7d", (qc, base) => {
      qc.setQueryData(["energy", "7d", "room2"], { ...base, range: period("7d", 7, 7, "room2") });
    });
    expect(document.querySelector("[data-room-chip]")).toBeNull();
    const row = screen.getByRole("button", { name: "Hall A" });
    expect(row).toHaveAttribute("aria-pressed", "false");
    fireEvent.click(row);
    expect(where()).toBe("?range=7d&room=room2");
    expect(document.querySelector("[data-room-chip]")).toHaveTextContent("Hall A");
    expect(document.querySelector("[data-waste-over]")).toHaveAttribute("data-waste-room", "room2");
    expect(screen.getByRole("button", { name: "Hall A" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByText("RM 7.00")).toBeInTheDocument();  // the figures at the top stay the building's
    fireEvent.click(screen.getByRole("button", { name: "Show the whole building" }));
    expect(where()).toBe("?range=7d");
    expect(document.querySelector("[data-room-chip]")).toBeNull();
    expect(document.querySelector("[data-waste-over]")).not.toHaveAttribute("data-waste-room");
  });

  it("opens filtered from the address, and a second click on the row shows the building again", () => {
    const where = show("/energy?range=7d&room=room2", (qc, base) => {
      qc.setQueryData(["energy", "7d", "room2"], { ...base, range: period("7d", 7, 7, "room2") });
    });
    expect(document.querySelector("[data-room-chip]")).toHaveTextContent("Hall A");
    fireEvent.click(screen.getByRole("button", { name: "Hall A" }));
    expect(where()).toBe("?range=7d");
  });

  it("starts a day chart at the first day with data and says from when; today keeps its 24 hours", () => {
    const first = show("/energy?range=30d", (qc, base) => {
      qc.setQueryData(["energy", "30d", ""], { ...base, range: period("30d", 32, null, null, 19) });  // nothing before 20 Nov
    });
    expect(document.querySelector("[data-waste-over]")).toHaveAttribute("data-points", "11");
    expect(document.querySelector("[data-data-from]")).toHaveTextContent("Data from 20 Nov");
    first();
    cleanup();
    show("/energy?range=today");
    expect(document.querySelector("[data-waste-over]")).toHaveAttribute("data-points", "24");
    expect(document.querySelector("[data-data-from]")).toBeNull();
  });

  it("words the change in both languages", () => {
    expect(changeText(-0.5, "7d", (k) => T(k))).toBe("−RM 0.50 vs the 7 days before");
    expect(changeText(0.001, "30d", (k) => T(k, undefined, "ms"))).toBe("Sama seperti 30 hari sebelumnya");
    expect(changeText(2, "today", (k) => T(k, undefined, "ms"))).toBe("+RM 2.00 berbanding semalam");
  });
});

describe("money ticks", () => {
  it("are even steps from 0 that reach the highest value", async () => {
    const { moneyTicks } = await import("@/components/charts");
    expect(moneyTicks(1.4)).toEqual([0, 0.5, 1, 1.5]);
    expect(moneyTicks(16)).toEqual([0, 5, 10, 15, 20]);
    expect(moneyTicks(0.6)).toEqual([0, 0.2, 0.4, 0.6]);
    expect(moneyTicks(0)).toEqual([0, 0.25, 0.5, 0.75, 1]);
    expect(moneyTicks(123)).toEqual([0, 50, 100, 150]);
  });
});
