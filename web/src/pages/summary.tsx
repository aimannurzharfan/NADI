// Today's summary: the detail behind the "Today's summary" card of the overview. The day's people chart, one row
// per room (peak, hours occupied, sensor uptime, air conditioning waste) and today's emergencies and drills with
// links to their reports. Built from the endpoints the console already has; it is not in the sidebar, the overview
// links here and the title row links back.
import { ArrowLeft } from "lucide-react";
import { Link } from "react-router-dom";

import { OccupancyChart } from "@/components/charts";
import { PageHeader, Panel } from "@/components/panel";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useEnergy, useHistory, useIncidents, useInfo, useRooms, useUptime } from "@/lib/api";
import { duration, hhmm, num, rm } from "@/lib/format";
import { T } from "@/lib/i18n";
import { midnightBefore, minutesToday, summaryRows, uptimeText } from "@/lib/overview";
import { BUILTIN_PLAN as PLAN } from "@/lib/plan";

export function SummaryPage() {
  const rooms = useRooms();
  const info = useInfo();
  const now = rooms.data?.now ?? Math.floor(Date.now() / 1000);
  const minutes = minutesToday(now);
  const history = useHistory(minutes);
  const uptime = useUptime();
  const energy = useEnergy();
  const incidents = useIncidents();

  const names = info.data?.room_names ?? {};
  const nameOf = (id: string) => rooms.data?.rooms.find((r) => r.room_id === id)?.name ?? names[id] ?? PLAN.rooms[id]?.name ?? id;
  const rows = summaryRows(history.data, uptime.data, energy.data, now);
  const series = history.data?.rooms ?? {};
  const today = (incidents.data?.incidents ?? []).filter((i) => i.started >= midnightBefore(now)).sort((a, b) => b.started - a.started);
  const active = incidents.data?.active;

  return (
    <>
      <PageHeader title={T("sum.title")} description={T("sum.description")} actions={
        <Link to="/" data-back className="inline-flex items-center gap-1.5 text-base font-medium text-foreground underline underline-offset-2 hover:text-heading">
          <ArrowLeft className="size-4" aria-hidden />{T("sum.back")}
        </Link>
      } />
      <Panel title={T("sum.people")} loading={history.isLoading} error={history.data ? undefined : history.error}
        empty={!Object.values(series).some((points) => points.length)} emptyText={T("ov.today_none")}>
        <OccupancyChart series={series} names={Object.fromEntries(Object.keys(series).map((id) => [id, nameOf(id)]))} height={260} />
      </Panel>
      <Panel title={T("sum.by_room")} bodyClassName="p-0" loading={history.isLoading && uptime.isLoading && energy.isLoading}
        empty={!rows.length} emptyText={T("sum.no_rooms")}>
        <Table data-summary-rooms>
          <TableHeader><TableRow>
            <TableHead>{T("sum.col_room")}</TableHead>
            <TableHead className="text-right">{T("sum.col_peak")}</TableHead>
            <TableHead className="text-right">{T("sum.col_hours")}</TableHead>
            <TableHead className="text-right">{T("sum.col_uptime")}</TableHead>
            <TableHead className="text-right">{T("sum.col_waste")}</TableHead>
          </TableRow></TableHeader>
          <TableBody>
            {rows.map((r) => (
              <TableRow key={r.id} data-room={r.id}>
                <TableCell className="font-medium">{nameOf(r.id)}</TableCell>
                <TableCell className="text-right tabular-nums">{num(r.peak)}</TableCell>
                <TableCell className="text-right tabular-nums">{r.hours == null ? "–" : T("ov.today_hours_value", { n: num(r.hours, 1) })}</TableCell>
                <TableCell className="text-right tabular-nums">{uptimeText(r.uptimePct)}</TableCell>
                <TableCell className="text-right tabular-nums">{rm(r.wasteRm)}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </Panel>
      <Panel title={T("sum.incidents")} bodyClassName="p-0" loading={incidents.isLoading} error={incidents.data ? undefined : incidents.error}>
        {active && (
          <p role="status" className="border-b px-4 py-2 text-base font-medium text-crit">
            {T(active.drill ? "bs.drill" : "bs.emergency_on")}{" · "}{T("report.started")} {hhmm(active.since)}
          </p>
        )}
        {!today.length ? <p className="px-4 py-3 text-base text-muted-foreground">{T("sum.incidents_none")}</p> : (
          <Table data-summary-incidents>
            <TableHeader><TableRow>
              <TableHead>{T("report.started")}</TableHead><TableHead>{T("alerts.col_type")}</TableHead>
              <TableHead>{T("report.duration")}</TableHead><TableHead className="w-32 text-right" />
            </TableRow></TableHeader>
            <TableBody>
              {today.map((i) => (
                <TableRow key={i.id}>
                  <TableCell className="tabular-nums">{hhmm(i.started)}</TableCell>
                  <TableCell>{T(i.kind === "drill" ? "alerts.type_drill" : "alerts.type_emergency")}</TableCell>
                  <TableCell className="tabular-nums">{duration(i.duration_s)}</TableCell>
                  <TableCell className="text-right">
                    <Link to={`/report/${i.id}`} className="font-medium underline underline-offset-2 hover:text-heading">{T("sum.open_report")}</Link>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </Panel>
    </>
  );
}
