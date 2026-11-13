// Today's summary, as a small table: what is counted on the left, the figure on the right. No icons. The last row is
// the emergency and drill line (what is happening now, and what happened today); air conditioning waste is the
// highlight of the building status card above, so it is not repeated here. The link opens the full summary.
import { ArrowRight } from "lucide-react";
import { Link } from "react-router-dom";

import { Section } from "@/components/overview/section";
import { Skeleton } from "@/components/ui/skeleton";
import { num } from "@/lib/format";
import { T } from "@/lib/i18n";
import { uptimeText, type Today } from "@/lib/overview";
import { cn } from "@/lib/utils";

function Row({ label, hint, value, loading, tone }: { label: string; hint: string; value: string; loading?: boolean; tone?: "crit" }) {
  return (
    <tr className="border-b last:border-b-0">
      <th scope="row" className="py-1.5 pr-3 text-left font-normal">
        <span className="block font-medium">{label}</span>
        <span data-hint className="block text-muted-foreground">{hint}</span>
      </th>
      <td className={cn("whitespace-nowrap py-1.5 text-right align-top text-lg font-semibold tabular-nums", tone === "crit" && "text-crit")}>
        {loading ? <Skeleton className="ml-auto h-6 w-16 animate-none" /> : value}
      </td>
    </tr>
  );
}

export function TodayCard({ today, uptimePct, incidents, loading, uptimeLoading, incidentsLoading, offline, uptimeOffline, link, className }: {
  today: Today | null; uptimePct: number | null | undefined;
  /** the emergency and drill line (lib/overview drillLine) */
  incidents: { value: string; hint: string; tone?: "crit" };
  loading?: boolean; uptimeLoading?: boolean; incidentsLoading?: boolean;
  /** the history database cannot be read: the figures that come from it say so instead of "no data" */
  offline?: boolean;
  /** the same for the uptime figure, which has its own request */
  uptimeOffline?: boolean;
  /** where "View full summary" leads */
  link?: string;
  className?: string;
}) {
  const none = !loading && !today;
  const why = T(offline ? "ov.today_offline" : "ov.today_none");
  return (
    <Section title={T("ov.today_label")} className={className} bodyClassName="overflow-y-auto px-4 py-1"
      action={link && (
        <Link to={link} data-full-summary className="inline-flex items-center gap-1 font-medium text-foreground underline underline-offset-2 hover:text-heading">
          {T("ov.today_full")}<ArrowRight className="size-[1.1em]" aria-hidden />
        </Link>
      )}>
      <table className="w-full text-base" data-today>
        <tbody>
          <Row label={T("ov.today_peak")} loading={loading} value={none ? "–" : num(today?.peak)} hint={none ? why : T("ov.today_peak_hint")} />
          <Row label={T("ov.today_hours")} loading={loading} value={none ? "–" : T("ov.today_hours_value", { n: num(today?.occupiedHours, 1) })}
            hint={none ? why : T("ov.today_hours_hint")} />
          <Row label={T("ov.today_uptime")} loading={uptimeLoading} value={uptimeText(uptimePct)}
            hint={uptimePct == null && !uptimeLoading ? T(uptimeOffline ? "ov.today_offline" : "ov.today_none") : T("ov.today_uptime_hint")} />
          <Row label={T("ov.today_incidents")} loading={incidentsLoading} value={incidents.value} hint={incidents.hint} tone={incidents.tone} />
        </tbody>
      </table>
    </Section>
  );
}
