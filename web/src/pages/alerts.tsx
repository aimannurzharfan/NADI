import { useQueryClient } from "@tanstack/react-query";
import { Check, Trash2 } from "lucide-react";
import { useEffect, useId, useState } from "react";
import { Link, useLocation } from "react-router-dom";

import { AdminGate } from "@/components/admin";
import { changeLines } from "@/components/energy-settings";
import { findFloor, useSite } from "@/lib/site";
import { EXPANDED, ShowMore, useShowMore } from "@/components/list-limit";
import { NeedsAttention } from "@/components/overview/attention";
import { PageHeader, Panel } from "@/components/panel";
import { StatusPill, type Tone } from "@/components/status";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { ALERTS_PAGE, postJSON, useAlerts, useAudit, useIncidents, useInfo, useMe, useRooms } from "@/lib/api";
import { ago, dateTime, duration, hhmmss } from "@/lib/format";
import { T } from "@/lib/i18n";
import { attentionItems } from "@/lib/overview";
import type { Alert, AlertKind, AuditEntry, IncidentSummary } from "@/lib/types";
import { cn } from "@/lib/utils";

const TONE: Record<Alert["severity"], Tone> = { critical: "crit", warning: "warn", info: "neutral" };
const KINDS: AlertKind[] = ["emergency", "drill", "sensor", "waste", "info"];
const ACTION: Record<AuditEntry["action"], string> = {
  start: "alerts.audit_start", end: "alerts.audit_end", room_clear: "alerts.audit_room_clear",
  room_help: "alerts.audit_room_help", room_reset: "alerts.audit_room_reset", delete_all: "alerts.audit_delete_all",
  energy_settings: "alerts.audit_energy", plan_save: "alerts.audit_plan_save", plan_restore: "alerts.audit_plan_restore",
  site_add: "alerts.audit_site_add", site_rename: "alerts.audit_site_rename", plan_image: "alerts.audit_plan_image",
};
const clean = (s: string) => s.replace(/^NADI:\s*/, "");

function AuditLog() {
  const audit = useAudit(true);
  const { site } = useSite();
  const floorName = (id: string) => {
    const found = findFloor(site, id);
    return found ? `${found.building.name}, ${found.floor.name}` : id;
  };
  const { data: info } = useInfo();
  const rows = audit.data?.audit ?? [];
  const list = useShowMore(rows);
  const id = useId();
  return (
    <Panel title={T("alerts.audit_title")} description={T("alerts.audit_hint")} bodyClassName="p-0"
      loading={audit.isLoading} error={audit.error} empty={!!audit.data && !rows.length} emptyText={T("alerts.audit_none")}>
      <div id={id} data-audit className={cn(list.expanded && EXPANDED)}>
      <Table>
        <TableHeader><TableRow>
          <TableHead>{T("alerts.col_time")}</TableHead><TableHead>{T("alerts.col_action")}</TableHead>
          <TableHead>{T("alerts.col_room")}</TableHead>
          <TableHead>{T("alerts.col_by")}</TableHead><TableHead>{T("alerts.col_ip")}</TableHead><TableHead>{T("alerts.col_duration")}</TableHead>
        </TableRow></TableHeader>
        <TableBody>
          {list.shown.map((e, i) => (
            <TableRow key={`${e.ts}-${i}`}>
              <TableCell>{dateTime(e.ts)}</TableCell>
              <TableCell>{T(ACTION[e.action] ?? "alerts.audit_start")}
                {e.drill && <span className="ml-2 rounded-sm border px-1 text-2xs font-medium text-muted-foreground">{T("alerts.audit_drill")}</span>}
                {e.floor && e.version != null && (
                  <span className="block text-muted-foreground" data-audit-floor>
                    {T("alerts.audit_plan_detail", { floor: floorName(e.floor), version: e.version })}
                  </span>
                )}
                {e.capacity && e.capacity.length > 0 && (
                  // a plan save that changed a room's capacity: from what to what
                  <ul className="mt-1 text-muted-foreground" data-audit-capacity>
                    {e.capacity.map(([room, before, after]) => (
                      <li key={room}>{T("alerts.audit_capacity", { room: info?.room_names[room] ?? room,
                        old: before ?? T("alerts.audit_capacity_none"), new: after ?? T("alerts.audit_capacity_none") })}</li>
                    ))}
                  </ul>
                )}
                {e.changes && (
                  <ul className="mt-1 text-muted-foreground" data-audit-changes>
                    {changeLines(e.changes, (id) => info?.room_names[id] ?? id).map((line) => <li key={line}>{line}</li>)}
                  </ul>
                )}</TableCell>
              <TableCell>{e.room ? info?.room_names[e.room] ?? e.room : "–"}</TableCell>
              <TableCell className="font-medium">{e.by}</TableCell>
              <TableCell className="font-mono text-xs">{e.ip}</TableCell>
              <TableCell className="text-muted-foreground">{e.started ? duration(e.ts - e.started) : "–"}</TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
      </div>
      <ShowMore hidden={list.hidden} expanded={list.expanded} onToggle={list.toggle} controls={id} />
    </Panel>
  );
}

export function AlertsPage() {
  const [page, setPage] = useState(0);
  const alerts = useAlerts(page);
  const pages = Math.max(1, Math.ceil((alerts.data?.total ?? 0) / ALERTS_PAGE));
  const me = useMe();
  const qc = useQueryClient();
  const [severity, setSeverity] = useState<"all" | Alert["severity"]>("all");
  const [kind, setKind] = useState<"all" | Alert["kind"]>("all");
  const [openOnly, setOpenOnly] = useState(false);
  const [error, setError] = useState("");
  const list = (alerts.data?.alerts ?? []).filter((a) =>
    (severity === "all" || a.severity === severity) && (kind === "all" || a.kind === kind) && (!openOnly || !a.ack));
  const now = Math.floor(Date.now() / 1000);
  // what needs attention right now, in full: the overview shows only the cards that fit and links here
  const rooms = useRooms();
  const lost = rooms.isError ? { since: rooms.dataUpdatedAt ? Math.floor(rooms.dataUpdatedAt / 1000) : null } : null;
  const attention = attentionItems(rooms.data, lost);
  const { hash } = useLocation();
  const ready = !!rooms.data || !!lost;
  useEffect(() => {
    if (hash === "#attention" && ready) document.getElementById("attention")?.scrollIntoView?.({ block: "start" });
  }, [hash, ready]);

  async function ack(id: string) {
    try {
      await postJSON(`/api/alerts/${encodeURIComponent(id)}/ack`);
      setError("");
      qc.invalidateQueries({ queryKey: ["alerts"] });
      qc.invalidateQueries({ queryKey: ["rooms"] });
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  return (
    <>
      <PageHeader title={T("nav.alerts")} description={T("alerts.description")} />
      {error && <p role="alert" className="text-sm text-crit">{error}</p>}
      <div id="attention" className="scroll-mt-4">
        <NeedsAttention all title={T("alerts.attention_now")} items={attention} admin={!!me.data?.admin} loading={!ready} />
      </div>
      <Panel bodyClassName="p-0" title={T(list.length === 1 ? "alerts.count_one" : "alerts.count", { n: list.length })} loading={alerts.isLoading} error={alerts.error}
        empty={!!alerts.data && !list.length} emptyText={T("alerts.none_filtered")}
        actions={
          <div className="flex flex-wrap items-center gap-2">
            <Select value={severity} onValueChange={(v) => setSeverity(v as typeof severity)}>
              <SelectTrigger className="h-8 w-36 text-sm" aria-label={T("alerts.col_severity")}><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="all">{T("alerts.all_severities")}</SelectItem>
                {(["critical", "warning", "info"] as const).map((s) => <SelectItem key={s} value={s}>{T(`alerts.sev_${s}`)}</SelectItem>)}
              </SelectContent>
            </Select>
            <Select value={kind} onValueChange={(v) => setKind(v as typeof kind)}>
              <SelectTrigger className="h-8 w-44 text-sm" aria-label={T("alerts.col_type")}><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="all">{T("alerts.all_types")}</SelectItem>
                {KINDS.map((k) => <SelectItem key={k} value={k}>{T(`alerts.type_${k}`)}</SelectItem>)}
              </SelectContent>
            </Select>
            <label className="flex items-center gap-2 text-sm">
              <Switch checked={openOnly} onCheckedChange={setOpenOnly} aria-label={T("alerts.open_only")} />{T("alerts.open_only")}
            </label>
          </div>
        }>
        <Table>
          <TableHeader><TableRow>
            <TableHead className="w-28">{T("alerts.col_severity")}</TableHead><TableHead className="w-48">{T("alerts.col_type")}</TableHead>
            <TableHead className="w-36">{T("alerts.col_time")}</TableHead><TableHead>{T("alerts.col_alert")}</TableHead>
            <TableHead className="w-52 text-right">{T("alerts.col_ack")}</TableHead>
          </TableRow></TableHeader>
          <TableBody>
            {list.map((a) => (
              <TableRow key={a.id}>
                <TableCell><StatusPill tone={TONE[a.severity]}>{T(`alerts.sev_${a.severity}`)}</StatusPill></TableCell>
                <TableCell>{T(`alerts.type_${a.kind}`)}</TableCell>
                <TableCell title={dateTime(a.ts)}><span className="tabular-nums">{hhmmss(a.ts)}</span>
                  <span className="block text-xs text-muted-foreground">{ago(now - a.ts)}</span></TableCell>
                <TableCell><p className="font-medium">{clean(a.subject)}</p><p className="text-xs text-muted-foreground">{a.message}</p></TableCell>
                <TableCell className="text-right">
                  {a.ack ? (
                    <span className="inline-flex items-center gap-1 text-xs text-muted-foreground"><Check className="size-3.5 text-ok" aria-hidden />
                      {T("alerts.acked_by", { who: a.ack.by, ago: ago(now - a.ack.ts) })}</span>
                  ) : me.data?.admin ? (
                    <Button size="sm" variant="outline" className="h-7 text-xs" onClick={() => ack(a.id)}>{T("alerts.ack")}</Button>
                  ) : <span className="text-xs text-muted-foreground">{T("alerts.not_acked")}</span>}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
        {pages > 1 && (
          <div className="flex items-center justify-end gap-2 border-t px-4 py-2 text-sm">
            <span className="text-muted-foreground">{T("alerts.page", { page: page + 1, pages })}</span>
            <Button size="sm" variant="outline" className="h-7 text-xs" disabled={page === 0} onClick={() => setPage(page - 1)}>{T("alerts.prev")}</Button>
            <Button size="sm" variant="outline" className="h-7 text-xs" disabled={page + 1 >= pages} onClick={() => setPage(page + 1)}>{T("alerts.next")}</Button>
          </div>
        )}
      </Panel>
      <IncidentReports />
      <AdminGate what={T("alerts.audit_what")}><AuditLog /></AdminGate>
      <AdminGate what={T("privacy.what")}><DeleteData /></AdminGate>
    </>
  );
}

function ReportTable({ rows: every }: { rows: IncidentSummary[] }) {
  const list = useShowMore(every);
  const id = useId();
  const rows = list.shown;
  if (!every.length) return <p className="px-4 py-3 text-sm text-muted-foreground">{T("incidents.none")}</p>;
  return (
    <>
    <div id={id} data-reports className={cn(list.expanded && EXPANDED)}>
    <Table>
      <TableHeader><TableRow>
        <TableHead>{T("report.started")}</TableHead><TableHead>{T("report.duration")}</TableHead>
        <TableHead className="text-right">{T("incidents.col_people")}</TableHead>
        <TableHead className="text-right">{T("incidents.col_marked")}</TableHead>
        <TableHead className="text-right">{T("incidents.col_offline")}</TableHead><TableHead>{T("alerts.col_by")}</TableHead>
        <TableHead className="w-24 text-right" />
      </TableRow></TableHeader>
      <TableBody>
        {rows.map((r) => (
          <TableRow key={r.id}>
            <TableCell className="tabular-nums">{dateTime(r.started)}
              {r.demo && <span className="ml-2 rounded-sm border px-1 text-2xs font-medium text-muted-foreground">{T("incidents.demo")}</span>}</TableCell>
            <TableCell className="tabular-nums">{duration(r.duration_s)}</TableCell>
            <TableCell className="text-right tabular-nums">{r.start_at_least ? `${T("count.at_least", { n: r.start_total })}` : r.start_total}</TableCell>
            <TableCell className="text-right tabular-nums">{r.marked}</TableCell>
            <TableCell className="text-right tabular-nums">{r.offline_rooms}</TableCell>
            <TableCell>{r.started_by}</TableCell>
            <TableCell className="text-right">
              <Button size="sm" variant="outline" className="h-7 text-xs" asChild><Link to={`/report/${r.id}`}>{T("incidents.open")}</Link></Button>
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
    </div>
    <ShowMore hidden={list.hidden} expanded={list.expanded} onToggle={list.toggle} controls={id} />
    </>
  );
}

/** Reports of past emergencies and drills, kept apart: a drill never shows among real incidents. */
function IncidentReports() {
  const q = useIncidents();
  const all = q.data?.incidents ?? [];
  const active = q.data?.active;
  return (
    <Panel title={T("incidents.title")} description={T("incidents.hint")} bodyClassName="p-0" loading={q.isLoading} error={q.error}>
      {active && <p role="status" className="border-b px-4 py-2 text-sm font-medium">{T(active.snapshots === 1 ? "incidents.active_one" : "incidents.active", { n: active.snapshots })}</p>}
      <h3 className="px-4 pt-3 text-sm font-semibold">{T("incidents.real")}</h3>
      <ReportTable rows={all.filter((r) => r.kind === "real")} />
      <h3 className="border-t px-4 pt-3 text-sm font-semibold">{T("incidents.drills")}</h3>
      <ReportTable rows={all.filter((r) => r.kind === "drill")} />
    </Panel>
  );
}

/** PDPA request: delete every stored record, after typing the phrase. */
function DeleteData() {
  const qc = useQueryClient();
  const phrase = T("privacy.phrase");
  const [typed, setTyped] = useState("");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  async function go() {
    setBusy(true);
    try {
      await postJSON("/api/data/delete", { confirm: typed.trim() });
      setTyped("");
      setNote(T("privacy.done"));
      qc.invalidateQueries();
    } catch (e) {
      setNote(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }
  return (
    <Panel title={T("privacy.title")} description={T("privacy.body")}>
      <form className="flex flex-wrap items-end gap-3" onSubmit={(e) => { e.preventDefault(); go(); }}>
        <label className="w-full space-y-1 text-sm sm:w-auto">
          <span className="block font-medium">{T("privacy.type", { phrase })}</span>
          <Input value={typed} onChange={(e) => setTyped(e.target.value)} className="w-full sm:w-64" autoComplete="off" spellCheck={false} />
        </label>
        <Button type="submit" variant="outline" className="border-crit/50 text-crit hover:bg-crit-soft hover:text-crit"
          disabled={busy || typed.trim() !== phrase}>
          <Trash2 className="size-4" aria-hidden />{T("privacy.go")}
        </Button>
        {note && <p role="status" className="text-sm">{note}</p>}
      </form>
    </Panel>
  );
}
