// Energy: what air conditioning left on in empty rooms cost in the chosen period. One chart of the waste over time
// (the building's, or one room's), then the rooms ranked by what they wasted. A row is a button: it puts that room
// in the chart, and a chip with a remove button says so (kept in the address as ?room=).
import { X } from "lucide-react";
import { useEffect, useId, useState } from "react";
import { useSearchParams } from "react-router-dom";

import { WasteOverTimeChart, fromFirstDay } from "@/components/charts";
import { EnergySettingsCard } from "@/components/energy-settings";
import { EXPANDED, ShowMore, useShowMore } from "@/components/list-limit";
import { Kpi, KpiStrip } from "@/components/kpi";
import { PageHeader, Panel } from "@/components/panel";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { ApiError, useEnergy, useInfo, useMe, useRooms } from "@/lib/api";
import {
  ENERGY_RANGES, changeText, pickEnergyRange, storeEnergyRange, storedEnergyRange, type EnergyRange,
} from "@/lib/energy-range";
import { dateOnly, dayMonth, num, rm } from "@/lib/format";
import { T } from "@/lib/i18n";
import { cn } from "@/lib/utils";

/** Today, 7 days or 30 days: the figures at the top, the chart and the room list follow it. */
function EnergyRangeToggle({ value, onChange }: { value: EnergyRange; onChange: (r: EnergyRange) => void }) {
  return (
    <ToggleGroup type="single" value={value} onValueChange={(v) => v && onChange(v as EnergyRange)} variant="outline" size="sm"
      aria-label={T("energy.range")} data-energy-range>
      {ENERGY_RANGES.map((r) => (
        <ToggleGroupItem key={r} value={r} className="h-8 whitespace-nowrap px-3 text-base data-[state=on]:bg-primary-soft data-[state=on]:text-primary">
          {T(`energy.range_${r}`)}
        </ToggleGroupItem>
      ))}
    </ToggleGroup>
  );
}

export function EnergyPage() {
  const [params, setParams] = useSearchParams();
  const [stored, setStored] = useState(storedEnergyRange);
  const range = pickEnergyRange(params.get("range"), stored);
  const setRange = (r: EnergyRange) => {
    setStored(r);
    storeEnergyRange(r);
    setParams((before) => {
      const next = new URLSearchParams(before);
      next.set("range", r);
      return next;
    }, { replace: true });
  };
  // the room the chart is filtered to (the figures at the top stay the building's)
  const room = params.get("room") ?? "";
  const setRoom = (id: string) => setParams((before) => {
    const next = new URLSearchParams(before);
    if (id) next.set("room", id); else next.delete("room");
    return next;
  }, { replace: true });
  const energy = useEnergy(range, room);
  // a room the server does not know (an old link): back to the whole building
  const unknownRoom = !!room && energy.error instanceof ApiError && energy.error.status === 422;
  useEffect(() => { if (unknownRoom) setRoom(""); });
  const e = energy.data;
  // the figures of the period on screen: while another period loads, the last one stays (placeholder)
  const p = e?.range.id === range ? e.range : undefined;
  const loading = energy.isLoading || (!!e && !p);
  // the chart is this period's and this room's (or the building's), not the answer before it
  const chart = p && (p.series_room ?? "") === room ? fromFirstDay(p.series) : undefined;
  const { data: info } = useInfo();
  const admin = !!useMe().data?.admin;
  const saves = e?.rate_changes ?? [];
  const changed = saves[saves.length - 1];  // the latest save inside the period the figures cover
  // the rooms that wasted most in the period first: ten rows, then "Show N more"
  // a room drawn on the plan that has never reported has nothing to rank: it goes last, with "No sensor" and dashes
  const live = useRooms().data?.rooms;
  const silent = (r: { room_id: string; rm: number }) => !!live && r.rm === 0 && !live.some((l) => l.room_id === r.room_id);
  const ranked = [...(p?.by_room ?? [])].sort((a, b) =>
    Number(silent(a)) - Number(silent(b)) || b.rm - a.rm || a.name.localeCompare(b.name, undefined, { numeric: true }));
  const byRoom = useShowMore(ranked);
  const byRoomId = useId();
  const most = Math.max(0, ...ranked.map((r) => r.rm));
  const roomName = ranked.find((r) => r.room_id === room)?.name ?? info?.room_names?.[room] ?? room;
  const delta = p ? (p.previous ? p.total.rm - p.previous.rm : null) : undefined;
  return (
    <>
      <PageHeader title={T("nav.energy")} description={T("energy.description")}
        actions={<EnergyRangeToggle value={range} onChange={setRange} />} />
      <KpiStrip cols={3}>
        <Kpi label={T(`energy.k_rm_${range}`)} loading={loading} value={rm(p?.total.rm)} delta={delta} better="down"
          deltaText={p && delta != null ? changeText(delta, range, (k) => T(k)) : undefined} />
        <Kpi label={T(`energy.k_kwh_${range}`)} loading={loading} value={num(p?.total.kwh, 1)} unit={T("unit.kwh")}
          hint={e ? T("energy.tariff", { rate: e.tariff_rm_per_kwh.toFixed(4) }) : undefined} />
        <Kpi label={T(`energy.k_co2_${range}`)} loading={loading} value={num(p?.total.co2_kg, 1)} unit="kg"
          hint={e ? T("energy.co2_factor", { f: num(e.co2_kg_per_kwh, 2) }) : undefined} />
      </KpiStrip>
      {changed && (
        <p data-rate-changed className="rounded-lg border bg-card px-4 py-2 text-base text-muted-foreground">
          {T("es.rate_changed", { date: dateOnly(changed.ts) })}
        </p>
      )}
      <Panel title={T(`energy.over_${range}`)} loading={loading || (!!p && !chart && !energy.error)} error={unknownRoom ? undefined : energy.error}
        actions={(
          <div className="flex shrink-0 items-center gap-3 text-base">
            {chart?.dataFrom && (
              <span data-data-from className="hidden whitespace-nowrap text-muted-foreground sm:inline">
                {T("chart.data_from", { date: dayMonth(Date.parse(`${chart.dataFrom}T12:00:00+08:00`) / 1000) })}</span>
            )}
            {room && (
              <span data-room-chip className="inline-flex h-8 items-center gap-1 rounded-md border bg-primary-soft pl-2.5 pr-1 font-medium text-primary">
                <span className="max-w-48 truncate" title={roomName}>{roomName}</span>
                <button type="button" onClick={() => setRoom("")} aria-label={T("energy.filter_remove")} title={T("energy.filter_remove")}
                  className="inline-flex size-6 items-center justify-center rounded hover:bg-accent focus-visible:outline focus-visible:outline-2 focus-visible:outline-ring">
                  <X className="size-4" aria-hidden />
                </button>
              </span>
            )}
          </div>
        )}>
        {chart && (
          <div data-waste-over={chart.series.unit} data-points={chart.series.points.length} data-waste-room={room || undefined}>
            <WasteOverTimeChart series={chart.series} />
          </div>
        )}
      </Panel>
      <Panel title={T(`energy.by_room_${range}`)} loading={loading} error={unknownRoom ? undefined : energy.error} bodyClassName="p-0"
        empty={!!p && !ranked.length} emptyText={T(`energy.none_${range}`)}>
        <div id={byRoomId} data-by-room={byRoom.shown.length} className={cn(byRoom.expanded && EXPANDED)}>
          <table className="w-full text-base">
            <thead className="text-left text-muted-foreground">
              <tr className="border-b">
                <th scope="col" className="px-4 py-2 font-medium">{T("energy.col_room")}</th>
                {/* the bar repeats the "Wasted" figure as a length: decoration, so it has no heading and is not read out */}
                <td aria-hidden className="hidden w-2/5 px-4 py-2 md:table-cell" />
                <th scope="col" className="px-4 py-2 text-right font-medium">{T("energy.col_rm")}</th>
                <th scope="col" className="px-4 py-2 text-right font-medium">{T("energy.col_kwh")}</th>
                <th scope="col" className="px-4 py-2 text-right font-medium">{T("energy.col_hours")}</th>
              </tr>
            </thead>
            <tbody>
              {byRoom.shown.map((r) => {
                const on = r.room_id === room;
                if (silent(r) && !on) {
                  return (
                    <tr key={r.room_id} data-room={r.room_id} data-no-sensor-row className="border-b text-muted-foreground last:border-0">
                      <th scope="row" className="px-4 py-2 text-left font-medium">
                        <span className="mr-3">{r.name}</span><span className="font-normal">{T("plan.no_sensor")}</span>
                      </th>
                      <td className="hidden md:table-cell" aria-hidden />
                      <td className="px-4 py-2 text-right">–</td><td className="px-4 py-2 text-right">–</td><td className="px-4 py-2 text-right">–</td>
                    </tr>
                  );
                }
                return (
                  <tr key={r.room_id} data-room={r.room_id} onClick={() => setRoom(on ? "" : r.room_id)}
                    className={cn("cursor-pointer border-b last:border-0 hover:bg-accent/60", on && "bg-primary-soft hover:bg-primary-soft")}>
                    <th scope="row" className="px-4 py-2 text-left font-medium">
                      {/* the row's button: the click on the row is a convenience for the pointer */}
                      <button type="button" aria-pressed={on} title={T("energy.filter_room", { room: r.name })}
                        onClick={(ev) => { ev.stopPropagation(); setRoom(on ? "" : r.room_id); }}
                        className="max-w-full truncate rounded text-left underline-offset-2 hover:underline focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring">
                        {r.name}</button>
                    </th>
                    <td className="hidden px-4 py-2 md:table-cell" aria-hidden>
                      <span className="block h-1.5 rounded-full bg-muted">
                        <span data-room-bar className="block h-1.5 rounded-full bg-brand" style={{ width: `${most > 0 ? Math.max(r.rm > 0 ? 2 : 0, (r.rm / most) * 100) : 0}%` }} />
                      </span>
                    </td>
                    <td className="whitespace-nowrap px-4 py-2 text-right tabular-nums">{rm(r.rm)}</td>
                    <td className="whitespace-nowrap px-4 py-2 text-right tabular-nums">{num(r.kwh, 1)}</td>
                    <td className="whitespace-nowrap px-4 py-2 text-right tabular-nums">{num(r.hours, 1)}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
        <ShowMore hidden={byRoom.hidden} expanded={byRoom.expanded} onToggle={byRoom.toggle} controls={byRoomId} />
      </Panel>
      <EnergySettingsCard admin={admin} rooms={info?.room_names ?? {}} />
    </>
  );
}
