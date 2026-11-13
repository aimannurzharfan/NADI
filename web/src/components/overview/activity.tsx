// "Live activity": the latest alerts and events with their times. A row that was not there a moment ago slides in
// once; nothing else moves. Whole rows only, ten at most and fewer when the card is shorter, never a scroll box: when
// rows are hidden, "View all N" at the foot opens the Alerts page (components/list-limit).
import { ClipboardCheck, Info, RadioTower, Siren, Snowflake } from "lucide-react";
import { useRef } from "react";
import { ArrowRight } from "lucide-react";
import { Link } from "react-router-dom";

import { LIST_LIMIT, ViewAll, useWholeRows, wholeRows } from "@/components/list-limit";
import { Section } from "@/components/overview/section";
import { ago, dateTime, hhmmss } from "@/lib/format";
import { T } from "@/lib/i18n";
import { cleanSubject } from "@/lib/overview";
import type { Alert, AlertKind } from "@/lib/types";
import { cn } from "@/lib/utils";

const ICON: Record<AlertKind, typeof Info> = { emergency: Siren, waste: Snowflake, info: Info, sensor: RadioTower, drill: ClipboardCheck };
const SLIDE_MS = 600;
/** The server sends the overview its latest 20 alerts: at that many, how many there are in all is not known here. */
const FEED_CAP = 20;

/** Which rows arrived after the list was first shown, and within the last moment: only those slide in. */
function useFresh(ids: string[]): Set<string> {
  const seen = useRef<Map<string, number> | null>(null);
  const t = typeof performance !== "undefined" ? performance.now() : 0;
  if (seen.current === null) seen.current = new Map(ids.map((id) => [id, -Infinity]));
  const known = seen.current;
  for (const id of ids) if (!known.has(id)) known.set(id, t);
  for (const id of [...known.keys()]) if (!ids.includes(id)) known.delete(id);  // follows the capped list: never grows
  return new Set(ids.filter((id) => t - (known.get(id) ?? -Infinity) < SLIDE_MS));
}

export function LiveActivity({ alerts, now, still, loading, className }: {
  alerts: Alert[]; now: number; still: boolean; loading?: boolean; className?: string;
}) {
  const fresh = useFresh(alerts.map((a) => a.id));
  const box = useRef<HTMLDivElement>(null), list = useRef<HTMLOListElement>(null);
  const fit = useWholeRows(box, list, alerts.map((a) => a.id).join());
  const rows = alerts.slice(0, LIST_LIMIT);
  const visible = wholeRows(alerts.length, fit);
  const more = alerts.length > visible;
  return (
    <Section title={T("ov.activity_title")} className={className} bodyClassName="overflow-hidden" bodyRef={box}
      aside={!more && (
        <Link to="/alerts" className="inline-flex items-center gap-1 rounded-sm font-medium text-foreground underline underline-offset-2 hover:text-heading">
          {T("ov.all_alerts")}<ArrowRight className="size-[1.1em]" aria-hidden />
        </Link>
      )}
      footer={more && <ViewAll to="/alerts" count={alerts.length} label={alerts.length >= FEED_CAP ? T("ov.all_alerts") : undefined} />}>
      {loading ? null : !alerts.length ? (
        <p className="px-4 py-4 text-base text-muted-foreground">{T("ov.activity_none")}</p>
      ) : (
        <ol ref={list} className="divide-y" data-activity>
          {rows.map((a, i) => {
            const Icon = ICON[a.kind] ?? Info;
            const old = now - a.ts >= 86400;
            return (
              <li key={a.id} style={i >= visible ? { display: "none" } : undefined}
                className={cn("flex gap-3 px-4 py-2.5", !still && fresh.has(a.id) && "slide-in")}>
                <Icon aria-hidden className={cn("mt-0.5 size-5 shrink-0",
                  a.severity === "critical" ? "text-crit" : a.severity === "warning" ? "text-warn" : "text-muted-foreground")} />
                <div className="min-w-0 flex-1">
                  <p className="flex items-baseline gap-2 text-base">
                    <time className="shrink-0 font-semibold tabular-nums" dateTime={new Date(a.ts * 1000).toISOString()} title={ago(now - a.ts)}>
                      {old ? dateTime(a.ts) : hhmmss(a.ts)}
                    </time>
                    <span className="truncate font-medium" title={cleanSubject(a.subject)}>{cleanSubject(a.subject)}</span>
                  </p>
                  <p className="line-clamp-2 text-base text-muted-foreground">{a.message}</p>
                </div>
              </li>
            );
          })}
        </ol>
      )}
    </Section>
  );
}
