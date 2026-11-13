import { ArrowDown, ArrowUp, ArrowUpDown, Search } from "lucide-react";
import { useMemo, useState } from "react";

import { PageHeader, Panel } from "@/components/panel";
import { ExampleNote } from "@/components/site-switcher";
import { RoomDrawer } from "@/components/room-drawer";
import { RoomStatusPill, SimCounter, StatusDot, StatusPill } from "@/components/status";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useEnergy, useInfo, useRooms } from "@/lib/api";
import { ago, countOf, rm, shown, statusOf, temp, type RoomStatus } from "@/lib/format";
import { T } from "@/lib/i18n";
import { planRoomRefs } from "@/lib/plan";
import { useFloorRooms, usePlan } from "@/lib/site";
import type { Room } from "@/lib/types";
import { cn } from "@/lib/utils";

const AC_ON_BELOW_C = 26;  // until the server's answer is in: colder than this = air conditioning assumed on

type Key = "name" | "status" | "people" | "temp" | "humidity" | "ac" | "waste" | "sensor" | "seen";
const ORDER: Record<RoomStatus, number> = { off: 0, waste: 1, ok: 2, empty: 3 };

export function RoomsPage() {
  const rooms = useRooms();
  const energy = useEnergy();
  const below = useInfo().data?.ac_on_below_c ?? AC_ON_BELOW_C;  // the energy setting in force, same rule as the server
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState<"all" | RoomStatus>("all");
  const [sort, setSort] = useState<{ key: Key; dir: 1 | -1 }>({ key: "status", dir: 1 });
  const [selected, setSelected] = useState<string | null>(null);
  const floorRooms = useFloorRooms(rooms.data?.rooms ?? []);
  const data = rooms.data && { ...rooms.data, rooms: floorRooms };  // the rooms of the floor on screen
  const wasteToday = Object.fromEntries((energy.data?.by_room ?? []).map((r) => [r.room_id, r.rm_today]));
  // rooms drawn on this floor's plan that have never reported: listed after the others, so the table and the plan
  // show the same rooms ("No sensor", or "No report yet" where a sensor pair is drawn)
  const plan = usePlan();
  const names = useInfo().data?.room_names ?? {};
  const reporting = new Set(floorRooms.map((r) => r.room_id));
  const silent = !data ? [] : planRoomRefs(plan).filter((p) => !reporting.has(p.id))
    .map((p) => ({ id: p.id, name: names[p.id] ?? plan.rooms[p.id].name ?? p.id, linked: p.linked }))
    .sort((a, b) => a.name.localeCompare(b.name, undefined, { numeric: true }));
  const silentRows = status !== "all" ? [] : silent.filter((p) => (p.name + p.id).toLowerCase().includes(query.toLowerCase()));

  const rows = useMemo(() => {
    const value = (r: Room): number | string => {
      switch (sort.key) {
        case "name": return r.name.toLowerCase();
        case "status": return ORDER[statusOf(r)];
        case "people": return r.live ? r.headcount ?? -1 : -1;
        case "temp": return r.temp_c ?? -99;
        case "humidity": return r.humidity ?? -1;
        case "ac": return r.temp_c != null && r.temp_c < below ? 1 : 0;
        case "waste": return wasteToday[r.room_id] ?? 0;
        case "sensor": return r.live ? 1 : 0;
        case "seen": return r.count_ts ?? 0;
      }
    };
    return (data?.rooms ?? [])
      .filter((r) => (status === "all" || statusOf(r) === status) && (r.name + r.room_id).toLowerCase().includes(query.toLowerCase()))
      .sort((a, b) => {
        const x = value(a), y = value(b);
        return (x < y ? -1 : x > y ? 1 : 0) * sort.dir || a.name.localeCompare(b.name);
      });
  }, [data, status, query, sort, wasteToday, below]);

  const head = (key: Key, label: string, right = false) => {
    const active = sort.key === key;
    const Icon = !active ? ArrowUpDown : sort.dir === 1 ? ArrowUp : ArrowDown;
    return (
      <TableHead className={cn(right && "text-right")} aria-sort={active ? (sort.dir === 1 ? "ascending" : "descending") : "none"}>
        <button type="button" className={cn("inline-flex items-center gap-1 hover:text-foreground", right && "flex-row-reverse")}
          onClick={() => setSort({ key, dir: active ? (sort.dir === 1 ? -1 : 1) : 1 })}>
          {label}<Icon className="size-3 opacity-60" aria-hidden />
        </button>
      </TableHead>
    );
  };

  const room = data?.rooms.find((r) => r.room_id === selected) ?? null;
  const noSensor = room ? null : silent.find((p) => p.id === selected) ?? null;
  return (
    <>
      <PageHeader title={T("nav.rooms")} description={T("rooms.description")} />
      <ExampleNote />
      <Panel bodyClassName="p-0" loading={rooms.isLoading} error={!data && rooms.error}
        empty={!!data && !data.rooms.length && !silent.length} emptyText={T("rooms.none")}
        title={T("rooms.count", { n: rows.length + silentRows.length, total: (data?.rooms.length ?? 0) + silent.length })}
        actions={
          <div className="flex items-center gap-2">
            <div className="relative">
              <Search className="pointer-events-none absolute left-2 top-2 size-4 text-muted-foreground" aria-hidden />
              <Input value={query} onChange={(e) => setQuery(e.target.value)} placeholder={T("rooms.search")}
                aria-label={T("rooms.search")} className="h-8 w-48 pl-7 text-sm" />
            </div>
            <Select value={status} onValueChange={(v) => setStatus(v as "all" | RoomStatus)}>
              <SelectTrigger className="h-8 w-40 text-sm" aria-label={T("rooms.filter_status")}><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="all">{T("rooms.all_statuses")}</SelectItem>
                {(["ok", "empty", "waste", "off"] as const).map((s) => <SelectItem key={s} value={s}>{T(`status.${s}`)}</SelectItem>)}
              </SelectContent>
            </Select>
          </div>
        }>
        {data && (
          <Table>
            <TableHeader>
              <TableRow>
                {head("name", T("rooms.col_room"))}{head("status", T("rooms.col_status"))}{head("people", T("rooms.col_people"), true)}
                {head("temp", T("detail.temperature"), true)}{head("humidity", T("detail.humidity"), true)}{head("ac", T("rooms.col_ac"))}
                {head("waste", T("rooms.col_waste"), true)}{head("sensor", T("rooms.col_sensor"))}{head("seen", T("rooms.col_seen"))}
              </TableRow>
            </TableHeader>
            <TableBody>
              {rows.map((r) => {
                const st = statusOf(r);
                const ac = r.temp_c == null ? null : r.temp_c < below;
                return (
                  <TableRow key={r.room_id} className={cn("cursor-pointer", st === "off" && "bg-off-soft/50")} tabIndex={0}
                    onClick={() => setSelected(r.room_id)} onKeyDown={(e) => e.key === "Enter" && setSelected(r.room_id)}>
                    <TableCell className="font-medium">{r.name}<span className="ml-2 text-xs text-muted-foreground">{r.room_id}</span>
                      <SimCounter room={r} className="ml-2" /></TableCell>
                    <TableCell><RoomStatusPill status={st} /></TableCell>
                    <TableCell className="text-right font-medium">{countOf(r)}
                      {!r.live && r.headcount != null && <span className="block text-xs font-normal text-muted-foreground">{T("count.last_short", { count: shown(r.headcount, r.at_least) })}</span>}
                    </TableCell>
                    <TableCell className="text-right">{temp(r.temp_c)}</TableCell>
                    <TableCell className="text-right">{r.humidity != null ? `${Math.round(r.humidity)}%` : "–"}</TableCell>
                    <TableCell className={cn(st === "waste" && "font-medium text-warn")}>{ac == null ? "–" : ac ? T("rooms.ac_on", { temp: below }) : T("rooms.ac_off")}</TableCell>
                    <TableCell className="text-right">{rm(wasteToday[r.room_id] ?? 0)}</TableCell>
                    <TableCell><span className="inline-flex items-center gap-1.5"><StatusDot tone={r.live ? "ok" : "off"} />{T(r.live ? "rooms.sensor_live" : "status.off")}</span></TableCell>
                    <TableCell className="text-muted-foreground">{ago(r.count_ts ? data.now - r.count_ts : null)}</TableCell>
                  </TableRow>
                );
              })}
              {silentRows.map((p) => (
                <TableRow key={p.id} data-no-sensor-row={p.id} className="cursor-pointer text-muted-foreground" tabIndex={0}
                  onClick={() => setSelected(p.id)} onKeyDown={(e) => e.key === "Enter" && setSelected(p.id)}>
                  <TableCell className="font-medium text-foreground">{p.name}<span className="ml-2 text-xs text-muted-foreground">{p.id}</span></TableCell>
                  <TableCell><StatusPill tone="off" dashed>{T(p.linked ? "plan.no_report" : "plan.no_sensor")}</StatusPill></TableCell>
                  <TableCell className="text-right">–</TableCell><TableCell className="text-right">–</TableCell><TableCell className="text-right">–</TableCell>
                  <TableCell>–</TableCell><TableCell className="text-right">–</TableCell><TableCell>–</TableCell><TableCell>–</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </Panel>
      <RoomDrawer room={room} noSensor={noSensor} now={data?.now ?? 0} onClose={() => setSelected(null)} />
    </>
  );
}
