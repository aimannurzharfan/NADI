// Buildings and floors (docs/design/PLAN.md, Part 16): the switcher's search and keys, the floor kept in the
// address and the browser, and the pages following the floor.
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter, useLocation } from "react-router-dom";

import { SiteSwitcher, filterSite } from "@/components/site-switcher";
import { TooltipProvider } from "@/components/ui/tooltip";
import { BUILTIN_PLAN, labelOf, type Plan } from "@/lib/plan";
import { SiteProvider, useExitName, useFloorRooms, useSite, type Site } from "@/lib/site";
import type { Room } from "@/lib/types";

const floors = (prefix: string, n: number, rooms = 8) =>
  Array.from({ length: n }, (_, i) => ({ id: `${prefix}${i + 1}`, name: `Level ${i + 1}`, level: i + 1, rooms, version: 0 }));
const SITE: Site = { default_floor: "f1", editor: true, buildings: [
  { id: "b1", name: "Demo Building", code: "DEMO", example: false, floors: [{ id: "f1", name: "Level 4", level: 4, rooms: 3, version: 0 },
    { id: "f2", name: "Level 5", level: 5, rooms: 1, version: 2 }] },
  { id: "example", name: "Example Tower (example data)", code: "EX-01", example: true, floors: floors("ex-", 12) },
] };
const F2: Plan = { ...BUILTIN_PLAN, rooms: { lab9: { name: "Lab 9", x: 120, y: 20, w: 200, h: 200, exit: "west" } },
  exits: { west: { name: "West stair", x: 20, y: 20, w: 100, h: 200 } }, other: [{ name: "Plant room", x: 400, y: 320, w: 100, h: 100 }] };

beforeEach(() => {
  localStorage.clear();
  vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({ detail: "offline" }), { status: 503 })));
});
afterEach(() => vi.unstubAllGlobals());

function Probe({ rooms = [] }: { rooms?: Room[] }) {
  const site = useSite();
  const here = useFloorRooms(rooms);
  const exit = useExitName();
  const loc = useLocation();
  return (
    <p data-testid="probe">
      {[site.floorId, Object.keys(site.plan.rooms).join(","), site.example ? "example" : "real", here.map((r) => r.room_id).join(","),
        exit("room1"), exit("lab9"), loc.search].join("|")}
    </p>
  );
}

const room = (room_id: string): Room => ({ room_id, name: room_id, headcount: 1, at_least: false, count_ts: 1, counter: "csi",
  temp_c: 24, humidity: 60, live: true, waste: null });

function show(at = "/", rooms: Room[] = []) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false, staleTime: Infinity, refetchInterval: false } } });
  qc.setQueryData(["site"], SITE);
  qc.setQueryData(["plan", "f2"], { floor_id: "f2", version: 2, saved_ts: 1, saved_by: "admin", plan: F2 });
  qc.setQueryData(["info", "en"], { building: "Demo Building", level: "Level 4", room_names: {},
    room_floors: { room1: "f1", room2: "f1", room3: "f1", lab9: "f2" }, room_exits: { room1: "Stair B", lab9: "West stair" } });
  return render(<QueryClientProvider client={qc}><TooltipProvider><MemoryRouter initialEntries={[at]}><SiteProvider>
    <SiteSwitcher rail={false} /><Probe rooms={rooms} /></SiteProvider></MemoryRouter></TooltipProvider></QueryClientProvider>);
}
const probe = () => screen.getByTestId("probe").textContent!.split("|");

describe("the search", () => {
  it("keeps every floor of a building whose name or code matches, else only the matching floors", () => {
    expect(filterSite(SITE, "").map((b) => b.id)).toEqual(["b1", "example"]);
    expect(filterSite(SITE, "ex").map((b) => [b.id, b.floors.length])).toEqual([["example", 12]]);
    expect(filterSite(SITE, "DEMO")[0].floors).toHaveLength(2);
    expect(filterSite(SITE, "level 7").map((b) => [b.id, b.floors.map((f) => f.id)])).toEqual([["example", ["ex-7"]]]);
    expect(filterSite(SITE, "LEVEL 5").map((b) => b.id)).toEqual(["b1", "example"]);
    expect(filterSite(SITE, "nothing here")).toEqual([]);
  });

  it("names a typed stair as written and a built-in one in the page language", () => {
    expect(labelOf({ label: "plan.stair_a" })).toBe("Stair A");
    expect(labelOf({ name: " West stair " })).toBe("West stair");
    expect(labelOf({ label: "not.a.key", name: "Fallback" })).toBe("Fallback");
  });
});

describe("the switcher", () => {
  it("opens a wide panel beside the sidebar: buildings on the left, the highlighted building's floors on the right", () => {
    show("/", [room("room1"), room("lab9")]);
    expect(probe().slice(0, 4)).toEqual(["f1", "room2,room1,room3", "real", "room1"]);
    const chip = screen.getByRole("button", { name: "Change building or floor: Demo Building, Level 4" });
    expect(chip).toHaveAttribute("aria-haspopup", "dialog");
    fireEvent.click(chip);
    const panel = screen.getByRole("dialog", { name: "Change building or floor" });
    const search = within(panel).getByRole("combobox", { name: "Search building, code or floor" });
    expect(search).toHaveFocus();
    const buildings = within(panel).getByRole("listbox", { name: "Buildings" });
    expect(within(buildings).getAllByRole("option").map((o) => o.getAttribute("data-site-building"))).toEqual(["b1", "example"]);
    expect(within(buildings).getByRole("option", { name: /Example Tower/ })).toHaveTextContent("Example");
    // the building in use is highlighted, its floors on the right, the current one marked
    expect(search).toHaveAttribute("aria-activedescendant", within(buildings).getByRole("option", { name: /Demo Building/ }).id);
    const floorsOf = () => within(panel).getByRole("listbox", { name: /^Floors of / });
    expect(floorsOf()).toHaveAccessibleName("Floors of Demo Building");
    expect(within(floorsOf()).getByRole("option", { name: /Level 4.*current/ })).toHaveAttribute("data-current", "true");
    expect(within(floorsOf()).getByRole("option", { name: /Level 4/ })).toHaveTextContent("3 rooms");
    // Down moves to the example building: its floors show, ten of twelve, then "Show 2 more"
    fireEvent.keyDown(search, { key: "ArrowDown" });
    expect(floorsOf()).toHaveAccessibleName("Floors of Example Tower (example data)");
    expect(within(floorsOf()).getAllByRole("option").map((o) => o.textContent?.startsWith("Show") ? "more" : "floor").filter((x) => x === "floor")).toHaveLength(10);
    expect(within(floorsOf()).getByRole("option", { name: "Show 2 more" })).toBeInTheDocument();
    // Up, then Right (or Enter) goes into the floors; Down, Enter switches
    fireEvent.keyDown(search, { key: "ArrowUp" });
    fireEvent.keyDown(search, { key: "ArrowRight" });
    const highlighted = () => document.getElementById(search.getAttribute("aria-activedescendant") ?? "");
    expect(highlighted()).toHaveTextContent("Level 4");
    fireEvent.keyDown(search, { key: "ArrowDown" });
    expect(highlighted()).toHaveTextContent("Level 5");
    fireEvent.keyDown(search, { key: "ArrowLeft" });  // Left goes back to the buildings
    expect(highlighted()).toHaveAttribute("data-site-building", "b1");
    fireEvent.keyDown(search, { key: "Enter" });
    fireEvent.keyDown(search, { key: "ArrowDown" });
    expect(highlighted()).toHaveTextContent("Level 5");
    expect(search).toHaveFocus();  // the focus never leaves the search box
    fireEvent.keyDown(search, { key: "Enter" });
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(chip).toHaveFocus();
    expect(probe()).toEqual(["f2", "lab9", "real", "lab9", "Stair B", "West stair", "?floor=f2"]);
    expect(localStorage.getItem("nadiFloor")).toBe("f2");
    expect(chip).toHaveAccessibleName("Change building or floor: Demo Building, Level 5");
  });

  it("searches as one list of 'Building > Floor' rows and switches with Enter", () => {
    show();
    fireEvent.click(screen.getByRole("button", { name: /Change building or floor/ }));
    const search = screen.getByRole("combobox");
    fireEvent.change(search, { target: { value: "level 5" } });
    const rows = screen.getByRole("listbox", { name: "Matching floors" });
    expect(within(rows).getAllByRole("option").map((o) => o.textContent)).toEqual([
      "Demo BuildingLevel 51 room", "Example Tower (example data)Level 5Example8 rooms"]);
    expect(screen.queryByRole("listbox", { name: "Buildings" })).toBeNull();
    fireEvent.keyDown(search, { key: "ArrowDown" });
    fireEvent.keyDown(search, { key: "ArrowDown" });
    fireEvent.keyDown(search, { key: "Enter" });
    expect(probe()[0]).toBe("ex-5");
  });

  it("lists fifty floors ten at a time", () => {
    const big: Site = { ...SITE, buildings: [...SITE.buildings, { id: "b9", name: "Tower 9", code: "T9", example: false, floors: floors("t9-", 55, 2) }] };
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false, staleTime: Infinity, refetchInterval: false } } });
    qc.setQueryData(["site"], big);
    render(<QueryClientProvider client={qc}><TooltipProvider><MemoryRouter><SiteProvider><SiteSwitcher rail /></SiteProvider></MemoryRouter></TooltipProvider></QueryClientProvider>);
    fireEvent.click(screen.getByRole("button", { name: /Change building or floor/ }));  // the rail opens the same panel
    fireEvent.click(screen.getByRole("option", { name: /Tower 9/ }));
    const list = screen.getByRole("listbox", { name: "Floors of Tower 9" });
    expect(within(list).getAllByRole("option")).toHaveLength(11);
    fireEvent.click(within(list).getByRole("option", { name: "Show 45 more" }));
    expect(within(list).getAllByRole("option")).toHaveLength(56);  // all 55, then "Show fewer"
    expect(within(list).getByRole("option", { name: "Show fewer" })).toBeInTheDocument();
    const search = screen.getByRole("combobox");
    fireEvent.change(search, { target: { value: "tower" } });
    expect(within(screen.getByRole("listbox", { name: "Matching floors" })).getAllByRole("option")).toHaveLength(11);  // ten rows, then "Show 45 more"
  });

  it("closes with Escape and returns to the chip, and says when nothing matches", () => {
    show();
    const chip = screen.getByRole("button", { name: /Change building or floor/ });
    fireEvent.click(chip);
    const search = screen.getByRole("combobox");
    fireEvent.change(search, { target: { value: "zzz" } });
    expect(screen.getByText("No building or floor matches.")).toBeInTheDocument();
    fireEvent.keyDown(search, { key: "Escape" });
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(chip).toHaveFocus();
  });
});

describe("the floor on screen", () => {
  it("comes from the address, else this browser's last choice, else the default; an unknown floor falls back", () => {
    localStorage.setItem("nadiFloor", "f2");
    const first = show("/?floor=ex-7");
    expect(probe().slice(0, 3)).toEqual(["ex-7", "", "example"]);
    expect(localStorage.getItem("nadiFloor")).toBe("ex-7");  // a shared link becomes this browser's choice
    first.unmount();
    const second = show("/");
    expect(probe()[0]).toBe("ex-7");
    second.unmount();
    show("/?floor=f99");
    expect(probe()[0]).toBe("f1");
  });

  it("starts from the bundled plan for f1, so the plan never blanks while the server is away", () => {
    show();
    expect(probe()[1]).toBe(Object.keys(BUILTIN_PLAN.rooms).join(","));
  });
});
