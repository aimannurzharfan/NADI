// The frame around every page: header, folding sidebar, the Ask NADI box and panel, the live chip.
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import { SUGGESTED } from "@/components/chat-panel";
import { LiveChip } from "@/components/live-chip";
import { PageHeader } from "@/components/panel";
import { AppShell } from "@/components/shell";
import { TooltipProvider } from "@/components/ui/tooltip";
import { T } from "@/lib/i18n";
import { SettingsProvider } from "@/lib/settings";
import type { Alert, Room, RoomsState } from "@/lib/types";

const NOW = Math.floor(Date.now() / 1000);

const room = (extra: Partial<Room> = {}): Room => ({
  room_id: "room1", name: "Demo Room", headcount: 1, at_least: false, counter: "csi", count_ts: NOW - 3, temp_c: 24, humidity: 60,
  live: true, waste: null, ...extra,
});

const state = (rooms: Room[], extra: Partial<RoomsState> = {}): RoomsState => ({
  now: NOW, stale_s: 30, rooms, waste_today_rm: 0, emergency: { on: false, since: null, drill: false, id: null },
  accountability: {}, alerts: [], offline: {}, stale_ts: null, demo: { on: false, t: null }, clock: null, ...extra,
});

const alert = (id: string, extra: Partial<Alert> = {}): Alert => ({
  id, ts: NOW - 60, kind: "waste", severity: "warning", via: "console", subject: "Air conditioning on in an empty room", message: "m", ack: null, ...extra,
});

type Opts = { rooms?: Room[]; extra?: Partial<RoomsState>; admin?: boolean; page?: React.ReactNode; width?: number };

function show(path: string, { rooms = [room()], extra, admin = false, page = <p>page</p>, width }: Opts = {}) {
  if (width) Object.defineProperty(window, "innerWidth", { configurable: true, value: width });
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false, staleTime: Infinity, refetchInterval: false } } });
  qc.setQueryData(["rooms", "en"], state(rooms, extra));
  qc.setQueryData(["info", "en"], { mode: "local", building: "Test building", level: "Level 4", room_names: {}, chat_model: "built-in answers" });
  qc.setQueryData(["me"], { admin, who: admin ? "localhost" : null, rule: admin ? "localhost" : "token", viewer: true, viewer_required: false });
  const view = render(
    <QueryClientProvider client={qc}><SettingsProvider><TooltipProvider><MemoryRouter initialEntries={[path]}>
      <AppShell fill={path === "/"}>{page}</AppShell>
    </MemoryRouter></TooltipProvider></SettingsProvider></QueryClientProvider>);
  return { ...view, qc };
}

/** jsdom has no layout: say whether the window is wide enough for the sidebar to be part of the page. */
function widePage(wide: boolean) {
  vi.stubGlobal("matchMedia", (query: string) => ({ matches: wide, media: query, addEventListener() {}, removeEventListener() {} }));
}

beforeEach(() => {
  localStorage.clear();
  widePage(true);
  vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({ detail: "offline" }), { status: 503 })));
});
afterEach(() => {
  vi.unstubAllGlobals();
  Object.defineProperty(window, "innerWidth", { configurable: true, value: 1024 });
});

describe("header", () => {
  it("shows the logo for each theme, with no tagline, and the product name for screen readers", () => {
    show("/");
    const home = screen.getByRole("link", { name: "NADI, home" });
    const logos = [...home.querySelectorAll("img")];
    expect(logos.map((i) => i.getAttribute("data-logo"))).toEqual(["light", "dark"]);
    expect(logos[0].className).toContain("dark:hidden");          // one of the two shows, whichever theme is on
    expect(logos[1].className).toMatch(/\bhidden\b.*dark:block/);
    for (const img of logos) {
      expect(img.getAttribute("src")).toMatch(/svg/);              // the vector drawing, not a raster
      expect(img).toHaveAttribute("alt", "");                      // the link carries the name once
      expect(img).toHaveAttribute("height", "30");
    }
    expect(home).toHaveTextContent("");                             // the logo only
    expect(document.body).not.toHaveTextContent("Building occupancy and safety");
  });

  it("keeps 'Start emergency mode' in the header on every page", () => {
    for (const path of ["/", "/rooms", "/calibration"]) {
      const { unmount } = show(path);
      expect(within(screen.getByRole("banner")).getByRole("button", { name: "Start emergency mode" })).toBeInTheDocument();
      unmount();
    }
  });

  it("moves mode, rooms reporting and the clock out of the header", () => {
    show("/");
    const header = screen.getByRole("banner");
    expect(header).not.toHaveTextContent("LOCAL");
    expect(header).not.toHaveTextContent("rooms reporting");
    expect(header.querySelector("time")).toBeNull();
  });

  it("shows the alerts that are not acknowledged on the bell, in words for screen readers", () => {
    show("/", { extra: { alerts: [alert("a"), alert("b"), alert("c", { ack: { by: "warden", ts: NOW } }), alert("d", { severity: "info" })] } });
    const bell = within(screen.getByRole("banner")).getByRole("link", { name: "Alerts: 2 not acknowledged" });
    expect(bell).toHaveAttribute("href", "/alerts");
    expect(bell).toHaveTextContent("2");
  });

  it("has no time range in the frame: it sits in the room panel, with the charts it changes", () => {
    show("/rooms");
    expect(screen.queryByLabelText("Time range")).toBeNull();
  });
});

describe("sidebar", () => {
  it("is an icon rail below 1440 px wide and open from there, until the viewer chooses", () => {
    const narrow = show("/", { width: 1366 });
    expect(document.getElementById("sidebar")).toHaveAttribute("data-sidebar", "rail");
    expect(screen.getByRole("button", { name: "Open the menu" })).toHaveAttribute("aria-expanded", "false");
    narrow.unmount();
    show("/", { width: 1920 });
    expect(document.getElementById("sidebar")).toHaveAttribute("data-sidebar", "open");
    expect(screen.getByRole("button", { name: "Collapse the menu" })).toHaveAttribute("aria-expanded", "true");
  });

  it("folds and opens with the hamburger, and remembers the choice in the browser", () => {
    const first = show("/", { width: 1920 });
    const menu = screen.getByRole("button", { name: "Collapse the menu" });
    expect(menu).toHaveAttribute("aria-controls", "sidebar");
    fireEvent.click(menu);
    expect(document.getElementById("sidebar")).toHaveAttribute("data-sidebar", "rail");
    expect(localStorage.getItem("nadiSidebar")).toBe("rail");
    first.unmount();
    show("/", { width: 1920 });  // the same wide window again: the viewer's choice wins
    expect(document.getElementById("sidebar")).toHaveAttribute("data-sidebar", "rail");
    fireEvent.click(screen.getByRole("button", { name: "Open the menu" }));
    expect(localStorage.getItem("nadiSidebar")).toBe("open");
  });

  it("names the building and level when open, and keeps every destination reachable by name as a rail", () => {
    const open = show("/", { width: 1920 });
    const side = document.getElementById("sidebar")!;
    expect(side.querySelector("[data-building]")).toHaveTextContent("Test buildingLevel 4");
    const nav = within(side).getByRole("navigation", { name: "Main navigation" });
    expect(within(nav).getAllByRole("link").map((a) => a.textContent)).toEqual(["Overview", "Floor plan", "Rooms", "Sensors", "Energy", "Alerts"]);
    expect(within(nav).getByRole("link", { name: "Overview" })).toHaveAttribute("aria-current", "page");
    open.unmount();
    show("/", { width: 1366 });
    const rail = within(document.getElementById("sidebar")!).getByRole("navigation", { name: "Main navigation" });
    for (const name of ["Overview", "Floor plan", "Rooms", "Sensors", "Energy", "Alerts"]) {
      expect(within(rail).getByRole("link", { name })).toBeInTheDocument();  // the icon alone, named for screen readers
    }
    const chip = document.querySelector("#sidebar [data-building]")!;  // the rail's building icon opens the switcher
    expect(chip).toHaveAttribute("aria-label", "Change building or floor: Test building, Level 4");
    expect(chip).toHaveAttribute("aria-haspopup", "dialog");
    const current = within(rail).getByRole("link", { name: "Overview" });
    expect(current).toHaveAttribute("aria-current", "page");
    expect(current.className).toMatch(/ w-12 .* bg-nav-active /);  // a centred pill, and the current page is marked
    expect(current.className).not.toContain("=>");                      // class names, not a function printed as text
  });

  it("puts the alert count on the right of Alerts when open, and on the icon as a rail", () => {
    const alerts = { alerts: [alert("a"), alert("b")] };
    const open = show("/", { width: 1920, extra: alerts });
    expect(within(document.getElementById("sidebar")!).getByRole("link", { name: /Alerts/ })).toHaveTextContent("AlertsNot acknowledged: 2");
    open.unmount();
    show("/", { width: 1366, extra: alerts });
    expect(within(document.getElementById("sidebar")!).getByRole("link", { name: "Alerts: 2 not acknowledged" })).toHaveTextContent("2");
  });

  it("offers Calibration at the bottom to an admin only", () => {
    const viewer = show("/", { width: 1920 });
    expect(within(document.getElementById("sidebar")!).queryByRole("link", { name: "Calibration" })).toBeNull();
    viewer.unmount();
    show("/", { width: 1920, admin: true });
    const link = within(document.getElementById("sidebar")!).getByRole("link", { name: "Calibration" });
    expect(link).toHaveAttribute("href", "/calibration");
    expect(link.parentElement!.className).toContain("border-t");  // below a divider
  });

  it("opens over the page from the hamburger on a small screen", () => {
    widePage(false);
    show("/rooms");
    const menu = screen.getByRole("button", { name: "Open the menu" });
    expect(menu).toHaveAttribute("aria-expanded", "false");
    expect(menu).toHaveAttribute("aria-haspopup", "dialog");  // it opens a dialog here, it does not fold the sidebar
    expect(menu).not.toHaveAttribute("aria-controls");
    fireEvent.click(menu);
    const drawer = screen.getByRole("dialog");
    expect(within(drawer).getByRole("link", { name: "Rooms" })).toHaveAttribute("aria-current", "page");
    fireEvent.click(within(drawer).getByRole("link", { name: "Energy" }));
    expect(screen.queryByRole("dialog")).toBeNull();  // choosing a page closes it
  });
});

describe("Ask NADI", () => {
  const answer = (text: string) => vi.fn(async (url: string, _init?: RequestInit) => (String(url).includes("/api/chat")
    ? new Response(JSON.stringify({ answer: text, source: "fallback", model: "built-in answers" }), { status: 200 })
    : new Response(JSON.stringify({ detail: "offline" }), { status: 503 })));
  const asked = (fetch: ReturnType<typeof answer>) => fetch.mock.calls.filter(([url]) => String(url).includes("/api/chat"))
    .map(([, init]) => JSON.parse(String(init?.body)).question);

  it("is a search-style box in the header that sends the typed question to the side panel on Enter", async () => {
    const fetch = answer("1 person inside, in 1 room.");
    vi.stubGlobal("fetch", fetch);
    show("/");
    const box = within(screen.getByRole("search", { name: "Ask NADI" })).getByRole("textbox", { name: "Ask NADI a question" });
    expect(box).toHaveAttribute("placeholder", "Ask NADI about the building…");
    fireEvent.change(box, { target: { value: "How many people?" } });
    fireEvent.submit(box.closest("form")!);
    const panel = await screen.findByRole("dialog", { name: "Ask NADI" });
    expect(await within(panel).findByText("1 person inside, in 1 room.")).toBeInTheDocument();
    expect(asked(fetch)).toEqual(["How many people?"]);            // sent once
    expect(within(panel).getByText("How many people?")).toBeInTheDocument();
    expect(box).toHaveValue("");
  });

  it("offers three questions while the chat is empty, and sends one on click", async () => {
    const fetch = answer("No air conditioning is on in an empty room.");
    vi.stubGlobal("fetch", fetch);
    show("/");
    fireEvent.click(screen.getByRole("button", { name: "Open Ask NADI" }));
    const panel = await screen.findByRole("dialog", { name: "Ask NADI" });
    const chips = within(panel.querySelector("[data-suggestions]") as HTMLElement).getAllByRole("button");
    expect(chips.map((c) => c.textContent)).toEqual(["How many people are inside?", "Which rooms waste air conditioning?", "Bilik mana ada orang?"]);
    expect(chips.map((c) => c.getAttribute("lang"))).toEqual(["en", "en", "ms"]);
    expect(asked(fetch)).toEqual([]);  // opening the panel asks nothing
    fireEvent.click(chips[1]);
    expect(await within(panel).findByText("No air conditioning is on in an empty room.")).toBeInTheDocument();
    expect(asked(fetch)).toEqual(["Which rooms waste air conditioning?"]);
    expect(panel.querySelector("[data-suggestions]")).toBeNull();  // the suggestions are for the empty chat only
  });

  it("opens with Enter on an empty box, closes with Escape and gives the focus back to the box", async () => {
    show("/");
    const box = screen.getByRole("textbox", { name: "Ask NADI a question" });
    fireEvent.submit(box.closest("form")!);
    const panel = await screen.findByRole("dialog", { name: "Ask NADI" });
    expect(panel.querySelector("[data-suggestions]")).not.toBeNull();
    fireEvent.keyDown(panel, { key: "Escape" });
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    await waitFor(() => expect(document.activeElement).toBe(screen.getByRole("textbox", { name: "Ask NADI a question" })));
  });

  it("jumps to the box with the slash key, but not while typing somewhere else", () => {
    show("/", { page: <input aria-label="other" /> });
    const box = screen.getByRole("textbox", { name: "Ask NADI a question" });
    const other = screen.getByRole("textbox", { name: "other" });
    other.focus();
    fireEvent.keyDown(other, { key: "/" });
    expect(document.activeElement).toBe(other);
    other.blur();
    fireEvent.keyDown(document.body, { key: "/" });
    expect(document.activeElement).toBe(box);
  });

  it("keeps a question typed while another is being answered, and sends it next", async () => {
    let release: (r: Response) => void = () => {};
    const fetch = vi.fn((url: string, _init?: RequestInit) => (String(url).includes("/api/chat")
      ? new Promise<Response>((resolve) => { release = resolve; })
      : Promise.resolve(new Response(JSON.stringify({ detail: "offline" }), { status: 503 }))));
    vi.stubGlobal("fetch", fetch);
    const reply = (text: string) => new Response(JSON.stringify({ answer: text, source: "fallback", model: "built-in answers" }), { status: 200 });
    show("/");
    const box = screen.getByRole("textbox", { name: "Ask NADI a question" });
    fireEvent.change(box, { target: { value: "First question" } });
    fireEvent.submit(box.closest("form")!);
    const panel = await screen.findByRole("dialog", { name: "Ask NADI" });
    await within(panel).findByText("Checking the live readings…");
    fireEvent.change(box, { target: { value: "Second question" } });
    fireEvent.submit(box.closest("form")!);
    expect(asked(fetch)).toEqual(["First question"]);  // one at a time
    await act(async () => { release(reply("First answer")); });
    await within(panel).findByText("First answer");
    await waitFor(() => expect(asked(fetch)).toEqual(["First question", "Second question"]));
    await act(async () => { release(reply("Second answer")); });
    expect(await within(panel).findByText("Second answer")).toBeInTheDocument();
  });

  it("leaves the slash key alone while a dialog is open", async () => {
    show("/");
    fireEvent.click(screen.getByRole("button", { name: "Start emergency mode" }));
    const dialog = await screen.findByRole("dialog");
    const before = document.activeElement;
    fireEvent.keyDown(dialog, { key: "/" });
    expect(document.activeElement).toBe(before);
    expect(document.activeElement).not.toBe(screen.queryByRole("textbox", { name: "Ask NADI a question", hidden: true }));
  });

  it("every suggested question exists in both languages and has no emoji", () => {
    for (const [key] of SUGGESTED) {
      for (const lang of ["en", "ms"] as const) {
        const text = T(key, undefined, lang);
        expect(text).not.toBe(key);
        expect(text).toMatch(/^[\p{L}\p{N}\p{P}\p{Zs}]+$/u);
      }
    }
  });
});

describe("live chip beside the page title", () => {
  it("says 'Live' and how old the newest reading is, with mode, rooms reporting and the clock behind it", () => {
    show("/rooms", { page: <PageHeader title="Rooms" /> });
    expect(screen.getByRole("heading", { level: 1, name: "Rooms" })).toBeInTheDocument();
    const chip = document.querySelector("[data-live-chip]")!;
    expect(chip).toHaveAttribute("data-feed", "live");
    expect(chip).toHaveTextContent(/^Live\s?· updated/);
    expect(chip.querySelector(".live-beat")).toBeNull();  // still on page load: it beats once per new report
  });

  it("is grey and dashed with 'No live data', never a green 'Live', when no sensor is online", () => {
    show("/rooms", { rooms: [room({ live: false, count_ts: NOW - 140 })], page: <LiveChip /> });
    const chip = document.querySelector("[data-live-chip]")!;
    expect(chip).toHaveAttribute("data-feed", "none");
    expect(chip).toHaveTextContent(/^No live data\s?· updated/);  // when the last report came is still said
    expect(chip.className).toContain("border-dashed");
    expect(chip.className).not.toMatch(/bg-ok/);
    expect(chip.querySelector(".live-beat")).toBeNull();
  });

  it("beats once when a newer report arrives, and never during an emergency", async () => {
    const { qc } = show("/rooms", { page: <LiveChip /> });
    await act(async () => { qc.setQueryData(["rooms", "en"], state([room({ count_ts: NOW + 7 })], { now: NOW + 10 })); });
    await waitFor(() => expect(document.querySelectorAll("[data-live-chip] .live-beat")).toHaveLength(1));
    await act(async () => {
      qc.setQueryData(["rooms", "en"], state([room({ count_ts: NOW + 17 })], { now: NOW + 20, emergency: { on: true, since: NOW, drill: true, id: "d" } }));
    });
    await waitFor(() => expect(document.querySelector("[data-live-chip] .live-beat")).toBeNull());
  });
});

describe("Ask NADI footer", () => {
  const info = (extra: object) => ({ mode: "local", building: "Test building", level: "Level 4", room_names: {}, chat_model: "built-in answers", ...extra });
  const reply = (source: string, model: string) => vi.fn(async (url: string) => (String(url).includes("/api/chat")
    ? new Response(JSON.stringify({ answer: "1 person inside, in 1 room.", source, model }), { status: 200 })
    : new Response(JSON.stringify({ detail: "offline" }), { status: 503 })));
  const foot = (panel: HTMLElement) => panel.querySelector("[data-chat-foot]")?.textContent;
  async function open() {
    fireEvent.click(screen.getByRole("button", { name: "Open Ask NADI" }));
    return screen.findByRole("dialog", { name: "Ask NADI" });
  }

  it("says the answers come from live sensor data when no model words them", async () => {
    const { qc } = show("/");
    act(() => { qc.setQueryData(["info", "en"], info({ chat_source: "rules" })); });
    const panel = await open();
    expect(foot(panel)).toBe("Answered from live sensor data.");
    expect(panel.textContent).not.toMatch(/built-in answers/i);
  });

  it("names the local model as the one wording the reply, and the sensor data as the source of the numbers", async () => {
    const { qc } = show("/");
    act(() => { qc.setQueryData(["info", "en"], info({ chat_source: "ollama", chat_model: "qwen2.5:3b via Ollama (local)" })); });
    const panel = await open();
    expect(foot(panel)).toBe("Worded by qwen2.5:3b via Ollama (local). Numbers from live sensor data.");
  });

  it("follows the answer itself once there is one: a reply the rules built is not credited to the model", async () => {
    vi.stubGlobal("fetch", reply("fallback", "built-in answers (no language model)"));
    const { qc } = show("/");
    act(() => { qc.setQueryData(["info", "en"], info({ chat_source: "ollama", chat_model: "qwen2.5:3b via Ollama (local)" })); });
    const panel = await open();
    fireEvent.click(panel.querySelector("[data-suggestions] button")!);
    await within(panel).findByText("1 person inside, in 1 room.");
    expect(foot(panel)).toBe("Answered from live sensor data.");
  });

  it("credits the model when the model worded the answer", async () => {
    vi.stubGlobal("fetch", reply("ollama", "qwen2.5:3b via Ollama (local)"));
    show("/");
    const panel = await open();
    fireEvent.click(panel.querySelector("[data-suggestions] button")!);
    await within(panel).findByText("1 person inside, in 1 room.");
    expect(foot(panel)).toBe("Worded by qwen2.5:3b via Ollama (local). Numbers from live sensor data.");
  });
});
