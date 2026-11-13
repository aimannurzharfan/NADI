// /design: the console's design system on one page, for review and screenshots. Not linked from the navigation.
import { Kpi, KpiStrip } from "@/components/kpi";
import { EmptyState, ErrorState, PageHeader, Panel, PanelSkeleton } from "@/components/panel";
import { StatusDot, StatusPill } from "@/components/status";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { T } from "@/lib/i18n";
import { PlanLegend } from "@/components/floor-plan";

const SWATCHES: [string, string][] = [
  ["background", "bg-background"], ["card", "bg-card"], ["muted", "bg-muted"], ["border", "bg-border"],
  ["foreground", "bg-foreground"], ["muted-foreground", "bg-muted-foreground"], ["primary", "bg-primary"], ["primary-soft", "bg-primary-soft"],
];
const STATUS: [string, string, string][] = [
  ["ok", "bg-ok", "bg-ok-soft"], ["warn", "bg-warn", "bg-warn-soft"], ["crit", "bg-crit", "bg-crit-soft"], ["off", "bg-off", "bg-off-soft"],
];

export function DesignPage() {
  return (
    <>
      <PageHeader title={T("design.title")} description={T("design.description")} />
      <div className="grid gap-4 xl:grid-cols-2">
        <Panel title={T("design.colour")}>
          <div className="grid grid-cols-4 gap-3">
            {SWATCHES.map(([name, cls]) => (
              <div key={name}><div className={`h-12 rounded-md border ${cls}`} /><p className="mt-1 text-xs text-muted-foreground">{name}</p></div>
            ))}
          </div>
          <div className="mt-4 grid grid-cols-4 gap-3">
            {STATUS.map(([name, strong, soft]) => (
              <div key={name}><div className="flex h-12 overflow-hidden rounded-md border"><div className={`flex-1 ${strong}`} /><div className={`flex-1 ${soft}`} /></div>
                <p className="mt-1 text-xs text-muted-foreground">{name}</p></div>
            ))}
          </div>
        </Panel>
        <Panel title={T("design.type")}>
          <div className="space-y-2">
            <p className="text-2xl font-semibold tracking-tight">24 / 32 semibold: page figures</p>
            <p className="text-xl font-semibold tracking-tight">20 / 28 semibold: page titles</p>
            <p className="text-md font-semibold">15 / 22 semibold: drawer titles</p>
            <p className="text-sm">13 / 20 regular: body, tables, controls (tabular numbers 0123456789)</p>
            <p className="text-xs text-muted-foreground">12 / 16 regular: labels, hints, axis</p>
          </div>
        </Panel>
      </div>
      <Panel title={T("design.controls")}>
        <div className="flex flex-wrap items-center gap-2">
          <Button>Primary</Button><Button variant="outline">Outline</Button><Button variant="secondary">Secondary</Button>
          <Button variant="ghost">Ghost</Button><Button variant="outline" className="border-crit/40 text-crit">Critical action</Button>
          <Input className="h-9 w-56" placeholder="Input" />
          <StatusPill tone="ok">OK</StatusPill><StatusPill tone="warn">Warning</StatusPill>
          <StatusPill tone="crit">Critical</StatusPill><StatusPill tone="off">Offline</StatusPill><StatusPill tone="neutral">Neutral</StatusPill>
          <span className="inline-flex items-center gap-1.5 text-sm"><StatusDot tone="ok" />Dot</span>
        </div>
        <div className="mt-3"><PlanLegend /></div>
      </Panel>
      <KpiStrip>
        <Kpi label="Figure with change" value="4.2" delta={1.1} deltaText="+1.1 vs previous hour" better="up" />
        <Kpi label="Lower is better" value="RM 3.40" delta={0.8} deltaText="+RM 0.80 vs yesterday" better="down" tone="warn" />
        <Kpi label="No previous data" value="12" delta={null} />
        <Kpi label="Loading" value="" loading />
      </KpiStrip>
      <div className="grid gap-4 md:grid-cols-3">
        <Panel title={T("design.loading")}><PanelSkeleton /></Panel>
        <Panel title={T("design.empty")}><EmptyState>{T("rooms.none")}</EmptyState></Panel>
        <Panel title={T("design.error")}><ErrorState error={new Error("HTTP 503: the history database (MySQL) is offline")} /></Panel>
      </div>
      <Panel title={T("design.banner")} bodyClassName="p-0">
        <div className="border-b border-warn/30 bg-warn-soft px-4 py-2 text-sm text-warn">{T("banner.redis", { time: "10:03" })}</div>
        <div className="flex gap-2 bg-[#F1ECFA] px-4 py-1.5 text-sm text-[#4A2F80] dark:bg-[#2A2140] dark:text-[#D9C9F7]">
          <strong>{T("ui.demo")}</strong><span>{T("ui.demo_hint", { t: "1:40" })}</span>
        </div>
      </Panel>
      <Panel title={T("design.table")} bodyClassName="p-0">
        <Table>
          <TableHeader><TableRow><TableHead>Room</TableHead><TableHead>Status</TableHead><TableHead className="text-right">People</TableHead></TableRow></TableHeader>
          <TableBody>
            <TableRow><TableCell className="font-medium">Lab 2</TableCell><TableCell><StatusPill tone="warn">A/C on, empty</StatusPill></TableCell><TableCell className="text-right">0</TableCell></TableRow>
            <TableRow><TableCell className="font-medium">Hall A</TableCell><TableCell><StatusPill tone="ok">Occupied</StatusPill></TableCell><TableCell className="text-right">3+</TableCell></TableRow>
            <TableRow className="bg-crit-soft/40"><TableCell className="font-medium">Room 3</TableCell><TableCell><StatusPill tone="off">Offline</StatusPill></TableCell><TableCell className="text-right">–</TableCell></TableRow>
          </TableBody>
        </Table>
      </Panel>
    </>
  );
}
