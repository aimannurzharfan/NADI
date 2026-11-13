// The overview page as a whole, on canned answers: what it shows in each state and that it holds still when it must.
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter, useLocation } from "react-router-dom";

import { TooltipProvider } from "@/components/ui/tooltip";

import { ROOM_KEY, minutesToday } from "@/lib/overview";
import { OverviewPage } from "@/pages/overview";
import type { Room, RoomsState } from "@/lib/types";

const NOW = Math.floor(Date.now() / 1000);

const room = (extra: Partial<Room> = {}): Room => ({
  room_id: "room1", name: "Demo Room", headcount: 1, at_least: false, counter: "csi", count_ts: NOW - 3, temp_c: 24, humidity: 60,
  live: true, waste: null, ...extra,
});

const state = (extra: Partial<RoomsState> = {}): RoomsState => ({
  now: NOW, stale_s: 30, rooms: [room()], waste_today_rm: 0.6, waste_today_kwh: 2.01, emergency: { on: false, since: null, drill: false, id: null },
  accountability: {}, alerts: [], offline: {}, stale_ts: null, demo: { on: false, t: null }, clock: null, ...extra,
});

const signalOf = (id: string) => ({ now: NOW, room_id: id, minutes: 5, threshold: 1.301, last_report_ts: NOW - 3,
  points: [{ ts: NOW - 13, motion_std: 0.4, headcount: 0 }, { ts: NOW - 3, motion_std: 2.1, headcount: 1 }] });
const signalsOf = (ids: string[]) => ({ now: NOW, minutes: 5, threshold: 1.301, truncated: false, rooms: Object.fromEntries(ids.map((id) => [id, signalOf(id)])) });

/** The People card's answer for one room: a point a minute, someone inside since a minute and a half ago. */
const MINUTE = NOW - (NOW % 60);
const peopleOf = (id: string, bucket = 60, points: [number, number, number][] = [[MINUTE - 120, 0, 0], [MINUTE - 60, 1, 1], [MINUTE, 1, 1]],
  since: { occupied: boolean; ts: number | null } | null = { occupied: true, ts: NOW - 90 }) =>
  ({ now: NOW, bucket_s: bucket, room_id: id, people: points, since });
const hhmm = (ts: number) => new Date(ts * 1000).toLocaleTimeString("en-GB", { timeZone: "Asia/Kuala_Lumpur", hourCycle: "h23", hour: "2-digit", minute: "2-digit" });

/** Shows where the router is, so a test can read the address. */
function Where() {
  const { pathname, search } = useLocation();
  return <span data-where>{pathname}{search}</span>;
}
const where = () => document.querySelector("[data-where]")!.textContent;

function show(data: RoomsState | undefined, setup?: (qc: QueryClient) => void, at = "/") {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false, staleTime: Infinity, refetchInterval: false } } });
  if (data) qc.setQueryData(["rooms", "en"], data);
  qc.setQueryData(["info", "en"], { building: "Test building", level: "Level 4", room_names: { room1: "Demo Room", room2: "Hall A" },
    detector: { mode: "rule", threshold: 1.301, model: { framework: "MindSpore 2.10.0", trained_on: "synthetic", active: false } } });
  qc.setQueryData(["me"], { admin: false, who: null, rule: "token", viewer: true, viewer_required: false });
  qc.setQueryData(["signals"], signalsOf(["room1"]));
  qc.setQueryData(["people", "room1", 60], peopleOf("room1"));
  qc.setQueryData(["incidents"], { incidents: [], active: null });
  qc.setQueryData(["history", minutesToday(data?.now ?? NOW), ""], { now: NOW, bucket_s: 900, rooms: {} });
  qc.setQueryData(["uptime"], { now: NOW, since: NOW - 3600, stale_s: 30, rooms: { room1: { first_ts: NOW - 3600, up_s: 3590, expected_s: 3600 } }, pct: 99.72 });
  setup?.(qc);
  return render(<QueryClientProvider client={qc}><TooltipProvider><MemoryRouter initialEntries={[at]}><OverviewPage /><Where /></MemoryRouter></TooltipProvider></QueryClientProvider>);
}

describe("overview page", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({ detail: "offline" }), { status: 503 })));
    // jsdom has no layout: the chart's container only needs the observer to exist
    vi.stubGlobal("ResizeObserver", class { observe() {} unobserve() {} disconnect() {} });
  });
  afterEach(() => { vi.unstubAllGlobals(); vi.restoreAllMocks(); localStorage.clear(); });

  it("reads top to bottom: status, live plan, attention, activity, people, today", () => {
    show(state());
    expect(screen.getByRole("heading", { level: 1, name: "Building summary" })).toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent("All clear");
    expect(document.querySelector("[data-group=rooms]")).toHaveTextContent("1 occupied");
    expect(document.querySelector("[data-group=sensors]")).toHaveTextContent("All online");
    expect(screen.getByText("99.7%")).toBeInTheDocument();  // sensor uptime today, from the server
    for (const title of ["Building status", "Live floor plan", "Needs attention", "Live activity", "People", "Today's summary", "Detection"]) {
      expect(screen.getByRole("heading", { level: 2, name: title })).toBeInTheDocument();
    }
    expect(screen.getByText("Nothing needs attention")).toBeInTheDocument();
    expect(screen.getByText(/No activity yet/)).toBeInTheDocument();
    expect(screen.getByRole("figure", { name: "People in Demo Room over the last hour: at most 1 at once." })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Live signal" })).toBeNull();  // the signal lives in the room panel
    // the highlight of the status card: what the air conditioning wasted today, in money and in energy
    expect(document.querySelector("[data-group=ac] [data-waste-rm]")).toHaveTextContent("RM 0.60");
    expect(document.querySelector("[data-group=ac] [data-waste-kwh]")).toHaveTextContent("2.0 kWh");
    expect(document.querySelector("[data-group=emergency]")).toBeNull();
    const today = screen.getByRole("region", { name: "Today's summary" });
    expect(within(today).getByText("Normal")).toBeInTheDocument();          // the emergency and drill line lives here now
    expect(within(today).getByText("no drill today")).toBeInTheDocument();
    expect(within(today).queryByText(/RM/)).toBeNull();
    expect(within(today).getByRole("link", { name: "View full summary" })).toHaveAttribute("href", "/summary");
    expect(screen.getByText("Test building, Level 4")).toBeInTheDocument();
  });

  it("needs attention, with a card, when a room is empty with the air conditioning on", () => {
    show(state({ rooms: [room({ headcount: 0, waste: { since: NOW - 840, minutes: 14, rm: 0.7 } })] }));
    expect(screen.getByRole("status")).toHaveTextContent("1 needs attention");
    expect(screen.getByRole("status")).toHaveAttribute("data-level", "watch");
    expect(document.querySelector("[data-group=ac]")).toHaveTextContent("1 empty, A/C on");
    const queue = screen.getByRole("region", { name: "Needs attention" });
    expect(within(queue).getByText("Demo Room")).toBeInTheDocument();
    // the page has a non-breaking space after RM; getByText collapses it to a plain one
    expect(within(queue).getByText("empty 14 min, A/C on · RM 0.70 so far")).toBeInTheDocument();
    expect(within(queue).getByText("1 to deal with")).toBeInTheDocument();
  });

  it("is red and completely still during an emergency or drill", () => {
    const { container } = show(state({ emergency: { on: true, since: NOW - 60, drill: true, id: "d" } }));
    expect(screen.getByRole("status")).toHaveTextContent("Drill running");
    expect(screen.getByRole("status")).toHaveAttribute("data-level", "act");
    expect(container.querySelector("[data-still]")).not.toBeNull();
    expect(container.querySelector(".live-beat, .report-pulse, .slide-in, [data-beam-moving], .animate-pulse")).toBeNull();
  });

  it("has no loop: the live dot is still on page load and beats once when a newer report arrives", async () => {
    let client!: QueryClient;
    const { container } = show(state(), (qc) => { client = qc; });
    expect(container.querySelector("[data-still]")).toBeNull();
    expect(container.querySelector("[data-feed=live]")).not.toBeNull();
    expect(container.querySelector(".live-beat, .animate-pulse")).toBeNull();
    await act(async () => { client.setQueryData(["rooms", "en"], state({ now: NOW + 1 })); });  // a new answer, the same report
    expect(container.querySelector(".live-beat")).toBeNull();
    await act(async () => { client.setQueryData(["rooms", "en"], state({ now: NOW + 10, rooms: [room({ count_ts: NOW + 7 })] })); });
    // the page hears of the new answer a moment after it is stored: wait for it rather than race it
    await waitFor(() => expect(container.querySelectorAll(".live-beat")).toHaveLength(1));
  });

  it("names the live detector as the calibrated rule, and MindSpore only as the model being trained", () => {
    show(state());
    const card = screen.getByRole("region", { name: "Detection" });
    expect(card.querySelector("[data-live-detector]")).toHaveTextContent("Calibrated rule, threshold 1.30 dB");
    expect(card.querySelector("[data-live-detector]")).not.toHaveTextContent("MindSpore");
    expect(card).toHaveTextContent("Model training");
    expect(card).toHaveTextContent("Huawei MindSpore");
    expect(card.querySelector("[data-model-status]")).toHaveTextContent(/^Not active: trained on simulated data/);
    expect(within(card).getByRole("link", { name: "Open calibration" })).toHaveAttribute("href", "/calibration");
  });

  it("says MindSpore is the live detector only when the server says a model is counting", () => {
    show(state(), (qc) => void qc.setQueryData(["info", "en"], { building: "Test building", level: "Level 4", room_names: {},
      detector: { mode: "model", threshold: null, model: { framework: "MindSpore 2.10.0", trained_on: "real CSI", active: true } } }));
    const card = screen.getByRole("region", { name: "Detection" });
    expect(card.querySelector("[data-live-detector]")).toHaveTextContent("MindSpore model");
    expect(card.querySelector("[data-model-status]")).toHaveTextContent("Active: this model is counting people now.");
  });

  it("names rooms that report but are not on the plan", () => {
    const { container } = show(state({ rooms: [room(), room({ room_id: "annex", name: "Annex", headcount: 2 })] }));
    expect(container.querySelector("[data-off-plan]")).toHaveTextContent("Not on this plan: Annex 2 (Occupied)");
  });

  it("says the history database is offline instead of 'no data' when it cannot be read", async () => {
    // both requests that read the history database are made and answered 503
    show(state(), (qc) => { qc.removeQueries({ queryKey: ["history"] }); qc.removeQueries({ queryKey: ["uptime"] }); });
    expect(await screen.findAllByText("history database offline", { selector: "[data-hint]" })).toHaveLength(3);
  });

  it("shows a connection card and 'Not updating' when the server cannot be reached", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => { throw new TypeError("Failed to fetch"); }));
    show(undefined);
    expect((await screen.findAllByText("Not updating")).length).toBeGreaterThan(0);
    expect(screen.getByText("Connection lost")).toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent("1 needs attention");
  });
});

describe("overview: the selected room", () => {
  let calls: string[] = [];
  beforeEach(() => {
    calls = [];
    vi.stubGlobal("fetch", vi.fn(async (url: RequestInfo | URL) => {
      calls.push(String(url));
      return new Response(JSON.stringify({ detail: "offline" }), { status: 503 });
    }));
    vi.stubGlobal("ResizeObserver", class { observe() {} unobserve() {} disconnect() {} });
  });
  afterEach(() => { vi.unstubAllGlobals(); vi.restoreAllMocks(); localStorage.clear(); });

  const tile = (name: RegExp | string) => screen.getByRole("button", { name });
  const select = () => screen.getByRole("combobox", { name: "Room shown" }) as HTMLSelectElement;

  it("starts on the live sensing room without writing it to the address", () => {
    show(state());
    expect(tile(/Demo Room/)).toHaveAttribute("aria-pressed", "true");
    expect(select().value).toBe("room1");
    expect(where()).toBe("/");
    expect(localStorage.getItem(ROOM_KEY)).toBeNull();
    expect(screen.getByRole("link", { name: "Room details" })).toHaveAttribute("href", "/floor?room=room1");
    // the count now, and since when the room has been occupied
    expect(document.querySelector("[data-people-now]")).toHaveTextContent(`Now 1 · since ${hhmm(NOW - 90)}`);
  });

  it("leaves 'since' out while the live count and the stored reports disagree", () => {
    // the room filled a moment ago: the history still says "empty since"
    show(state(), (qc) => void qc.setQueryData(["people", "room1", 60], peopleOf("room1", 60, undefined, { occupied: false, ts: NOW - 600 })));
    expect(document.querySelector("[data-people-now]")).toHaveTextContent(/^Now 1$/);
    expect(document.querySelector("[data-people-since]")).toBeNull();
  });

  it("says 'Sensor offline' in place of the count when the room's sensor is silent, and still draws its history", () => {
    show(state({ rooms: [room({ live: false })] }));
    expect(document.querySelector("[data-people-now]")).toHaveTextContent("Sensor offline");
    expect(document.querySelector("[data-people-chart]")).not.toBeNull();
  });

  it("selects a room on a click: ring, card, address and this browser all follow, other parameters are kept", () => {
    show(state(), undefined, "/?lang=en");
    fireEvent.click(tile("Hall A: no sensor"));
    expect(tile("Hall A: no sensor")).toHaveAttribute("aria-pressed", "true");
    expect(tile(/Demo Room/)).toHaveAttribute("aria-pressed", "false");
    expect(select().value).toBe("room2");
    const card = screen.getByRole("region", { name: "People" });
    expect(within(card).getByText("No sensor in this room")).toBeInTheDocument();  // words, never an empty chart
    expect(card.querySelector("[data-people-chart]")).toBeNull();
    expect(where()).toBe("/?lang=en&room=room2");
    expect(localStorage.getItem(ROOM_KEY)).toBe("room2");
    expect(screen.getByRole("link", { name: "Room details" })).toHaveAttribute("href", "/floor?room=room2");
    // the dropdown does the same as a click on the plan
    fireEvent.change(select(), { target: { value: "room1" } });
    expect(tile(/Demo Room/)).toHaveAttribute("aria-pressed", "true");
    expect(where()).toBe("/?lang=en&room=room1");
    expect(within(card).getByRole("figure", { name: /^People in Demo Room/ })).toBeInTheDocument();
  });

  it("shows the last hour by default; another range is kept in the address and this browser, and the chart follows", () => {
    const H = 24 * 60;
    const day = NOW - (NOW % 10800);
    show(state(), (qc) => {
      qc.setQueryData(["people", "room1", 7 * H], peopleOf("room1", 10800, [[day - 5 * 10800, 2, 95], [day - 3 * 10800, 0, 0]]));
    }, "/?room=room1");
    const card = screen.getByRole("region", { name: "People" });
    // four ranges, no 5 minutes; the last hour by default
    const group = within(card).getByRole("radiogroup", { name: "Time range" });
    expect(within(group).getAllByRole("radio").map((r) => r.textContent)).toEqual(["1 h", "24 h", "7 d", "30 d"]);
    expect(within(group).getByRole("radio", { name: "1 h" })).toHaveAttribute("aria-checked", "true");
    expect(card.querySelector("[data-people-chart=\"1h\"]")).not.toBeNull();
    // the same choice as a compact select (shown at 1366 px and narrower)
    expect(within(card).getByRole("combobox", { name: "Time range" })).toHaveValue("1h");
    fireEvent.click(within(group).getByRole("radio", { name: "7 d" }));
    expect(where()).toBe("/?room=room1&range=7d");
    expect(localStorage.getItem("nadiSignalRange")).toBe("7d");
    expect(within(card).getByRole("figure")).toHaveAccessibleName("People in Demo Room over the last 7 days: at most 2 at once.");
    expect(card.querySelector("[data-people-chart=\"7d\"]")).not.toBeNull();
    // the range reaches back further than the data: the chart starts at the first report and says so
    expect(card.querySelector("[data-data-from]")).toHaveTextContent(/^Data from /);
    // back to the hour from the select
    fireEvent.change(within(card).getByRole("combobox", { name: "Time range" }), { target: { value: "1h" } });
    expect(where()).toBe("/?room=room1&range=1h");
    expect(card.querySelector("[data-people-chart=\"1h\"]")).not.toBeNull();
  });

  it("falls back to the last hour for a range it no longer has (5 minutes)", () => {
    localStorage.setItem("nadiSignalRange", "5m");
    show(state(), undefined, "/?room=room1&range=5m");
    expect(screen.getByRole("radio", { name: "1 h" })).toHaveAttribute("aria-checked", "true");
  });

  it("takes the range from the address, else this browser's last choice", () => {
    localStorage.setItem("nadiSignalRange", "24h");
    const first = show(state(), undefined, "/?room=room1");
    expect(screen.getByRole("radio", { name: "24 h" })).toHaveAttribute("aria-checked", "true");
    first.unmount();
    show(state(), undefined, "/?room=room1&range=30d");
    expect(screen.getByRole("radio", { name: "30 d" })).toHaveAttribute("aria-checked", "true");
  });

  it("takes the room from the address, and passes over one it does not know", () => {
    const first = show(state(), undefined, "/?room=room3");
    expect(tile("Room 3: no sensor")).toHaveAttribute("aria-pressed", "true");
    expect(select().value).toBe("room3");
    first.unmount();
    show(state(), undefined, "/?room=%3Cscript%3E");
    expect(tile(/Demo Room/)).toHaveAttribute("aria-pressed", "true");  // the default, and nothing of the address is shown
    expect(document.body.innerHTML).not.toContain("<script>");
  });

  it("brings the last choice back from this browser, and uses the default when storage is blocked", () => {
    localStorage.setItem(ROOM_KEY, "room2");
    const first = show(state());
    expect(tile("Hall A: no sensor")).toHaveAttribute("aria-pressed", "true");
    expect(where()).toBe("/");
    first.unmount();
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => { throw new DOMException("blocked", "SecurityError"); });
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => { throw new DOMException("blocked", "SecurityError"); });
    show(state());
    expect(tile(/Demo Room/)).toHaveAttribute("aria-pressed", "true");
    fireEvent.click(tile("Hall A: no sensor"));  // choosing still works: the address carries it
    expect(tile("Hall A: no sensor")).toHaveAttribute("aria-pressed", "true");
    expect(where()).toBe("/?room=room2");
  });

  it("does not jump to another room by itself when a different room becomes the busiest", async () => {
    let client!: QueryClient;
    const annex = room({ room_id: "annex", name: "Annex", headcount: 0 });
    show(state({ rooms: [room(), annex] }), (qc) => { client = qc; qc.setQueryData(["signals"], signalsOf(["room1", "annex"])); });
    expect(select().value).toBe("room1");
    await act(async () => {
      client.setQueryData(["rooms", "en"], state({ now: NOW + 10, rooms: [room({ headcount: 0 }), { ...annex, headcount: 4, count_ts: NOW + 8 }] }));
    });
    await waitFor(() => expect(document.querySelector("[data-off-plan]")).toHaveTextContent("Annex 4"));
    expect(select().value).toBe("room1");
    expect([...select().options].map((o) => o.text)).toEqual(["Annex", "Demo Room", "Hall A", "Room 3"]);  // every room, on the plan or off it, by name
  });

  it("draws the people of a room counted by a people counter, and says why a silent sensor pair has no chart", () => {
    const first = show(state({ rooms: [room({ counter: "count", headcount: 40 })] }),
      (qc) => void qc.setQueryData(["people", "room1", 60], peopleOf("room1", 60, [[MINUTE - 60, 38, 1], [MINUTE, 40, 1]])));
    expect(screen.getByRole("figure")).toHaveAccessibleName("People in Demo Room over the last hour: at most 40 at once.");
    first.unmount();
    show(state({ rooms: [] }));
    expect(select().value).toBe("room1");  // nothing reports: the room with a sensor pair on the plan
    expect(screen.getByText("No report from this room yet")).toBeInTheDocument();
  });

  it("opens the room panel on a double-click", () => {
    show(state());
    fireEvent.doubleClick(tile("Hall A: no sensor"));
    expect(where()).toBe("/floor?room=room2");
  });

  it("makes one signal request for thirteen sensing rooms, and none per room", async () => {
    const many = Array.from({ length: 13 }, (_, i) => room({ room_id: i < 3 ? `room${i + 1}` : `extra${i}`, name: `R${i}` }));
    vi.stubGlobal("fetch", vi.fn(async (url: RequestInfo | URL) => {
      calls.push(String(url));
      return new Response(JSON.stringify(signalsOf(many.map((r) => r.room_id))), { status: 200, headers: { "Content-Type": "application/json" } });
    }));
    show(state({ rooms: many }), (qc) => qc.removeQueries({ queryKey: ["signals"] }));
    await waitFor(() => expect(document.querySelectorAll("[data-room] [data-trace], [data-room] svg polyline, [data-room] svg path").length).toBeGreaterThan(0));
    expect(calls.filter((u) => u.includes("/api/signals"))).toHaveLength(1);
    expect(calls.filter((u) => /\/api\/rooms\/[^/]+\/signal/.test(u))).toHaveLength(0);
  });
});
