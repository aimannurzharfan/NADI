import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";

import { EmergencyTakeover, MarkText } from "@/components/emergency";
import { dayLabel, fullDateTime, hhmm, hhmmss } from "@/lib/format";
import type { RoomsState } from "@/lib/types";

describe("Malaysia time", () => {
  it("shows times in Asia/Kuala_Lumpur whatever the browser's own zone", () => {
    const ts = 1_793_660_400; // 2026-11-02 23:00 UTC = 3 Nov 07:00 in Kuala Lumpur
    expect(hhmm(ts)).toBe("07:00");
    expect(hhmmss(ts)).toBe("07:00:00");
    expect(fullDateTime(ts)).toContain("3 Nov 2026");
    expect(dayLabel("2026-11-03")).toContain("3");
  });
});

describe("warden marks", () => {
  it("says who marked a room and when", () => {
    render(<MarkText mark={{ status: "help", by: "warden1", ts: 1_793_660_400 }} />);
    expect(screen.getByText("People still inside, need help (warden1, 07:00)")).toBeInTheDocument();
  });
  it("says when a room is not marked yet", () => {
    render(<MarkText mark={null} />);
    expect(screen.getByText("Not marked")).toBeInTheDocument();
  });
});

function withData(rooms: RoomsState) {
  const qc = new QueryClient();
  qc.setQueryData(["rooms", "en"], rooms);
  qc.setQueryData(["me"], { admin: false, who: null, rule: "token", viewer: true, viewer_required: false });
  return render(<QueryClientProvider client={qc}><EmergencyTakeover /></QueryClientProvider>);
}

const state = (drill: boolean): RoomsState => ({
  now: 1_793_660_400, stale_s: 60, waste_today_rm: 0, alerts: [], offline: {}, stale_ts: null,
  demo: { on: false, t: null }, clock: null,
  emergency: { on: true, since: 1_793_660_300, drill, id: "20261102-230000-drill-abcd" },
  accountability: { room1: { status: "clear", by: "warden1", ts: 1_793_660_350 } },
  rooms: [{ room_id: "room1", name: "Lab 2", headcount: 2, at_least: false, count_ts: 1_793_660_390, temp_c: 24,
    humidity: 60, live: true, waste: null }],
});

describe("emergency takeover", () => {
  it("puts a DRILL banner on a drill and says drill, not emergency", () => {
    withData(state(true));
    expect(screen.getByText("DRILL: this is a practice run, not a real emergency.")).toBeInTheDocument();
    expect(screen.getByRole("alertdialog", { name: "Drill" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "End drill" })).toBeInTheDocument();
    expect(screen.getByText(/Searched, clear \(warden1, 06:59\)/)).toBeInTheDocument();
  });
  it("has no DRILL banner in a real emergency, and no mark buttons for non-admins", () => {
    withData(state(false));
    expect(screen.queryByText(/DRILL:/)).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "End emergency mode" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /need help/ })).not.toBeInTheDocument();
  });
});
