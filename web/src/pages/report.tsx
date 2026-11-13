// Incident or drill report, written by the server when emergency mode or a drill ends: start and end, people inside
// at the start, how long each room took to reach zero, the wardens' marks, sensors offline, alerts and who
// acknowledged them. Printable, like the export page.
import { ArrowLeft, FileText, Printer } from "lucide-react";
import { Link, useParams } from "react-router-dom";

import { MarkText } from "@/components/emergency";
import { Button } from "@/components/ui/button";
import { openSnapshot, useReport } from "@/lib/api";
import { duration, fullDateTime, hhmmss, shown } from "@/lib/format";
import { T } from "@/lib/i18n";
import type { ReportRoom } from "@/lib/types";

const count = (n: number | null, atLeast: boolean, live: boolean) => (!live || n == null ? "?" : shown(n, atLeast));

function zeroText(r: ReportRoom) {
  if (r.empty_at_start) return T("report.empty_start");
  return r.to_zero_s == null ? T("report.not_zero") : duration(r.to_zero_s);
}

export function ReportPage() {
  const { id = "" } = useParams();
  const report = useReport(id);
  const r = report.data;
  if (report.isLoading) return <p className="p-8 text-muted-foreground">{T("common.loading")}</p>;
  if (!r) return (
    <div className="p-8">
      <p role="alert" className="text-crit">{T("report.not_found")}</p>
      <Link to="/alerts" className="mt-3 inline-flex items-center gap-1 text-sm underline"><ArrowLeft className="size-4" aria-hidden />{T("report.back")}</Link>
    </div>
  );
  const drill = r.kind === "drill";
  const th = "py-1.5 pr-2 text-left";
  const td = "py-1.5 pr-2 align-top";
  return (
    <div className="mx-auto max-w-[860px] bg-white p-4 text-[#111] sm:p-8 print:p-0">
      <div className="no-print mb-6 flex flex-wrap items-center justify-between gap-2">
        <Link to="/alerts" className="inline-flex items-center gap-1 text-sm underline"><ArrowLeft className="size-4" aria-hidden />{T("report.back")}</Link>
        <div className="flex flex-wrap gap-2">
          {r.snapshots.length > 0 && (
            <Button variant="outline" onClick={() => openSnapshot(r.id).catch(() => undefined)}>
              <FileText className="size-4" aria-hidden />{T("report.open_snapshot")}
            </Button>
          )}
          <Button onClick={() => window.print()}><Printer className="size-4" aria-hidden />{T("print.print")}</Button>
        </div>
      </div>
      {drill && <p className="mb-3 bg-[#111] px-3 py-1.5 text-sm font-bold tracking-wide text-white">{T("drill.banner")}</p>}
      <header className="border-b-2 border-[#111] pb-3">
        <p className="text-sm font-semibold">{T(drill ? "report.title_drill" : "report.title_real")}{r.demo ? ` (${T("incidents.demo")})` : ""}</p>
        <h1 className="text-2xl font-bold">{r.building}, {r.level}</h1>
        <p className="text-xs">{T("report.record", { id: r.id })}, {T("time.zone")}</p>
      </header>
      <dl className="mt-4 grid grid-cols-2 gap-x-6 gap-y-2 text-sm sm:grid-cols-4">
        <div><dt className="font-semibold">{T("report.started")}</dt><dd>{fullDateTime(r.started)}<br />{T("report.by", { who: r.started_by })}</dd></div>
        <div><dt className="font-semibold">{T("report.ended")}</dt><dd>{fullDateTime(r.ended)}<br />{T("report.by", { who: r.ended_by })}</dd></div>
        <div><dt className="font-semibold">{T("report.duration")}</dt><dd className="text-lg font-bold">{duration(r.duration_s)}</dd></div>
        <div><dt className="font-semibold">{T("report.people_start")}</dt>
          <dd className="text-lg font-bold">{r.start_at_least ? `${T("count.at_least_label")} ` : ""}{r.start_total}</dd></div>
      </dl>
      {r.start_unknown.length > 0 && <p className="mt-2 text-sm font-semibold">{T("report.unknown_start", { rooms: r.start_unknown.join(", ") })}</p>}

      <h2 className="mt-6 text-lg font-bold">{T("report.rooms_title")}</h2>
      <div className="overflow-x-auto"><table className="mt-1 w-full border-collapse text-sm">
        <thead><tr className="border-b border-[#111]">
          <th className={th}>{T("rooms.col_room")}</th><th className={th}>{T("report.col_start")}</th>
          <th className={th}>{T("report.col_zero")}</th><th className={th}>{T("acc.col")}</th><th className={th}>{T("report.col_end")}</th>
        </tr></thead>
        <tbody>
          {r.rooms.map((x) => (
            <tr key={x.room_id} className="border-b border-[#ccc]">
              <td className={`${td} font-semibold`}>{x.name}</td>
              <td className={td}>{count(x.start_count, x.start_at_least, x.start_live)}</td>
              <td className={td}>{zeroText(x)}</td>
              <td className={td}><MarkText mark={x.status} /></td>
              <td className={td}>{count(x.end_count, !!x.end_at_least, x.end_live)}</td>
            </tr>
          ))}
        </tbody>
      </table></div>

      <h2 className="mt-6 text-lg font-bold">{T("report.offline_title")}</h2>
      {r.offline.length === 0 ? <p className="text-sm">{T("report.offline_none")}</p> : (
        <ul className="mt-1 list-disc pl-5 text-sm">
          {r.offline.map((o) => (
            <li key={o.room_id}><span className="font-semibold">{o.name}</span>:{" "}
              {o.periods.map(([a, b]) => T("report.period", { start: hhmmss(a), end: b ? hhmmss(b) : T("report.until_end") })).join("; ")}</li>
          ))}
        </ul>
      )}

      <h2 className="mt-6 text-lg font-bold">{T("report.alerts_title")}</h2>
      {r.alerts.length === 0 ? <p className="text-sm">{T("report.alerts_none")}</p> : (
        <div className="overflow-x-auto"><table className="mt-1 w-full border-collapse text-sm">
          <thead><tr className="border-b border-[#111]">
            <th className={th}>{T("alerts.col_time")}</th><th className={th}>{T("alerts.col_alert")}</th><th className={th}>{T("alerts.col_ack")}</th>
          </tr></thead>
          <tbody>
            {r.alerts.map((a) => (
              <tr key={a.id} className="border-b border-[#ccc]">
                <td className={`${td} tabular-nums`}>{hhmmss(a.ts)}</td>
                <td className={td}><p className="font-semibold">{a.subject}</p><p className="text-xs">{a.message}</p></td>
                <td className={td}>{a.ack ? `${a.ack.by}, ${hhmmss(a.ack.ts)}` : T("alerts.not_acked")}</td>
              </tr>
            ))}
          </tbody>
        </table></div>
      )}
      {r.snapshots.length > 0 && (
        <p className="mt-4 text-xs">{T(r.snapshots.length === 1 ? "report.snapshots_one" : "report.snapshots",
          { n: r.snapshots.length, time: hhmmss(r.snapshots[r.snapshots.length - 1]) })}</p>
      )}
      <p className="mt-2 text-xs">{T("safety.disclaimer")}</p>
    </div>
  );
}
