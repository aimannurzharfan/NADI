// Ask NADI's scope chip (docs/design/PLAN.md, Part 24): the floor chosen in the switcher or the whole building,
// sent with each question; locked to the whole building, and saying why, during an emergency or drill.
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import { ChatPanel } from "@/components/chat-panel";
import { T } from "@/lib/i18n";
import { SiteProvider, type Site } from "@/lib/site";

const SITE: Site = { default_floor: "f1", editor: true, buildings: [{ id: "b1", name: "Demo Building", code: "", example: false,
  floors: [{ id: "f1", name: "Level 4", level: 4, rooms: 3, version: 0 }, { id: "f2", name: "Level 5", level: 5, rooms: 8, version: 1 }] }] };

function show(emergency = { on: false, since: null as number | null, drill: false, id: null as string | null }, at = "/?floor=f2") {
  const send = vi.fn(async (_url: string, init?: RequestInit) => new Response(JSON.stringify({ answer: "Level 5: 2 people inside, in 1 room.",
    source: "fallback", model: "built-in answers", scope: { kind: "floor", floor_id: "f2", label: "Level 5", locked: false, reason: null }, init }), { status: 200 }));
  vi.stubGlobal("fetch", send);
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false, staleTime: Infinity, refetchInterval: false } } });
  qc.setQueryData(["site"], SITE);
  qc.setQueryData(["info", "en"], { building: "Demo Building", level: "Level 4", room_names: {}, chat_source: "rules" });
  qc.setQueryData(["rooms", "en"], { now: 1, stale_s: 30, rooms: [], waste_today_rm: 0, emergency, accountability: {}, alerts: [], offline: {}, stale_ts: null });
  render(<QueryClientProvider client={qc}><MemoryRouter initialEntries={[at]}><SiteProvider>
    <ChatPanel open onOpenChange={() => {}} /></SiteProvider></MemoryRouter></QueryClientProvider>);
  return send;
}
const sent = (send: ReturnType<typeof vi.fn>) => send.mock.calls.filter(([url]) => String(url).includes("/api/chat")).map(([, init]) => JSON.parse((init as RequestInit).body as string));

afterEach(() => vi.unstubAllGlobals());

describe("the chat scope chip", () => {
  it("follows the floor chosen in the switcher and sends it; the whole building sends none", async () => {
    const send = show();
    const scope = screen.getByRole("radiogroup", { name: "Answers for" });
    const floor = screen.getByRole("radio", { name: "This floor: Level 5" });
    expect(floor).toHaveAttribute("aria-checked", "true");
    expect(scope).toBeInTheDocument();
    fireEvent.change(screen.getByRole("textbox", { name: /question/i }), { target: { value: "How many people are inside?" } });
    fireEvent.click(screen.getByRole("button", { name: T("chat.ask") }));
    await waitFor(() => expect(screen.getByText("Level 5: 2 people inside, in 1 room.")).toBeInTheDocument());
    expect(sent(send)[0]).toMatchObject({ question: "How many people are inside?", floor: "f2" });
    fireEvent.click(screen.getByRole("radio", { name: "Whole building" }));
    expect(screen.getByRole("radio", { name: "Whole building" })).toHaveAttribute("aria-checked", "true");
    fireEvent.change(screen.getByRole("textbox", { name: /question/i }), { target: { value: "Which rooms are empty?" } });
    fireEvent.click(screen.getByRole("button", { name: T("chat.ask") }));
    await waitFor(() => expect(sent(send)).toHaveLength(2));
    expect(sent(send)[1].floor).toBeNull();
    expect(T("scope.this_floor", { floor: "Level 5" }, "ms")).toBe("Tingkat ini: Level 5");
  });

  it("is locked to the whole building during an emergency or a drill, and says why", async () => {
    for (const [drill, reason] of [[false, "Emergency mode is on: answers cover the whole building."], [true, "A drill is on: answers cover the whole building."]] as const) {
      const send = show({ on: true, since: 1, drill, id: "x" });
      expect(screen.queryByRole("radiogroup")).toBeNull();
      expect(document.querySelector("[data-chat-scope]")).toHaveAttribute("data-chat-scope", "locked");
      expect(screen.getByText(reason)).toBeInTheDocument();
      fireEvent.change(screen.getByRole("textbox", { name: /question/i }), { target: { value: "How many people are inside?" } });
      fireEvent.click(screen.getByRole("button", { name: T("chat.ask") }));
      await waitFor(() => expect(sent(send)).toHaveLength(1));
      expect(sent(send)[0].floor).toBeNull();
      cleanup();  // the next case renders its own panel
    }
  });
});
