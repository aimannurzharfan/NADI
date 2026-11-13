// The floor plan editor (docs/design/PLAN.md, Part 16.4): its checks answer exactly as the server's do (the shared
// cases in tests/fixtures/plan_cases.json), and it works without a mouse: add a room, type its fields, read the
// checks, move it with the arrow keys, remove it with Delete, save.
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import shared from "../../../tests/fixtures/plan_cases.json";
import { TooltipProvider } from "@/components/ui/tooltip";
import { BUILTIN_PLAN, type Plan } from "@/lib/plan";
import { changeSummary, corridorTemplate, hallTemplate, suggestedPairs, summaryText, validatePlan } from "@/lib/plan-validate";
import { SiteProvider, type Site } from "@/lib/site";
import { PlanEditorPage } from "@/pages/plan-editor";

type Case = { name: string; set?: Record<string, unknown>; del?: string[]; rename?: [string, string]; keys: string[] };

function applyCase(plan: Plan, c: Case): Plan {
  const doc = structuredClone(plan) as unknown as Record<string, unknown>;
  const walk = (path: string): [Record<string, unknown>, string] => {
    const parts = path.split(".");
    const last = parts.pop()!;
    let node = doc;
    for (const p of parts) node = node[p] as Record<string, unknown>;
    return [node, last];
  };
  for (const [path, value] of Object.entries(c.set ?? {})) {
    const [node, key] = walk(path);
    node[key] = value;
  }
  for (const path of c.del ?? []) {
    const [node, key] = walk(path);
    delete node[key];
  }
  if (c.rename) {
    const rooms = doc.rooms as Record<string, unknown>;
    doc.rooms = Object.fromEntries(Object.entries(rooms).map(([k, v]) => [k === c.rename![0] ? c.rename![1] : k, v]));
  }
  return doc as unknown as Plan;
}

describe("the editor's checks match the server's", () => {
  for (const c of (shared as { cases: Case[] }).cases) {
    it(c.name, () => {
      expect(validatePlan(applyCase(BUILTIN_PLAN, c)).map((p) => p.key).sort()).toEqual(c.keys);
    });
  }

  it("refuses an ID used on another floor and removing a room whose sensor reports", () => {
    expect(validatePlan(BUILTIN_PLAN, { room3: "Demo Building, Level 5" }).map((p) => p.key)).toEqual(["site.err_taken"]);
    const { room1: _gone, ...rooms } = BUILTIN_PLAN.rooms;
    const without = { ...BUILTIN_PLAN, rooms };
    expect(validatePlan(without, {}, new Set(["room2"]), BUILTIN_PLAN.rooms)).toEqual([]);
    expect(validatePlan(without, {}, new Set(["room1"]), BUILTIN_PLAN.rooms)).toEqual([{ key: "site.err_live", values: { id: "room1", name: "Lab 2" } }]);
  });

  it("starts from templates that pass every rule, and suggests one sensor pair per 16 m²", () => {
    expect(validatePlan(corridorTemplate("new", 3))).toEqual([]);
    expect(validatePlan(hallTemplate("h"))).toEqual([]);
    expect([suggestedPairs(10), suggestedPairs(16), suggestedPairs(17), suggestedPairs(48)]).toEqual([1, 1, 2, 3]);
  });

  it("sums up what a save changes", () => {
    const moved = applyCase(BUILTIN_PLAN, { name: "", set: { "rooms.room1.x": 530, "rooms.room2.name": "Hall B" }, keys: [] });
    expect(summaryText(changeSummary(BUILTIN_PLAN, moved))).toBe("1 moved or reshaped, 1 renamed");
    expect(summaryText(changeSummary(BUILTIN_PLAN, BUILTIN_PLAN))).toBe("No change to the rooms.");
  });
});

// the built-in plan without Room 3 and the pantry: room for a new one at the bottom
const { room3: _r3, ...TWO } = BUILTIN_PLAN.rooms;
const PLAN: Plan = { ...BUILTIN_PLAN, rooms: TWO, other: BUILTIN_PLAN.other.filter((o) => o.label !== "plan.pantry") };
const SITE: Site = { default_floor: "f1", editor: true, buildings: [{ id: "b1", name: "Demo Building", code: "", example: false,
  floors: [{ id: "f1", name: "Level 4", level: 4, rooms: 2, version: 3 }] }] };

function show(fetcher: unknown = vi.fn(async () => new Response(JSON.stringify({ detail: "offline" }), { status: 503 }))) {
  vi.stubGlobal("fetch", fetcher);
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false, staleTime: Infinity, refetchInterval: false } } });
  qc.setQueryData(["me"], { admin: true, who: "localhost", rule: "localhost", viewer: true, viewer_required: false });
  qc.setQueryData(["site"], SITE);
  qc.setQueryData(["plan", "f1"], { floor_id: "f1", version: 3, saved_ts: 1, saved_by: "admin", plan: PLAN });
  qc.setQueryData(["versions", "f1"], { versions: [{ version: 3, saved_ts: 1_794_463_320, saved_by: "admin", note: "", rooms: 2 },
    { version: 2, saved_ts: 1_794_460_000, saved_by: "warden1", note: "", rooms: 3, restored_from: 0 }] });
  qc.setQueryData(["info", "en"], { building: "Demo Building", level: "Level 4", room_names: {}, room_floors: { room1: "f1", room2: "f1" }, room_exits: {} });
  qc.setQueryData(["rooms", "en"], { now: 1, stale_s: 30, rooms: [], waste_today_rm: 0, waste_today_kwh: 0,
    emergency: { on: false, since: null, drill: false, id: null }, accountability: {}, alerts: [], offline: {}, stale_ts: null });
  qc.setQueryData(["energy-settings"], { settings: { tariff_rm_per_kwh: 0.3, ac_kw: 10, ac_kw_rooms: { room1: 3.5 }, ac_on_below_c: 26,
    waste_after_min: 10, co2_kg_per_kwh: 0.75 } });
  return render(<QueryClientProvider client={qc}><TooltipProvider><MemoryRouter initialEntries={["/floor/edit?floor=f1"]}><SiteProvider>
    <PlanEditorPage /></SiteProvider></MemoryRouter></TooltipProvider></QueryClientProvider>);
}

beforeEach(() => vi.stubGlobal("ResizeObserver", class { observe() {} unobserve() {} disconnect() {} }));
afterEach(() => vi.unstubAllGlobals());

describe("the editor", () => {
  it("adds a room without a mouse, takes typed values, lists problems and moves and removes the room by keyboard", () => {
    const { container } = show();
    expect(screen.getByRole("heading", { name: "Edit plan: Demo Building, Level 4", level: 1 })).toBeInTheDocument();
    expect(screen.getByText("No problems found")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Save..." })).toBeDisabled();  // nothing changed yet
    fireEvent.click(screen.getByRole("button", { name: "Add a room" }));
    const id = screen.getByRole("textbox", { name: "Room ID (what the sensors report)" }) as HTMLInputElement;
    expect(id.value).toBe("room3");
    fireEvent.change(screen.getByRole("textbox", { name: "Name" }), { target: { value: "Lab 9" } });
    fireEvent.change(id, { target: { value: "lab9" } });
    expect(within(container.querySelector("[data-shape-list]") as HTMLElement).getByRole("button", { name: /Lab 9 \(lab9\)/ })).toHaveAttribute("aria-pressed", "true");
    fireEvent.change(screen.getByRole("spinbutton", { name: "Area in m²" }), { target: { value: "48" } });
    expect(container.querySelector("[data-guideline]")).toHaveTextContent("Guideline only: suggested sensor pairs: 3");
    expect(container.querySelector("[data-room-ac]")).toHaveTextContent("Air conditioner power: 10 kW.");
    expect(screen.getByText("No problems found")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Save..." })).toBeEnabled();
    // into Hall A: the problem is listed, Save goes off, and the problem selects the room
    fireEvent.change(screen.getByRole("spinbutton", { name: "Y" }), { target: { value: "100" } });
    const checks = container.querySelector("[data-checks]") as HTMLElement;
    expect(within(checks).getByRole("button", { name: "Hall A and Lab 9 overlap." })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Checks: 1 problems" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Save..." })).toBeDisabled();
    fireEvent.change(screen.getByRole("spinbutton", { name: "Y" }), { target: { value: "310" } });
    // the arrow keys move the selected shape by 10, Shift by 1
    const canvas = container.querySelector("[data-editor-canvas]") as SVGSVGElement;
    fireEvent.keyDown(canvas, { key: "ArrowRight" });
    expect((screen.getByRole("spinbutton", { name: "X" }) as HTMLInputElement).value).toBe("350");
    fireEvent.keyDown(canvas, { key: "ArrowDown", shiftKey: true });
    expect((screen.getByRole("spinbutton", { name: "Y" }) as HTMLInputElement).value).toBe("311");
    fireEvent.keyDown(canvas, { key: "Delete" });
    expect(container.querySelector('[data-shape="room:lab9"]')).toBeNull();
    expect(screen.getByText("Select a shape on the drawing or in the list to see its details.")).toBeInTheDocument();
  });

  it("says why when the floor's plan cannot be fetched, instead of loading for ever", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({ detail: "There is no floor f9." }), { status: 404 })));
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false, staleTime: Infinity, refetchInterval: false } } });
    qc.setQueryData(["me"], { admin: true, who: "localhost", rule: "localhost", viewer: true, viewer_required: false });
    qc.setQueryData(["site"], { ...SITE, buildings: [{ ...SITE.buildings[0], floors: [...SITE.buildings[0].floors, { id: "f9", name: "Level 9", level: 9, rooms: 0, version: 0 }] }] });
    render(<QueryClientProvider client={qc}><TooltipProvider><MemoryRouter initialEntries={["/floor/edit?floor=f9"]}><SiteProvider>
      <PlanEditorPage /></SiteProvider></MemoryRouter></TooltipProvider></QueryClientProvider>);
    expect(await screen.findByText(/There is no floor f9\./)).toBeInTheDocument();
  });

  it("places a sensor pair with two clicks inside the room", () => {
    const { container } = show();
    fireEvent.click(within(container.querySelector("[data-shape-list]") as HTMLElement).getByRole("button", { name: /Lab 2 \(room1\)/ }));
    fireEvent.click(screen.getByRole("button", { name: "Clear" }));
    expect(container.querySelector("[data-pair]")).toHaveTextContent("No sensor pair drawn.");
    fireEvent.click(screen.getByRole("button", { name: "Place" }));
    expect(screen.getByText("Click inside the room where the sender stands.")).toBeInTheDocument();
    expect(container.querySelector("[data-room-ac]")).toHaveTextContent("Air conditioner power: 3.5 kW.");
  });

  it("saves with a note and a summary, and says which version it became", async () => {
    const send = vi.fn(async (_url: string, init?: RequestInit) => (init?.method === "PUT"
      ? new Response(JSON.stringify({ ok: true, floor_id: "f1", version: 4 }), { status: 200 })
      : new Response(JSON.stringify({ detail: "offline" }), { status: 503 })));
    show(send);
    fireEvent.click(screen.getByRole("button", { name: "Add a room" }));
    fireEvent.click(screen.getByRole("button", { name: "Save..." }));
    const dialog = screen.getByRole("dialog", { name: "Save this plan as a new version?" });
    expect(within(dialog).getByText("1 room added")).toBeInTheDocument();
    fireEvent.change(within(dialog).getByRole("textbox", { name: "Note" }), { target: { value: "Lab 9 opened" } });
    fireEvent.click(within(dialog).getByRole("button", { name: "Save" }));
    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("Saved as version 4."));
    const put = send.mock.calls.find(([, init]) => init?.method === "PUT")!;
    expect(put[0]).toBe("/api/floors/f1/plan?lang=en");
    const body = JSON.parse(put[1]!.body as string);
    expect(body.base_version).toBe(3);
    expect(body.note).toBe("Lab 9 opened");
    expect(Object.keys(body.plan.rooms)).toEqual(["room2", "room1", "room3"]);
  });

  it("takes an optional capacity per room: saved with the plan, refused when it is not a whole number from 1 to 1000, removable", async () => {
    const send = vi.fn(async (_url: string, init?: RequestInit) => (init?.method === "PUT"
      ? new Response(JSON.stringify({ ok: true, floor_id: "f1", version: 4 }), { status: 200 })
      : new Response(JSON.stringify({ detail: "offline" }), { status: 503 })));
    const { container } = show(send);
    fireEvent.click(within(container.querySelector("[data-shape-list]") as HTMLElement).getByRole("button", { name: /Lab 2 \(room1\)/ }));
    const field = screen.getByRole("spinbutton", { name: "Capacity (people), optional" }) as HTMLInputElement;
    expect(field.value).toBe("");  // none set: no line on the people chart
    expect(field).toHaveAccessibleDescription("Shown as a dashed line on the room's people chart. Not an alert.");
    fireEvent.change(field, { target: { value: "0" } });
    expect(screen.getAllByText("The capacity of Lab 2 must be a whole number from 1 to 1000.").length).toBeGreaterThan(0);
    expect(screen.getByRole("button", { name: "Save..." })).toBeDisabled();
    // emptied again: the capacity goes, and nothing is left to save
    fireEvent.change(field, { target: { value: "" } });
    expect(screen.getByText("No problems found")).toBeInTheDocument();
    fireEvent.change(field, { target: { value: "30" } });
    expect(screen.getByText("No problems found")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Save..." }));
    const dialog = screen.getByRole("dialog", { name: "Save this plan as a new version?" });
    expect(within(dialog).getByText("details of 1 room changed")).toBeInTheDocument();
    fireEvent.click(within(dialog).getByRole("button", { name: "Save" }));
    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("Saved as version 4."));
    const body = JSON.parse(send.mock.calls.find(([, init]) => init?.method === "PUT")![1]!.body as string);
    expect(body.plan.rooms.room1.capacity).toBe(30);
    expect("capacity" in body.plan.rooms.room2).toBe(false);
    expect(changeSummary(PLAN, { ...PLAN, rooms: { ...PLAN.rooms, room1: { ...PLAN.rooms.room1, capacity: 30 } } }).details).toBe(1);
  });

  it("has no field for the detection threshold: it comes from calibration only", () => {
    const { container } = show();
    fireEvent.click(within(container.querySelector("[data-shape-list]") as HTMLElement).getByRole("button", { name: /Lab 2 \(room1\)/ }));
    expect(screen.queryByRole("spinbutton", { name: /threshold/i })).toBeNull();
    expect(screen.queryByRole("textbox", { name: /threshold/i })).toBeNull();
  });

  it("labels every group of the toolbar, with the file limits as a note under the upload button", () => {
    const { container } = show();
    const toolbar = container.querySelector("[data-editor-toolbar]") as HTMLElement;
    expect([...toolbar.querySelectorAll("[data-toolbar-group]")].map((g) => g.getAttribute("data-toolbar-group"))).toEqual(["draw", "start", "image"]);
    const draw = within(toolbar).getByRole("radiogroup", { name: "Draw" });
    expect(within(draw).getAllByRole("radio").map((r) => r.textContent)).toEqual(["Select", "Room", "Stairs or exit", "Other space"]);
    expect(within(toolbar).getByRole("combobox", { name: "Start from" })).toBeInTheDocument();
    const image = within(toolbar).getByRole("group", { name: "Background image" });
    expect(within(image).getByText("Choose an image")).toBeInTheDocument();
    expect(within(image).getByText("PNG or JPG, up to 2 MB")).toBeInTheDocument();
    expect(image.querySelector("input[type=file]")).toHaveAccessibleDescription("PNG or JPG, up to 2 MB");
    expect(toolbar.textContent).not.toContain("Upload a floor plan image (PNG or JPG, up to 2 MB)");
    // the shapes list holds whole rows: every row has one fixed height and the box is a whole number of them
    const list = container.querySelector("[data-shape-list]") as HTMLElement;
    expect(list.className).toContain("max-h-[calc(13.5rem+2px)]");
    expect([...list.querySelectorAll("button")].every((b) => b.className.includes("h-9"))).toBe(true);
  });

  it("offers a reload when someone else saved first, and lists versions with restore", async () => {
    show(vi.fn(async (_url: string, init?: RequestInit) => (init?.method === "PUT"
      ? new Response(JSON.stringify({ detail: "Someone else saved this plan. Reload to see their version." }), { status: 409 })
      : new Response(JSON.stringify({ detail: "offline" }), { status: 503 }))));
    const versions = screen.getByRole("table");
    expect(within(versions).getAllByRole("row")[2]).toHaveTextContent("Restored from version 0");
    expect(within(versions).getAllByRole("row")[1]).toHaveTextContent("current");
    fireEvent.click(within(versions).getByRole("button", { name: "Restore this version" }));
    expect(screen.getByRole("dialog", { name: "Restore version 2?" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    fireEvent.click(screen.getByRole("button", { name: "Add a room" }));
    fireEvent.click(screen.getByRole("button", { name: "Save..." }));
    fireEvent.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Save" }));
    const conflict = await screen.findByRole("dialog", { name: "The plan has changed" });
    expect(within(conflict).getByRole("button", { name: "Reload" })).toBeInTheDocument();
  });
});
