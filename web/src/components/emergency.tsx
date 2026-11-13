// Emergency mode: a dark, high-contrast takeover on every screen while the alarm is on. Same rules as before: rooms
// with people first (offline rooms at their last known count, first on ties), the nearest exit by name, each room's
// place in that order on the plan (no route is drawn), a two-step end. "Export for emergency services" opens a printable one-page snapshot. A drill shows the same
// screens under a DRILL banner. Wardens (admin) mark each room "searched, clear" or "people still inside, need help".
import { useQueryClient } from "@tanstack/react-query";
import { CircleCheck, FileDown, LifeBuoy, Siren, Undo2 } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { OfflineBanner } from "@/components/banners";
import { FloorPlan } from "@/components/floor-plan";
import { SimCounter } from "@/components/status";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { ApiError, postJSON, useInfo, useMe, useRooms } from "@/lib/api";
import { ago, countOf, duration, hhmm, shown, totals, unknownText } from "@/lib/format";
import { T } from "@/lib/i18n";
import { useEmergencyPlan, useExitName } from "@/lib/site";
import type { Emergency, Mark, Room } from "@/lib/types";
import { cn } from "@/lib/utils";

/** Rooms in rescue order, and the rest. A room whose sensor is not reporting is unknown, never empty: it is ranked
 *  by its last known count (first on ties) and makes the total a minimum ("at least N"). */
export function rescueOrder(rooms: Room[]) {
  const t = totals(rooms);
  const ranked = rooms.filter((r) => !(r.live && r.headcount != null) || r.headcount > 0)
    .sort((a, b) => (b.headcount ?? 0) - (a.headcount ?? 0) || Number(a.live) - Number(b.live));
  const zero = t.live.filter((r) => r.headcount === 0);
  return { ranked, zero, total: t.people, plus: t.atLeast, unknown: t.unknown, occupied: t.occupied, all: rooms };
}

async function setEmergency(on: boolean, drill = false) {
  return postJSON<Emergency>("/api/emergency", { on, drill });
}

const errorText = (e: unknown) =>
  e instanceof ApiError && (e.status === 401 || e.status === 403) ? T("admin.needed_short") : e instanceof Error ? e.message : String(e);

/** "Searched, clear (warden1, 07:52)", or "Not marked". */
export function MarkText({ mark }: { mark?: Mark | null }) {
  if (!mark) return <>{T("acc.none")}</>;
  return <>{T("acc.by", { status: T(mark.status === "clear" ? "acc.clear" : "acc.help"), who: mark.by, time: hhmm(mark.ts) })}</>;
}

export function StartEmergencyDialog({ open, onOpenChange }: { open: boolean; onOpenChange: (v: boolean) => void }) {
  const qc = useQueryClient();
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  async function go(drill: boolean) {
    setBusy(true);
    try {
      await setEmergency(true, drill);
      setError("");
      onOpenChange(false);
      qc.invalidateQueries({ queryKey: ["rooms"] });
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  }
  return (
    <Dialog open={open} onOpenChange={(v) => { setError(""); onOpenChange(v); }}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2"><Siren className="size-5 text-crit" aria-hidden />{T("start.title")}</DialogTitle>
          <DialogDescription>{T("start.body")}</DialogDescription>
        </DialogHeader>
        <p className="text-sm text-muted-foreground">{T("start.drill_hint")}</p>
        {error && <p role="alert" className="text-sm text-crit">{error}</p>}
        <DialogFooter className="gap-2 sm:gap-0">
          <Button variant="outline" onClick={() => onOpenChange(false)}>{T("start.cancel")}</Button>
          <Button variant="outline" onClick={() => go(true)} disabled={busy}>{T("drill.start")}</Button>
          <Button className="bg-[#B8352A] text-white hover:bg-[#B8352A]/90" onClick={() => go(false)} disabled={busy}>{T("start.go")}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function useTicker() {
  const [now, setNow] = useState(() => Math.floor(Date.now() / 1000));
  useEffect(() => {
    const id = setInterval(() => setNow(Math.floor(Date.now() / 1000)), 1000);
    return () => clearInterval(id);
  }, []);
  return now;
}

/** The warden's mark on a room, and (for admins) the buttons to set or remove it. */
function RoomMark({ room, mark, admin, onError }: { room: Room; mark?: Mark; admin: boolean; onError: (s: string) => void }) {
  const qc = useQueryClient();
  const [busy, setBusy] = useState(false);
  async function set(status: Mark["status"] | null) {
    setBusy(true);
    try {
      await postJSON(`/api/emergency/rooms/${encodeURIComponent(room.room_id)}`, { status });
      onError("");
      qc.invalidateQueries({ queryKey: ["rooms"] });
    } catch (e) {
      onError(errorText(e));
    } finally {
      setBusy(false);
    }
  }
  const label = (s: string) => `${room.name}: ${s}`;
  return (
    <div className="mt-1 flex flex-wrap items-center gap-1.5">
      {mark && (
        <span className={cn("inline-flex items-center gap-1 rounded-sm px-1.5 py-0.5 text-xs font-semibold",
          // fixed colours: readable (white on green 6.5:1, on red 5.8:1) on both the dark takeover and light pages
          mark.status === "clear" ? "bg-[#1E6B45] text-white" : "bg-[#B8352A] text-white")}>
          {mark.status === "clear" ? <CircleCheck className="size-3.5" aria-hidden /> : <LifeBuoy className="size-3.5" aria-hidden />}
          <MarkText mark={mark} />
        </span>
      )}
      {admin && mark?.status !== "clear" && (
        <Button size="sm" variant="outline" className="h-7 border-border bg-transparent px-2 text-xs" disabled={busy}
          aria-label={label(T("acc.clear"))} onClick={() => set("clear")}>
          <CircleCheck className="size-3.5" aria-hidden />{T("acc.clear_short")}
        </Button>
      )}
      {admin && mark?.status !== "help" && (
        <Button size="sm" variant="outline" className="h-7 border-crit/60 bg-transparent px-2 text-xs text-crit" disabled={busy}
          aria-label={label(T("acc.help"))} onClick={() => set("help")}>
          <LifeBuoy className="size-3.5" aria-hidden />{T("acc.help_short")}
        </Button>
      )}
      {admin && mark && (
        <Button size="sm" variant="ghost" className="h-7 px-2 text-xs" disabled={busy} aria-label={label(T("acc.undo"))}
          onClick={() => set(null)}>
          <Undo2 className="size-3.5" aria-hidden />{T("acc.undo")}
        </Button>
      )}
    </div>
  );
}

export function EmergencyTakeover() {
  const { data } = useRooms();
  const exitFor = useExitName();
  const plan = useEmergencyPlan(data?.rooms ?? []);  // a floor with reporting rooms, never the example building
  const { data: info } = useInfo();
  const me = useMe();
  const qc = useQueryClient();
  const tick = useTicker();
  const [confirm, setConfirm] = useState(false);
  const [error, setError] = useState("");
  const timer = useRef<ReturnType<typeof setTimeout>>();
  const panel = useRef<HTMLDivElement>(null);

  const on = !!data?.emergency.on;
  useEffect(() => {
    if (on) panel.current?.focus();
    else setConfirm(false);
  }, [on]);
  if (!data || !on) return null;

  const drill = !!data.emergency.drill;
  const admin = !!me.data?.admin;
  const marks = data.accountability ?? {};
  const now = tick + (data.now - Math.floor(Date.now() / 1000));
  const { ranked, zero, total, plus, unknown, occupied, all } = rescueOrder(data.rooms);

  function askEnd() {
    setConfirm(true);
    clearTimeout(timer.current);
    timer.current = setTimeout(() => setConfirm(false), 10000);
  }
  async function end() {
    try {
      await setEmergency(false);
      setConfirm(false);
      qc.invalidateQueries({ queryKey: ["rooms"] });
      qc.invalidateQueries({ queryKey: ["incidents"] });
    } catch (e) {
      setError(errorText(e));
    }
  }

  const item = (r: Room, rank: string) => (
    <li key={r.room_id} className={cn("flex items-center gap-4 border-b border-border py-3 last:border-0",
      r.live && !r.headcount && !marks[r.room_id] && "opacity-60")}>
      <span className={cn("w-7 text-center text-xl font-bold", !r.live || r.headcount ? "text-crit" : "text-muted-foreground")}>{rank}</span>
      <div className="min-w-0 flex-1">
        <p className="truncate text-lg font-semibold">{r.name}</p>
        {exitFor(r.room_id) && <p data-nearest-exit className="text-base font-medium">{T("detail.nearest_exit_is", { exit: exitFor(r.room_id)! })}</p>}
        <p className={cn("text-sm", r.live ? "text-muted-foreground" : "font-medium text-warn")}>
          {r.live ? T("em.live", { ago: ago(r.count_ts ? now - r.count_ts : null) })
            : r.headcount != null && r.count_ts ? T("count.last_known", { count: shown(r.headcount, r.at_least), ago: ago(now - r.count_ts) })
            : T("count.unknown")}
        </p>
        <SimCounter room={r} className="mt-1" />
        <RoomMark room={r} mark={marks[r.room_id]} admin={admin} onError={setError} />
      </div>
      <span className={cn("text-3xl font-bold tabular-nums", !r.live && "text-warn")}>{countOf(r)}</span>
    </li>
  );

  return (
    <div ref={panel} tabIndex={-1} role="alertdialog" aria-modal="true" aria-label={T(drill ? "drill.flag" : "em.label")}
      className="em-theme fixed inset-0 z-50 flex flex-col overflow-auto bg-background text-foreground outline-none">
      {drill ? (
        <p role="status" data-drill-banner className="shrink-0 bg-[#F2C744] px-6 py-2 text-center text-base font-bold tracking-wide text-[#1A1400]">
          {T("drill.banner")}
        </p>
      ) : <div className="h-1.5 shrink-0 bg-crit" />}
      <header className="flex flex-wrap items-center gap-x-8 gap-y-2 border-b px-6 py-3">
        <p className={cn("flex items-center gap-2 text-xl font-bold", drill ? "text-[#F2C744]" : "text-crit")}>
          <Siren className="size-6" aria-hidden />{T(drill ? "drill.flag" : "em.flag")}
        </p>
        <p className="text-2xl font-bold tabular-nums">{duration(now - (data.emergency.since ?? now))}
          <span className="ml-2 text-sm font-normal text-muted-foreground">{T(drill ? "drill.since" : "em.since")}</span></p>
        <p className="text-sm text-muted-foreground">{info ? `${info.building}, ${info.level}` : ""}</p>
        {data.demo.on && <span className="rounded-sm bg-[#D9C9F7] px-2 py-0.5 text-sm font-semibold text-[#2A1A4F]">{T("ui.demo")}</span>}
        <div className="ml-auto flex flex-wrap items-center gap-2">
          <Button variant="outline" className="border-border bg-transparent" onClick={() => window.open("/export", "_blank", "noopener")}>
            <FileDown className="size-4" aria-hidden />{T("em.export")}
          </Button>
          {!confirm ? (
            <Button variant="outline" className="border-border bg-transparent" onClick={askEnd}>{T(drill ? "drill.end" : "em.end")}</Button>
          ) : (
            <div className="flex items-center gap-2">
              <span className="text-sm font-medium">{T("em.confirm_question")}</span>
              <Button variant="outline" className="border-border bg-transparent" onClick={() => setConfirm(false)}>{T(drill ? "drill.keep" : "em.keep")}</Button>
              <Button className="bg-foreground text-background hover:bg-foreground/90" onClick={end} autoFocus>
                {T(drill ? "drill.confirm_end" : "em.confirm_end")}
              </Button>
            </div>
          )}
        </div>
      </header>
      <OfflineBanner />
      {error && <p role="alert" className="px-6 pt-3 text-sm text-crit">{error}</p>}
      <div className="grid min-h-0 flex-1 gap-4 p-4 lg:grid-cols-[minmax(320px,460px)_1fr] lg:p-6">
        <div className="flex min-h-0 flex-col gap-4">
          <section className="rounded-lg border bg-card px-5 py-4" aria-live="polite">
            {plus && <p className="text-lg font-semibold">{T("count.at_least_label")}</p>}
            <p className="text-5xl font-bold tabular-nums">{total}</p>
            <p className="mt-1 text-lg font-semibold">{T(total === 1 ? "em.still_inside_one" : "em.still_inside")}</p>
            <p className="text-sm text-muted-foreground">
              {T("em.in_rooms", { n: occupied, room_word: T(occupied === 1 ? "unit.room" : "unit.rooms") })}
              {unknown.length ? "" : T("em.all_live")}
            </p>
            {unknown.length > 0 && (
              <p className="mt-1 text-sm font-semibold text-warn">{unknownText(unknown.length)}: {unknown.map((r) => r.name).join(", ")}</p>
            )}
          </section>
          <section className="flex min-h-0 flex-1 flex-col rounded-lg border bg-card px-5 py-3">
            <h2 className="text-lg font-bold text-crit">{T("em.go_first")}</h2>
            {admin && <p className="pb-1 text-xs text-muted-foreground">{T("acc.hint")}</p>}
            <ol className="overflow-y-auto">
              {ranked.map((r, i) => item(r, String(i + 1)))}
              {zero.map((r) => item(r, "–"))}
              {!all.length && <li className="py-3 text-muted-foreground">{T("em.no_data")}</li>}
            </ol>
          </section>
          <p className="rounded-lg border border-warn/40 px-4 py-2 text-sm font-medium" role="note">{T("safety.disclaimer")}</p>
        </div>
        <section className="flex items-center rounded-lg border bg-card p-4">
          <FloorPlan rooms={data.rooms} now={now} emergency ranked={ranked} plan={plan} />
        </section>
      </div>
    </div>
  );
}
