// The room panel's Signal section (pair picture, live chart, recorded waves, rooms without a sensor) and the
// Calibration page (which detector is live, the model's true state, the labelled dots), on canned answers.
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import { LabelledDots, LiveDetector, ModelTraining, detectorRows, modelStatus } from "@/components/calibration-charts";
import { RecordedWaves, kindName, longDate, sourceLine } from "@/components/recorded-waves";
import { RoomDrawer } from "@/components/room-drawer";
import { SignalDiagram, pairCaption, pairState } from "@/components/signal-diagram";
import { TooltipProvider } from "@/components/ui/tooltip";
import { hhmmss, peopleWord } from "@/lib/format";
import { T } from "@/lib/i18n";
import { cleanRecording, isRecordingFile, spread } from "@/lib/recordings";
import { SettingsProvider } from "@/lib/settings";
import { CalibrationPage } from "@/pages/calibration";
import type { Detector, ModelFacts, Room, RoomsState, Signal } from "@/lib/types";

const NOW = Math.floor(Date.now() / 1000);

const room = (extra: Partial<Room> = {}): Room => ({
  room_id: "room1", name: "Demo Room", headcount: 0, at_least: false, counter: "csi", count_ts: NOW - 4, temp_c: 24, humidity: 60,
  live: true, waste: null, ...extra,
});

const signal = (extra: Partial<Signal> = {}): Signal => ({
  now: NOW, room_id: "room1", minutes: 5, threshold: 1.301, last_report_ts: NOW - 4,
  points: [{ ts: NOW - 14, motion_std: 0.5, headcount: 0 }, { ts: NOW - 4, motion_std: 0.42, headcount: 0 }], ...extra,
});

const above = signal({ points: [{ ts: NOW - 4, motion_std: 2.1, headcount: 1 }] });

const rooms = (extra: Partial<RoomsState> = {}): RoomsState => ({
  now: NOW, stale_s: 30, rooms: [room()], waste_today_rm: 0, emergency: { on: false, since: null, drill: false, id: null },
  accountability: {}, alerts: [], offline: {}, stale_ts: null, demo: { on: false, t: null }, clock: null, ...extra,
});

const recording = (kind: string, values: number[]) => ({
  room_id: "room1", name: kind, kind, date: "2026-11-12", distance_m: 3.5, packets: 1, duration_ms: 1, std_db: 99, mean_dbm: 0,
  points: values.map((v, i) => [1000 + i * 20, v]),
});

beforeEach(() => {
  vi.stubGlobal("ResizeObserver", class { observe() {} unobserve() {} disconnect() {} });
  vi.stubGlobal("fetch", vi.fn(async () => new Response("{}", { status: 503 })));
});
afterEach(() => vi.unstubAllGlobals());

describe("sensor pair picture", () => {
  it("follows the latest real report: calm below the threshold, disturbed above, offline when the sensor is", () => {
    expect(pairState(room(), signal())).toBe("calm");
    expect(pairState(room(), above)).toBe("disturbed");
    expect(pairState(room({ live: false }), above)).toBe("offline");
    expect(pairState(room(), signal({ points: [] }))).toBe("waiting");
    expect(pairState(room(), undefined)).toBe("waiting");
    // exactly on the threshold is not above it (the same rule as the count)
    expect(pairState(room(), signal({ points: [{ ts: NOW, motion_std: 1.301, headcount: 0 }] }))).toBe("calm");
  });

  it("follows the count of the report when a model is counting and there is no threshold", () => {
    expect(pairState(room(), signal({ threshold: null, points: [{ ts: NOW, motion_std: 0.2, headcount: 2 }] }))).toBe("disturbed");
    expect(pairState(room(), signal({ threshold: null }))).toBe("calm");
    expect(pairCaption("calm", signal({ threshold: null }))).toBe("Calm signal: 0.42 dB, counted as empty");
  });

  it("says in words what it shows, once: the caption gives the live reading and no second sentence repeats it", () => {
    expect(pairCaption("calm", signal())).toBe("Calm signal: 0.42 dB, below the threshold of 1.30 dB");
    expect(pairCaption("disturbed", above)).toBe("Disturbed signal: 2.10 dB, above the threshold of 1.30 dB");
    expect(pairCaption("offline", above)).toBe("Sensor offline: no signal is being measured");
    expect(pairCaption("waiting", signal({ points: [] }))).toBe("No report from this room in the last 5 minutes");
    render(<SignalDiagram state="calm" caption="Calm" reportTs={NOW} still={false} />);
    expect(screen.queryByText(/Illustration/)).toBeNull();
    expect(screen.getByRole("img", { name: "Calm" })).toBeInTheDocument();
    expect(screen.getByText("Sender")).toBeInTheDocument();
    expect(screen.getByText("Receiver")).toBeInTheDocument();
  });

  it("draws a person in the path only when the signal is disturbed, and a grey dashed line when offline", () => {
    const calm = render(<SignalDiagram state="calm" caption="c" reportTs={NOW} still={false} />);
    expect(calm.container.querySelector("[data-person]")).toBeNull();
    calm.unmount();
    const busy = render(<SignalDiagram state="disturbed" caption="d" reportTs={NOW} still={false} />);
    expect(busy.container.querySelector("[data-person]")).not.toBeNull();
    expect(busy.container.querySelector("[data-scatter]")).not.toBeNull();
    busy.unmount();
    const off = render(<SignalDiagram state="offline" caption="o" reportTs={NOW} still={false} />);
    expect(off.container.querySelector("[data-person]")).toBeNull();
    expect(off.container.querySelector("path[stroke-dasharray]")?.getAttribute("stroke")).toBe("hsl(var(--off))");
    expect(off.container.querySelector(".wave-travel")).toBeNull();
  });

  it("is still on load, travels once per newer report, and never while still or offline", () => {
    const view = render(<SignalDiagram state="calm" caption="c" reportTs={NOW} still={false} />);
    expect(view.container.querySelector(".wave-travel")).toBeNull();  // page load is not news
    view.rerender(<SignalDiagram state="calm" caption="c" reportTs={NOW} still={false} />);
    expect(view.container.querySelector(".wave-travel")).toBeNull();  // the same report again
    view.rerender(<SignalDiagram state="calm" caption="c" reportTs={NOW + 10} still={false} />);
    expect(view.container.querySelectorAll(".wave-travel")).toHaveLength(1);
    view.rerender(<SignalDiagram state="disturbed" caption="d" reportTs={NOW + 20} still={false} />);
    expect(view.container.querySelectorAll(".wave-travel")).toHaveLength(2);  // before and after the person
    view.rerender(<SignalDiagram state="disturbed" caption="d" reportTs={NOW + 30} still />);
    expect(view.container.querySelector(".wave-travel")).toBeNull();  // emergency, drill or reduced motion
    view.rerender(<SignalDiagram state="offline" caption="o" reportTs={NOW + 40} still={false} />);
    expect(view.container.querySelector(".wave-travel")).toBeNull();
  });

  it("puts room names and captions on the page as text, never as markup", () => {
    const { container } = render(<SignalDiagram state="calm" caption={'<img src=x onerror="alert(1)">'} reportTs={NOW} still />);
    expect(container.querySelector("img")).toBeNull();
    expect(container.querySelector("[data-pair-caption]")?.textContent).toBe('<img src=x onerror="alert(1)">');
  });
});

describe("recorded waves", () => {
  it("accepts only plain recording file names", () => {
    expect(isRecordingFile("room1-empty.json")).toBe(true);
    for (const bad of ["../x.json", "a/b.json", "x.js", "", null, "http://evil/x.json", ".hidden.json"]) expect(isRecordingFile(bad)).toBe(false);
  });

  it("works the figures out from the packets, not from what the file says about itself", () => {
    const r = cleanRecording(recording("empty", [-50, -52, -50, -52]), "room1")!;
    expect(r.packets).toBe(4);
    expect(r.std_db).toBeCloseTo(1);
    expect(r.mean_dbm).toBeCloseTo(-51);
    expect(r.duration_ms).toBe(60);
    expect(r.points[0]).toEqual([0, -50]);
    expect(spread([])).toBe(0);
  });

  it("drops what is not a recording of this room", () => {
    expect(cleanRecording(recording("empty", [-50, -51]), "room2")).toBeNull();
    expect(cleanRecording({ room_id: "room1", points: "x" }, "room1")).toBeNull();
    expect(cleanRecording({ room_id: "room1", points: [[0, -50], ["a", "b"], [5, 40], [1, null]] }, "room1")).toBeNull();
    expect(cleanRecording(null, "room1")).toBeNull();
    const odd = cleanRecording({ ...recording("<b>", [-50, -51]), date: "<script>", distance_m: "3" }, "room1")!;
    expect(odd.kind).toBe("other");
    expect(odd.date).toBe("");
    expect(odd.distance_m).toBeNull();
  });

  it("names a recording honestly and gives its date and setup", () => {
    expect(kindName("empty")).toBe("Empty room");
    expect(kindName("walk")).toBe("One person walking through the line");
    expect(kindName("hand")).toBe("Hand waved near the receiver");
    expect(kindName("whatever")).toBe("Recording");
    expect(longDate("2026-11-12")).toBe("12 November 2026");
    expect(sourceLine({ date: "2026-11-12", distance_m: 3.5 })).toBe("Recorded on 12 November 2026 with the boards 3.5 m apart.");
    expect(sourceLine({ date: "2026-11-12", distance_m: null })).toBe("Recorded on 12 November 2026.");
  });

  function show(files: Record<string, unknown>) {
    vi.stubGlobal("fetch", vi.fn(async (url: string) => (url in files
      ? new Response(JSON.stringify(files[url]), { status: 200 }) : new Response("<!doctype html>", { status: 200 }))));
    return render(
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
        <RecordedWaves roomId="room1" size={{ width: 420, height: 130 }} />
      </QueryClientProvider>);
  }

  it("stacks the recordings of this room on one y-axis and one time scale, with the measured spread under each", async () => {
    const { container } = show({
      "/recordings/index.json": { recordings: [{ room_id: "room1", file: "room1-empty.json" }, { room_id: "room1", file: "room1-walk.json" },
        { room_id: "room2", file: "room2-empty.json" }, { room_id: "room1", file: "../secret.json" }] },
      "/recordings/room1-empty.json": recording("empty", Array.from({ length: 51 }, (_, i) => (i % 2 ? -50 : -52))),
      "/recordings/room1-walk.json": recording("walk", Array.from({ length: 101 }, (_, i) => (i % 2 ? -44 : -60))),
    });
    await waitFor(() => expect(container.querySelector("[data-recorded-waves]")).not.toBeNull());
    expect(screen.getByText("Empty room")).toBeInTheDocument();
    expect(screen.getByText("One person walking through the line")).toBeInTheDocument();
    expect(screen.getByText("Measured spread (standard deviation): 1.00 dB over 51 packets")).toBeInTheDocument();
    expect(screen.getByText("Measured spread (standard deviation): 8.00 dB over 101 packets")).toBeInTheDocument();
    expect(screen.getByText(/Signal strength of each Wi-Fi packet between this room's two boards, 50 per second\. A body in the path disturbs it\./)).toBeInTheDocument();
    expect(screen.getByText("Recorded on 12 November 2026 with the boards 3.5 m apart.")).toBeInTheDocument();
    const charts = [...container.querySelectorAll("[data-recording]")];
    expect(charts.map((c) => c.getAttribute("data-recording"))).toEqual(["empty", "walk"]);
    // the same axis on both: the lowest and highest tick labels match
    const ticks = charts.map((c) => [...c.querySelectorAll(".recharts-yAxis .recharts-cartesian-axis-tick-value")].map((t) => t.textContent));
    expect(ticks[0].length).toBeGreaterThan(1);
    expect(ticks[0]).toEqual(ticks[1]);
    const xs = charts.map((c) => [...c.querySelectorAll(".recharts-xAxis .recharts-cartesian-axis-tick-value")].map((t) => t.textContent));
    expect(xs[0]).toEqual(xs[1]);
  });

  it("shows nothing when the room has no recordings or the files cannot be read", async () => {
    const none = show({ "/recordings/index.json": { recordings: [] } });
    await act(async () => { await new Promise((r) => setTimeout(r, 20)); });
    expect(none.container.querySelector("[data-recorded-waves]")).toBeNull();
    none.unmount();
    const missing = show({});  // the console answers every unknown path with its own page, not JSON
    await act(async () => { await new Promise((r) => setTimeout(r, 20)); });
    expect(missing.container.querySelector("[data-recorded-waves]")).toBeNull();
  });
});

describe("room panel", () => {
  function panel(props: Partial<Parameters<typeof RoomDrawer>[0]>, data = rooms(), sig: Signal | null = signal(), setup?: (qc: QueryClient) => void) {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false, staleTime: Infinity, refetchInterval: false } } });
    qc.setQueryData(["rooms", "en"], data);
    qc.setQueryData(["me"], { admin: false, who: null, rule: "token", viewer: true, viewer_required: false });
    if (sig) qc.setQueryData(["signal", "room1", 5], sig);
    qc.setQueryData(["recordings", "room1"], []);
    setup?.(qc);
    return render(
      <QueryClientProvider client={qc}><MemoryRouter><SettingsProvider>
        <RoomDrawer room={null} now={NOW} onClose={() => {}} {...props} />
      </SettingsProvider></MemoryRouter></QueryClientProvider>);
  }

  it("reads in the order a visitor asks: count and 'since', the exit, people, signal, climate, facts, sensors", () => {
    const m = NOW - (NOW % 60);
    panel({ room: room({ headcount: 1 }) }, rooms(), signal(), (qc) => {
      qc.setQueryData(["people", "room1", 60], { now: NOW, bucket_s: 60, room_id: "room1", people: [[m - 60, 0, 0], [m, 1, 1]], since: { occupied: true, ts: NOW - 40 } });
      qc.setQueryData(["climate", "room1", 60], { now: NOW, room_id: "room1", points: [[NOW - 120, 24.1, 61], [NOW - 60, 24.2, 60]] });
    });
    expect(document.querySelector("[data-room-count]")).toHaveTextContent(/^1 person · since \d\d:\d\d$/);
    expect(document.querySelector("[data-room-exit]")).toHaveTextContent("Nearest exit: Stair B");
    const order = [...document.querySelectorAll("[role=dialog] h3, [role=dialog] h4")].map((h) => h.textContent);
    expect(order).toEqual(["People", "Signal", "Live signal", "Temperature and humidity", "Sensor health"]);
    // the same People card as the overview's, without a second count or a link to itself; its range is the compact select
    expect(document.querySelector("[data-people-chart=\"1h\"]")).not.toBeNull();
    expect(document.querySelector("[data-people-now], [data-room-details]")).toBeNull();
    expect(screen.getByRole("combobox", { name: "Time range" })).toHaveValue("1h");
    // the figures that were a strip of three are in the header and the climate heading
    expect(document.querySelector("[data-climate-now]")).toHaveTextContent(/^24\.0\s°C · 60%$/);
    // one legend, for the chart with two series; none that repeats the room's name
    expect(document.querySelectorAll("[data-chart-legend]")).toHaveLength(1);
    expect(document.querySelector("[data-chart-legend]")).toHaveTextContent("TemperatureHumidity");
    expect(screen.queryByText(/Illustration/)).toBeNull();
  });

  it("follows the People range with the climate chart, and remembers the range in this browser", async () => {
    const calls: string[] = [];
    vi.stubGlobal("fetch", vi.fn(async (url: RequestInfo | URL) => { calls.push(String(url)); return new Response("{}", { status: 503 }); }));
    panel({ room: room() });
    fireEvent.change(screen.getByRole("combobox", { name: "Time range" }), { target: { value: "24h" } });
    expect(localStorage.getItem("nadiSignalRange")).toBe("24h");
    await waitFor(() => expect(calls.some((u) => u.includes("/api/rooms/room1/climate?minutes=1440"))).toBe(true));
    expect(calls.some((u) => u.includes("/api/history?minutes=1440&room=room1&view=people"))).toBe(true);
    expect(calls.some((u) => /signal\?minutes=(60|1440)/.test(u))).toBe(false);  // the live signal stays at 5 minutes
    vi.unstubAllGlobals();
    localStorage.clear();
  });

  it("has a Signal section with the pair picture and the live chart, and no link back to itself", () => {
    panel({ room: room() });
    expect(screen.getByRole("heading", { name: "Signal" })).toBeInTheDocument();
    expect(document.querySelector("[data-pair=calm]")).not.toBeNull();
    expect(screen.getByRole("heading", { name: "Live signal" })).toBeInTheDocument();
    expect(document.querySelector("[data-open-room-signal]")).toBeNull();
    expect(document.querySelector("[data-recorded-waves]")).toBeNull();  // no recordings: picture and live chart only
  });

  it("shows the person when the latest report is above the threshold, and grey when the sensor is offline", () => {
    const busy = panel({ room: room({ headcount: 1 }) }, rooms(), above);
    expect(document.querySelector("[data-pair=disturbed] [data-person]")).not.toBeNull();
    busy.unmount();
    panel({ room: room({ live: false }) }, rooms({ rooms: [room({ live: false })] }), above);
    expect(document.querySelector("[data-pair=offline]")).not.toBeNull();
    expect(document.querySelector("[data-person]")).toBeNull();
    expect(document.querySelector("[data-signal-chart=offline]")).not.toBeNull();
  });

  it("holds still during an emergency or drill", () => {
    panel({ room: room() }, rooms({ emergency: { on: true, since: NOW - 30, drill: true, id: "d" } }));
    expect(document.querySelector("[data-still]")).not.toBeNull();
    expect(document.querySelector(".wave-travel")).toBeNull();
  });

  it("opens for a room without a sensor and says so, dashed and in words", () => {
    panel({ noSensor: { id: "room2", name: "Hall A" } });
    expect(screen.getByRole("heading", { name: "Hall A" })).toBeInTheDocument();
    const box = document.querySelector("[data-no-sensor]")!;
    expect(box).toHaveTextContent("No sensor");
    expect(box.className).toContain("border-dashed");
    expect(document.querySelector("[data-pair]")).toBeNull();
    expect(screen.queryByRole("heading", { name: "Live signal" })).toBeNull();
    expect(screen.getByText("Room ID on the plan: room2")).toBeInTheDocument();
  });

  it("does not call a silent sensor pair 'no sensor'", () => {
    panel({ noSensor: { id: "room1", name: "Lab 2", linked: true } });
    const box = document.querySelector("[data-no-sensor]")!;
    expect(box).toHaveTextContent("No report yet");
    expect(box).not.toHaveTextContent("No sensor");
  });

  it("leaves the signal out for a simulated people counter (no Wi-Fi pair to draw)", () => {
    panel({ room: room({ counter: "count", headcount: 40 }) });
    expect(screen.queryByRole("heading", { name: "Signal" })).toBeNull();
  });

  it("opens at the signal when asked to", async () => {
    const scroll = vi.fn();
    Element.prototype.scrollIntoView = scroll;
    panel({ room: room(), section: "signal" });
    await waitFor(() => expect(scroll).toHaveBeenCalled());
    expect((scroll.mock.instances[0] as unknown as HTMLElement).id).toBe("room-signal");
  });
});

describe("calibration", () => {
  const model = (extra: Partial<ModelFacts> = {}): ModelFacts => ({
    framework: "MindSpore 2.10.0", platform: "local", trained_on: "synthetic", accuracy: 1, threshold_accuracy: 0.9967,
    trained_at: 1792843820, n_train: 3600, n_test: null, active: false, ...extra,
  });
  const detector = (extra: Partial<Detector> = {}): Detector => ({
    now: NOW, mode: "rule", threshold: 1.301, report_interval_s: 10, model: model(),
    rooms: { room1: [{ ts: 1, headcount_label: 0, motion_std: 0.3 }, { ts: 2, headcount_label: 0, motion_std: 0.7 },
      { ts: 3, headcount_label: 1, motion_std: 2.2 }] }, ...extra,
  });

  const PLAN3 = [{ id: "room1", linked: true }, { id: "room2", linked: false }, { id: "room3", linked: false }];
  const NAMES: Record<string, string> = { room1: "Demo Room", room2: "Hall A", room3: "Room 3", hall: "Main Hall", lab9: "Lab 9" };
  const nameOf = (id: string) => NAMES[id] ?? id;
  const sig = (id: string): Signal => ({ now: NOW, room_id: id, minutes: 5, threshold: 1.301, last_report_ts: NOW - 4,
    points: [{ ts: NOW - 14, motion_std: 0.9, headcount: 0 }, { ts: NOW - 4, motion_std: 0.41, headcount: 0 }] });

  it("says per room what is counting it: the calibrated rule, MindSpore only when a model is loaded, a counter, or no sensor", () => {
    const reporting = [room(), room({ room_id: "hall", name: "Main Hall", counter: "count", headcount: 40 })];
    const rows = detectorRows(detector(), PLAN3, reporting, { room1: sig("room1") }, nameOf);
    expect(rows.map((r) => r.name)).toEqual(["Demo Room", "Hall A", "Main Hall", "Room 3"]);  // every room, by name
    expect(rows[0]).toMatchObject({ kind: "rule", counting: "Calibrated rule", threshold: "1.30 dB", last: `0.41 dB at ${hhmmss(NOW - 4)}` });
    expect(rows[1]).toMatchObject({ kind: "none", counting: "No sensor", threshold: "–", last: "–" });
    expect(rows[2]).toMatchObject({ kind: "counter", counting: "People counter", threshold: "–", last: "–" });
    expect(rows.some((r) => r.counting.includes("MindSpore"))).toBe(false);
    // a model is named only when the server says one is counting
    const live = detectorRows(detector({ mode: "model", threshold: null, model: model({ active: true }) }), PLAN3, reporting, { room1: sig("room1") }, nameOf);
    expect(live[0]).toMatchObject({ kind: "model", counting: "MindSpore model", threshold: "MindSpore 2.10.0" });
    expect(live[1].counting).toBe("No sensor");
    // a sensor pair on the plan that has not reported, and a sensing room with nothing in the last minutes
    expect(detectorRows(detector(), PLAN3, [], undefined, nameOf)[0]).toMatchObject({ kind: "rule", last: "No report yet" });
    expect(detectorRows(detector(), PLAN3, [room({ live: false })], {}, nameOf)[0].last).toBe("–");
    expect(detectorRows(undefined, PLAN3, [room()], {}, nameOf)[0].threshold).toBe("–");
  });

  it("draws the live detector as a table across the page, ten rooms and then 'Show N more'", () => {
    const many = Array.from({ length: 13 }, (_, i) => room({ room_id: `r${i}`, name: `Room ${i + 1}` }));
    const rows = detectorRows(detector(), [], many, {}, (id) => many.find((r) => r.room_id === id)!.name);
    const { container } = render(<LiveDetector rows={rows} mode="rule" />);
    expect(screen.getByRole("heading", { name: "Live detector" })).toBeInTheDocument();
    expect(container.querySelector("[data-detector=rule]")).not.toBeNull();
    expect(screen.getAllByRole("columnheader").map((h) => h.textContent)).toEqual(["Room", "Counting by", "Threshold or model", "Last reading"]);
    expect(container.querySelectorAll("[data-detector-rows] tbody tr")).toHaveLength(10);
    expect(screen.getAllByRole("rowheader").map((h) => h.textContent).slice(0, 3)).toEqual(["Room 1", "Room 2", "Room 3"]);  // 2 before 10
    const more = screen.getByRole("button", { name: "Show 3 more" });
    expect(more).toHaveAttribute("aria-expanded", "false");
    fireEvent.click(more);
    expect(container.querySelectorAll("[data-detector-rows] tbody tr")).toHaveLength(13);
    const box = document.getElementById(more.getAttribute("aria-controls")!)!;
    expect(box.className).toContain("max-h-[26rem]");  // expanded, the rows scroll inside the card
    expect(box.className).toContain("overflow-y-auto");
    fireEvent.click(screen.getByRole("button", { name: "Show fewer" }));
    expect(container.querySelectorAll("[data-detector-rows] tbody tr")).toHaveLength(10);
    expect(container).toHaveTextContent("A room counts as occupied when the movement of its signal rises above the threshold.");
  });

  it("gives the model training card its facts as a table", () => {
    const { container } = render(<ModelTraining model={model()} />);
    expect(screen.getByRole("heading", { name: "Model training · Huawei MindSpore" })).toBeInTheDocument();
    expect(container.querySelector("[data-model-facts]")!.querySelectorAll("tr")).toHaveLength(6);  // facts as a table
    expect(container.querySelector("[data-model=inactive]")).toHaveTextContent(
      "Not active: trained on simulated data. Goes live once it beats the rule on real labelled data.");
  });

  it("says the model figures come from simulated rows when they do", () => {
    const sim = render(<ModelTraining model={model()} />);
    expect(sim.container).toHaveTextContent("Accuracy on simulated test rows");
    expect(sim.container).toHaveTextContent("Threshold rule on the same simulated rows");
    sim.unmount();
    const real = render(<ModelTraining model={model({ trained_on: "real CSI" })} />);
    expect(real.container).toHaveTextContent("Accuracy on its own test rows");
    expect(real.container).not.toHaveTextContent("simulated");
  });

  it("gives the model its true status", () => {
    expect(modelStatus(null)).toBe("No trained model file yet.");
    expect(modelStatus(model({ active: true, trained_on: "real CSI" }))).toBe("Active: this model is counting people now.");
    expect(modelStatus(model({ trained_on: "real CSI" }))).toMatch(/^Not active: the calibrated rule is counting\./);
    expect(modelStatus(model())).toMatch(/^Not active: trained on simulated data/);
  });

  it("draws one dot per labelled report, hollow grey for empty and solid teal for occupied, with the threshold", () => {
    const { container } = render(<LabelledDots name="Demo Room" points={detector().rooms.room1} threshold={1.301} size={{ width: 500, height: 220 }} />);
    const dots = [...container.querySelectorAll(".recharts-scatter circle")];
    expect(dots).toHaveLength(3);
    expect(dots.filter((d) => d.getAttribute("stroke") === "hsl(var(--brand-grey))")).toHaveLength(2);
    expect(dots.filter((d) => d.getAttribute("fill") === "hsl(var(--brand))")).toHaveLength(1);
    expect(screen.getByText("threshold 1.30 dB")).toBeInTheDocument();
    expect(screen.getByText("2 labelled empty, 1 labelled occupied")).toBeInTheDocument();
    expect(screen.getByText("Labelled empty")).toBeInTheDocument();  // the columns are named: not colour alone
    expect(screen.getByText("Labelled occupied")).toBeInTheDocument();
    expect(screen.getByRole("img", { name: /Demo Room: 2 reports labelled empty, 1 labelled occupied/ })).toBeInTheDocument();
  });

  function page(d: Detector | null, admin = true, labels: unknown = { recent: [], open: {} }) {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false, staleTime: Infinity, refetchInterval: false } } });
    qc.setQueryData(["me"], { admin, who: admin ? "localhost" : null, rule: admin ? "localhost" : "token", viewer: true, viewer_required: false });
    qc.setQueryData(["info", "en"], { building: "B", level: "L", room_names: { room1: "Demo Room" } });
    qc.setQueryData(["rooms", "en"], rooms());
    qc.setQueryData(["labels"], labels);
    qc.setQueryData(["signals"], { now: NOW, minutes: 5, threshold: 1.301, truncated: false, rooms: { room1: sig("room1") } });
    if (d) qc.setQueryData(["detector"], d);
    return render(<QueryClientProvider client={qc}><TooltipProvider><MemoryRouter><CalibrationPage /></MemoryRouter></TooltipProvider></QueryClientProvider>);
  }

  it("is called Calibration and keeps the labelling controls in one card: room, a 0 to 5 row, another number, stop", () => {
    const { container } = page(detector());
    expect(screen.getByRole("heading", { level: 1, name: "Calibration" })).toBeInTheDocument();
    expect(container.querySelector("[data-live-chip]")).not.toBeNull();  // the same page header as every other page
    const card = screen.getByRole("region", { name: "Label headcount" });
    expect(within(card).getByRole("combobox", { name: "Room" })).toHaveValue("room1");
    const row = within(card).getByRole("group", { name: "People in the room now" });
    expect(row).toHaveAttribute("data-segmented");
    expect(within(row).getAllByRole("button").map((b) => b.textContent)).toEqual(["0", "1", "2", "3", "4", "5"]);
    expect(within(row).getAllByRole("button").every((b) => b.getAttribute("aria-pressed") === "false")).toBe(true);
    expect(within(card).getByRole("spinbutton")).toBeInTheDocument();
    expect(within(card).getByRole("button", { name: /Stop/ })).toBeDisabled();  // nothing is being labelled
    expect(within(card).getByRole("button", { name: /Undo last/ })).toBeDisabled();
    expect(screen.getByText("Each dot is a real 10-second report we labelled.")).toBeInTheDocument();
  });

  it("lists the recent labels as a table and marks the count being labelled", () => {
    const qcLabels = { recent: [{ room_id: "room1", name: "Demo Room", headcount: 2, start_ts: NOW - 120, end_ts: null },
      { room_id: "room1", name: "Demo Room", headcount: 0, start_ts: NOW - 400, end_ts: NOW - 120 }],
      open: { room1: { headcount: 2, start_ts: NOW - 120 } } };
    const { container } = page(detector(), true, qcLabels);
    const rows = [...container.querySelectorAll("[data-recent-labels] tbody tr")];
    expect(rows).toHaveLength(2);
    expect(rows[0]).toHaveTextContent(/^Demo Room2/);
    expect(within(container.querySelector("[data-recent-labels]") as HTMLElement).getAllByRole("columnheader").map((h) => h.textContent)).toEqual(["Room", "People", "Time"]);
    const row = screen.getByRole("group", { name: "People in the room now" });
    expect(within(row).getByRole("button", { name: "2" })).toHaveAttribute("aria-pressed", "true");
    expect(container.querySelector("[data-label-state]")).toHaveTextContent("hidden");  // the sensor's count, while labelling
    expect(screen.getByRole("button", { name: /Stop/ })).toBeEnabled();
  });

  it("says when there is no labelled data yet", () => {
    const { container } = page(detector({ rooms: { room1: [] } }));
    expect(container.querySelector("[data-no-labelled]")).toHaveTextContent("No labelled data yet");
    expect(container.querySelector("[data-dots]")).toBeNull();
    expect(container.querySelector("[data-dots-room]")).toBeNull();  // nothing to choose between
  });

  it("lays out two columns of the same height with the live detector across the page below", () => {
    const { container } = page(detector());
    const columns = container.querySelector("[data-cal-columns]")!;
    expect(columns.className).toContain("items-stretch");
    expect(columns.children).toHaveLength(2);
    expect(columns.children[0]).toHaveAccessibleName("Label headcount");
    expect(columns.children[0].className).toContain("h-full");
    const right = columns.children[1];
    expect(right.querySelectorAll("section")).toHaveLength(2);  // model training, then the labelled reports
    expect(right.querySelectorAll("section")[1].className).toContain("flex-1");  // it takes the height that is left
    const table = container.querySelector("[data-detector]")!;
    expect(columns.contains(table)).toBe(false);  // below both, not in a column
    expect(columns.compareDocumentPosition(table) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    const rows = [...table.querySelectorAll("tbody tr")].map((r) => r.textContent);
    expect(rows).toEqual([`Demo RoomCalibrated rule1.30 dB0.41 dB at ${hhmmss(NOW - 4)}`, "Hall ANo sensor––", "Room 3No sensor––"]);
  });

  it("shows the labelled reports of one room at a time: the room being labelled, or the one chosen there", () => {
    const two = detector({ rooms: { room1: detector().rooms.room1, room2: [{ ts: 5, headcount_label: 0, motion_std: 0.2 }] } });
    const { container } = page(two);
    expect(container.querySelectorAll("[data-dots]")).toHaveLength(1);
    expect(container.querySelector("[data-dots]")).toHaveAttribute("data-dots", "Demo Room");
    const dots = screen.getByRole("combobox", { name: "Room shown" }) as HTMLSelectElement;
    expect(dots.value).toBe("room1");
    fireEvent.change(dots, { target: { value: "room2" } });
    expect(container.querySelectorAll("[data-dots]")).toHaveLength(1);
    expect(container.querySelector("[data-dots]")).toHaveAttribute("data-dots", "Hall A");
    expect(screen.getByRole("combobox", { name: "Room" })).toHaveValue("room1");  // the labeller's own room did not move
    // a room with no labelled reports says so; choosing a room in the labeller takes the dots with it again
    fireEvent.change(dots, { target: { value: "room3" } });
    expect(container.querySelector("[data-no-labelled-room]")).toHaveTextContent("No labelled reports for this room yet");
    fireEvent.change(screen.getByRole("combobox", { name: "Room" }), { target: { value: "room2" } });
    expect(dots.value).toBe("room2");
  });

  it("shows ten recent labels, then 'Show N more', and scrolls inside the card once expanded", () => {
    const recent = Array.from({ length: 13 }, (_, i) => ({ room_id: "room1", name: "Demo Room", headcount: i % 3, start_ts: NOW - i * 100, end_ts: i ? NOW - i * 100 + 90 : null }));
    const { container } = page(detector(), true, { recent, open: {} });
    const table = container.querySelector("[data-recent-labels]") as HTMLElement;
    expect(table.querySelectorAll("tbody tr")).toHaveLength(10);
    const card = screen.getByRole("region", { name: "Label headcount" });
    const more = within(card).getByRole("button", { name: "Show 3 more" });
    fireEvent.click(more);
    expect(table.querySelectorAll("tbody tr")).toHaveLength(13);
    expect(table.parentElement!.className).toContain("max-h-[26rem]");
    expect(more).toHaveAttribute("aria-controls", table.parentElement!.id);
    fireEvent.click(within(card).getByRole("button", { name: "Show fewer" }));
    expect(table.querySelectorAll("tbody tr")).toHaveLength(10);
    expect(table.parentElement!.className).not.toContain("max-h-");
  });

  it("is for admins only", () => {
    const { container } = page(detector(), false);
    expect(container.querySelector("[data-detector]")).toBeNull();
    expect(screen.queryByRole("button", { name: "0" })).toBeNull();
  });

  it("exists in Malay", () => {
    expect(T("label.title", undefined, "ms")).toBe("Kalibrasi");
    expect(T("cal.none", undefined, "ms")).toBe("Belum ada data berlabel");
    expect(T("plan.no_sensor", undefined, "ms")).toBe("Tiada sensor");
    expect(T("plan.no_report", undefined, "ms")).toBe("Belum ada laporan");
  });
});

describe("one person, two people", () => {
  it("never says 1 people", () => {
    expect(peopleWord(1)).toBe("person");
    expect(peopleWord(2)).toBe("people");
    expect(T("em.still_inside_one")).toBe("person still inside");
    expect(T("em.still_inside_one", undefined, "ms")).toBe("orang masih di dalam");
  });
});
