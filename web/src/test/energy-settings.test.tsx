// Energy settings (docs/design/PLAN.md, Part 15): everyone reads the values, an admin edits them, a save lists
// every change first, and what the server refuses lands under its field.
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import { EnergySettingsCard, changeLines, checkForm, diffOf, formOf, valueText } from "@/components/energy-settings";
import { TooltipProvider } from "@/components/ui/tooltip";
import { T } from "@/lib/i18n";
import { SettingsProvider } from "@/lib/settings";
import type { EnergySettings, EnergyValues } from "@/lib/types";
import { AlertsPage } from "@/pages/alerts";
import { EnergyPage } from "@/pages/energy";
import { RoomsPage } from "@/pages/rooms";

const NOW = 1_794_463_320;  // 12 Nov 2026, 14:02 in Malaysia
const VALUES: EnergyValues = { tariff_rm_per_kwh: 0.2983, ac_kw: 10, ac_kw_rooms: {}, ac_on_below_c: 26, waste_after_min: 10, co2_kg_per_kwh: 0.75 };
const LIMITS: EnergySettings["limits"] = { tariff_rm_per_kwh: [0.01, 5], ac_kw: [0.1, 500], ac_on_below_c: [16, 35],
  waste_after_min: [1, 240], co2_kg_per_kwh: [0.01, 2] };
const ROOMS = { room1: "Lab 2", room2: "Hall A", room3: "Room 3" };
const settings = (over: Partial<EnergySettings> = {}): EnergySettings => ({ now: NOW, settings: VALUES, effective_from: null,
  changed_by: null, source: "defaults", database: true, limits: LIMITS, max_rooms: 100, history: [], history_total: 0, ...over });
const nameOf = (id: string) => ROOMS[id as keyof typeof ROOMS] ?? id;

const client = (data?: EnergySettings) => {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false, staleTime: Infinity, refetchInterval: false } } });
  qc.setQueryData(["me"], { admin: true, who: "localhost", rule: "localhost", viewer: true, viewer_required: false });
  qc.setQueryData(["info", "en"], { building: "B", level: "L", room_names: ROOMS, ac_on_below_c: 28 });
  if (data) qc.setQueryData(["energy-settings"], data);
  return qc;
};
const wrap = (qc: QueryClient, node: React.ReactNode, at = "/") =>
  render(<QueryClientProvider client={qc}><TooltipProvider><MemoryRouter initialEntries={[at]}><SettingsProvider>{node}</SettingsProvider></MemoryRouter></TooltipProvider></QueryClientProvider>);
const card = (data: EnergySettings, admin = true) => wrap(client(data), <EnergySettingsCard admin={admin} rooms={ROOMS} />);
const input = (name: string) => screen.getByRole("textbox", { name }) as HTMLInputElement;

beforeEach(() => {
  vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({ detail: "offline" }), { status: 503 })));
  vi.stubGlobal("ResizeObserver", class { observe() {} unobserve() {} disconnect() {} });
});
afterEach(() => vi.unstubAllGlobals());

describe("the words for the values", () => {
  it("writes each value with its unit", () => {
    expect(valueText("tariff_rm_per_kwh", 0.2983)).toBe("RM 0.2983 per kWh");
    expect(valueText("tariff_rm_per_kwh", 0.35)).toBe("RM 0.35 per kWh");
    expect(valueText("ac_kw", 10)).toBe("10 kW");
    expect(valueText("ac_on_below_c", 26)).toBe("26.0 °C");
    expect(valueText("waste_after_min", 10)).toBe("10 minutes");
    expect(valueText("waste_after_min", 1)).toBe("1 minute");
    expect(valueText("co2_kg_per_kwh", 0.75)).toBe("0.75 kg per kWh");
    expect(T("es.val_tariff", { x: 0.35 }, "ms")).toBe("RM 0.35 sekWj");
    expect(T("es.val_min", { x: 10 }, "ms")).toBe("10 minit");
  });

  it("writes a change as old to new, and a room's own power by the room's name", () => {
    expect(changeLines({ tariff_rm_per_kwh: [0.2983, 0.35], waste_after_min: [10, 1], "ac_kw_rooms.room1": [null, 3.5],
      "ac_kw_rooms.room2": [4, null] }, nameOf)).toEqual([
      "Electricity tariff: RM 0.2983 per kWh → RM 0.35 per kWh",
      "Waste flagged after: 10 minutes → 1 minute",
      "Air conditioner power for Lab 2: building value → 3.5 kW",
      "Air conditioner power for Hall A: 4 kW → building value",
    ]);
  });

  it("checks the form like the server does", () => {
    const form = { ...formOf(VALUES), tariff_rm_per_kwh: "-1", ac_kw: "0", ac_on_below_c: "60", waste_after_min: "ten",
      rooms: [{ id: "room1", value: "900" }] };
    const { errors, values } = checkForm(form, LIMITS, nameOf);
    expect(values).toBeNull();
    expect(errors).toEqual({
      tariff_rm_per_kwh: "Electricity tariff must be between 0.01 and 5 RM per kWh.",
      ac_kw: "Air conditioner power must be between 0.1 and 500 kW.",
      ac_on_below_c: "Air conditioning counts as on below must be between 16 and 35 °C.",
      waste_after_min: "Waste flagged after must be a number.",
      "ac_kw_rooms.room1": "Lab 2 must be between 0.1 and 500 kW.",
    });
    const ok = checkForm({ ...formOf(VALUES), tariff_rm_per_kwh: " 0.35 ", rooms: [{ id: "room1", value: "3.5" }] }, LIMITS, nameOf);
    expect(ok.errors).toEqual({});
    expect(ok.values).toEqual({ ...VALUES, tariff_rm_per_kwh: 0.35, ac_kw_rooms: { room1: 3.5 } });
    expect(diffOf(VALUES, ok.values!)).toEqual({ tariff_rm_per_kwh: [0.2983, 0.35], "ac_kw_rooms.room1": [null, 3.5] });
    expect(diffOf(VALUES, { ...VALUES })).toEqual({});
    for (const text of ["", "1e3", "0x10", "1,5", "abc", "Infinity"]) {
      expect(checkForm({ ...formOf(VALUES), ac_kw: text }, LIMITS, nameOf).errors.ac_kw).toBe("Air conditioner power must be a number.");
    }
  });
});

describe("the energy settings card", () => {
  it("shows a viewer five tiles (label, value, unit), where the values come from and the rule line; no Edit button", () => {
    const { container } = card(settings(), false);
    const tile = (key: string) => container.querySelector(`[data-setting="${key}"]`)!;
    expect(container.querySelectorAll("[data-settings-tiles] > [data-setting]")).toHaveLength(5);
    expect(tile("tariff_rm_per_kwh").textContent).toBe("Electricity tariff0.2983RM per kWh");
    expect(tile("ac_kw").querySelector("[data-value]")?.textContent).toBe("10");
    expect(tile("ac_on_below_c").textContent).toBe("Air conditioning counts as on below26.0°C");
    expect(tile("waste_after_min").textContent).toBe("Waste flagged after10minutes");
    expect(tile("co2_kg_per_kwh").textContent).toBe("CO2 factor0.75kg per kWh");
    expect(container.querySelector("[data-settings-tiles]")?.className).toMatch(/2xl:grid-cols-5/);
    expect(screen.getByText("Default values from the server configuration")).toBeInTheDocument();
    expect(container.querySelector("[data-rule-line]")).toHaveTextContent(
      "Waste: empty room, below 26.0 °C, longer than 10 min. RM = 10 kW x hours x RM 0.2983 per kWh. CO2 = kWh x 0.75 (estimate).");
    expect(container.querySelector("[data-per-room]")).toBeNull();  // no room has its own power
    expect(screen.queryByRole("button", { name: "Edit" })).toBeNull();
    expect(screen.queryByRole("textbox")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "History" }));
    expect(screen.getByRole("dialog", { name: "Change history" })).toHaveTextContent("No change has been saved yet.");
  });

  it("says who changed the values last, and lists the rooms with their own power", () => {
    const changed = { ...VALUES, tariff_rm_per_kwh: 0.35, ac_kw_rooms: { room1: 3.5 } };
    const { container } = card(settings({ settings: changed, source: "database", effective_from: NOW, changed_by: "warden1",
      history: [{ id: 1, effective_from: NOW, changed_by: "warden1", settings: changed,
        changes: { tariff_rm_per_kwh: [0.2983, 0.35], "ac_kw_rooms.room1": [null, 3.5] } }], history_total: 1 }), false);
    expect(screen.getByText("Last changed by warden1 on 12 Nov 2026, 14:02")).toBeInTheDocument();
    // "Per room (1)" under the A/C power tile opens the row inside the card
    const per = screen.getByRole("button", { name: "Per room (1)" });
    expect(per).toHaveAttribute("aria-expanded", "false");
    fireEvent.click(per);
    expect(container.querySelector('[data-setting="ac_kw_rooms.room1"]')?.textContent).toBe("Lab 2 3.5 kW");
    fireEvent.click(screen.getByRole("button", { name: "History" }));
    const history = screen.getByRole("dialog", { name: "Change history" });
    expect(within(history).getByText("Electricity tariff: RM 0.2983 per kWh → RM 0.35 per kWh")).toBeInTheDocument();
    expect(within(history).getByText("Air conditioner power for Lab 2: building value → 3.5 kW")).toBeInTheDocument();
    expect(within(history).getByText("warden1")).toBeInTheDocument();
  });

  it("says so in amber words when the database is offline", () => {
    const first = card(settings({ source: "last_known", database: false, effective_from: NOW, changed_by: "admin" }), false);
    const line = first.container.querySelector("[data-settings-source]") as HTMLElement;
    expect(line).toHaveTextContent("The database is offline: these are the last known values.");
    expect(line.className).toContain("text-warn");
    first.unmount();
    card(settings({ source: "defaults", database: false }), false);
    expect(screen.getByText("The database is offline: default values are in use until it is back.")).toBeInTheDocument();
  });

  it("shows ten rows of the change history, then 'Show 3 more'", () => {
    const history = Array.from({ length: 13 }, (_, i) => ({ id: 13 - i, effective_from: NOW - i * 3600, changed_by: "admin", settings: VALUES,
      changes: { ac_kw: [10 + i, 11 + i] as [number, number] } }));
    card(settings({ source: "database", effective_from: NOW, changed_by: "admin", history, history_total: 13 }), false);
    fireEvent.click(screen.getByRole("button", { name: "History" }));
    const rows = () => document.querySelectorAll("[data-settings-history] tbody tr").length;
    expect(rows()).toBe(10);
    fireEvent.click(screen.getByRole("button", { name: "Show 3 more" }));
    expect(rows()).toBe(13);
  });

  it("lets an admin edit: refused values get a message under their field and nothing is sent", () => {
    card(settings());
    fireEvent.click(screen.getByRole("button", { name: "Edit" }));
    const tariff = input("Electricity tariff");
    expect(tariff.value).toBe("0.2983");
    expect(tariff).toHaveAttribute("inputmode", "decimal");
    expect(document.getElementById(tariff.getAttribute("aria-describedby")!.split(" ")[0])).toHaveTextContent("RM per kWh");
    fireEvent.change(tariff, { target: { value: "-1" } });
    fireEvent.change(input("Air conditioner power"), { target: { value: "abc" } });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    const alerts = screen.getAllByRole("alert").map((a) => a.textContent);
    expect(alerts).toEqual(["Electricity tariff must be between 0.01 and 5 RM per kWh.", "Air conditioner power must be a number."]);
    expect(tariff).toHaveAttribute("aria-invalid", "true");
    const described = tariff.getAttribute("aria-describedby")!.split(" ");
    expect(document.getElementById(described[1])).toHaveTextContent("Electricity tariff must be between");
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(fetch).not.toHaveBeenCalled();
    // Save and Cancel are in the card header
    expect(screen.getByRole("button", { name: "Save" }).closest("header")).not.toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));  // Cancel restores the read-only values
    expect(screen.queryByRole("textbox")).toBeNull();
    expect(screen.getByText("0.2983")).toBeInTheDocument();
  });

  it("lists every change before saving, sends the six values, and shows the new ones at once", async () => {
    const next = { ...VALUES, tariff_rm_per_kwh: 0.35, ac_kw_rooms: { room2: 4 } };
    const answer = { ok: true, changed: true, ...settings({ settings: next, source: "database", effective_from: NOW, changed_by: "localhost",
      history: [{ id: 1, effective_from: NOW, changed_by: "localhost", settings: next, changes: { tariff_rm_per_kwh: [0.2983, 0.35] } }], history_total: 1 }) };
    const send = vi.fn(async () => new Response(JSON.stringify(answer), { status: 200 }));
    vi.stubGlobal("fetch", send);
    const { container } = card(settings());
    fireEvent.click(screen.getByRole("button", { name: "Edit" }));
    fireEvent.change(input("Electricity tariff"), { target: { value: "0.35" } });
    fireEvent.click(screen.getByRole("button", { name: "Per room (0)" }));
    expect(screen.getByText("Every room uses the building value.")).toBeInTheDocument();
    fireEvent.change(screen.getByRole("combobox", { name: "Room to add" }), { target: { value: "room2" } });
    fireEvent.click(screen.getByRole("button", { name: "Add a room" }));
    const own = input("Hall A");
    expect(own.value).toBe("10");  // starts from the building value
    fireEvent.change(own, { target: { value: "4" } });
    expect(screen.getByRole("button", { name: "Remove Hall A" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    const dialog = screen.getByRole("dialog", { name: "Save these changes?" });
    expect(within(dialog).getByText("Applies from now. Earlier figures keep the earlier values.")).toBeInTheDocument();
    expect(within(dialog).getAllByRole("listitem").map((li) => li.textContent)).toEqual([
      "Electricity tariff: RM 0.2983 per kWh → RM 0.35 per kWh", "Air conditioner power for Hall A: building value → 4 kW"]);
    expect(send).not.toHaveBeenCalled();
    fireEvent.click(within(dialog).getByRole("button", { name: "Save" }));
    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("Saved. The new values apply from 14:02:00."));
    const [url, init] = send.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe("/api/energy/settings?lang=en");
    expect(init.method).toBe("PUT");
    expect(JSON.parse(init.body as string)).toEqual(next);
    expect(container.querySelector('[data-setting="tariff_rm_per_kwh"] [data-value]')?.textContent).toBe("0.35");
    expect(screen.getByText("Last changed by localhost on 12 Nov 2026, 14:02")).toBeInTheDocument();
    expect(screen.queryByRole("textbox")).toBeNull();
  });

  it("says nothing was changed when the values are the same", () => {
    card(settings());
    fireEvent.click(screen.getByRole("button", { name: "Edit" }));
    fireEvent.change(input("Electricity tariff"), { target: { value: "0.29830" } });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    expect(screen.getByRole("status")).toHaveTextContent("Nothing was changed.");
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(fetch).not.toHaveBeenCalled();
  });

  it("puts what the server refuses under its field, and an offline database in words", async () => {
    const refuse = vi.fn(async () => new Response(JSON.stringify({ detail: "x", errors: { co2_kg_per_kwh: "CO2 factor must be between 0.01 and 2 kg per kWh." } }), { status: 422 }));
    vi.stubGlobal("fetch", refuse);
    card(settings());
    fireEvent.click(screen.getByRole("button", { name: "Edit" }));
    fireEvent.change(input("CO2 factor"), { target: { value: "1.5" } });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    fireEvent.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Save" }));
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("CO2 factor must be between 0.01 and 2 kg per kWh.");
    expect(input("CO2 factor").getAttribute("aria-describedby")).toContain(alert.id);
    expect(input("CO2 factor").value).toBe("1.5");  // the form stays open with what was typed
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({ detail: "The database is offline, so the change cannot be saved." }), { status: 503 })));
    fireEvent.change(input("CO2 factor"), { target: { value: "1.2" } });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    fireEvent.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Save" }));
    await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent("The database is offline, so the change cannot be saved."));
  });
});

describe("the pages that show the settings", () => {
  const amounts = { rm: 1, kwh: 3, co2_kg: 2 };
  const energy = (rate_changes: { ts: number; by: string }[]) => ({ now: NOW, today: amounts, week: amounts, previous_week: amounts,
    yesterday: amounts, daily: [], by_room: [], tariff_rm_per_kwh: 0.35, ac_kw: 10, co2_kg_per_kwh: 0.75, stale_ts: null, rate_changes,
    range: { id: "7d", days: 7, total: amounts, previous: amounts, by_room: [], series: { unit: "day", points: [] }, series_room: null, first_ts: null } });

  it("Energy: says when the rate changed, and works the notes out from the live values", () => {
    const qc = client(settings({ settings: { ...VALUES, tariff_rm_per_kwh: 0.35, ac_on_below_c: 28, waste_after_min: 1 }, source: "database",
      effective_from: NOW, changed_by: "admin" }));
    qc.setQueryData(["energy", "7d", ""], energy([{ ts: NOW - 86400 * 3, by: "admin" }, { ts: NOW, by: "admin" }]));
    const { container } = wrap(qc, <EnergyPage />);
    expect(container.querySelector("[data-rate-changed]")).toHaveTextContent("Rate changed on 12 Nov 2026. Figures before then use the earlier values.");
    // one card: the rule line uses the live values; the separate "How these figures are worked out" card is gone
    expect(container.querySelector("[data-rule-line]")).toHaveTextContent("below 28.0 °C, longer than 1 min. RM = 10 kW x hours x RM 0.35 per kWh");
    expect(screen.queryByText("How these figures are worked out")).toBeNull();
    expect(screen.getByRole("region", { name: "Energy settings" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Edit" })).toBeInTheDocument();  // this viewer is an admin
  });

  it("Energy: no line when nothing was saved in the period, and no Edit button for a viewer", () => {
    const qc = client(settings());
    qc.setQueryData(["me"], { admin: false, who: null, rule: "token", viewer: true, viewer_required: false });
    qc.setQueryData(["energy", "7d", ""], energy([]));
    const { container } = wrap(qc, <EnergyPage />);
    expect(container.querySelector("[data-rate-changed]")).toBeNull();
    expect(screen.queryByRole("button", { name: "Edit" })).toBeNull();
    expect(screen.getByText("Same as the 7 days before")).toBeInTheDocument();  // no "+RM 0.00" when nothing changed
    expect(screen.getByText("0.2983")).toBeInTheDocument();
  });

  it("Rooms: 'On' uses the temperature in force, not a fixed 26", () => {
    const qc = client(settings());
    const room = (id: string, name: string, temp_c: number) => ({ room_id: id, name, headcount: 1, at_least: false, count_ts: NOW, counter: "csi",
      temp_c, humidity: 60, live: true, waste: null });
    qc.setQueryData(["rooms", "en"], { now: NOW, stale_s: 30, rooms: [room("room1", "Lab 2", 27), room("room2", "Hall A", 29)], waste_today_rm: 0,
      waste_today_kwh: 0, emergency: { on: false, since: null, drill: false, id: null }, accountability: {}, alerts: [], offline: {}, stale_ts: null });
    qc.setQueryData(["energy", "7d", ""], energy([]));
    wrap(qc, <RoomsPage />);
    const row = (name: string) => screen.getByText(name).closest("tr") as HTMLElement;
    expect(within(row("Lab 2")).getByText("On (below 28 °C)")).toBeInTheDocument();  // 27 °C: on with 28, off with 26
    expect(within(row("Hall A")).queryByText(/On \(below/)).toBeNull();
  });

  it("Rooms: lists the rooms drawn on the plan that have no sensor, after the others, with 'No sensor' and dashes", () => {
    const qc = client(settings());
    const room = (id: string, name: string) => ({ room_id: id, name, headcount: 1, at_least: false, count_ts: NOW, counter: "csi",
      temp_c: 24, humidity: 60, live: true, waste: null });
    qc.setQueryData(["rooms", "en"], { now: NOW, stale_s: 30, rooms: [room("room1", "Lab 2")], waste_today_rm: 0,
      waste_today_kwh: 0, emergency: { on: false, since: null, drill: false, id: null }, accountability: {}, alerts: [], offline: {}, stale_ts: null });
    qc.setQueryData(["energy", "7d", ""], energy([]));
    const { container } = wrap(qc, <RoomsPage />);
    expect(screen.getByRole("heading", { name: "3 of 3 rooms" })).toBeInTheDocument();  // the plan draws three: the table lists three
    const rows = [...container.querySelectorAll("tbody tr")] as HTMLElement[];
    expect(rows.map((r) => r.querySelector("td")!.textContent)).toEqual(["Lab 2room1", "Hall Aroom2", "Room 3room3"]);
    const hall = container.querySelector("[data-no-sensor-row=room2]") as HTMLElement;
    expect(within(hall).getByText("No sensor").closest("[data-tone=off]")!.className).toContain("border-dashed");
    expect(within(hall).getAllByRole("cell").slice(2).map((c) => c.textContent)).toEqual(["–", "–", "–", "–", "–", "–", "–"]);
    // a status filter is about rooms that report: the rooms without a sensor leave the list
    fireEvent.change(screen.getByRole("textbox", { name: /Search/ }), { target: { value: "hall" } });
    expect(container.querySelectorAll("tbody tr")).toHaveLength(1);
    expect(screen.getByRole("heading", { name: "1 of 3 rooms" })).toBeInTheDocument();
    // its row opens the panel that says there is no sensor
    fireEvent.click(hall.isConnected ? hall : (container.querySelector("[data-no-sensor-row=room2]") as HTMLElement));
    expect(document.querySelector("[data-no-sensor]")).toHaveTextContent("No sensor");
  });

  it("Alerts: the audit log shows a settings change with old and new values", () => {
    const qc = client(settings());
    qc.setQueryData(["audit"], { audit: [{ ts: NOW, action: "energy_settings", by: "warden1", ip: "10.0.0.5",
      changes: { tariff_rm_per_kwh: [0.2983, 0.35], "ac_kw_rooms.room1": [null, 3.5] } }], total: 1, limit: 50, offset: 0 });
    qc.setQueryData(["alerts", "en", 0], { alerts: [], total: 0, limit: 50, offset: 0 });
    qc.setQueryData(["incidents"], { incidents: [] });
    const { container } = wrap(qc, <AlertsPage />, "/alerts");
    const row = container.querySelector("[data-audit] tbody tr") as HTMLElement;
    expect(row).toHaveTextContent("Energy settings changed");
    expect(within(row).getAllByRole("listitem").map((li) => li.textContent)).toEqual([
      "Electricity tariff: RM 0.2983 per kWh → RM 0.35 per kWh", "Air conditioner power for Lab 2: building value → 3.5 kW"]);
    expect(T("alerts.audit_energy", undefined, "ms")).toBe("Tetapan tenaga diubah");
  });

  it("Alerts: a plan save that changed a room's capacity says from what to what", () => {
    const qc = client(settings());
    qc.setQueryData(["audit"], { audit: [{ ts: NOW, action: "plan_save", by: "warden1", ip: "10.0.0.5", floor: "f1", version: 4,
      capacity: [["room1", null, 30], ["room2", 120, null]] }], total: 1, limit: 50, offset: 0 });
    qc.setQueryData(["alerts", "en", 0], { alerts: [], total: 0, limit: 50, offset: 0 });
    qc.setQueryData(["incidents"], { incidents: [] });
    const { container } = wrap(qc, <AlertsPage />, "/alerts");
    const lines = [...container.querySelectorAll("[data-audit-capacity] li")].map((li) => li.textContent);
    expect(lines).toEqual(["Capacity of Lab 2: not set → 30", "Capacity of Hall A: 120 → not set"]);
    expect(T("alerts.audit_capacity", { room: "Lab 2", old: 20, new: 30 }, "ms")).toBe("Kapasiti Lab 2: 20 → 30");
  });
});
