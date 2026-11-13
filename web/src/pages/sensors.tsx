// Sensors: every board, like a network device list. Admin only (device IDs are broker usernames). The CSI sender has no
// network connection of its own, so its row is worked out from its receiver's packet count.
import { useQueryClient } from "@tanstack/react-query";
import { Network, Trash2, TriangleAlert } from "lucide-react";
import { useState } from "react";

import { AdminGate } from "@/components/admin";
import { PageHeader, Panel } from "@/components/panel";
import { StatusDot, StatusPill } from "@/components/status";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { postJSON, useBoardSetup, useDevices, useMe } from "@/lib/api";
import { ago, num, uptime } from "@/lib/format";
import { T } from "@/lib/i18n";
import type { Device } from "@/lib/types";
import { cn } from "@/lib/utils";

const MIN_PACKETS = 20;  // the receiver sends no report below this, so the room shows offline

type Row = Device & { kind: "receiver" | "sender" | "climate" | "simulator" | "counter"; inferred?: boolean };

function rowsFrom(devices: Device[]): Row[] {
  const rows: Row[] = [];
  for (const d of devices.sort((a, b) => (a.room_id ?? "").localeCompare(b.room_id ?? "") || a.device_id.localeCompare(b.device_id))) {
    if (d.simulator) {
      rows.push({ ...d, kind: "simulator", name: T("sensors.all_rooms") });  // one connection reporting for every room
    } else if (d.service === "csi") {
      rows.push({ ...d, kind: "receiver" });
      rows.push({ ...d, kind: "sender", inferred: true, device_id: T("sensors.sender_of", { id: d.device_id }),
        online: d.online && (d.n_packets ?? 0) >= MIN_PACKETS, wifi_rssi: null, uptime_s: null, fw_version: null,
        free_heap: null, dropped: null });
    } else if (d.service === "count") {
      rows.push({ ...d, kind: "counter" });
    } else {
      rows.push({ ...d, kind: "climate" });
    }
  }
  return rows;
}

function rssiTone(dbm: number | null) {
  return dbm == null ? "neutral" : dbm >= -67 ? "ok" : dbm >= -80 ? "warn" : "crit";
}

function DeviceTable() {
  const [retired, setRetired] = useState(false);
  const [confirm, setConfirm] = useState(false);
  const [note, setNote] = useState("");
  const devices = useDevices(true, retired);
  const qc = useQueryClient();
  const data = devices.data;
  const rows = rowsFrom([...(data?.devices ?? [])]);
  const offline = rows.filter((r) => !r.online).length;
  async function clear() {
    try {
      const out = await postJSON<{ cleared: number }>("/api/devices/clear");
      setNote(T(out.cleared === 1 ? "sensors.cleared_one" : "sensors.cleared", { n: out.cleared }));
      qc.invalidateQueries({ queryKey: ["devices"] });
    } catch (e) {
      setNote(e instanceof Error ? e.message : String(e));
    } finally {
      setConfirm(false);
    }
  }
  return (
    <Panel bodyClassName="p-0" loading={devices.isLoading} error={devices.error} empty={!!data && !rows.length}
      emptyText={T("sensors.none")}
      title={T(rows.length === 1 ? "sensors.count_one" : "sensors.count", { n: rows.length })}
      description={(offline ? T("sensors.offline_count", { n: offline }) : T("sensors.all_online")) + (note ? ` ${note}` : "")}
      actions={
        <div className="flex flex-wrap items-center gap-2">
          <label className="flex items-center gap-2 text-sm">
            <Switch checked={retired} onCheckedChange={setRetired} aria-label={T("sensors.show_retired", { n: data?.retired_hidden ?? 0 })} />
            {T("sensors.show_retired", { n: retired ? rows.filter((r) => r.retired && !r.inferred).length : data?.retired_hidden ?? 0 })}
          </label>
          {!confirm ? (
            <Button size="sm" variant="outline" className="h-8 text-xs" onClick={() => setConfirm(true)}>
              <Trash2 className="size-3.5" aria-hidden />{T("sensors.clear_test")}</Button>
          ) : (
            <span className="flex items-center gap-2 text-xs">
              <span className="max-w-xs">{T("sensors.clear_confirm")}</span>
              <Button size="sm" variant="outline" className="h-8 text-xs" onClick={() => setConfirm(false)}>{T("start.cancel")}</Button>
              <Button size="sm" className="h-8 text-xs" onClick={clear}>{T("sensors.clear_test")}</Button>
            </span>
          )}
        </div>
      }>
      {data && (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>{T("sensors.col_device")}</TableHead><TableHead>{T("rooms.col_room")}</TableHead>
              <TableHead>{T("sensors.col_type")}</TableHead><TableHead>{T("rooms.col_status")}</TableHead>
              <TableHead>{T("sensors.col_last")}</TableHead><TableHead className="text-right">{T("sensors.col_rssi")}</TableHead>
              <TableHead className="text-right">{T("sensors.col_packets", { s: data.report_interval_s })}</TableHead>
              <TableHead className="text-right">{T("sensors.col_uptime")}</TableHead><TableHead>{T("sensors.col_fw")}</TableHead>
              <TableHead className="text-right">{T("sensors.col_heap")}</TableHead><TableHead className="text-right">{T("sensors.col_dropped")}</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {rows.map((r) => (
              <TableRow key={r.kind + r.device_id} className={cn(!r.online && "bg-crit-soft/40 hover:bg-crit-soft/60")}>
                <TableCell className={cn("font-mono text-xs", r.inferred && "font-sans text-muted-foreground")}>
                  {r.device_id}
                  {r.simulator && <span className="ml-2 rounded-sm border px-1 font-sans text-2xs font-medium text-muted-foreground">{T("sensors.simulator")}</span>}
                  {r.retired && !r.inferred && <span className="ml-2 rounded-sm border px-1 font-sans text-2xs font-medium text-muted-foreground">{T("sensors.retired")}</span>}
                </TableCell>
                <TableCell>{r.name ?? "–"}</TableCell>
                <TableCell>{T(`sensors.type_${r.kind}`)}</TableCell>
                <TableCell><StatusPill tone={r.online ? "ok" : "crit"}>{T(r.online ? "sensors.online" : "sensors.offline")}</StatusPill></TableCell>
                <TableCell className="text-muted-foreground">{r.inferred ? T("sensors.via_receiver") : ago(r.last_seen ? data.now - r.last_seen : null)}</TableCell>
                <TableCell className="text-right">
                  {r.wifi_rssi == null ? "–" : <span className="inline-flex items-center gap-1.5"><StatusDot tone={rssiTone(r.wifi_rssi)} />{r.wifi_rssi} dBm</span>}
                </TableCell>
                <TableCell className="text-right">{r.kind === "receiver" ? num(r.n_packets) : "–"}</TableCell>
                <TableCell className="text-right">{uptime(r.uptime_s)}</TableCell>
                <TableCell className="font-mono text-xs">{r.fw_version ?? "–"}</TableCell>
                <TableCell className="text-right">{r.free_heap == null ? "–" : `${num(r.free_heap / 1024)} KB`}</TableCell>
                <TableCell className={cn("text-right", (r.dropped ?? 0) > 0 && "font-medium text-warn")}>{num(r.dropped)}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}
    </Panel>
  );
}

function BoardAddress() {
  const me = useMe();
  const setup = useBoardSetup(!!me.data?.admin);
  const s = setup.data;
  return (
    <Panel title={T("board.title")} description={T("sensors.board_hint")} loading={setup.isLoading} error={setup.error}>
      {s && (
        <div className="space-y-3 text-sm">
          <div className="flex flex-wrap items-start gap-x-8 gap-y-2">
            <div><p className="text-xs text-muted-foreground">{T("sensors.broker_address")}</p>
              <p className="flex items-center gap-2 font-mono text-lg font-semibold"><Network className="size-4 text-muted-foreground" aria-hidden />{s.ip ?? "–"}</p></div>
            <div><p className="text-xs text-muted-foreground">{T("sensors.broker_port")}</p><p className="font-mono text-lg font-semibold">{s.port ?? "–"}</p></div>
          </div>
          <p className="text-muted-foreground">{s.ip ? T("board.body", { ip: s.ip, port: s.port }) : T("board.unknown")}</p>
          {s.mismatch && (
            <p role="alert" className="flex gap-2 rounded-md bg-warn-soft px-3 py-2 text-warn">
              <TriangleAlert className="mt-0.5 size-4 shrink-0" aria-hidden />{T("board.mismatch", { configured: s.configured_ip ?? "", ip: s.ip ?? "" })}
            </p>
          )}
        </div>
      )}
    </Panel>
  );
}

export function SensorsPage() {
  return (
    <>
      <PageHeader title={T("nav.sensors")} description={T("sensors.description")} />
      <AdminGate what={T("sensors.what")}>
        <div className="flex flex-col gap-4">
          <DeviceTable />
          <BoardAddress />
        </div>
      </AdminGate>
    </>
  );
}
