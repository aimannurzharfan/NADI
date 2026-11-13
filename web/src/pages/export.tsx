// Export for emergency services: a one-page snapshot to print or save as PDF. Who is where, when, the nearest stairs,
// what wardens have checked, and the number to call. The server also saves this snapshot by itself every minute.
import { Printer } from "lucide-react";
import { useEffect, useState } from "react";

import { MarkText, rescueOrder } from "@/components/emergency";
import { FloorPlan } from "@/components/floor-plan";
import { Button } from "@/components/ui/button";
import { getJSON, useIncidents, useInfo } from "@/lib/api";
import { countOf, duration, fullDateTime, hhmm, hhmmss, shown, unknownText } from "@/lib/format";
import { T } from "@/lib/i18n";
import { useEmergencyPlan, useExitName } from "@/lib/site";
import type { RoomsState } from "@/lib/types";

export function ExportPage() {
  const { data: info } = useInfo();
  const { data: incidents } = useIncidents();
  const [snap, setSnap] = useState<RoomsState | null>(null);
  const [error, setError] = useState("");
  const exitFor = useExitName();
  const plan = useEmergencyPlan(snap?.rooms ?? []);
  useEffect(() => {
    getJSON<RoomsState>("/api/rooms").then(setSnap).catch((e) => setError(e instanceof Error ? e.message : String(e)));
  }, []);
  if (error) return <p role="alert" className="p-8 text-crit">{T("common.load_failed")}: {error}</p>;
  if (!snap) return <p className="p-8 text-muted-foreground">{T("common.loading")}</p>;
  const { ranked, zero, total, plus, unknown } = rescueOrder(snap.rooms);
  const since = snap.emergency.since;
  const marks = snap.accountability ?? {};
  const active = incidents?.active;
  return (
    <div className="mx-auto max-w-[800px] bg-white p-4 text-[#111] sm:p-8 print:p-0">
      <div className="no-print mb-6 flex justify-end">
        <Button onClick={() => window.print()}><Printer className="size-4" aria-hidden />{T("print.print")}</Button>
      </div>
      {snap.emergency.drill && <p className="mb-3 bg-[#111] px-3 py-1.5 text-sm font-bold tracking-wide text-white">{T("drill.banner")}</p>}
      <header className="border-b-2 border-[#111] pb-3">
        <p className="text-sm font-semibold">{T("print.title")}</p>
        <h1 className="text-2xl font-bold">{info ? `${info.building}, ${info.level}` : ""}</h1>
        <p className="mt-1 text-sm">
          {T("print.taken", { time: `${fullDateTime(snap.now)} (${T("time.zone")})` })}
          {since ? ` ${T("print.alarm", { time: hhmmss(since), duration: duration(snap.now - since) })}` : ` ${T("print.no_alarm")}`}
        </p>
        {snap.demo.on && (
          <p className="mt-1 text-sm font-semibold">
            {T("ui.demo")}: {snap.demo.t != null ? T("ui.demo_hint", { t: duration(snap.demo.t) }) : T("ui.demo_pause")}
          </p>
        )}
      </header>
      <p className="mt-3 border-2 border-[#111] px-3 py-1.5 text-lg font-bold">
        {T("print.call", { number: info?.emergency_number || T("print.number_default") })}
      </p>
      <section className="mt-4 flex items-baseline gap-3">
        <p className="text-4xl font-bold">{plus && <span className="mr-2 text-lg font-semibold">{T("count.at_least_label")}</span>}{total}</p>
        <p className="text-lg font-semibold">{T(total === 1 ? "em.still_inside_one" : "em.still_inside")}</p>
        <p className="text-sm">{unknown.length ? `${unknownText(unknown.length)}: ${unknown.map((r) => r.name).join(", ")}` : T("print.all_live")}</p>
      </section>
      <p className="mt-2 border border-[#111] px-2 py-1 text-sm font-semibold">{T("safety.disclaimer")}</p>
      <div className="mt-4 overflow-x-auto"><table className="w-full border-collapse text-sm">
        <thead>
          <tr className="border-b border-[#111] text-left">
            <th className="py-1.5 pr-2">#</th><th className="py-1.5 pr-2">{T("rooms.col_room")}</th>
            <th className="py-1.5 pr-2 text-right">{T("rooms.col_people")}</th><th className="py-1.5 pr-2">{T("detail.nearest_exit")}</th>
            <th className="py-1.5 pr-2">{T("print.count_source")}</th><th className="py-1.5">{T("acc.col")}</th>
          </tr>
        </thead>
        <tbody>
          {[...ranked, ...zero].map((r, i) => (
            <tr key={r.room_id} className="border-b border-[#ccc]">
              <td className="py-1.5 pr-2 font-semibold">{!r.live || r.headcount ? i + 1 : "–"}</td>
              <td className="py-1.5 pr-2 font-semibold">{r.name}</td>
              <td className="py-1.5 pr-2 text-right text-base font-bold">{countOf(r)}</td>
              <td className="py-1.5 pr-2">{exitFor(r.room_id) ?? "–"}</td>
              <td className="py-1.5 pr-2">{r.live ? T("print.live") : r.headcount != null && r.count_ts
                ? T("count.last_known", { count: shown(r.headcount, r.at_least), ago: T("time.seconds", { n: snap.now - r.count_ts }) })
                : T("count.unknown")}
                {r.counter === "count" && <span className="block text-xs">{T("room.sim_counter")}</span>}</td>
              <td className="py-1.5"><MarkText mark={marks[r.room_id]} /></td>
            </tr>
          ))}
        </tbody>
      </table></div>
      <div className="mt-5 border border-[#999] p-2"><FloorPlan rooms={snap.rooms} now={snap.now} emergency ranked={ranked} plan={plan} /></div>
      <p className="mt-3 text-xs">{T("print.footer")}</p>
      {active && active.last_snapshot && (
        <p className="mt-1 text-xs">{T("print.autosaved", { n: active.snapshots, time: hhmm(active.last_snapshot) })}</p>
      )}
    </div>
  );
}
