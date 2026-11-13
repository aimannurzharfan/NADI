// The redesigned overview: building status rules, the "needs attention" queue, the signal chart's threshold handling,
// movement only on new data and none at all with reduced motion or during an emergency, labels and keyboard use.
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, render, renderHook, screen, waitFor, within } from "@testing-library/react";
import { LazyMotion, domAnimation } from "motion/react";
import { MemoryRouter } from "react-router-dom";

import { NumberTicker } from "@/components/magicui/number-ticker";
import { LiveActivity } from "@/components/overview/activity";
import { NeedsAttention } from "@/components/overview/attention";
import { LivePlan, LivePlanLegend } from "@/components/overview/live-plan";
import { LiveSignal } from "@/components/overview/signal-chart";
import { BuildingStatus } from "@/components/overview/building-status";
import { TodayCard } from "@/components/overview/today-card";
import { ApiError } from "@/lib/api";
import { T } from "@/lib/i18n";
import { prefersReducedMotion, useNewer, usePrefersReducedMotion } from "@/lib/motion";
import {
  ROOM_KEY, attentionItems, buildingStatus, defaultRoom, drillLine, feedOf, levelOf, midnightBefore, minutesToday, overallStatus,
  pickRoom, signalScale, span, storeRoom, storedRoom, summaryRows, todayStats, uptimeText,
} from "@/lib/overview";
import type { Alert, IncidentSummary, Room, RoomsState, Signal } from "@/lib/types";

const NOW = 1_793_660_400; // 3 Nov 2026, 07:00 in Kuala Lumpur

const room = (extra: Partial<Room> = {}): Room => ({
  room_id: "room1", name: "Demo Room", headcount: 0, at_least: false, counter: "csi", count_ts: NOW - 4, temp_c: 24, humidity: 60,
  live: true, waste: null, ...extra,
});

const state = (extra: Partial<RoomsState> = {}): RoomsState => ({
  now: NOW, stale_s: 30, rooms: [room()], waste_today_rm: 0, emergency: { on: false, since: null, drill: false, id: null },
  accountability: {}, alerts: [], offline: {}, stale_ts: null, demo: { on: false, t: null }, clock: null, ...extra,
});

const alert = (extra: Partial<Alert> = {}): Alert => ({
  id: "a1", ts: NOW - 30, kind: "info", severity: "info", via: "console", subject: T("alert.suspicious_subject"),
  message: "Demo Room went from 1 to 40 people in one report.", ack: null, drill: false, ...extra,
});

const signal = (extra: Partial<Signal> = {}): Signal => ({
  now: NOW, room_id: "room1", minutes: 5, threshold: 1.301, last_report_ts: NOW - 4,
  points: [{ ts: NOW - 24, motion_std: 0.4, headcount: 0 }, { ts: NOW - 14, motion_std: 0.5, headcount: 0 }, { ts: NOW - 4, motion_std: 0.3, headcount: 0 }],
  ...extra,
});

describe("building status: labelled pills and one overall pill", () => {
  // the plan as drawn: a sensor pair in room1, none in room2 and room3
  const PLAN3 = [{ id: "room1", linked: true }, { id: "room2", linked: false }, { id: "room3", linked: false }];
  const texts = (data: RoomsState) => Object.fromEntries(buildingStatus(data, PLAN3).map((g) => [g.id, g.pills.map((p) => p.text)]));

  it("is all clear when nothing needs attention, and names the rooms with no sensor", () => {
    const data = state({ rooms: [room({ headcount: 1 })] });
    expect(levelOf(data, attentionItems(data))).toBe("calm");
    expect(texts(data)).toEqual({ rooms: ["1 occupied", "2 no sensor"], ac: ["No waste"], sensors: ["All online"] });
    // three groups, the air conditioning first (the highlight); an emergency is not a group of this card
    expect(buildingStatus(data, PLAN3).map((g) => g.id)).toEqual(["ac", "rooms", "sensors"]);
    // nothing wasting now but some earlier today: "None right now", never "No waste"
    expect(texts({ ...data, waste_today_rm: 0.6 }).ac).toEqual(["None right now"]);
    expect(T("bs.none_now", undefined, "ms")).toBe("Tiada sekarang");
    expect(texts({ ...data, waste_today_rm: 0 }).ac).toEqual(["No waste"]);
    expect(overallStatus(data, attentionItems(data), false)).toMatchObject({ level: "calm", tone: "ok", text: "All clear" });
  });

  it("needs attention for a waste flag, a sensor that stopped, a suspicious reading, a service or the server being offline", () => {
    const cases: RoomsState[] = [
      state({ rooms: [room({ waste: { since: NOW - 840, minutes: 14, rm: 0.7 } })] }),
      state({ rooms: [room({ live: false, count_ts: NOW - 140 })] }),
      state({ alerts: [alert()] }),
      state({ offline: { mysql: NOW - 600 } }),
    ];
    for (const data of cases) {
      expect(levelOf(data, attentionItems(data))).toBe("watch");
      expect(overallStatus(data, attentionItems(data), false)).toMatchObject({ level: "watch", tone: "warn", text: "1 needs attention" });
    }
    expect(levelOf(state(), attentionItems(state(), { since: NOW - 20 }))).toBe("watch");
    expect(levelOf(undefined, attentionItems(undefined, { since: null }))).toBe("watch");
    const two = state({ rooms: [room({ room_id: "room1", waste: { since: 1, minutes: 12, rm: 0.6 } }), room({ room_id: "room2", waste: { since: 1, minutes: 20, rm: 1 } })] });
    expect(overallStatus(two, attentionItems(two), false).text).toBe("2 need attention");
    expect(texts(two).ac).toEqual(["2 empty, A/C on"]);
    expect(texts(cases[0]).ac).toEqual(["1 empty, A/C on"]);
  });

  it("is red during an emergency and during a drill, whatever else is going on", () => {
    for (const drill of [false, true]) {
      const data = state({ emergency: { on: true, since: NOW - 60, drill, id: "x" }, rooms: [room({ waste: { since: 1, minutes: 14, rm: 0.7 } })] });
      const words = drill ? "Drill running" : "Emergency active";
      expect(levelOf(data, attentionItems(data))).toBe("act");
      expect(overallStatus(data, attentionItems(data), false)).toMatchObject({ level: "act", tone: "crit", text: words });
    }
  });

  it("never calls a room whose sensor stopped empty: it is unknown, grey and dashed", () => {
    const data = state({ rooms: [room({ room_id: "room1", headcount: 0 }), room({ room_id: "room2", live: false, headcount: 1, count_ts: NOW - 140 })] });
    const groups = buildingStatus(data, PLAN3);
    expect(texts(data).rooms).toEqual(["1 empty", "1 unknown", "1 no sensor"]);
    expect(groups[1].pills.find((p) => p.id === "unknown")).toMatchObject({ tone: "off", dashed: true });
    expect(groups[1].pills.find((p) => p.id === "no-sensor")).toMatchObject({ tone: "off", dashed: true });
    expect(texts(data).sensors).toEqual(["1 offline", "1 online"]);
    expect(groups[2].pills[0]).toMatchObject({ tone: "off", dashed: true });
  });

  it("says 'no report yet' only for a plan room with a sensor pair that has never reported", () => {
    expect(texts(state({ rooms: [] }))).toEqual({
      rooms: ["1 no report yet", "2 no sensor"], ac: ["No live data"], sensors: ["No sensor reporting"] });
    expect(texts(state({ rooms: [room({ room_id: "room2", headcount: 3 })] })).rooms).toEqual(["1 occupied", "1 no report yet", "1 no sensor"]);
  });

  it("never says 'All clear' or 'No waste' while no sensor is reporting", () => {
    const none = state({ rooms: [room({ live: false, count_ts: NOW - 140 })] });
    expect(feedOf(none, false)).toBe("none");
    expect(feedOf(state({ rooms: [] }), false)).toBe("none");
    expect(feedOf(state({ rooms: [room({ room_id: "a", live: false }), room({ room_id: "b" })] }), false)).toBe("live");
    expect(feedOf(state({ stale_ts: NOW - 60 }), false)).toBe("stopped");
    expect(feedOf(state(), true)).toBe("stopped");
    expect(feedOf(undefined, false)).toBe("stopped");
    expect(overallStatus(none, [], false)).toMatchObject({ tone: "off", dashed: true, text: "No live data" });
    expect(overallStatus(state({ rooms: [] }), [], false).text).toBe("No live data");
    expect(overallStatus(state(), [], true)).toMatchObject({ tone: "off", text: "Not updating" });
    expect(texts(none).ac).toEqual(["No live data"]);
  });

  it("shows each group as a label with pills, and announces only the overall pill", () => {
    render(<BuildingStatus data={state({ rooms: [room({ headcount: 1 })] })} items={[]} lost={false} />);
    expect(screen.getByRole("heading", { level: 2, name: "Building status" })).toBeInTheDocument();
    const status = screen.getByRole("status");
    expect(status).toHaveTextContent("Overall: All clear");
    expect(status).toHaveAttribute("data-level", "calm");
    expect(screen.queryByText(/CALM|WATCH|ACT/)).toBeNull();  // the old sentence bar is gone
    const rooms = document.querySelector("[data-group=rooms]")!;
    expect(rooms).toHaveTextContent("Rooms");
    expect(rooms).toHaveTextContent("1 occupied");
    expect(rooms.querySelector("[data-tone=off]")!.className).toContain("border-dashed");  // "2 no sensor": grey and dashed
    expect(document.querySelector("[data-group=ac]")).toHaveTextContent("No waste");
    expect(document.querySelector("[data-group=sensors]")).toHaveTextContent("All online");
    expect(document.querySelector("[data-group=emergency]")).toBeNull();
    expect(document.querySelectorAll("[data-group]")).toHaveLength(3);
    // every pill carries a mark as well as a colour
    for (const pill of document.querySelectorAll("[data-tone]")) expect(pill.querySelector("span[aria-hidden]")).not.toBeNull();
  });

  it("leads with what the air conditioning wasted today: the figure, the energy and one pill", () => {
    const wasting = state({ waste_today_rm: 1.1, waste_today_kwh: 3.69, rooms: [room({ waste: { since: NOW - 840, minutes: 14, rm: 0.7 } })] });
    const { unmount } = render(<BuildingStatus data={wasting} items={attentionItems(wasting)} lost={false} />);
    const groups = [...document.querySelectorAll("[data-group]")].map((g) => g.getAttribute("data-group"));
    expect(groups).toEqual(["ac", "rooms", "sensors"]);  // the highlight comes first
    const ac = document.querySelector("[data-group=ac]")!;
    expect(ac).toHaveTextContent("Air conditioning waste today");
    const figure = ac.querySelector("[data-waste-rm]")!;
    expect(figure).toHaveTextContent("RM 1.10");
    expect(figure.className).toContain("text-2xl");   // the figure size, 24 px
    expect(figure.className).toContain("text-warn");  // amber above zero, and the pill beside it says why in words
    expect(ac.querySelector("[data-waste-kwh]")).toHaveTextContent("3.7 kWh");
    expect(ac.querySelectorAll("[data-tone]")).toHaveLength(1);
    expect(ac).toHaveTextContent("1 empty, A/C on");
    unmount();
    render(<BuildingStatus data={state({ waste_today_rm: 0, waste_today_kwh: 0 })} items={[]} lost={false} />);
    const calm = document.querySelector("[data-waste-rm]")!;
    expect(calm).toHaveTextContent("RM 0.00");
    expect(calm.className).not.toContain("text-warn");
    expect(document.querySelector("[data-group=ac]")).toHaveTextContent("No waste");
  });

  it("shows a skeleton before the first answer, and says 'Not updating' when the server cannot be reached", () => {
    const { unmount } = render(<BuildingStatus data={undefined} items={[]} lost={false} />);
    expect(screen.getByText("Checking the building…")).toBeInTheDocument();
    expect(screen.queryByText("All clear")).toBeNull();
    unmount();
    render(<BuildingStatus data={undefined} items={[]} lost />);
    expect(screen.getAllByText("Not updating")).toHaveLength(4);  // the overall pill and each group
    expect(document.querySelector("[data-waste-rm]")).toHaveTextContent("–");  // no figure is claimed while not live
    expect(screen.queryByText("All clear")).toBeNull();
  });
});

describe("needs attention queue", () => {
  it("writes the waste card as where, what, how bad and what to do", () => {
    const [card] = attentionItems(state({ rooms: [room({ waste: { since: NOW - 840, minutes: 14, rm: 0.7 } })] }));
    expect(card).toMatchObject({ kind: "waste", title: "Demo Room", detail: "empty 14 min, A/C on · RM 0.70 so far",
      todo: "Switch off the air conditioner in this room." });
  });

  it("says how long a sensor has been silent and the last known count", () => {
    const [card] = attentionItems(state({ rooms: [room({ live: false, headcount: 2, count_ts: NOW - 140 })] }));
    expect(card.kind).toBe("sensor");
    expect(card.detail).toBe("sensor offline, no report for 2 min · count unknown (last known 2)");
    expect(span(45)).toBe("45 s");
    expect(span(7300)).toBe("2 h");
  });

  it("orders the queue: connection, services, sensors, waste, suspicious readings", () => {
    const data = state({
      rooms: [room({ room_id: "a", name: "A", waste: { since: 1, minutes: 11, rm: 0.5 } }), room({ room_id: "b", name: "B", live: false })],
      alerts: [alert()], offline: { mysql: NOW - 60 },
    });
    expect(attentionItems(data).map((i) => i.kind)).toEqual(["service", "sensor", "waste", "suspicious"]);
  });

  it("shows one card, not one per room, when the server, the live store or the sensor link is down", () => {
    const rooms = [room({ room_id: "a", live: false }), room({ room_id: "b", live: false })];
    expect(attentionItems(state({ rooms, offline: { redis: NOW - 30 }, stale_ts: NOW - 30 })).map((i) => i.kind)).toEqual(["service"]);
    expect(attentionItems(state({ rooms, offline: { mqtt: NOW - 30 } })).map((i) => i.kind)).toEqual(["service"]);
    expect(attentionItems(state({ rooms }), { since: NOW - 30 }).map((i) => i.kind)).toEqual(["connection"]);
  });

  it("keeps a suspicious reading only while it is recent and not acknowledged", () => {
    expect(attentionItems(state({ alerts: [alert()] }))).toHaveLength(1);
    expect(attentionItems(state({ alerts: [alert({ ack: { by: "admin", ts: NOW } })] }))).toHaveLength(0);
    expect(attentionItems(state({ alerts: [alert({ ts: NOW - 3600 })] }))).toHaveLength(0);
    expect(attentionItems(state({ alerts: [alert({ subject: "NADI: Emergency mode ended by admin" })] }))).toHaveLength(0);
  });

  it("has a calm empty state", () => {
    render(<QueryClientProvider client={new QueryClient()}><NeedsAttention items={[]} admin={false} /></QueryClientProvider>);
    expect(screen.getByText("Nothing needs attention")).toBeInTheDocument();
  });

  it("offers a button only for the one command the server has (acknowledge, admin only), otherwise the instruction", async () => {
    const items = attentionItems(state({ rooms: [room({ waste: { since: 1, minutes: 14, rm: 0.7 } })], alerts: [alert({ id: "abc123" })] }));
    const qc = new QueryClient();
    const view = render(<QueryClientProvider client={qc}><NeedsAttention items={items} admin={false} /></QueryClientProvider>);
    expect(screen.queryByRole("button")).toBeNull();
    expect(screen.getByText("Switch off the air conditioner in this room.")).toBeInTheDocument();
    view.unmount();

    const fetchMock = vi.fn(async () => new Response(JSON.stringify({ ok: true }), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    render(<QueryClientProvider client={qc}><NeedsAttention items={items} admin /></QueryClientProvider>);
    const buttons = screen.getAllByRole("button");
    expect(buttons).toHaveLength(1);  // none on the waste card: there is no "switch off" command to call
    fireEvent.click(buttons[0]);
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe("/api/alerts/abc123/ack");
    expect(init.method).toBe("POST");
    vi.unstubAllGlobals();
  });

  it("shows text from the server as text, never as markup", () => {
    const evil = "<img src=x onerror=alert(1)>";
    const items = attentionItems(state({ rooms: [room({ name: evil, waste: { since: 1, minutes: 14, rm: 0.7 } })] }));
    const { container } = render(<QueryClientProvider client={new QueryClient()}><NeedsAttention items={items} admin={false} /></QueryClientProvider>);
    expect(container.querySelector("img")).toBeNull();
    expect(screen.getByText(evil)).toBeInTheDocument();
  });
});

describe("live signal chart", () => {
  const size = { width: 800, height: 200 };

  it("always fits the threshold on the axis with room above it", () => {
    expect(signalScale([0.2, 0.4], 1.301).top).toBeGreaterThan(1.301 * 1.5);
    expect(signalScale([9.4], 1.301).top).toBeGreaterThanOrEqual(9.4);
    expect(signalScale([], null)).toMatchObject({ top: 4, ticks: [0, 2, 4] });
    expect(signalScale([2.9], 1.301).ticks).toEqual([0, 2, 4]);  // even whole numbers, never 1 and 3
    for (const s of [signalScale([7.5], 1.3), signalScale([45], null), signalScale([0.1], 0.35)]) {
      expect(s.ticks.every((v) => Number.isInteger(v) && v % 2 === 0)).toBe(true);
    }
    expect(signalScale([NaN, Infinity], 1).ticks[0]).toBe(0);
    for (const s of [signalScale([0.3], 0.35), signalScale([45], 1.3), signalScale([900], null)]) {
      expect(s.ticks.length).toBeLessThanOrEqual(6);
      expect(s.ticks[s.ticks.length - 1]).toBeCloseTo(s.top);
    }
  });

  it("draws the threshold line without words, marks it on the axis and names it on hover or focus", () => {
    const { container } = render(<LiveSignal room={room()} signal={signal()} size={size} />);
    expect(screen.queryByText(/occupied above/)).toBeNull();
    expect(container.querySelector(".recharts-reference-line")).not.toBeNull();
    // the threshold is its own tick, "1.3", in the dashed line's colour; the other ticks are even whole numbers
    const tick = container.querySelector("[data-threshold-tick]")!;
    expect(tick.textContent).toBe("1.3");
    expect(tick.getAttribute("fill")).toBe("hsl(var(--heading))");
    const others = [...container.querySelectorAll(".recharts-yAxis text:not([data-threshold-tick])")].map((t) => t.textContent).filter((t) => t && t !== "dB");
    expect(others.every((t) => Number(t) % 2 === 0)).toBe(true);
    expect(container.querySelector("[data-threshold] line")?.getAttribute("stroke")).toBe("hsl(var(--heading))");
    // the axis title is just "dB"
    expect(screen.getByText("dB")).toBeInTheDocument();
    expect(screen.queryByText("Motion (dB)")).toBeNull();
    // hovering or focusing the line names it
    const line = container.querySelector("[data-threshold]") as SVGGElement;
    expect(line).toHaveAttribute("tabindex", "0");
    expect(line).toHaveAccessibleName("Threshold 1.30 dB");
    expect(container.querySelector("[data-threshold-tip]")).toBeNull();
    fireEvent.focus(line);
    expect(container.querySelector("[data-threshold-tip]")).toHaveTextContent("Threshold 1.30 dB");
    fireEvent.blur(line);
    expect(container.querySelector("[data-threshold-tip]")).toBeNull();
    fireEvent.mouseEnter(line);
    expect(container.querySelector("[data-threshold-tip]")).not.toBeNull();
    expect(T("sig.threshold_tip", { x: "1.30" }, "ms")).toBe("Ambang 1.30 dB");
    // the chart keeps the full meaning for a screen reader
    expect(screen.getByRole("figure")).toHaveAccessibleName(
      "Live signal of Demo Room: now 0.30 dB, below the threshold of 1.30 dB: steady.");
    expect(container.querySelector(".recharts-reference-area")).not.toBeNull();  // the area above is shaded
    // one accent: only the line is teal; the band is a neutral step and nothing is filled under the line
    expect(container.querySelector(".recharts-reference-area path, .recharts-reference-area rect")?.getAttribute("fill")).toBe("hsl(var(--muted))");
    expect(container.querySelector(".recharts-area-curve")?.getAttribute("stroke")).toBe("hsl(var(--brand))");
    expect(container.querySelector(".recharts-area-area")?.getAttribute("fill") ?? "none").toBe("none");
    expect(container.innerHTML).not.toContain("brand-light");
    expect(screen.queryByText(/When a body crosses the line between the boards/)).toBeNull();  // no sentence under the chart
    // one row: no above/below pill and no range words; "Now" is plain text
    expect(screen.queryByText(/Below the threshold|Above the threshold|last 5 minutes/)).toBeNull();
    expect(screen.getByText("Now 0.30 dB")).toBeInTheDocument();
    expect(container.querySelector("[data-signal-now]")?.className).not.toMatch(/bg-|border/);
  });

  it("says movement is detected when the latest report is above the threshold, in the chart's label", () => {
    render(<LiveSignal room={room({ headcount: 1 })} signal={signal({ points: [{ ts: NOW - 4, motion_std: 2.2, headcount: 1 }] })} size={size} />);
    expect(screen.getByRole("figure")).toHaveAccessibleName("Live signal of Demo Room: now 2.20 dB, above the threshold of 1.30 dB: movement detected.");
    expect(T("sig.chart_above", { name: "Demo Room", now: "2.20", x: "1.30" }, "ms")).toBe("Isyarat langsung Demo Room: kini 2.20 dB, di atas ambang 1.30 dB: pergerakan dikesan.");
    expect(screen.getByText("Now 2.20 dB")).toBeInTheDocument();
  });

  it("draws no threshold line or tick when a trained model is counting, and says so to a screen reader", () => {
    const { container } = render(<LiveSignal room={room()} signal={signal({ threshold: null })} size={size} />);
    expect(container.querySelector(".recharts-reference-line")).toBeNull();
    expect(container.querySelector(".recharts-reference-area")).toBeNull();
    expect(container.querySelector("[data-threshold-tick]")).toBeNull();
    expect(screen.getByRole("figure")).toHaveAccessibleName(
      "Live signal of Demo Room: now 0.30 dB; a trained model is counting, so there is no single threshold.");
    expect(screen.queryByText(/Above the threshold|Below the threshold/)).toBeNull();
  });

  it("explains an empty chart: no reports, no room, history database offline", () => {
    const { rerender } = render(<LiveSignal room={room()} signal={signal({ points: [], last_report_ts: null })} size={size} />);
    expect(screen.getByText("No reports from this room in the last 5 minutes.")).toBeInTheDocument();
    rerender(<LiveSignal room={undefined} signal={undefined} size={size} />);
    expect(screen.getByText("No room with Wi-Fi sensing has reported yet.")).toBeInTheDocument();
    rerender(<LiveSignal room={room()} signal={undefined} error={new ApiError(503, "offline")} size={size} />);
    expect(screen.getByText("History database offline. The chart returns when it is back.")).toBeInTheDocument();
    rerender(<LiveSignal room={room()} signal={signal()} error={new ApiError(503, "offline")} size={size} />);  // last good data stays
    expect(document.querySelector("[data-threshold-tick]")).toHaveTextContent("1.3");
    expect(screen.getByText(/History database offline/)).toBeInTheDocument();
  });

  it("greys the chart out and says since when, when the sensor is offline", () => {
    const off = room({ live: false, count_ts: NOW - 140 });
    const { container, rerender } = render(<LiveSignal room={off} signal={signal({ last_report_ts: NOW - 140 })} size={size} />);
    expect(screen.getAllByText("Sensor offline").length).toBeGreaterThan(0);
    expect(screen.getByText("No data since 06:57")).toBeInTheDocument();  // 140 s before 07:00
    expect(container.querySelector("[data-signal-chart]")).toHaveAttribute("data-signal-chart", "offline");
    expect(container.querySelector(".recharts-reference-area")).toBeNull();  // no live band above the threshold
    const line = container.querySelector(".recharts-area-curve")!;
    expect(line.getAttribute("stroke")).toBe("hsl(var(--off))");  // grey, not the brand teal
    expect(container.innerHTML).not.toContain('stroke="hsl(var(--brand))"');
    expect(screen.queryByText(/Now 0.30 dB/)).toBeNull();
    expect(screen.queryByText(/Above the threshold|Below the threshold/)).toBeNull();
    expect(screen.queryByText(/When a body crosses|The line stops at the last report/)).toBeNull();  // no sentence under the chart
    expect(screen.getByRole("figure")).toHaveAccessibleName("Live signal of Demo Room: sensor offline, no data since 06:57; threshold 1.30 dB.");
    // offline for longer than the chart covers: no points left, the same words stand in for the chart
    rerender(<LiveSignal room={room({ live: false, count_ts: NOW - 3600 })} signal={signal({ points: [], last_report_ts: null })} size={size} />);
    expect(screen.getByText("No data since 06:00")).toBeInTheDocument();
    expect(screen.queryByText(/No reports from this room/)).toBeNull();
    // back online: brand colours and the band return
    rerender(<LiveSignal room={room()} signal={signal()} size={size} />);
    expect(container.querySelector("[data-signal-chart]")).toHaveAttribute("data-signal-chart", "live");
    expect(container.querySelector(".recharts-reference-area")).not.toBeNull();
    expect(screen.queryByText(/No data since/)).toBeNull();
  });
});

describe("which room the live signal shows", () => {
  const PLAN3 = [{ id: "room1", linked: true }, { id: "room2", linked: false }, { id: "room3", linked: false }];
  afterEach(() => { vi.restoreAllMocks(); localStorage.clear(); });

  it("starts on the room with the most recent movement, then a live sensing room, then a room with a sensor pair", () => {
    const a = room({ room_id: "roomA" }), linked = room({ room_id: "room1" }), counter = room({ room_id: "hall", counter: "count", headcount: 40 });
    expect(defaultRoom([a, linked], PLAN3)).toBe("room1");                                  // live, its boards on the plan
    expect(defaultRoom([a, { ...linked, live: false }], PLAN3)).toBe("roomA");              // the live one
    const older = room({ room_id: "roomB", headcount: 2, count_ts: NOW - 20 }), newer = room({ room_id: "roomC", headcount: 1, count_ts: NOW - 3 });
    expect(defaultRoom([linked, older, newer], PLAN3)).toBe("roomC");                       // occupied now, newest report
    expect(defaultRoom([linked, { ...newer, live: false }], PLAN3)).toBe("room1");          // an offline room is not "moving"
    expect(defaultRoom([counter], PLAN3)).toBe("room1");                                    // a counter has no Wi-Fi signal
    expect(defaultRoom([], PLAN3)).toBe("room1");                                           // nothing reports: the pair on the plan
    expect(defaultRoom([], [{ id: "x", linked: false }])).toBe("x");
    expect(defaultRoom([], [])).toBeNull();
  });

  it("takes the address first, then the last choice, then the default, and passes over rooms it does not know", () => {
    const known = ["room1", "room2", "room3"];
    expect(pickRoom(known, "room2", "room3", "room1")).toBe("room2");
    expect(pickRoom(known, null, "room3", "room1")).toBe("room3");
    expect(pickRoom(known, null, null, "room1")).toBe("room1");
    expect(pickRoom(known, "gone", "room3", "room1")).toBe("room3");
    expect(pickRoom(known, "<script>", "also-gone", "room1")).toBe("room1");
    expect(pickRoom(known, "gone", null, null)).toBeNull();
    expect(pickRoom([], "room1", "room1", "room1")).toBeNull();
  });

  it("keeps the last choice in this browser, and carries on when storage is blocked", () => {
    storeRoom("room2");
    expect(localStorage.getItem(ROOM_KEY)).toBe("room2");
    expect(storedRoom()).toBe("room2");
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => { throw new DOMException("blocked", "SecurityError"); });
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => { throw new DOMException("full", "QuotaExceededError"); });
    expect(storedRoom()).toBeNull();
    expect(() => storeRoom("room3")).not.toThrow();
  });
});

function mockMotionPreference(reduce: boolean) {
  const listeners = new Set<() => void>();
  const mq = { matches: reduce, addEventListener: (_: string, f: () => void) => listeners.add(f), removeEventListener: (_: string, f: () => void) => listeners.delete(f) };
  vi.stubGlobal("matchMedia", () => mq);
  return { set(v: boolean) { mq.matches = v; listeners.forEach((f) => f()); } };
}

describe("movement: only on new data, none with reduced motion or in an emergency", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("reads the reduced-motion preference and follows changes to it", () => {
    expect(prefersReducedMotion()).toBe(false);  // no matchMedia at all: treated as "no preference", never a crash
    const pref = mockMotionPreference(true);
    const { result } = renderHook(() => usePrefersReducedMotion());
    expect(result.current).toBe(true);
    act(() => pref.set(false));
    expect(result.current).toBe(false);
  });

  it("counts a report only when it is newer than every report seen before", () => {
    const { result, rerender } = renderHook(({ v }: { v: number | null }) => useNewer(v), { initialProps: { v: null as number | null } });
    expect(result.current).toBe(0);
    rerender({ v: 100 });  // first value to arrive: page load, not news
    expect(result.current).toBe(0);
    rerender({ v: 100 });  // a poll that brought nothing new
    expect(result.current).toBe(0);
    rerender({ v: 110 });
    expect(result.current).toBe(1);
    rerender({ v: 100 });  // a late answer from the other request: older, so nothing replays
    rerender({ v: 110 });
    expect(result.current).toBe(1);
    rerender({ v: null });  // sensor offline, then back with a newer report
    rerender({ v: 120 });
    expect(result.current).toBe(2);
  });

  it("changes a count instantly when still", () => {
    const { rerender, container } = render(<NumberTicker value={1} still />);
    expect(container).toHaveTextContent("1");
    rerender(<NumberTicker value={7} still format={(n) => `${n}+`} />);
    expect(container).toHaveTextContent("7+");
  });

  function plan(data: RoomsState, still: boolean, qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })) {
    let signals: Record<string, Signal> = { room1: signal({ points: [{ ts: (data.rooms[0]?.count_ts ?? NOW) - 10, motion_std: 0.4, headcount: 0 },
      { ts: data.rooms[0]?.count_ts ?? NOW, motion_std: 2.4, headcount: 1 }], last_report_ts: data.rooms[0]?.count_ts ?? NOW }) };
    const ui = (d: RoomsState, s: boolean) => (
      <QueryClientProvider client={qc}><MemoryRouter><LazyMotion features={domAnimation}>
        <LivePlan rooms={d.rooms} names={{ room2: "Hall A" }} still={s} signals={signals} onSelect={() => {}} />
      </LazyMotion></MemoryRouter></QueryClientProvider>
    );
    const view = render(ui(data, still));
    // the next answer of GET /api/signals (the plan reads every room's signal from it, it asks for nothing itself)
    return { ...view, qc, signals: (next: Signal) => { signals = { room1: next }; }, update: (d: RoomsState, s = still) => view.rerender(ui(d, s)) };
  }

  beforeEach(() => vi.stubGlobal("fetch", vi.fn(async () => new Response("{}", { status: 503 }))));

  it("rings a tile once a new report arrives, not on page load", () => {
    const first = state({ rooms: [room({ headcount: 1 })] });
    const view = plan(first, false);
    expect(view.container.querySelector(".report-pulse")).toBeNull();
    view.update(first);  // the same data again
    expect(view.container.querySelector(".report-pulse")).toBeNull();
    const next = state({ rooms: [room({ headcount: 1, count_ts: NOW + 6 })] });
    view.signals(signal({ points: [{ ts: NOW + 6, motion_std: 2.4, headcount: 1 }], last_report_ts: NOW + 6 }));
    view.update(next);
    expect(view.container.querySelectorAll(".report-pulse")).toHaveLength(1);
  });

  it("does not move at all when still (reduced motion, emergency or drill)", () => {
    const view = plan(state({ rooms: [room({ headcount: 1 })] }), true);
    view.signals(signal({ points: [{ ts: NOW + 6, motion_std: 2.4, headcount: 1 }], last_report_ts: NOW + 6 }));
    view.update(state({ rooms: [room({ headcount: 2, count_ts: NOW + 6 })] }));
    expect(view.container.querySelector(".report-pulse")).toBeNull();
    expect(within(view.container.querySelector("[data-room=room1]") as HTMLElement).getByText("2")).toBeInTheDocument();  // instantly
  });

  it("draws no sender/receiver line, dots or labels on a tile: name, count, status and trace only", () => {
    for (const r of [room({ headcount: 1 }), room({ live: false, count_ts: NOW - 200 })]) {
      const view = plan(state({ rooms: [r] }), false);
      // room1 has a sensor pair on the plan: it is drawn in the room panel and the editor, not on the Overview
      expect(view.container.querySelector("[data-beam]")).toBeNull();
      expect(view.container.querySelectorAll("svg.absolute circle")).toHaveLength(0);  // the plan drawing: no sensor dots
      expect(view.container).not.toHaveTextContent("Sender");
      expect(view.container).not.toHaveTextContent("Receiver");
      expect(within(view.container.querySelector("[data-room=room1]") as HTMLElement).getByText("Demo Room")).toBeInTheDocument();
      view.unmount();
    }
    render(<LivePlanLegend />);
    expect(screen.queryByText("Signal line, brighter with movement")).toBeNull();
  });

  it("slides in only activity rows that arrive after the list is first shown, and none when still", () => {
    const a = alert({ id: "a", subject: "NADI: Sensor back online (Demo Room)", message: "m" });
    const b = alert({ id: "b", subject: "NADI: Second", message: "m" });
    const list = (alerts: Alert[], still = false) => <MemoryRouter><LiveActivity alerts={alerts} now={NOW} still={still} /></MemoryRouter>;
    const view = render(list([a]));
    expect(view.container.querySelector(".slide-in")).toBeNull();
    expect(screen.getByText("Sensor back online (Demo Room)")).toBeInTheDocument();  // "NADI:" dropped
    view.rerender(list([b, a]));
    expect(view.container.querySelectorAll(".slide-in")).toHaveLength(1);
    const still = render(list([a], true));
    still.rerender(list([b, a], true));
    expect(still.container.querySelector(".slide-in")).toBeNull();
  });
});

describe("floor plan tiles: labels, keyboard, rooms without a sensor", () => {
  beforeEach(() => vi.stubGlobal("fetch", vi.fn(async () => new Response("{}", { status: 503 }))));
  afterEach(() => vi.unstubAllGlobals());

  const show = (rooms: Room[], onSelect = vi.fn(), extra: { selected?: string; onOpen?: (id: string) => void } = {}) => {
    render(
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
        <LazyMotion features={domAnimation}><LivePlan rooms={rooms} names={{ room2: "Hall A" }} still onSelect={onSelect} {...extra} /></LazyMotion>
      </QueryClientProvider>);
    return onSelect;
  };

  it("names every room for screen readers, with its count and a status word", () => {
    show([room({ headcount: 1 })]);
    expect(screen.getByRole("group", { name: "Floor plan" })).toBeInTheDocument();
    const tile = screen.getByRole("button", { name: "Demo Room: 1 person, Occupied" });
    expect(within(tile).getByText("Occupied")).toBeInTheDocument();  // a word, not colour alone
  });

  it("shows a room with no sensor as '–' and 'No sensor', like the Floor plan page; '?' is only for a sensor that stopped", () => {
    const onSelect = show([room()]);
    // a button like the others: its panel says there is no sensor in the room
    const hall = screen.getByRole("button", { name: "Hall A: no sensor" });
    expect(within(hall).getByText("–")).toBeInTheDocument();
    expect(within(hall).queryByText("?")).toBeNull();
    expect(within(hall).getByText("No sensor")).toBeInTheDocument();
    expect(hall.getAttribute("data-status")).toBe("none");
    fireEvent.click(hall);
    expect(onSelect).toHaveBeenCalledWith("room2");
    // no name set for room3: the name written on the floor plan, never the room ID
    expect(screen.getByRole("button", { name: "Room 3: no sensor" })).toBeInTheDocument();
    expect(screen.queryByText("room3")).toBeNull();
  });

  it("shows an offline sensor as '?' and 'Offline', never as 0", () => {
    show([room({ live: false, headcount: 0 })]);
    const tile = screen.getByRole("button", { name: "Demo Room: count unknown, Offline" });
    expect(within(tile).getByText("?")).toBeInTheDocument();
    expect(within(tile).queryByText("0")).toBeNull();
  });

  it("selects a room with the keyboard or a click (a real button), and opens it on a double-click", () => {
    const onOpen = vi.fn();
    const onSelect = show([room()], vi.fn(), { selected: "room2", onOpen });
    const tile = screen.getByRole("button", { name: /Demo Room/ });
    expect(tile.tagName).toBe("BUTTON");  // so Enter and Space select it like a click
    tile.focus();
    expect(document.activeElement).toBe(tile);
    fireEvent.click(tile);
    expect(onSelect).toHaveBeenCalledWith("room1");
    expect(onOpen).not.toHaveBeenCalled();
    fireEvent.doubleClick(tile);
    expect(onOpen).toHaveBeenCalledWith("room1");
  });

  it("marks the selected room with a ring and a tick tab, and says so to screen readers", () => {
    show([room()], vi.fn(), { selected: "room2" });
    const hall = screen.getByRole("button", { name: "Hall A: no sensor" });
    expect(hall).toHaveAttribute("aria-pressed", "true");
    expect(hall.querySelector("[data-selected-tab] svg")).not.toBeNull();  // a shape, not only the purple
    expect(hall.innerHTML).toContain("ring-primary");
    const other = screen.getByRole("button", { name: /Demo Room/ });
    expect(other).toHaveAttribute("aria-pressed", "false");
    expect(other.querySelector("[data-selected-tab]")).toBeNull();
    // how to use the plan is said to screen readers too
    expect(screen.getByRole("group", { name: "Floor plan" })).toHaveAccessibleDescription(/Click a room for its chart, double-click for details/);
  });

  it("asks the server for nothing itself: every tile reads the one answer it is given", () => {
    const fetchSpy = vi.mocked(fetch);
    const many = Array.from({ length: 13 }, (_, i) => room({ room_id: i < 3 ? `room${i + 1}` : `extra${i}`, headcount: 1 }));
    show(many, vi.fn(), {});
    expect(fetchSpy).not.toHaveBeenCalled();
  });

  it("labels a simulated counter as such", () => {
    show([room({ counter: "count", headcount: 120 })]);
    expect(screen.getByText("Simulated counter (phase 2)")).toBeInTheDocument();
  });
});

describe("today's summary", () => {
  it("starts the day at midnight in Malaysia", () => {
    expect(midnightBefore(NOW)).toBe(NOW - 7 * 3600);
    expect(minutesToday(NOW)).toBe(7 * 60);
    expect(minutesToday(midnightBefore(NOW) + 61)).toBe(15);
  });

  it("works out the peak and the hours occupied from the bucketed history", () => {
    const b = 900, start = midnightBefore(NOW) + 6 * 3600;  // first report at 06:00
    const hist = { now: NOW, bucket_s: b, rooms: {
      room1: [[start - 86400, 9], [start, 0], [start + b, 2], [start + 2 * b, 1], [start + 4 * b, 0]] as [number, number][],  // 06:45 missing
      room2: [[start + b, 3], [start + 2 * b, 0], [start + 3 * b, 0], [start + 4 * b, 0]] as [number, number][],
    } };
    const today = todayStats(hist, NOW)!;
    expect(today.peak).toBe(5);                      // 2 + 3 at 06:15; yesterday's 9 is not today
    expect(today.occupiedHours).toBeCloseTo(0.5);    // 06:15 and 06:30
    expect(todayStats(undefined, NOW)).toBeNull();
    expect(todayStats({ now: NOW, bucket_s: b, rooms: {} }, NOW)).toEqual({ peak: 0, occupiedHours: 0 });
  });

  it("writes the uptime so that any time offline shows: 100% only when nothing was missed", () => {
    expect(uptimeText(100)).toBe("100%");
    expect(uptimeText(99.97)).toBe("99.9%");  // rounded down, never up to 100%
    expect(uptimeText(99.72)).toBe("99.7%");
    expect(uptimeText(75)).toBe("75.0%");
    expect(uptimeText(0)).toBe("0.0%");
    expect(uptimeText(null)).toBe("–");
    expect(uptimeText(undefined)).toBe("–");
  });

  const QUIET = { value: "Normal", hint: "no drill today" };

  it("shows the four rows, and dashes with a note before any data", () => {
    const { rerender, container } = render(<TodayCard today={{ peak: 5, occupiedHours: 3.5 }} uptimePct={99.72} incidents={QUIET} />);
    expect(screen.getByRole("heading", { level: 2, name: "Today's summary" })).toBeInTheDocument();
    expect(container.querySelector("svg")).toBeNull();  // a label, a number and what it counts: no icons
    expect(container.querySelectorAll("tbody tr")).toHaveLength(4);
    expect(screen.getByText("5")).toBeInTheDocument();
    expect(screen.getByText("3.5 h")).toBeInTheDocument();
    expect(screen.getByText("99.7%")).toBeInTheDocument();
    expect(screen.getByText("Emergency and drills")).toBeInTheDocument();
    expect(screen.getByText("Normal")).toBeInTheDocument();
    expect(screen.getByText("no drill today")).toBeInTheDocument();
    expect(screen.queryByText(/RM/)).toBeNull();  // the waste figure is the highlight of the status card, not repeated here
    rerender(<TodayCard today={{ peak: 5, occupiedHours: 3.5 }} uptimePct={100} incidents={QUIET} />);
    expect(screen.getByText("100%")).toBeInTheDocument();
    rerender(<TodayCard today={null} uptimePct={null} incidents={QUIET} />);
    expect(screen.getAllByText("–").length).toBeGreaterThanOrEqual(3);
    expect(screen.getAllByText("no data yet today")).toHaveLength(3);
    // each figure says why it is missing from its own request: history answers, the uptime request does not
    rerender(<TodayCard today={{ peak: 5, occupiedHours: 3.5 }} uptimePct={undefined} incidents={QUIET} uptimeOffline />);
    expect(screen.getAllByText("history database offline")).toHaveLength(1);
    expect(screen.queryByText("no data yet today")).toBeNull();
  });

  it("links to the full summary from its title row", () => {
    render(<MemoryRouter><TodayCard today={null} uptimePct={null} incidents={QUIET} link="/summary" /></MemoryRouter>);
    expect(screen.getByRole("link", { name: "View full summary" })).toHaveAttribute("href", "/summary");
  });

  it("writes the emergency and drill line from what is running now and what happened today", () => {
    const start = midnightBefore(NOW);
    const inc = (extra: Partial<IncidentSummary>): IncidentSummary => ({
      id: "i1", kind: "drill", started: start + 3600, ended: start + 3900, duration_s: 300, started_by: "warden", ended_by: "warden",
      start_total: 3, start_at_least: false, demo: false, marked: 0, offline_rooms: 0, ...extra,
    });
    const calm = { on: false, since: null, drill: false, id: null };
    expect(drillLine({ incidents: [], active: null }, calm, NOW)).toEqual({ value: "Normal", hint: "no drill today", tone: undefined });
    expect(drillLine(undefined, undefined, NOW).value).toBe("Normal");
    // one drill at 01:00, then a second at 06:30: the count and the time of the last one
    expect(drillLine({ incidents: [inc({})], active: null }, calm, NOW).hint).toBe("1 drill today, last at 01:00");
    expect(drillLine({ incidents: [inc({}), inc({ id: "i2", started: start + 6.5 * 3600 })], active: null }, calm, NOW).hint)
      .toBe("2 drills today, last at 06:30");
    // no drill today, one yesterday: when the last one was
    expect(drillLine({ incidents: [inc({ started: start - 3600 })], active: null }, calm, NOW).hint).toMatch(/^last drill: /);
    // a real emergency today is named before the drills, and a drill never counts as one
    const mixed = drillLine({ incidents: [inc({ id: "r", kind: "real" }), inc({})], active: null }, calm, NOW);
    expect(mixed.hint).toBe("emergencies today: 1 · 1 drill today, last at 01:00");
    expect(drillLine({ incidents: [inc({ id: "r", kind: "real" })], active: null }, calm, NOW).hint).toBe("emergencies today: 1");
    // while one runs, the value says which and is red
    expect(drillLine({ incidents: [], active: null }, { on: true, since: NOW - 60, drill: true, id: "d" }, NOW)).toMatchObject({ value: "Drill running", tone: "crit" });
    expect(drillLine({ incidents: [], active: null }, { on: true, since: NOW - 60, drill: false, id: "e" }, NOW)).toMatchObject({ value: "Emergency active", tone: "crit" });
  });

  it("works out one row per room for the full summary, with a dash where a room has no figure", () => {
    const b = 900, start = midnightBefore(NOW) + 6 * 3600;
    const hist = { now: NOW, bucket_s: b, rooms: { room1: [[start, 0], [start + b, 2], [start + 2 * b, 1]] as [number, number][] } };
    const uptime = { now: NOW, since: start, stale_s: 30, pct: 75, rooms: {
      room1: { first_ts: start, up_s: 2700, expected_s: 3600 }, room2: { first_ts: null, up_s: 0, expected_s: 0 } } };
    const amounts = { rm: 0, kwh: 0, co2_kg: 0 };
    const energy = { now: NOW, today: amounts, week: amounts, previous_week: amounts, yesterday: amounts, daily: [], tariff_rm_per_kwh: 0.2983,
      ac_kw: 10, co2_kg_per_kwh: 0.75, stale_ts: null,
      by_room: [{ room_id: "room1", name: "Demo Room", rm_today: 0.7, rm_week: 2 }, { room_id: "room3", name: "Room 3", rm_today: 0, rm_week: 0 }] };
    expect(summaryRows(hist, uptime, energy, NOW)).toEqual([
      { id: "room1", peak: 2, hours: 0.5, uptimePct: 75, wasteRm: 0.7 },
      { id: "room2", peak: null, hours: null, uptimePct: null, wasteRm: 0 },  // known to the uptime answer only: dashes, never 0 people
    ]);
    expect(summaryRows(undefined, undefined, undefined, NOW)).toEqual([]);
    expect(summaryRows(hist, undefined, undefined, NOW)[0]).toMatchObject({ uptimePct: null, wasteRm: null });
  });
});
