// "Needs attention": a short queue of cards, each saying where, what and how bad, and what to do. A button appears
// only where the server already has an authenticated command for it (acknowledging an alert, admin only).
// On the overview only whole cards are drawn (ten at most), with "View all N" to the Alerts page when some are
// hidden; the Alerts page shows the same queue in full (`all`).
import { useQueryClient } from "@tanstack/react-query";
import { CircleCheck, CloudOff, ServerOff, Snowflake, TriangleAlert, WifiOff } from "lucide-react";
import { useRef, useState } from "react";

import { LIST_LIMIT, ViewAll, useWholeRows, wholeRows } from "@/components/list-limit";
import { Section } from "@/components/overview/section";
import { Button } from "@/components/ui/button";
import { postJSON } from "@/lib/api";
import { T } from "@/lib/i18n";
import type { AttentionItem, AttentionKind } from "@/lib/overview";
import { cn } from "@/lib/utils";

const AMBER = { card: "border-warn/50 border-l-warn bg-warn-soft/40", ink: "text-warn" };
const KIND: Record<AttentionKind, { icon: typeof Snowflake; tag: string; card: string; ink: string }> = {
  connection: { icon: CloudOff, tag: "ov.kind_connection", ...AMBER },
  service: { icon: ServerOff, tag: "ov.kind_service", ...AMBER },
  sensor: { icon: WifiOff, tag: "legend.off", card: "border-dashed border-off bg-off-soft/50", ink: "text-off" },
  waste: { icon: Snowflake, tag: "alerts.type_waste", ...AMBER },
  suspicious: { icon: TriangleAlert, tag: "alert.suspicious_subject", ...AMBER },
};

function Card({ item, admin, cut }: { item: AttentionItem; admin: boolean; cut?: boolean }) {
  const qc = useQueryClient();
  const [busy, setBusy] = useState(false);
  const [failed, setFailed] = useState(false);
  const { icon: Icon, tag, card, ink } = KIND[item.kind];
  async function acknowledge(alertId: string) {
    setBusy(true);
    try {
      await postJSON(`/api/alerts/${encodeURIComponent(alertId)}/ack`);
      setFailed(false);
      qc.invalidateQueries({ queryKey: ["rooms"] });
      qc.invalidateQueries({ queryKey: ["alerts"] });
    } catch {
      setFailed(true);
    } finally {
      setBusy(false);
    }
  }
  return (
    <li data-kind={item.kind} style={cut ? { display: "none" } : undefined} className={cn("flex gap-3 rounded-md border border-l-4 px-3 py-2.5", card)}>
      <Icon className={cn("mt-0.5 size-5 shrink-0", ink)} aria-hidden />
      <div className="min-w-0 flex-1">
        <p className="flex flex-wrap items-baseline gap-x-2">
          <span className="text-md font-semibold">{item.title}</span>
          {T(tag) !== item.title && <span className={cn("text-base font-medium", ink)}>{T(tag)}</span>}
        </p>
        <p className="text-base">{item.detail}</p>
        <p className="mt-1 text-base text-muted-foreground"><span className="font-semibold text-foreground">{T("ov.todo_label")}: </span>{item.todo}</p>
        {item.alertId && admin && (
          <div className="mt-2 flex flex-wrap items-center gap-2">
            <Button size="sm" variant="outline" className="h-8 bg-card text-base" disabled={busy} onClick={() => acknowledge(item.alertId!)}>
              {T("alerts.ack")}
            </Button>
            {failed && <span role="alert" className="text-base text-crit">{T("ov.ack_failed")}</span>}
          </div>
        )}
      </div>
    </li>
  );
}

export function NeedsAttention({ items, admin, loading, className, all, title }: {
  items: AttentionItem[]; admin: boolean; loading?: boolean; className?: string;
  /** the full queue (the Alerts page): every item, the page scrolls */
  all?: boolean;
  title?: string;
}) {
  const box = useRef<HTMLDivElement>(null), list = useRef<HTMLUListElement>(null);
  const fit = useWholeRows(box, list, all ? "all" : items.map((i) => i.id).join());
  const visible = all ? items.length : wholeRows(items.length, fit);
  const rows = all ? items : items.slice(0, LIST_LIMIT);
  return (
    <Section title={title ?? T("ov.attention_title")} className={className} bodyClassName={all ? "p-3" : "overflow-hidden p-3"} bodyRef={all ? undefined : box}
      aside={items.length > 0 && <span className="font-medium text-warn">{T("ov.attention_count", { n: items.length })}</span>}
      footer={items.length > visible && <ViewAll to="/alerts#attention" count={items.length} />}>
      {loading ? null : items.length ? (
        <ul ref={list} className="flex flex-col gap-2" data-attention>
          {rows.map((item, i) => <Card key={item.id} item={item} admin={admin} cut={i >= visible} />)}
        </ul>
      ) : (
        <div className="flex items-center gap-3 px-1 py-2">
          <CircleCheck className="size-7 shrink-0 text-ok" aria-hidden />
          <div>
            <p className="text-md font-semibold">{T("ov.attention_none")}</p>
            <p className="text-base text-muted-foreground">{T("ov.attention_none_hint")}</p>
          </div>
        </div>
      )}
    </Section>
  );
}
