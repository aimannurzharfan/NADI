// The full summary of the day (/summary): one row per room from the answers the console already has, today's
// emergencies and drills with links to their reports, and the way back to the overview.
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import { TooltipProvider } from "@/components/ui/tooltip";
import { midnightBefore, minutesToday } from "@/lib/overview";
import { SummaryPage } from "@/pages/summary";

const NOW = Math.floor(Date.now() / 1000);
const START = midnightBefore(NOW);

function show(setup?: (qc: QueryClient) => void) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false, staleTime: Infinity, refetchInterval: false } } });
  qc.setQueryData(["rooms", "en"], { now: NOW, stale_s: 30, waste_today_rm: 0.7, emergency: { on: false, since: null, drill: false, id: null },
    accountability: {}, alerts: [], offline: {}, stale_ts: null, demo: { on: false, t: null }, clock: null,
    rooms: [{ room_id: "room1", name: "Demo Room", headcount: 1, at_least: false, counter: "csi", count_ts: NOW - 3, temp_c: 24, humidity: 60, live: true, waste: null }] });
  qc.setQueryData(["info", "en"], { building: "Test building", level: "Level 4", room_names: { room1: "Demo Room", room2: "Hall A" } });
  qc.setQueryData(["me"], { admin: false, who: null, rule: "token", viewer: true, viewer_required: false });
  qc.setQueryData(["history", minutesToday(NOW), ""], { now: NOW, bucket_s: 900, rooms: { room1: [[START, 0], [START + 900, 2], [START + 1800, 1]] } });
  qc.setQueryData(["uptime"], { now: NOW, since: START, stale_s: 30, pct: 75, rooms: { room1: { first_ts: START, up_s: 2700, expected_s: 3600 } } });
  const amounts = { rm: 0.7, kwh: 2.3, co2_kg: 1.8 };
  qc.setQueryData(["energy", "7d", ""], { now: NOW, today: amounts, week: amounts, previous_week: amounts, yesterday: amounts, daily: [], tariff_rm_per_kwh: 0.2983,
    ac_kw: 10, co2_kg_per_kwh: 0.75, stale_ts: null, by_room: [{ room_id: "room1", name: "Demo Room", rm_today: 0.7, rm_week: 2 }] });
  qc.setQueryData(["incidents"], { active: null, incidents: [
    { id: "d1", kind: "drill", started: START + 60, ended: START + 360, duration_s: 300, started_by: "warden", ended_by: "warden",
      start_total: 3, start_at_least: false, demo: false, marked: 0, offline_rooms: 0 },
    { id: "old", kind: "drill", started: START - 86400, ended: START - 86000, duration_s: 400, started_by: "warden", ended_by: "warden",
      start_total: 1, start_at_least: false, demo: false, marked: 0, offline_rooms: 0 }] });
  setup?.(qc);
  return render(<QueryClientProvider client={qc}><TooltipProvider><MemoryRouter><SummaryPage /></MemoryRouter></TooltipProvider></QueryClientProvider>);
}

describe("full summary of the day", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({ detail: "offline" }), { status: 503 })));
    vi.stubGlobal("ResizeObserver", class { observe() {} unobserve() {} disconnect() {} });
  });
  afterEach(() => vi.unstubAllGlobals());

  it("has one title, the way back, and a row per room with its four figures", () => {
    show();
    expect(screen.getAllByRole("heading", { level: 1 })).toHaveLength(1);
    expect(screen.getByRole("heading", { level: 1, name: "Today's summary" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Building summary" })).toHaveAttribute("href", "/");
    const table = document.querySelector("[data-summary-rooms]") as HTMLElement;
    expect(within(table).getAllByRole("columnheader").map((h) => h.textContent)).toEqual(["Room", "Peak people", "Hours occupied", "Sensor uptime", "A/C waste"]);
    const row = table.querySelector("[data-room=room1]") as HTMLElement;
    expect(within(row).getAllByRole("cell").map((c) => c.textContent)).toEqual(["Demo Room", "2", "0.5 h", "75.0%", "RM 0.70"]);
  });

  it("lists only today's emergencies and drills, each with a link to its report", () => {
    show();
    const table = document.querySelector("[data-summary-incidents]") as HTMLElement;
    expect(within(table).getAllByRole("row")).toHaveLength(2);  // the header and today's drill; yesterday's is not listed
    expect(within(table).getByText("Drill")).toBeInTheDocument();
    expect(within(table).getByRole("link", { name: "Open report" })).toHaveAttribute("href", "/report/d1");
  });

  it("says so in words when there is nothing to list", () => {
    show((qc) => {
      qc.setQueryData(["incidents"], { active: null, incidents: [] });
      qc.setQueryData(["history", minutesToday(NOW), ""], { now: NOW, bucket_s: 900, rooms: {} });
      qc.setQueryData(["uptime"], { now: NOW, since: START, stale_s: 30, pct: null, rooms: {} });
      qc.removeQueries({ queryKey: ["energy"] });  // asked again, and answered 503
    });
    expect(screen.getByText("None today.")).toBeInTheDocument();
    expect(screen.getByText("No room has reported today.")).toBeInTheDocument();
    expect(screen.getByText("no data yet today")).toBeInTheDocument();
  });

  it("names a drill that is running now", () => {
    show((qc) => { qc.setQueryData(["incidents"], { incidents: [], active: { id: "x", drill: true, since: NOW - 60, snapshots: 1, last_snapshot: NOW - 5 } }); });
    expect(screen.getByRole("status")).toHaveTextContent(/^Drill running/);
  });
});
