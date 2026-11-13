// The list rule (docs/design/DIRECTION.md, "Lists"): feeds draw whole rows only with "View all N" when rows are
// hidden; short lists draw ten rows and then "Show N more", scrolling inside the card once expanded.
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, renderHook, screen, act, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import { LIST_LIMIT, ShowMore, ViewAll, useShowMore, wholeRows } from "@/components/list-limit";
import { LiveActivity } from "@/components/overview/activity";
import { NeedsAttention } from "@/components/overview/attention";
import { TooltipProvider } from "@/components/ui/tooltip";
import { T } from "@/lib/i18n";
import type { AttentionItem } from "@/lib/overview";
import { AlertsPage } from "@/pages/alerts";
import { EnergyPage } from "@/pages/energy";
import type { Alert } from "@/lib/types";

const NOW = 1_793_660_400;
const alert = (i: number): Alert => ({ id: `a${i}`, ts: NOW - i * 60, kind: "info", severity: "info", via: "console",
  subject: `Subject ${i}`, message: `Message ${i}`, ack: null, drill: false });
const item = (i: number): AttentionItem => ({ id: `w${i}`, kind: "waste", title: `Room ${i}`, detail: "empty 14 min, A/C on", todo: "Switch it off." });

describe("the list rule", () => {
  it("shows ten of a short list, all of it once expanded, and no button when it fits", () => {
    const items = Array.from({ length: 13 }, (_, i) => i);
    const { result } = renderHook(() => useShowMore(items));
    expect(LIST_LIMIT).toBe(10);
    expect(result.current).toMatchObject({ shown: items.slice(0, 10), hidden: 3, expanded: false });
    act(() => result.current.toggle());
    expect(result.current).toMatchObject({ shown: items, hidden: 3, expanded: true });
    act(() => result.current.toggle());
    expect(result.current.shown).toHaveLength(10);
    const few = renderHook(() => useShowMore([1, 2, 3]));
    expect(few.result.current).toMatchObject({ shown: [1, 2, 3], hidden: 0, expanded: false });
    act(() => few.result.current.toggle());
    expect(few.result.current.expanded).toBe(false);  // nothing to expand
  });

  it("draws 'Show N more' as a button that says what it opens, and nothing when the list fits", () => {
    const onToggle = vi.fn();
    const { rerender, container } = render(<ShowMore hidden={3} expanded={false} onToggle={onToggle} controls="the-list" />);
    const button = screen.getByRole("button", { name: "Show 3 more" });
    expect(button).toHaveAttribute("aria-expanded", "false");
    expect(button).toHaveAttribute("aria-controls", "the-list");
    fireEvent.click(button);
    expect(onToggle).toHaveBeenCalledTimes(1);
    rerender(<ShowMore hidden={3} expanded onToggle={onToggle} controls="the-list" />);
    expect(screen.getByRole("button", { name: "Show fewer" })).toHaveAttribute("aria-expanded", "true");
    rerender(<ShowMore hidden={0} expanded={false} onToggle={onToggle} />);
    expect(container).toBeEmptyDOMElement();
    expect(T("list.show_more", { n: 3 }, "ms")).toBe("Papar 3 lagi");
  });

  it("draws 'View all N' as a link with its count and target", () => {
    render(<MemoryRouter><ViewAll to="/alerts" count={14} /></MemoryRouter>);
    const link = screen.getByRole("link", { name: "View all 14" });
    expect(link).toHaveAttribute("href", "/alerts");
    expect(link.querySelector("svg")).not.toBeNull();
    expect(T("list.view_all", { n: 14 }, "ms")).toBe("Lihat semua 14");
  });

  it("counts whole rows only: never more than ten, never more than fit, and one at least", () => {
    expect(wholeRows(13, null)).toBe(10);  // no layout to measure (tests): the limit
    expect(wholeRows(4, null)).toBe(4);
    expect(wholeRows(13, 6)).toBe(6);      // a shorter card shows fewer
    expect(wholeRows(13, 40)).toBe(10);
    expect(wholeRows(3, 6)).toBe(3);
    expect(wholeRows(5, 0)).toBe(1);       // a card too short for one row still shows one
    expect(wholeRows(0, 0)).toBe(0);
  });
});

describe("feeds on the overview", () => {
  const feed = (n: number) => render(<MemoryRouter><LiveActivity alerts={Array.from({ length: n }, (_, i) => alert(i))} now={NOW} still /></MemoryRouter>);

  it("shows ten whole rows of thirteen alerts, no scroll box, and 'View all 13' to the Alerts page", () => {
    const { container } = feed(13);
    const rows = [...container.querySelectorAll("[data-activity] > li")] as HTMLElement[];
    expect(rows.filter((r) => r.style.display !== "none")).toHaveLength(10);
    expect(container.innerHTML).not.toContain("overflow-y-auto");
    expect(container.innerHTML).not.toContain("overflow-auto");
    expect(screen.getByRole("link", { name: "View all 13" })).toHaveAttribute("href", "/alerts");
    expect(screen.queryByRole("link", { name: "All alerts" })).toBeNull();  // one link to Alerts at a time
  });

  it("keeps the 'All alerts' link in the title row while nothing is hidden", () => {
    feed(4);
    expect(screen.getByRole("link", { name: "All alerts" })).toHaveAttribute("href", "/alerts");
    expect(screen.queryByRole("link", { name: /View all/ })).toBeNull();
  });

  it("does not claim a total it does not know: at the server's cap of 20 the link reads 'All alerts'", () => {
    feed(20);
    expect(screen.getByRole("link", { name: "All alerts" })).toHaveAttribute("href", "/alerts");
    expect(screen.queryByText(/View all 20/)).toBeNull();
  });

  it("shows ten whole cards of thirteen things to deal with, and links to the full queue", () => {
    const items = Array.from({ length: 13 }, (_, i) => item(i));
    const qc = new QueryClient();
    const { container } = render(<QueryClientProvider client={qc}><MemoryRouter><NeedsAttention items={items} admin={false} /></MemoryRouter></QueryClientProvider>);
    const cards = [...container.querySelectorAll("[data-attention] > li")] as HTMLElement[];
    expect(cards.filter((c) => c.style.display !== "none")).toHaveLength(10);
    expect(screen.getByText("13 to deal with")).toBeInTheDocument();  // the count is of all of them
    expect(screen.getByRole("link", { name: "View all 13" })).toHaveAttribute("href", "/alerts#attention");
    expect(container.innerHTML).not.toContain("overflow-y-auto");
  });

  it("lists every item when it is the full queue", () => {
    const items = Array.from({ length: 13 }, (_, i) => item(i));
    const { container } = render(<QueryClientProvider client={new QueryClient()}><MemoryRouter>
      <NeedsAttention all title="Needs attention now" items={items} admin={false} /></MemoryRouter></QueryClientProvider>);
    expect(screen.getByRole("heading", { name: "Needs attention now" })).toBeInTheDocument();
    expect(container.querySelectorAll("[data-attention] > li")).toHaveLength(13);
    expect(screen.queryByRole("link", { name: /View all/ })).toBeNull();
  });
});

describe("lists on the other pages", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({ detail: "offline" }), { status: 503 })));
    vi.stubGlobal("ResizeObserver", class { observe() {} unobserve() {} disconnect() {} });
  });
  afterEach(() => vi.unstubAllGlobals());

  const client = () => {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false, staleTime: Infinity, refetchInterval: false } } });
    qc.setQueryData(["me"], { admin: true, who: "localhost", rule: "localhost", viewer: true, viewer_required: false });
    qc.setQueryData(["info", "en"], { building: "B", level: "L", room_names: {} });
    return qc;
  };
  const wrap = (qc: QueryClient, page: React.ReactNode, at = "/") =>
    render(<QueryClientProvider client={qc}><TooltipProvider><MemoryRouter initialEntries={[at]}>{page}</MemoryRouter></TooltipProvider></QueryClientProvider>);

  it("shows the ten rooms that wasted most this week, then 'Show 3 more'", () => {
    const qc = client();
    const amounts = { rm: 1, kwh: 3, co2_kg: 2 };
    const rooms = Array.from({ length: 13 }, (_, i) => ({ room_id: `r${i}`, name: `Room ${i + 1}`, rm_today: 0.1, rm_week: i + 1 }));
    qc.setQueryData(["energy", "7d", ""], { now: NOW, today: amounts, week: amounts, previous_week: amounts, yesterday: amounts, daily: [],
      tariff_rm_per_kwh: 0.2983, ac_kw: 10, co2_kg_per_kwh: 0.75, stale_ts: null, by_room: rooms,
      range: { id: "7d", days: 7, total: amounts, previous: amounts, first_ts: null, series: { unit: "day", points: [] },
        series_room: null,
        by_room: rooms.map((r) => ({ room_id: r.room_id, name: r.name, rm: r.rm_week, kwh: r.rm_week * 3, hours: r.rm_week / 3 })) } });
    const { container } = wrap(qc, <EnergyPage />);
    const box = container.querySelector("[data-by-room]") as HTMLElement;
    expect(box).toHaveAttribute("data-by-room", "10");
    const more = screen.getByRole("button", { name: "Show 3 more" });
    expect(more).toHaveAttribute("aria-controls", box.id);
    fireEvent.click(more);
    expect(box).toHaveAttribute("data-by-room", "13");
    expect(box.className).toContain("max-h-[26rem]");
    expect(screen.getByRole("button", { name: "Show fewer" })).toBeInTheDocument();
  });

  it("opens the Alerts page with everything that needs attention now, then ten audit entries and ten reports per table", () => {
    const qc = client();
    const waste = { since: NOW - 840, minutes: 14, rm: 0.7 };
    qc.setQueryData(["rooms", "en"], { now: NOW, stale_s: 30, waste_today_rm: 1, emergency: { on: false, since: null, drill: false, id: null },
      accountability: {}, alerts: [], offline: {}, stale_ts: null, demo: { on: false, t: null }, clock: null,
      rooms: Array.from({ length: 13 }, (_, i) => ({ room_id: `r${i}`, name: `Room ${i + 1}`, headcount: 0, at_least: false, counter: "csi",
        count_ts: NOW - 3, temp_c: 23, humidity: 60, live: true, waste })) });
    qc.setQueryData(["alerts", "en", 0], { alerts: [], total: 0 });
    qc.setQueryData(["audit"], { audit: Array.from({ length: 13 }, (_, i) => ({ ts: NOW - i * 60, action: "start", by: "warden", ip: "127.0.0.1", drill: true })) });
    const report = (i: number, kind: "real" | "drill") => ({ id: `${kind}${i}`, kind, started: NOW - i * 3600, ended: NOW - i * 3600 + 300, duration_s: 300,
      started_by: "warden", ended_by: "warden", start_total: 1, start_at_least: false, demo: false, marked: 0, offline_rooms: 0 });
    qc.setQueryData(["incidents"], { active: null, incidents: [...Array.from({ length: 13 }, (_, i) => report(i, "drill")), report(1, "real")] });
    const { container } = wrap(qc, <AlertsPage />, "/alerts#attention");
    const queue = container.querySelector("#attention") as HTMLElement;
    expect(within(queue).getByRole("heading", { name: "Needs attention now" })).toBeInTheDocument();
    expect(queue.querySelectorAll("[data-attention] > li")).toHaveLength(13);  // the full queue, the page scrolls
    expect(container.querySelectorAll("[data-audit] tbody tr")).toHaveLength(10);
    const tables = [...container.querySelectorAll("[data-reports]")];
    expect(tables.map((t) => t.querySelectorAll("tbody tr").length)).toEqual([1, 10]);  // real incidents, then drills
    expect(screen.getAllByRole("button", { name: "Show 3 more" })).toHaveLength(2);     // the audit log and the drills
    fireEvent.click(screen.getAllByRole("button", { name: "Show 3 more" })[0]);
    expect(tables[1].querySelectorAll("tbody tr")).toHaveLength(13);
    expect(tables[1].className).toContain("max-h-[26rem]");
  });
});
